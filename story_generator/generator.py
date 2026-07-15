"""策划案生成器 - 调用DeepSeek API生成完整短剧策划案"""

import os
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from openai import OpenAI
except ImportError:
    raise ImportError("请安装 openai: pip install openai")

from key_manager import KeyManager


class EpisodeGenerator:
    """
    策划案生成器

    输入：小说章节 / 故事主题 / 题材类型
    输出：结构化JSON策划案（可直接被DramaFlow读取）

    使用 DeepSeek v4-flash 模型（便宜、够用）
    """

    SYSTEM_PROMPT = """你是一个专业的短剧编剧和策划师。你的任务是为用户的故事生成完整的短剧策划案。

你需要输出以下所有内容，严格按照JSON格式：

## 输出要求

### 1. 项目基本信息
- 剧名、题材类型、目标受众、每集时长、总集数、视觉风格、一句话简介

### 2. 故事梗概
- Logline（一句话概括）
- Synopsis（300-500字完整概述）

### 3. 角色设定（5-8个主要角色）
每个角色包含：
- name（中文名）、age、gender、occupation
- personality（性格关键词，箭头分隔如"隐忍→黑化→复仇"）
- appearance（外貌详细描写）
- wardrobe（每套造型的详细描述）
- backstory（背景故事）
- image_prompts（英文版角色图片提示词，包含：年龄、种族、肤色、眼睛、发型发色、服装、姿势表情、光线、背景、构图、画质风格）
- variants（不同状态的变体，如"重生前/重生后"，每个变体有自己的image_prompt）

### 4. 分集大纲（每集包含）
每集3-6个场景，每个场景包含：
- scene_id（场景编号）
- slugline（标准场景标题，格式：场景号. 内/外景 地点 日/夜 镜头类型）
- name（场景英文名，snake_case）
- location（地点）
- time（day/night/rain/snow等）
- weather（天气）
- mood（氛围：dark/warm/tense/sad/joyful）
- props（关键道具）
- characters_present（在场角色）
- action（动作描写，可见的动作和表情）
- narration（旁白文本，中文）
- narration_voice（旁白声线推荐）
- narration_rate（旁白语速推荐）
- dialogues（台词列表，每个包含character、text、voice、rate、pitch）
- image_prompt（场景图片提示词，英文）
- video_prompt（视频运镜提示词，英文）
- transition（转场效果：fade_in/fade_out/cut/slide_left等）

### 5. 悬念钩子
- 每集结尾的悬念，吸引观众看下一集

### 6. 制作规格
- 分辨率（目标1080x1920竖屏9:16）
- 帧率（24fps）
- 单段视频时长（5秒）

请确保：
1. 角色图片提示词要非常详细，包含所有视觉要素
2. 视频运镜提示词要专业，使用标准电影术语
3. TTS旁白和台词要区分清楚
4. 台词要符合角色性格
5. 悬念钩子要足够吸引人
6. 全部用JSON格式输出，不要有其他文字

"""

    def __init__(self, model: str = "deepseek-v4-flash", thinking_enabled: bool = False):
        """
        Args:
            model: 模型选择（deepseek-v4-flash 或 deepseek-v4-pro）
            thinking_enabled: 是否开启思考模式（策划案不需要，设为False）
        """
        key_mgr = KeyManager()
        api_key = key_mgr.get_key("deepseek")
        if not api_key:
            raise ValueError("未设置DEEPSEEK_API_KEY，请先配置API Key")

        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
        )
        self.model = model
        self.thinking_enabled = thinking_enabled

    def generate_from_story(self, story_text: str, episode_count: int = 12,
                             total_episodes: int = 80) -> Dict[str, Any]:
        """
        从故事文本生成完整策划案
        Args:
            story_text: 故事文本（小说章节、故事大纲等）
            episode_count: 每部剧集数
            total_episodes: 总集数
        Returns:
            策划案JSON
        """
        user_prompt = f"""请为以下故事生成完整的短剧策划案：

故事内容：
{story_text}

要求：
- 每部 {episode_count} 集
- 总共 {total_episodes} 集
- 每集时长约2分钟
- 目标受众：18-35岁
- 视觉风格：写实电影感

请生成第1集的完整策划案（包含所有角色、场景、提示词）。
"""

        return self._call_api(user_prompt)

    def generate_from_theme(self, theme: str, genre: str = "都市",
                             episode_count: int = 12,
                             total_episodes: int = 80) -> Dict[str, Any]:
        """
        从故事主题生成策划案
        Args:
            theme: 故事主题（如"重生复仇"、"穿越修仙"）
            genre: 题材类型
            episode_count: 每部剧集数
            total_episodes: 总集数
        Returns:
            策划案JSON
        """
        user_prompt = f"""请基于以下主题生成完整的短剧策划案：

- 题材：{genre}
- 主题：{theme}
- 每部 {episode_count} 集
- 总共 {total_episodes} 集
- 每集时长约2分钟
- 目标受众：18-35岁
- 视觉风格：写实电影感

请生成第1集的完整策划案（包含所有角色、场景、提示词）。
"""

        return self._call_api(user_prompt)

    def _call_api(self, user_prompt: str) -> Dict[str, Any]:
        """调用DeepSeek API"""
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        extra_params = {}
        if self.thinking_enabled:
            extra_params["extra_body"] = {
                "thinking": {"type": "enabled"},
            }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.7,
                    stream=False,
                    **extra_params,
                )

                content = response.choices[0].message.content
                # 尝试解析JSON
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()

                result = json.loads(content)
                return result

            except Exception as e:
                print(f"[EpisodeGenerator] 第{attempt + 1}次尝试失败: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    raise RuntimeError(f"策划案生成失败，已重试{max_retries}次: {e}")

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        估算API调用成本
        Args:
            input_tokens: 输入tokens数
            output_tokens: 输出tokens数
        Returns:
            费用（人民币）
        """
        # deepseek-v4-flash 价格
        input_price_per_million = 1.0  # 缓存未命中
        output_price_per_million = 2.0
        return (input_tokens / 1_000_000 * input_price_per_million +
                output_tokens / 1_000_000 * output_price_per_million)
