# 短剧/短视频数据采集生态全景

> 最后更新: 2026-07-16
> 定位: 轻量化项目数据源选型指南

---

## 一、国内数据源

### 免费可用

| 名称 | 类型 | 获取方式 | 适用场景 | 限制 |
|------|------|---------|---------|------|
| **巨量算数** | 官方网页 | trendinsight.oceanengine.com | 抖音搜索指数/热点追踪/人群洞察 | 需手动浏览，无公开API |
| **B站搜索** | 网页 | Jina可抓 / yt-dlp下载 | 短剧视频/讨论/行业分析 | 内容质量参差 |
| **豆瓣小组** | 网页 | Jina可抓 | 短剧讨论/口碑 | 数据量小 |
| **36Kr/少数派/简书** | 技术文章 | Jina可抓 | AI短剧行业动态 | 非短剧专属 |
| **抖音开放平台API** | 官方API | open.douyin.com (免费) | 仅能操作自己授权账号数据 | 不提供第三方数据 |
| **抖音创作者服务** | 官方工具 | creator.douyin.com (免费) | 自有账号数据分析 | 只看自己数据 |

### 收费专业

| 名称 | 价格 | 核心能力 |
|------|------|---------|
| **飞瓜数据** | ¥198-748+/月 | 抖音/快手/B站全平台达人+短剧数据 |
| **蝉妈妈短剧版** | ¥数百-数千/月 | 播放量/付费用户/ARPU/热门排行 |
| **新抖** | ¥数百/月起 | 抖音达人排行+短视频分析 |
| **灰豚数据** | 收费 | 性价比高 |
| **考古加** | Freemium | 轻量抖音数据 |

### 开源项目 (GitHub)

| 项目 | 功能 | 状态 |
|------|------|------|
| `douyin-open-api/DouYin` | 抖音/TikTok爬虫API | 活跃 |
| `nicholasluyao/Douyin-API-Python` | 抖音数据采集 | 活跃 |
| `woolssm/douyin_video_dl` | 抖音去水印下载 | 维护中 |
| `mltcode/douyin-bot-python` | 纯Python抖音工具 | 轻量 |

---

## 二、海外数据源

### 免费可用

| 名称 | 类型 | 获取方式 | 适用场景 | 限制 |
|------|------|---------|---------|------|
| **TikTok Creative Center** | 官方网页 | creative-center.tiktok.com | 趋势/音乐/Hashtag/Creator | 免费，需手动浏览 |
| **TikTok Creative Center API** | 官方API | developers.tiktok.com | 程序化获取趋势数据 | 需开发者审核 |
| **YouTube Data API v3** | 官方API | developers.google.com (免费10000units/天) | Shorts搜索/热门视频/元数据 | 每天约100次搜索配额 |
| **Apify 免费额度** | 云平台 | apify.com ($5/月免费) | TikTok Scraper + Trends Scraper | 免费额度有限 |
| **AppMagic 免费版** | App数据 | appmagic.pro | 海外短剧App收入/下载估算 | 仅短期数据 |

### 收费专业

| 名称 | 价格 | 核心能力 |
|------|------|---------|
| **Sensor Tower** | 企业级 | 海外短剧App收入估算+排名 (#1平台) |
| **data.ai (App Annie)** | 企业级 | 下载/收入趋势+行业报告 |
| **Apify 付费版** | $49+/月 | TikTok/ReelShort全功能爬虫 |

### 开源项目 (GitHub)

| 项目 | 功能 | 状态 |
|------|------|------|
| `apify/tiktok-scraper` | TikTok视频/Hashtag/用户爬虫 | 活跃 |
| `apify/tiktok-trends-scraper` | TikTok趋势数据提取 | 活跃 |
| `apify/reelshort-data-extractor` | ReelShort结构化数据 | 活跃 |
| `jsnippet/reelshort-api-wrapper` | ReelShort内部API封装(Node.js) | 轻量 |
| `maheshmurukutti/reelshort-scraper` | Python ReelShort爬虫 | 轻量 |

---

## 三、通用工具

| 工具 | 费用 | 功能 | 跨平台适用 |
|------|------|------|-----------|
| **yt-dlp** | 完全免费开源 | 下载1000+网站视频+元数据 | YouTube/B站/TikTok/抖音 |
| **lux** | 完全免费开源 | Go语言媒体下载器 | 抖音/B站/快手/YouTube |
| **Jina Reader** | 免费1000credits | 网页转Markdown | 海外网页(B站/豆瓣/36Kr) |
| **Agent-Reach** | 完全免费开源 | MCP Server自动化 | 自部署无限制 |

---

## 四、轻量化项目推荐方案

### 原则
- 能免费则免费，不花冤枉钱
- 优先利用现有开源项目，不重复造轮子
- 不依赖需要科学上网才能访问的国内源
- 不追求大而全，聚焦短剧策划案生成的核心需求

### 推荐组合

#### 国内趋势（免费）
1. **巨量算数** — 手动浏览 + 程序抓取公开页面数据
2. **B站** — Jina Reader 抓取搜索页/热门视频标题
3. **豆瓣** — Jina Reader 抓取短剧讨论帖
4. **36Kr/少数派/简书** — Jina Reader 抓取行业分析文章

#### 海外趋势（免费）
1. **TikTok Creative Center** — 程序抓取趋势页面（免费）
2. **YouTube Data API v3** — 每日10000单位配额足够中小规模调研
3. **yt-dlp** — 下载样本视频提取元数据
4. **AppMagic 免费层** — 海外短剧App基础数据

#### 海外短剧App（免费）
1. **Apify 免费额度** ($5/月) — TikTok Scraper + ReelScraper
2. **手动追踪** — App Store/Google Play 排行榜

### 未来可扩展（按需付费）
- 蝉妈妈/飞瓜数据：需要深度短剧市场分析时开通
- Sensor Tower：需要海外短剧App收入精算时开通
- Apify 付费版：需要高频自动化采集时升级
