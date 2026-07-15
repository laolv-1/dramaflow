# DramaFlow Story Generator

AI短剧策划案自动生成工具。输入故事/主题，AI自动生成完整策划案。

## 功能

- 从小说章节自动生成策划案
- 从故事主题自动生成策划案
- 生成角色图片提示词（英文，含完整视觉描述）
- 生成场景图片提示词（英文，含环境描述）
- 生成视频运镜提示词（英文，专业电影术语）
- 生成TTS音频提示词（旁白+台词+声线选择）
- 输出结构化JSON，可直接被DramaFlow读取

## 快速开始

```bash
# 1. 安装依赖
pip install openai

# 2. 配置API Key
python -m story_generator.main init

# 3. 从故事文本生成
python -m story_generator.main story "一个女孩被未婚夫背叛，车祸后重生回到三年前..."

# 4. 从主题生成
python -m story_generator.main theme "重生复仇" --genre "都市"

# 5. 查看已生成的策划案
python -m story_generator.main list
```

## API Key管理

```bash
# 查看所有服务商Key状态
python -m story_generator.main keys list

# 设置DeepSeek API Key
python -m story_generator.main keys set --provider deepseek --key "你的key"

# 验证所有Key
python -m story_generator.main keys validate
```

## 输出格式

生成的策划案是标准JSON，包含：
- 项目基本信息
- 故事梗概（Logline + Synopsis）
- 角色设定（含image_prompts和variants）
- 分集场景（含slugline、action、dialogues、narration、image_prompt、video_prompt）
- 悬念钩子
- 制作规格

可直接被DramaFlow的pipeline读取，形成完整管道：
```
故事/主题 → story_generator → episode_X.json → DramaFlow → 成品视频
```

## 成本

使用 deepseek-v4-flash 模型：
- 单集策划案 ≈ ¥0.08
- 全套80集 ≈ ¥6.40
