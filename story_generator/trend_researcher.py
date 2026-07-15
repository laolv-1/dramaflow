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
# 注意：tophub.today 有 CAPTCHA 防护，Jina 无法抓取
# 以下 URL 均已通过 Jina Reader 实际测试，确认可抓取有效内容
RESEARCH_SOURCES = {
    # ReelShort - 海外短剧应用
    "reelshort": {
        "name": "ReelShort短剧榜",
        "urls": [
            "https://www.reelshort.com/",
        ],
    },
    # 36Kr - AI短剧行业分析
    "tech_articles": {
        "name": "AI短剧行业(36Kr)",
        "urls": [
            "https://36kr.com/search/articles/ai%E7%9F%AD%E5%89%A7",
        ],
    },
    # B站 - 短剧相关视频（Jina 可抓取 20KB+）
    "bilibili_drama": {
        "name": "B站短剧内容",
        "urls": [
            "https://search.bilibili.com/all?keyword=%E7%9F%AD%E5%89%A7+%E9%87%8D%E7%94%9F&order=click",
        ],
    },
    # 豆瓣 - 短剧讨论
    "douban_drama": {
        "name": "豆瓣短剧讨论",
        "urls": [
            "https://www.douban.com/search?q=%E7%9F%AD%E5%89%A7+%E9%87%8D%E7%94%9F",
        ],
    },
    # 小红书 - 短剧推荐
    "xiaohongshu_drama": {
        "name": "小红书短剧推荐",
        "urls": [
            "https://www.xiaohongshu.com/search_result?keyword=%E7%9F%AD%E5%89%A7",
        ],
    },
    # 少数派 - AI短剧技术文章
    "sspai_drama": {
        "name": "少数派AI短剧",
        "urls": [
            "https://sspai.com/search?q=%E7%9F%AD%E5%89%A7",
        ],
    },
    # 简书 - 短剧创作经验
    "jianshu_drama": {
        "name": "简书短剧创作",
        "urls": [
            "https://www.jianshu.com/search?q=%E7%9F%AD%E5%89%A7",
        ],
    },
    # TikTok 挑战页
    "tiktok_challenges": {
        "name": "TikTok挑战",
        "urls": [
            "https://www.tiktok.com/challenges",
        ],
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

        # Step 2: 本地整理（提取题材关键词、统计频次）
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
        """抓取所有数据源 — 直接获取原始内容，不做关键词过滤"""
        results = {}

        for source_key in sources:
            if source_key not in RESEARCH_SOURCES:
                continue
            source = RESEARCH_SOURCES[source_key]
            print(f"  抓取 {source['name']}...")

            source_results = []
            for url in source.get("urls", []):
                data = self._fetch_via_jina(url, user_idea)
                if data:
                    source_results.append(data)

            results[source_key] = {
                "name": source["name"],
                "results": source_results,
                "fetched_at": datetime.now().isoformat(),
            }

        return results

    def _clean_content(self, content: str) -> str:
        """清洗网页内容，移除噪音"""
        import re
        # 移除URL
        content = re.sub(r'https?://\S+', '', content)
        # 移除HTML标签
        content = re.sub(r'<[^>]+>', '', content)
        # 移除导航/菜单类文本（中英文）
        noise_patterns = [
            r'(?i)(?:follow|followers|sign\s*in|sign\s*out|login)',
            r'(?i)(?:settings|preferences|help|about)',
            r'(?i)(?:cookie|privacy|terms)',
            r'(?i)(?:广告|推广|推荐|热门|最新|标签|话题|Copyright)',
        ]
        for pat in noise_patterns:
            content = re.sub(pat, '', content)
        # 清理空白行
        lines = [l.strip() for l in content.split('\n') if l.strip()]
        return '\n'.join(lines)

    def _fetch_via_jina(self, url: str, user_idea: str) -> Optional[Dict]:
        """通过Jina Reader抓取网页内容 — 返回干净原始文本"""
        if not self.jina_token:
            return self._fetch_direct(url, user_idea)

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

            # 不做关键词过滤，直接返回清洗后的完整文本
            cleaned = self._clean_content(content)
            if not cleaned or len(cleaned) < 100:
                return None

            return {
                "url": url,
                "content_length": len(cleaned),
                "raw_text": cleaned,  # 保留完整原始文本
            }
        except Exception as e:
            print(f"    [警告] 抓取失败: {e}")
            return None

    def _fetch_direct(self, url: str, user_idea: str) -> Optional[Dict]:
        """直接抓取网页（Jina不可用时降级）"""
        import requests
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            content = resp.text
            cleaned = self._clean_content(content)
            if not cleaned:
                return None
            return {
                "url": url,
                "content_length": len(cleaned),
                "raw_text": cleaned,
            }
        except Exception as e:
            print(f"    [警告] 直接抓取失败: {e}")
            return None

    def _local_analysis(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """本地统计分析 — 从原始文本中提取题材关键词"""
        # 收集所有源的原始文本
        all_texts = []
        total_items = 0
        for source_key, source_data in raw_data.items():
            for result in source_data.get("results", []):
                raw_text = result.get("raw_text", "")
                if raw_text:
                    all_texts.append((source_key, raw_text))
                    total_items += 1

        # 使用预定义的短剧题材关键词集合进行统计
        genre_keywords = [
            # 中文题材词
            "重生", "复仇", "逆袭", "闪婚", "马甲", "大女主", "修仙", "玄幻",
            "甜宠", "虐恋", "霸总", "CEO", "离婚", "带球跑", "换亲", "年代",
            "末世", "丧尸", "系统", "空间", "团宠", "炮灰", "攻略", "修罗场",
            "狼人", "Alpha", "Omega", "兽世", "星际", "末世", "无限流",
            # 英文题材词
            "rebirth", "revenge", "contract", "secret identity", "hidden power",
            "amnesia", "twin", "surrogate", "boss", "ceo", "marriage",
        ]

        # 统计题材关键词频次
        kw_freq = {}
        for source_key, text in all_texts:
            text_lower = text.lower()
            for kw in genre_keywords:
                kw_lower = kw.lower()
                # 中文词：精确匹配
                if any('\u4e00' <= c <= '\u9fff' for c in kw):
                    count = text.count(kw)
                else:
                    # 英文词：用正则匹配单词边界
                    count = len(re.findall(rf'\b{re.escape(kw_lower)}\b', text_lower))
                if count > 0:
                    kw_freq[kw] = kw_freq.get(kw, 0) + count

        # 热门题材TOP（排除通用噪音词）
        noise_words = {"drama", "short", "video", "watch", "follow", "share", "like",
                       "the", "and", "or", "new", "popular", "trending", "series",
                       "episode", "season", "story", "love", "life", "family"}
        hot_keywords = sorted(
            [(k, v) for k, v in kw_freq.items()
             if k.lower() not in noise_words and len(k) >= 2 and v >= 1],
            key=lambda x: x[1], reverse=True
        )[:20]

        # 数据来源覆盖统计
        sources_covered = sum(1 for s in raw_data.values() if s.get("results"))

        return {
            "total_sources": len(raw_data),
            "sources_covered": sources_covered,
            "hot_keywords": [{"keyword": k, "frequency": v} for k, v in hot_keywords],
            "total_extracted_items": total_items,
            "raw_data_summary": {k: len(v.get("results", [])) for k, v in raw_data.items()},
            "extraction_method": "genre_keyword_match",
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
        hot_kws = "\n".join([f"- {kw}: 出现{freq}次" for kw, freq in local_analysis.get("hot_keywords", [])[:15]])
        data_summary = json.dumps(local_analysis.get("raw_data_summary", {}), ensure_ascii=False)
        total_items = local_analysis.get("total_extracted_items", 0)
        sources_covered = local_analysis.get("sources_covered", 0)
        total_sources = local_analysis.get("total_sources", 0)

        prompt = f"""你是短剧行业分析师。请基于以下调研数据，给出趋势分析和针对用户想法的建议。

【调研数据概况】
- 数据源数量: {sources_covered}/{total_sources}个成功抓取
- 提取内容项: {total_items}条
- 提取方式: 题材关键词匹配

【热门题材关键词TOP15】
{hot_kws or '（数据不足，请根据行业知识补充）'}

【数据来源分布】
{data_summary}

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
