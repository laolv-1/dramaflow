# DramaFlow

> AI驱动的短剧自动化流水线。从剧本到成片，一键完成。

一个轻量级的 Manifest 驱动型命令行工具，用于自动化AI短剧生产。受 [AI-CanvasPro](https://github.com/ashuoAI/AI-CanvasPro) 启发，但简化为个人学习和自用版本。

## 功能特点

- **Manifest驱动架构**：用JSON定义AI模型，新增服务商无需改代码
- **适配器模式**：统一接口对接多个AI服务商（图片/视频/音频）
- **线性流水线**：剧本 → 图片 → 视频 → 音频 → 合成
- **竖屏视频支持**：1080x1920 (9:16)，专为抖音/快手/Shorts优化
- **免费优先**：Edge TTS（免费）+ agnes-ai API + FFmpeg
- **虚拟路径抽象**：彻底解决FFmpeg路径解析问题
- **原子文件名**：`gen_YYYYMMDD_NNNN.mp4` 格式，天然防冲突
- **预览模式**：跑正式流程前先预览，不消耗API额度

## 架构

```
剧本/episode.json
    │
    ▼
manifests/          ← AI模型注册表（JSON定义）
    │
    ▼
adapters/           ← 适配器（agnes-ai、免费替代方案...）
    │
    ▼
pipeline/           ← 线性执行：文本 → 图片 → 视频 → 音频 → 合成
    │
    ▼
output/             ← gen_YYYYMMDD_NNNN.mp4（自动编号，无冲突）
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
pip install python-dotenv  # 支持.env文件
```

### 2. 配置API Key

```bash
# 复制示例文件并填入你的key
cp .env.example .env

# 编辑 .env 文件，填入 AGNES_API_KEY
```

或者设置环境变量：
```bash
set AGNES_API_KEY=你的key
```

### 3. 运行

```bash
# 预览模式（不调用API）
python main.py episode 2 --dry-run

# 完整流水线执行
python main.py episode 2

# 跳过某些步骤
python main.py episode 2 --skip-image --skip-video
```

### 4. 自定义剧集数据

把 `main.py` 里的 `get_sample_episode_info()` 替换为你的剧集JSON，或从文件加载：

```python
# 从JSON文件加载
from pipeline.step_text import load_episode_from_file
parser = load_episode_from_file("episode_2.json")
episode_info = parser.info
```

## 项目结构

```
DramaFlow/
├── main.py                  # CLI入口
├── config.example.yaml      # 配置模板
├── manifests/               # AI模型注册表
│   ├── image_models.json    # 图片生成模型
│   ├── video_models.json    # 视频生成模型
│   └── audio_models.json    # 音频/TTS模型
├── adapters/
│   ├── base.py              # 适配器抽象接口
│   └── agnes_ai.py          # Agnes AI适配器
├── pipeline/
│   ├── step_text.py         # 剧集数据解析
│   ├── step_image.py        # 角色&场景图片生成
│   ├── step_video.py        # 图生视频
│   ├── step_audio.py        # TTS音频生成
│   └── step_synthesize.py   # FFmpeg视频合成
├── media/
│   ├── processor.py         # FFmpeg/Pillow封装
│   └── utils.py             # 虚拟路径、文件命名、去重
└── tests/
```

## 支持的AI服务商

| 类别 | 当前 | 计划 |
|------|------|------|
| 图片 | Agnes AI (agnes-image-2.1-flash) | 免费替代方案 |
| 视频 | Agnes AI (agnes-video-v2.0) | 免费替代方案 |
| 音频 | Microsoft Edge TTS（免费） | - |
| 合成 | FFmpeg 8.x | - |

## 待办事项

- [ ] FFmpeg字幕添加（路径解析修复）
- [ ] 竖屏模糊扩展（目前是黑边填充）
- [ ] 场景过渡效果（淡入淡出）
- [ ] 并行执行（目前是串行）
- [ ] API失败重试机制
- [ ] 从外部JSON/YAML文件加载剧集数据

## 灵感来源

- [AI-CanvasPro](https://github.com/ashuoAI/AI-CanvasPro) — 基于节点的AI画布编辑器（1078星）
  - 学到了：Manifest注册系统、适配器模式、虚拟路径抽象、原子写入

## 协议

MIT License — 个人学习和自用，非商业用途。

## 技术栈

- Python 3.10+
- httpx / aiohttp
- edge-tts
- FFmpeg 8.x
- Pillow
- PyYAML
