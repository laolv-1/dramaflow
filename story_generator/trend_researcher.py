"""短剧热门榜调研工具

使用Jina Reader + Agent-Reach抓取海内外短剧热门榜数据，
本地Python整理后，用DeepSeek做趋势分析。

成本：Jina/Agent-Reach免费，DeepSeek仅1次调用(~0.1元)
"""

import os
import json
import re
import time
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

try:
    from openai import OpenAI
except ImportError:
    raise ImportError("请安装 openai: pip install openai")

from key_manager import KeyManager


# 调研数据源配置
RESEARCH_SOURCES = {
    # 海外
    "tiktok_trending": {
        "name": "TikTok热门",
        "urls": [
            "https://www.tiktok.com/challenges",
            "https://www.tiktok.com/api/trending/",
        ],
        "keywords": ["shortdrama", "mikudrama", "reelshort", "drama", "rebirth", "revenge"],
    },
    "youtube_shorts": {
        "name": "YouTube Shorts热门",
        "urls": [
            "https://www.youtube.com/shorts/trending",
        ],
        "keywords": ["short drama", "ai drama", "shortform", "rebirth story"],
    },
    "redshort": {
        "name": "RedShort/ReelShort",
        "urls": [
            "https://www.reelshort.com/",
        ],
        "keywords": ["drama", "rebirth", "CEO", "secret", "twins", "revenge"],
    },
    # 国内
    "douyin_hot": {
        "name": "抖音热榜",
        "urls": [
            "https://www.douyin.com/hot",
        ],
        "keywords": ["短剧", "重生", "复仇", "逆袭", "大女主", "修仙"],
    },
    "kuaishou_hot": {
        "name": "快手热榜",
        "urls": [
            "https://www.kuaishou.com/",
        ],
        "keywords": ["短剧", "微剧", "重生", "逆袭", "爽剧"],
    },
    "hongguo_drama": {
        "name": "红果短剧",
        "urls": [
            "https://www.hongguodianying.com/",
        ],
        "keywords": ["短剧", "热播", "排行", "重生", "复仇"],
    },
    # 行业分析
    "tech_articles": {
        "name": "AI短剧行业分析",
        "urls": [
            "https://36kr.com/search/articles/ai%E7%9F%AD%E5%89%A7",
        ],
        "keywords": ["AI短剧", "AI drama", "自动化", "爆款"],
    },
}


class TrendResearcher:
    """短剧热门榜调研工具"""

    def __init__(self, config_dir: Optional[str] = None):
        self.config_dir = Path(config_dir) if config_dir else Path(__file__).parent
        self.key_mgr = KeyManager(config_dir=str(self.config_dir))
        self.output_dir = self.config_dir / "output"
        self.output_dir.mkdir(exist_ok=True)

        # Jina Reader API
        jina_token = self.key_mgr.get_key("jina")
        self.jina_base_url = "https://r.jina.ai/"
        self.jina_token = jina_token

        # DeepSeek客户端（用于分析）
        self._deepseek_client = None

    @property
    def deepseek_client(self):
        if self._deepseek_client is None:
            ds_key = self.key_mgr.get_key("deepseek")
            if not ds_key:
                raise ValueError("未设置DEEPSEEK_API_KEY，无法进行分析")
            self._deepseek_client = OpenAI(
                api_key=ds_key,
                base_url="https://api.deepseek.com",
            )
        return self._deepseek_client

    def research(
        self,
        user_idea: str = "",
        sources: Optional[List[str]] = None,
        use_deepseek: bool = True,
    ) -> Dict[str, Any]:
        """
        执行完整调研流程
        Args:
            user_idea: 用户想法/题材方向
            sources: 要调研的数据源列表，None表示全部
            use_deepseek: 是否用DeepSeek做分析（True则额外调用一次）
        Returns:
            调研结果 {raw_data, analysis, summary}
        """
        sources = sources or list(RESEARCH_SOURCES.keys())
        print(f"[TrendResearcher] 开始调研，数据源: {', '.join([RESEARCH_SOURCES[s]['name'] for s in sources if s in RESEARCH_SOURCES])}")

        # Step 1: 并行抓取所有数据源
        raw_data = self._fetch_all(sources, user_idea)

        # Step 2: 本地整理（提取关键词、统计频次）
        analysis = self._local_analysis(raw_data)

        # Step 3: DeepSeek深度分析（可选）
        deepseek_insight = None
        if use_deepseek:
            print("[TrendResearcher] 调用DeepSeek做趋势分析...")
            deepseek_insight = self._deepseek_analysis(analysis, user_idea)

        # Step 4: 保存结果
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        hash_id = hashlib.md5(timestamp.encode()).hexdigest()[:8]

        result = {
            "id": hash_id,
            "timestamp": timestamp,
            "user_idea": user_idea,
            "raw_data": raw_data,
            "local_analysis": analysis,
            "deepseek_insight": deepseek_insight,
        }

        # 保存JSON
        safe_idea = re.sub(r'[\\/:*?"<>|]', '_', user_idea)[:20] if user_idea else "untitled"
        filepath = self.output_dir / f"research_{timestamp}_{safe_idea}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"[TrendResearcher] 调研完成，结果已保存: {filepath}")
        return result

    def _fetch_all(self, sources: List[str], user_idea: str) -> Dict[str, Any]:
        """并行抓取所有数据源"""
        results = {}

        for source_key in sources:
            if source_key not in RESEARCH_SOURCES:
                continue
            source = RESEARCH_SOURCES[source_key]
            print(f"  抓取 {source['name']}...")

            source_results = []
            for url in source.get("urls", []):
                data = self._fetch_via_jina(url, source.get("keywords", []), user_idea)
                if data:
                    source_results.append(data)

            results[source_key] = {
                "name": source["name"],
                "results": source_results,
                "keywords": source.get("keywords", []),
                "fetched_at": datetime.now().isoformat(),
            }

        return results

    def _fetch_via_jina(self, url: str, keywords: List[str], user_idea: str) -> Optional[Dict]:
        """通过Jina Reader抓取网页内容"""
        if not self.jina_token:
            # 没有Jina Token，尝试直接用requests
            return self._fetch_direct(url, keywords, user_idea)

        jina_url = f"https://r.jina.ai/{url}"
        headers = {
            "Authorization": f"Bearer {self.jina_token}",
            "X-Return-Format": "markdown",
        }

        import requests
        try:
            resp = requests.get(jina_url, headers=headers, timeout=30)
            content = resp.text
            if not content:
                return None

            # 提取关键词相关的片段
            extracted = self._extract_keywords(content, keywords, user_idea)

            return {
                "url": url,
                "content_length": len(content),
                "extracted_items": extracted,
            }
        except Exception as e:
            print(f"    [警告] 抓取失败: {e}")
            return None

    def _fetch_direct(self, url: str, keywords: List[str], user_idea: str) -> Optional[Dict]:
        """直接抓取网页（Jina不可用时降级）"""
        import requests
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            content = resp.text
            extracted = self._extract_keywords(content, keywords, user_idea)
            return {
                "url": url,
                "content_length": len(content),
                "extracted_items": extracted,
            }
        except Exception as e:
            print(f"    [警告] 直接抓取失败: {e}")
            return None

    def _extract_keywords(self, content: str, keywords: List[str], user_idea: str) -> List[Dict]:
        """从内容中提取关键词相关的片段"""
        items = []
        all_kw = keywords[:]
        if user_idea:
            all_kw.extend([kw.strip() for kw in user_idea.split()])

        for kw in all_kw:
            if not kw:
                continue
            # 查找关键词附近的上下文
            matches = list(re.finditer(re.escape(kw), content, re.IGNORECASE))
            for m in matches[:5]:  # 每个关键词最多取5条
                start = max(0, m.start() - 100)
                end = min(len(content), m.end() + 100)
                context = content[start:end].strip()
                if context:
                    items.append({
                        "keyword": kw,
                        "context": context,
                        "position": m.start(),
                    })

        return items

    def _local_analysis(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """本地Python统计分析"""
        # 统计所有关键词出现频次
        kw_freq = {}
        source_freq = {}
        all_items = []

        for source_key, source_data in raw_data.items():
            for result in source_data.get("results", []):
                for item in result.get("extracted_items", []):
                    kw = item.get("keyword", "")
                    all_items.append(item)
                    kw_freq[kw] = kw_freq.get(kw, 0) + 1

        # 热门题材TOP
        hot_keywords = sorted(kw_freq.items(), key=lambda x: x[1], reverse=True)[:20]

        # 数据来源覆盖
        sources_covered = sum(1 for s in raw_data.values() if s.get("results"))

        return {
            "total_sources": len(raw_data),
            "sources_covered": sources_covered,
            "hot_keywords": [{"keyword": k, "frequency": v} for k, v in hot_keywords],
            "total_extracted_items": len(all_items),
            "raw_data_summary": {k: len(v.get("results", [])) for k, v in raw_data.items()},
        }

    def _deepseek_analysis(
        self,
        local_analysis: Dict[str, Any],
        user_idea: str,
    ) -> Dict[str, Any]:
        """
        调用DeepSeek v4-pro做深度分析
        只调用1次，约0.05-0.1元
        """
        # 准备上下文（压缩到合理长度）
        hot_kws = "\n".join([f"- {kw}: 出现{freq}次" for kw, freq in local_analysis.get("hot_keywords", [])[:10]])
        data_summary = json.dumps(local_analysis.get("raw_data_summary", {}), ensure_ascii=False)

        prompt = f"""你是短剧行业分析师。请基于以下调研数据，给出趋势分析和针对用户想法的建议。

【调研数据覆盖】
- 数据源数量: {local_analysis.get('total_sources', 0)}个
- 成功抓取: {local_analysis.get('sources_covered', 0)}个
- 提取内容项: {local_analysis.get('total_extracted_items', 0)}条

【热门关键词TOP10】
{hot_kws or '（数据不足）'}

【数据来源分布】
{data_summary}

【用户想法】
{user_idea or '（未提供）'}

请按以下格式输出分析结果（用中文）：

## 短剧热门榜调研摘要
调研时间：{datetime.now().strftime("%Y-%m-%d")}

### 🔥 热门题材
（总结当前最火的题材类型）

### 🎣 高效钩子类型
（哪些开头和结尾方式最有效）

### 📈 趋势关键词
（列出5-10个趋势词）

### 💡 针对"{user_idea or '该方向'}"的建议
（具体建议：核心冲突、推荐钩子、参考套路）
"""

        try:
            response = self.deepseek_client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[
                    {"role": "system", "content": "你是一位资深短剧行业分析师，精通抖音、快手、TikTok等平台的短剧爆款规律。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )
            insight_text = response.choices[0].message.content

            # 解析结构化建议
            structured = self._parse_insight(insight_text)

            return {
                "raw_insight": insight_text,
                "structured": structured,
                "model": "deepseek-v4-pro",
                "generated_at": datetime.now().isoformat(),
            }
        except Exception as e:
            print(f"[TrendResearcher] DeepSeek分析失败: {e}")
            return {
                "raw_insight": f"分析失败: {e}",
                "structured": {},
                "model": "deepseek-v4-pro",
                "error": str(e),
            }

    def _parse_insight(self, text: str) -> Dict[str, str]:
        """从Markdown文本中提取结构化字段"""
        sections = {}
        # 简单按二级标题分割
        parts = re.split(r'^## ', text, flags=re.MULTILINE)
        for part in parts[1:]:  # 跳过第一个（没有标题的部分）
            lines = part.strip().split('\n', 1)
            if len(lines) == 2:
                title = re.sub(r'[#\n*]', '', lines[0]).strip()
                content = lines[1].strip()
                sections[title] = content
            elif len(lines) == 1:
                title = re.sub(r'[#\n*]', lines[0].strip()).strip()
                sections[title] = lines[1].strip() if len(lines) > 1 else ""
        return sections

    def get_research_history(self) -> List[Dict]:
        """获取历史调研记录"""
        records = []
        for f in sorted(self.output_dir.glob("research_*.json")):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    records.append({
                        "id": data.get("id", ""),
                        "timestamp": data.get("timestamp", ""),
                        "user_idea": data.get("user_idea", ""),
                        "sources_covered": data.get("local_analysis", {}).get("sources_covered", 0),
                        "filepath": str(f),
                    })
            except:
                pass
        return records[::-1]  # 最新的在前
