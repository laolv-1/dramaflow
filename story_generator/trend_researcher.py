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
    # 海外 - 使用真实可抓取的榜单页面
    "tiktok_creators": {
        "name": "TikTok创作者榜",
        "urls": [
            "https://www.tiktok.com/challenges",
            "https://www.tiktok.com/creators/discover",
        ],
        "search_queries": ["short drama", "reelshort", "mikudrama", "ai drama", "rebirth revenge"],
    },
    "youtube_shorts": {
        "name": "YouTube Shorts热门",
        "urls": [
            "https://www.youtube.com/feed/trending",
        ],
        "search_queries": ["short drama", "ai drama", "rebirth story", "CEO secret"],
    },
    "reelshort": {
        "name": "ReelShort短剧榜",
        "urls": [
            "https://www.reelshort.com/",
        ],
        "search_queries": ["drama", "rebirth", "CEO", "secret", "twins", "revenge"],
    },
    # 国内 - 使用可抓取的第三方榜单
    "douyin_hot": {
        "name": "抖音热榜(第三方)",
        "urls": [
            "https://tophub.today/n/DpaQlEdmn9",
            "https://www.douyin.com/hot",
        ],
        "search_queries": ["短剧", "重生", "复仇", "逆袭", "大女主", "修仙", "马甲"],
    },
    "kuaishou_hot": {
        "name": "快手热榜(第三方)",
        "urls": [
            "https://tophub.today/n/q1lVdbPoKE",
        ],
        "search_queries": ["短剧", "微剧", "重生", "逆袭", "爽剧", "闪婚"],
    },
    "hongguo_drama": {
        "name": "红果短剧榜",
        "urls": [
            "https://tophub.today/n/Jb0qvB0FSE",
        ],
        "search_queries": ["短剧", "热播", "排行", "重生", "复仇", "年代"],
    },
    # 行业分析
    "tech_articles": {
        "name": "AI短剧行业",
        "urls": [
            "https://36kr.com/search/articles/ai%E7%9F%AD%E5%89%A7",
        ],
        "search_queries": ["AI短剧", "AI drama", "自动化", "爆款"],
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

        # 把原始上下文片段加入 analysis（供 DeepSeek 分析用）
        all_items = []
        for source_key, source_data in raw_data.items():
            for result in source_data.get("results", []):
                all_items.extend(result.get("extracted_items", []))
        analysis["raw_items"] = all_items[:20]  # 最多传20条给 DeepSeek

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
                data = self._fetch_via_jina(url, source.get("search_queries", []), user_idea)
                if data:
                    source_results.append(data)

            results[source_key] = {
                "name": source["name"],
                "results": source_results,
                "search_queries": source.get("search_queries", []),
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
            "X-With-Generated-Alt": "false",
        }

        import requests
        try:
            resp = requests.get(jina_url, headers=headers, timeout=30)
            content = resp.text
            if not content or len(content) < 200:
                return None

            # 清洗内容：移除HTML标签、导航等噪音
            cleaned = self._clean_content(content)
            if not cleaned or len(cleaned) < 100:
                return None

            # 提取关键词相关的片段
            extracted = self._extract_keywords(cleaned, keywords, user_idea)

            return {
                "url": url,
                "content_length": len(cleaned),
                "extracted_items": extracted,
            }
        except Exception as e:
            print(f"    [警告] 抓取失败: {e}")
            return None

    def _clean_content(self, content: str) -> str:
        """清洗网页内容，移除噪音"""
        import re
        # 移除URL
        content = re.sub(r'https?://\S+', '', content)
        # 移除HTML标签
        content = re.sub(r'<[^>]+>', '', content)
        # 移除导航/菜单类文本
        noise_patterns = [
            r'(?i)(?:follow|followers|sign\s*in|sign\s*out|login)',
            r'(?i)(?:settings|preferences|help|about)',
            r'(?i)(?:cookie|privacy|terms)',
        ]
        for pat in noise_patterns:
            content = re.sub(pat, '', content)
        # 清理空白行
        lines = [l.strip() for l in content.split('\n') if l.strip()]
        return '\n'.join(lines)

    def _fetch_direct(self, url: str, keywords: List[str], user_idea: str) -> Optional[Dict]:
        """直接抓取网页（Jina不可用时降级）"""
        import requests
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            content = resp.text
            cleaned = self._clean_content(content)
            extracted = self._extract_keywords(cleaned, keywords, user_idea)
            return {
                "url": url,
                "content_length": len(cleaned) if cleaned else 0,
                "extracted_items": extracted,
            }
        except Exception as e:
            print(f"    [警告] 直接抓取失败: {e}")
            return None

    def _extract_keywords(self, content: str, keywords: List[str], user_idea: str) -> List[Dict]:
        """从内容中提取关键词相关的片段（增强版：提取有意义的上下文）"""
        items = []
        all_kw = keywords[:]
        if user_idea:
            all_kw.extend([kw.strip() for kw in user_idea.split() if kw.strip()])

        # 移除重复关键词
        seen = set()
        all_kw = [k for k in all_kw if not (k.lower() in seen or seen.add(k.lower()))]

        for kw in all_kw:
            if not kw or len(kw) < 1:
                continue
            # 查找关键词附近的上下文（扩大范围以获取更多信息）
            matches = list(re.finditer(re.escape(kw), content, re.IGNORECASE))
            for m in matches[:3]:  # 每个关键词最多取3条
                start = max(0, m.start() - 150)
                end = min(len(content), m.end() + 150)
                context = content[start:end].strip()
                if context and len(context) > 20:
                    items.append({
                        "keyword": kw,
                        "context": context,
                        "source": kw,
                    })

        # 如果没有匹配到任何关键词，返回内容摘要（前200字符）
        if not items and len(content) > 200:
            items.append({
                "keyword": "summary",
                "context": content[:200],
                "source": "auto_extract",
            })

        return items

    def _local_analysis(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """本地Python统计分析 — 增强版：提取有意义的题材关键词"""
        # 统计所有关键词出现频次
        kw_freq = {}
        all_items = []

        for source_key, source_data in raw_data.items():
            for result in source_data.get("results", []):
                for item in result.get("extracted_items", []):
                    kw = item.get("keyword", "")
                    all_items.append(item)
                    # 跳过 summary 和 noise
                    if kw in ("summary", "auto_extract"):
                        continue
                    kw_freq[kw] = kw_freq.get(kw, 0) + 1

        # 热门题材TOP（排除通用噪音词）
        noise_words = {"drama", "short", "video", "watch", "follow", "share", "like", "comment",
                       "re", "the", "and", "or", "new", "popular", "trending"}
        hot_keywords = sorted(
            [(k, v) for k, v in kw_freq.items() if k.lower() not in noise_words and len(k) >= 2],
            key=lambda x: x[1], reverse=True
        )[:20]

        # 数据来源覆盖统计
        sources_covered = sum(1 for s in raw_data.values() if s.get("results"))
        total_items = sum(len(r.get("extracted_items", [])) for s in raw_data.values()
                         for r in s.get("results", []))

        return {
            "total_sources": len(raw_data),
            "sources_covered": sources_covered,
            "hot_keywords": [{"keyword": k, "frequency": v} for k, v in hot_keywords],
            "total_extracted_items": total_items,
            "raw_data_summary": {k: len(v.get("results", [])) for k, v in raw_data.items()},
            "extraction_method": "keyword_context",
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
        # 准备上下文
        hot_kws = "\n".join([f"- {kw}: 出现{freq}次" for kw, freq in local_analysis.get("hot_keywords", [])[:15]])
        data_summary = json.dumps(local_analysis.get("raw_data_summary", {}), ensure_ascii=False)
        total_items = local_analysis.get("total_extracted_items", 0)
        sources_covered = local_analysis.get("sources_covered", 0)
        total_sources = local_analysis.get("total_sources", 0)

        # 提取一些上下文片段作为样例（给DeepSeek更多原始材料）
        sample_contexts = []
        for item in local_analysis.get("raw_items", [])[:5]:
            sample_contexts.append(f"  - [{item.get('keyword','')}] {item.get('context','')[:100]}")
        samples_text = "\n".join(sample_contexts) if sample_contexts else "（无足够上下文样本）"

        prompt = f"""你是短剧行业分析师。请基于以下调研数据，给出趋势分析和针对用户想法的建议。

【调研数据概况】
- 数据源数量: {sources_covered}/{total_sources}个成功抓取
- 提取内容项: {total_items}条
- 提取方式: 关键词上下文匹配

【热门题材关键词TOP15】
{hot_kws or '（数据不足，请根据行业知识补充）'}

【数据来源分布】
{data_summary}

【上下文样本（前5条）】
{samples_text}

【用户想法】
{user_idea or '（未提供）'}

请按以下格式输出分析结果（用中文）：

## 短剧热门榜调研摘要
调研时间：{datetime.now().strftime("%Y-%m-%d")}

### 🔥 热门题材
（总结当前最火的题材类型，结合上面的关键词数据。如果关键词数据不足，就根据行业知识给出。）

### 🎣 高效钩子类型
（哪些开头和结尾方式最有效，举具体例子）

### 📈 趋势关键词
（列出5-10个趋势词，从上面关键词中提炼或根据行业知识补充）

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
