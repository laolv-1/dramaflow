"""通用行业数据调研工具

基于实测可用的免费数据源，采集各行业趋势数据。
任何话题都能灌入，不限于特定领域。
成本：全部免费

数据源选型原则：能免费则免费，实测可用才配置。
详见 claude核心记忆/02_工具/数据源完整清单.md
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


# ============================================================
# 数据源配置 — 热点排行榜（全部免费，已实测）
# ============================================================
HOTLIST_SOURCES = {
    "weibo_hot": {
        "name": "微博热搜",
        "urls": ["https://weibo.com/hot/search"],
        "fetcher": "_fetch_via_jina",
    },
    "baidu_hot": {
        "name": "百度热搜",
        "urls": ["https://top.baidu.com/board?tab=realtime"],
        "fetcher": "_fetch_via_jina",
    },
    "toutiao_hot": {
        "name": "头条热榜",
        "urls": ["https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"],
        "fetcher": "_fetch_via_jina",
    },
    "zhihu_hot": {
        "name": "知乎热榜",
        "urls": ["https://www.zhihu.com/hot"],
        "fetcher": "_fetch_via_jina",
    },
    "douyin_hot": {
        "name": "抖音热榜",
        "urls": ["https://www.douyin.com/hot"],
        "fetcher": "_fetch_via_jina",
    },
    "kuaishou_hot": {
        "name": "快手热榜",
        "urls": ["https://www.kuaishou.com/hot"],
        "fetcher": "_fetch_via_jina",
    },
    "36kr_hot": {
        "name": "36Kr热榜",
        "urls": ["https://36kr.com/hot-list/catalog"],
        "fetcher": "_fetch_via_jina",
    },
}


# ============================================================
# 数据源配置 — 搜索趋势（全部免费，已实测）
# ============================================================
TREND_SOURCES = {
    "baidu_index": {
        "name": "百度指数",
        "urls": ["https://index.baidu.com/v2/main/index.html"],
        "fetcher": "_fetch_via_jina",
    },
    "wechat_index": {
        "name": "微信指数",
        "urls": ["https://weixin.sogou.com/weixin?type=2&query=%E6%8C%87%E6%95%B0"],
        "fetcher": "_fetch_via_jina",
    },
}


# ============================================================
# 数据源配置 — 行业数据（全部免费，已实测）
# ============================================================
INDUSTRY_SOURCES = {
    "newrank": {
        "name": "新榜",
        "urls": ["https://www.newrank.cn/"],
        "fetcher": "_fetch_via_jina",
    },
    "taobao_index": {
        "name": "淘宝指数",
        "urls": ["https://www.1688.com/"],
        "fetcher": "_fetch_via_jina",
    },
}


# ============================================================
# 数据源配置 — 内容社区（全部免费，已实测）
# ============================================================
COMMUNITY_SOURCES = {
    "bilibili": {
        "name": "B站",
        "urls": ["https://search.bilibili.com/all?keyword={keyword}&order=click"],
        "fetcher": "_fetch_via_jina",
    },
    "douban": {
        "name": "豆瓣",
        "urls": ["https://www.douban.com/group/search?cat=1012&q={keyword}&sort=time"],
        "fetcher": "_fetch_via_jina",
    },
    "36kr_article": {
        "name": "36Kr文章",
        "urls": ["https://36kr.com/"],
        "fetcher": "_fetch_via_jina",
    },
    "sspai": {
        "name": "少数派",
        "urls": ["https://sspai.com/search?q={keyword}"],
        "fetcher": "_fetch_via_jina",
    },
    "iimedia": {
        "name": "艾媒咨询",
        "urls": ["https://www.iimedia.cn/"],
        "fetcher": "_fetch_via_jina",
    },
    "douyin_creator": {
        "name": "抖音创作者服务",
        "urls": ["https://creator.douyin.com/"],
        "fetcher": "_fetch_via_jina",
    },
    "juliang": {
        "name": "巨量算数",
        "urls": ["https://trendinsight.oceanengine.com/"],
        "fetcher": "_fetch_via_jina",
    },
    "jianshu": {
        "name": "简书",
        "urls": ["https://www.jianshu.com/search?q={keyword}"],
        "fetcher": "_fetch_via_jina",
    },
}


# ============================================================
# 数据源配置 — YouTube（官方API，免费10000units/天）
# ============================================================
YOUTUBE_SOURCE = {
    "youtube": {
        "name": "YouTube",
        "fetcher": "_fetch_youtube_api",
        "keywords": ["trending", "top topics", "viral"],
    },
}


# 合并所有源
ALL_SOURCES = {
    **HOTLIST_SOURCES,
    **TREND_SOURCES,
    **INDUSTRY_SOURCES,
    **COMMUNITY_SOURCES,
    **YOUTUBE_SOURCE,
}

# 分类别名（用户可以选择只调研某一类）
SOURCE_CATEGORIES = {
    "hotlist": HOTLIST_SOURCES,      # 热点排行榜
    "trend": TREND_SOURCES,           # 搜索趋势
    "industry": INDUSTRY_SOURCES,     # 行业数据
    "community": COMMUNITY_SOURCES,   # 内容社区
    "youtube": YOUTUBE_SOURCE,        # YouTube
}


class TrendResearcher:
    """通用行业数据调研工具 — 免费方案"""

    def __init__(self, config_dir: Optional[str] = None):
        self.config_dir = Path(config_dir) if config_dir else Path(__file__).parent
        self.key_mgr = KeyManager(config_dir=str(self.config_dir))
        self.output_dir = self.config_dir / "output"
        self.output_dir.mkdir(exist_ok=True)

        # Jina Reader API
        jina_token = self.key_mgr.get_key("jina")
        self.jina_base_url = "https://r.jina.ai/"
        self.jina_token = jina_token

        # DeepSeek客户端
        self._deepseek_client = None
        # YouTube API Key
        self._youtube_api_key = None

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

    def _get_youtube_api_key(self) -> Optional[str]:
        if self._youtube_api_key is None:
            self._youtube_api_key = self.key_mgr.get_key("youtube")
        return self._youtube_api_key

    def research(
        self,
        user_topic: str = "",
        sources: Optional[List[str]] = None,
        category: str = "all",  # hotlist / trend / industry / community / youtube / all
        use_deepseek: bool = True,
    ) -> Dict[str, Any]:
        """
        执行完整调研流程
        Args:
            user_topic: 调研主题/话题（会注入到支持keyword的数据源）
            sources: 指定数据源列表，None表示全部
            category: 调研类别 "hotlist"/"trend"/"industry"/"community"/"youtube"/"all"
            use_deepseek: 是否用DeepSeek做分析
        Returns:
            调研结果 {raw_data, analysis, summary}
        """
        # 按类别筛选数据源
        if category == "all":
            active_sources = list(ALL_SOURCES.keys())
        elif category in SOURCE_CATEGORIES:
            active_sources = list(SOURCE_CATEGORIES[category].keys())
        else:
            active_sources = list(ALL_SOURCES.keys())

        if sources:
            active_sources = [s for s in sources if s in ALL_SOURCES]

        source_names = ", ".join([ALL_SOURCES[s]['name'] for s in active_sources if s in ALL_SOURCES])
        print(f"[TrendResearcher] 开始调研，主题: {user_topic or '通用'}, 数据源: {source_names}")

        # Step 1: 抓取所有数据源
        raw_data = self._fetch_all(active_sources, user_topic)

        # Step 2: 本地整理（提取关键词、统计频次）
        analysis = self._local_analysis(raw_data, user_topic)

        # Step 3: DeepSeek深度分析
        deepseek_insight = None
        if use_deepseek:
            print("[TrendResearcher] 调用DeepSeek做趋势分析...")
            deepseek_insight = self._deepseek_analysis(analysis, user_topic)

        # Step 4: 保存结果
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        hash_id = hashlib.md5(timestamp.encode()).hexdigest()[:8]

        result = {
            "id": hash_id,
            "timestamp": timestamp,
            "user_topic": user_topic,
            "category": category,
            "raw_data": raw_data,
            "local_analysis": analysis,
            "deepseek_insight": deepseek_insight,
        }

        # 保存JSON
        safe_topic = re.sub(r'[\\/:*?"<>|]', '_', user_topic)[:20] if user_topic else "untitled"
        filepath = self.output_dir / f"research_{timestamp}_{safe_topic}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"[TrendResearcher] 调研完成，结果已保存: {filepath}")
        return result

    def _fetch_all(self, sources: List[str], user_topic: str) -> Dict[str, Any]:
        """抓取所有数据源"""
        results = {}

        for source_key in sources:
            if source_key not in ALL_SOURCES:
                continue
            source = ALL_SOURCES[source_key]
            print(f"  抓取 {source['name']}...")

            fetcher_name = source.get("fetcher", "_fetch_via_jina")
            fetcher = getattr(self, fetcher_name)

            try:
                if fetcher_name == "_fetch_youtube_api":
                    data = fetcher(source_key, source, user_topic)
                elif fetcher_name == "_fetch_via_jina":
                    urls = source.get("urls", [])
                    # 替换URL中的keyword占位符
                    urls = [u.format(keyword=user_topic) if "{keyword}" in u else u for u in urls]
                    data = fetcher(urls, user_topic)
                else:
                    data = fetcher(source.get("urls", []), user_topic)

                if data is not None:
                    results[source_key] = {
                        "name": source["name"],
                        "results": data if isinstance(data, list) else [data],
                        "fetched_at": datetime.now().isoformat(),
                    }
            except Exception as e:
                print(f"    [警告] {source['name']} 抓取失败: {e}")
                results[source_key] = {
                    "name": source["name"],
                    "results": [],
                    "fetched_at": datetime.now().isoformat(),
                    "error": str(e),
                }

        return results

    def _clean_content(self, content: str) -> str:
        """清洗网页内容，移除噪音"""
        # 移除URL
        content = re.sub(r'https?://\S+', '', content)
        # 移除HTML标签
        content = re.sub(r'<[^>]+>', '', content)
        # 移除导航/菜单类文本
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

    def _fetch_via_jina(self, urls: List[str], user_topic: str) -> Optional[Dict]:
        """通过Jina Reader抓取网页内容"""
        if not self.jina_token:
            return self._fetch_direct(urls, user_topic)

        all_texts = []
        for url in urls:
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
                    continue

                cleaned = self._clean_content(content)
                if cleaned and len(cleaned) >= 100:
                    all_texts.append(cleaned)
            except Exception as e:
                continue

        if not all_texts:
            return None

        return {
            "url": urls[0],
            "content_length": sum(len(t) for t in all_texts),
            "raw_text": "\n\n---\n\n".join(all_texts),
        }

    def _fetch_direct(self, urls: List[str], user_topic: str) -> Optional[Dict]:
        """直接抓取网页（Jina不可用时降级）"""
        import requests
        all_texts = []
        for url in urls:
            try:
                resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                cleaned = self._clean_content(resp.text)
                if cleaned and len(cleaned) >= 100:
                    all_texts.append(cleaned)
            except Exception:
                continue

        if not all_texts:
            return None

        return {
            "url": urls[0],
            "content_length": sum(len(t) for t in all_texts),
            "raw_text": "\n\n---\n\n".join(all_texts),
        }

    def _fetch_youtube_api(self, source_key: str, source_config: Dict, user_topic: str) -> Optional[Dict]:
        """通过YouTube Data API v3获取趋势数据"""
        api_key = self._get_youtube_api_key()
        if not api_key:
            print(f"    [提示] 未设置YOUTUBE_API_KEY，跳过YouTube")
            return None

        try:
            import requests
            keywords = source_config.get("keywords", ["trending"])
            if user_topic:
                keywords.insert(0, user_topic)
            all_videos = []

            for keyword in keywords[:3]:  # 最多3个关键词
                search_url = "https://www.googleapis.com/youtube/v3/search"
                params = {
                    "part": "snippet",
                    "q": keyword,
                    "type": "video",
                    "maxResults": 10,
                    "regionCode": "CN",
                    "chart": "mostPopular",
                    "key": api_key,
                }
                resp = requests.get(search_url, params=params, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("items", []):
                        snippet = item.get("snippet", {})
                        all_videos.append({
                            "title": snippet.get("title", ""),
                            "description": snippet.get("description", "")[:300],
                            "channel": snippet.get("channelTitle", ""),
                            "published": snippet.get("publishedAt", ""),
                        })

            if not all_videos:
                return None

            raw_text = "\n".join([
                f"标题: {v['title']}\n频道: {v['channel']}\n描述: {v.get('description', '')}"
                for v in all_videos
            ])

            return {
                "url": "YouTube Data API v3",
                "content_length": len(raw_text),
                "raw_text": raw_text,
                "video_count": len(all_videos),
            }
        except Exception as e:
            print(f"    [警告] YouTube API抓取失败: {e}")
            return None

    def _local_analysis(self, raw_data: Dict[str, Any], user_topic: str) -> Dict[str, Any]:
        """本地统计分析"""
        all_texts = []
        total_items = 0
        for source_key, source_data in raw_data.items():
            for result in source_data.get("results", []):
                raw_text = result.get("raw_text", "")
                if raw_text:
                    all_texts.append((source_key, raw_text))
                    total_items += 1

        # 提取高频词（简单词频统计）
        word_freq = {}
        for source_key, text in all_texts:
            # 中文词：按2-4字分词
            chinese_chars = re.findall(r'[\u4e00-\u9fff]{2,4}', text)
            for word in chinese_chars:
                if len(word) >= 2:
                    word_freq[word] = word_freq.get(word, 0) + 1

            # 英文词
            english_words = re.findall(r'\b[a-z]{3,}\b', text.lower())
            for word in english_words:
                word_freq[word] = word_freq.get(word, 0) + 1

        # 热门词TOP20
        hot_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:20]

        sources_covered = sum(1 for s in raw_data.values() if s.get("results"))

        return {
            "total_sources": len(raw_data),
            "sources_covered": sources_covered,
            "hot_words": [{"word": w, "count": c} for w, c in hot_words],
            "total_extracted_items": total_items,
            "raw_data_summary": {k: len(v.get("results", [])) for k, v in raw_data.items()},
            "extraction_method": "word_frequency",
        }

    def _deepseek_analysis(
        self,
        local_analysis: Dict[str, Any],
        user_topic: str,
    ) -> Dict[str, Any]:
        """调用DeepSeek做深度分析"""
        hot_words = "\n".join([f"- {w}: 出现{c}次" for w, c in local_analysis.get("hot_words", [])[:15]])
        data_summary = json.dumps(local_analysis.get("raw_data_summary", {}), ensure_ascii=False)
        total_items = local_analysis.get("total_extracted_items", 0)
        sources_covered = local_analysis.get("sources_covered", 0)
        total_sources = local_analysis.get("total_sources", 0)

        prompt = f"""你是行业数据分析师。请基于以下调研数据，给出趋势分析和针对用户话题的建议。

【调研数据概况】
- 数据源数量: {sources_covered}/{total_sources}个成功抓取
- 提取内容项: {total_items}条
- 提取方式: 词频统计

【热门词汇TOP15】
{hot_words or '（数据不足，请根据行业知识补充）'}

【数据来源分布】
{data_summary}

【用户话题】
{user_topic or '（未提供）'}

请按以下格式输出分析结果（用中文）：

## 行业趋势调研摘要
调研时间：{datetime.now().strftime("%Y-%m-%d")}

### 🔥 热门话题
（总结当前最热的话题类型，结合上面的词汇数据）

### 📈 趋势关键词
（列出5-10个趋势词）

### 💡 针对"{user_topic or '该话题'}"的建议
（具体建议：核心关注点、推荐角度、参考方向）
"""

        try:
            response = self.deepseek_client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[
                    {"role": "system", "content": "你是一位资深行业数据分析师。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )
            insight_text = response.choices[0].message.content

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
        parts = re.split(r'^## ', text, flags=re.MULTILINE)
        for part in parts[1:]:
            lines = part.strip().split('\n', 1)
            if len(lines) == 2:
                title = re.sub(r'[#\n*]', '', lines[0]).strip()
                content = lines[1].strip()
                sections[title] = content
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
                        "user_topic": data.get("user_topic", ""),
                        "category": data.get("category", "all"),
                        "sources_covered": data.get("local_analysis", {}).get("sources_covered", 0),
                        "filepath": str(f),
                    })
            except:
                pass
        return records[::-1]
