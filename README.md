# DramaFlow — 语录短视频流水线

DeepSeek 金句 → Mossland TTS 配音 → 竖屏视频合成

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置 API Key
# 编辑 .env_moss，填入 MOSS_API_KEY
# 编辑 .env，填入 DEEPSEEK_API_KEY

# 运行
python main.py
```

## 用法

```bash
python main.py                              # 全自动生成一条语录短视频
python main.py --template 扎心励志           # 指定语录模板
python main.py --text "自定义文案"           # 使用自定义文案
python main.py --skip-tts                    # 跳过配音（使用已有音频）
```

## 技术栈

- DeepSeek API — 金句文案生成
- Mossland TTS (api.mosi.cn) — 语音合成
- FFmpeg — 竖屏视频合成
- Pillow — 茶桌背景图生成
