# Story Generator 使用指南

## 前置要求

- Python 3.10+
- 已配置 API Key（DeepSeek）

## 安装依赖

```bash
cd story_generator
pip install openai python-dotenv edge-tts
```

## 配置 API Key

编辑 `story_generator/.env` 文件：

```
DEEPSEEK_API_KEY=your_key_here
```

或通过命令行设置：
```bash
python -m story_generator.main keys set --provider deepseek --your_key_here
```

## 使用方法

### 从故事文本生成策划案

```bash
python -m story_generator.main story "少年林飞被师兄陷害废去修为扔下断魂崖..."
```

### 从主题生成策划案

```bash
python -m story_generator.main theme "重生复仇" --genre "玄幻修仙"
```

### 查看已生成的策划案

```bash
python -m story_generator.main list
```

## 输出

策划案保存在 `story_generator/output/episode_XXX.json`，包含：

- 项目基本信息（剧名、题材、角色设定）
- 5-8个角色的详细设定（含英文图片提示词）
- 每集3-6个场景的完整大纲
- 每个场景的：旁白、台词、图片提示词、视频运镜提示词
- 悬念钩子和制作规格

## 连接到视频流水线

生成策划案后，使用 DramaFlow 流水线生成视频：

```bash
cd ..
python main.py episode 1 --json story_generator/output/episode_001.json
```

这将自动读取策划案，生成角色图、场景图、视频、配音，并合成成品。
