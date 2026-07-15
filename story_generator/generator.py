"""策划案生成器 - 调用DeepSeek API生成完整短剧策划案"""

import os
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

try:
    from openai import OpenAI
except ImportError:
    raise ImportError("请安装 openai: pip install openai")

from key_manager import KeyManager


class EpisodeGenerator:
    """
    策划案生成器

    输入：小说章节 / 故事主题 / 题材类型 / 调研结果
    输出：结构化JSON策划案（可直接被DramaFlow读取）

    模型策略：
    - 调研分析：deepseek-v4-pro（需要推理能力）
    - 策划案生成：deepseek-v4-flash（结构化输出，成本低）
    """

    # 爆款短剧核心规则 - 注入SYSTEM_PROMPT
    VIRAL_RULES = """

【爆款短剧核心规则 - 必须严格遵守】
1. 题材公式：重生+复仇+逆袭 = 最高完播率；大女主+权谋 = 最高付费转化
2. 节奏标准：每集1-2分钟，无注水内容，每8-12秒一个情绪点
3. 钩子体系：
   - 开头3秒：视觉冲击或戏剧性台词（决定滑走率）
   - 集尾3-5秒：最大悬念（触发下一集点击）
   - 每3集一次重大反转，每10集一次高潮
4. 情绪工程：每集必须有情绪曲线（平静→紧张→反转→释放→悬念）
5. 微反转：每集至少2-3个迷你反转，不只是大情节反转
6. 台词标准：每集至少1句可传播的金句/爽句
7. 受众定位：核心付费人群30-45岁女性，兼顾18-35岁年轻群体
"""

    # 小说改编专用prompt
    NOVEL_SYSTEM_PROMPT = """你是一个专业的短剧编剧和策划师。你的任务是将小说内容改编为短剧策划案。

【改编原则】
1. 保留小说的核心冲突和精彩台词
2. 将小说叙述转化为短剧场景格式
3. 每集必须有明确的开头钩子（0-3秒）和结尾悬念
4. 对话要口语化、有张力，不要书面语
5. 场景要精简，每集不超过6个场景

【极其重要】你必须严格按照以下JSON结构输出，字段名和层级不能有任何偏差：

```json
{
  "project": {
    "title": "剧名（必填）",
    "genre": "题材类型",
    "target_audience": "目标受众",
    "episode_duration": "每集时长（如：2分钟）",
    "total_episodes": 总集数（数字）,
    "visual_style": "视觉风格",
    "logline": "一句话简介",
    "synopsis": "故事梗概（300-500字）"
  },
  "characters": [
    {
      "name": "角色中文名",
      "age": "年龄（数字）",
      "gender": "性别",
      "occupation": "身份/职业",
      "personality": "性格关键词，用箭头分隔",
      "appearance": "外貌详细描写",
      "wardrobe": ["造型1描述", "造型2描述"],
      "backstory": "背景故事",
      "image_prompts": "英文版角色图片提示词",
      "variants": {
        "变体名": "变体的英文图片提示词"
      }
    }
  ],
  "episodes": [
    {
      "episode_number": 1,
      "title": "集标题",
      "hook": "本集结尾悬念钩子",
      "scenes": [
        {
          "scene_id": 1,
          "slugline": "场景编号. 内/外景 地点 日/夜 镜头类型",
          "name": "scene_english_name",
          "location": "地点",
          "time": "day或night",
          "weather": "天气",
          "mood": "dark或warm或tense或sad或joyful或mysterious",
          "props": "关键道具描述（字符串，不要用数组）",
          "characters_present": ["角色1", "角色2"],
          "action": "动作描写",
          "narration": "旁白文本",
          "narration_voice": "旁白声线推荐",
          "narration_rate": "语速推荐",
          "dialogues": [
            {"character": "角色名", "text": "台词内容", "voice": "声线", "rate": "语速", "pitch": "音高"}
          ],
          "image_prompt": "场景图片英文提示词",
          "video_prompt": "视频运镜英文提示词",
          "transition": "fade_in或fade_out或cut或slide_left等"
        }
      ]
    }
  ],
  "production_specs": {
    "resolution": "1080x1920 (竖屏9:16)",
    "frame_rate": "24fps",
    "segment_duration": "5秒"
  }
}
```

【极其重要的字段名约束】
- 项目信息字段必须用：project.title, project.genre, project.target_audience, project.episode_duration, project.total_episodes, project.visual_style, project.logline, project.synopsis
- 分集大纲必须用：episodes（数组），不要用 episode_1、episode_outline 等其他字段名
- 每个episode必须包含：episode_number, title, hook, scenes（数组）
- wardrobe 必须是数组格式 ["造型1", "造型2"]，不要用中文描述字符串
- variants 必须是对象格式 {"变体名": "提示词字符串"}，不要用数组
- image_prompts 必须是字符串（英文提示词），不要用对象
- props 必须是字符串，不要用数组
- 所有字段都必须有值，不要省略任何字段
- 不要使用任何不在上述Schema中定义的字段名
"""

    def __init__(self, model: str = "deepseek-v4-flash", thinking_enabled: bool = False, api_key: Optional[str] = None):
        """
        Args:
            model: 模型选择（deepseek-v4-flash 或 deepseek-v4-pro）
            thinking_enabled: 是否开启思考模式（策划案不需要，设为False）
            api_key: 自定义API Key（可选，不传则从KeyManager加载）
        """
        if api_key:
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com",
            )
        else:
            key_mgr = KeyManager(config_dir=str(Path(__file__).parent))
            api_key_val = key_mgr.get_key("deepseek")
            if not api_key_val:
                raise ValueError("未设置DEEPSEEK_API_KEY，请先配置API Key")
            self.client = OpenAI(
                api_key=api_key_val,
                base_url="https://api.deepseek.com",
            )
        self.model = model
        self.thinking_enabled = thinking_enabled

    def generate_from_story(self, story_text: str, episode_count: int = 12,
                             total_episodes: int = 80,
                             research_context: Optional[str] = None) -> Dict[str, Any]:
        """
        从故事文本生成完整策划案
        Args:
            story_text: 故事文本（小说章节、故事大纲等）
            episode_count: 每部剧集数
            total_episodes: 总集数
            research_context: 调研结果文本（可选，注入到prompt中）
        Returns:
            策划案JSON
        """
        viral_rules = self.VIRAL_RULES if research_context else ""
        user_prompt = f"""请为以下故事生成完整的短剧策划案：

故事内容：
{story_text}{research_context}
{'【市场趋势参考】' + research_context if research_context else ''}

要求：
- 每部 {episode_count} 集
- 总共 {total_episodes} 集
- 每集时长约2分钟
- 目标受众：18-35岁
- 视觉风格：写实电影感
{viral_rules}
请生成第1集的完整策划案（包含所有角色、场景、提示词）。
"""

        return self._call_api(user_prompt)

    def generate_from_theme(self, theme: str, genre: str = "都市",
                             episode_count: int = 12,
                             total_episodes: int = 80,
                             research_context: Optional[str] = None) -> Dict[str, Any]:
        """
        从故事主题生成策划案
        Args:
            theme: 故事主题（如"重生复仇"、"穿越修仙"）
            genre: 题材类型
            episode_count: 每部剧集数
            total_episodes: 总集数
            research_context: 调研结果文本（可选）
        Returns:
            策划案JSON
        """
        viral_rules = self.VIRAL_RULES if research_context else ""
        user_prompt = f"""请基于以下主题生成完整的短剧策划案：

- 题材：{genre}
- 主题：{theme}
- 每部 {episode_count} 集
- 总共 {total_episodes} 集
- 每集时长约2分钟
- 目标受众：18-35岁
- 视觉风格：写实电影感
{research_context + '\n' if research_context else ''}{viral_rules}
请生成第1集的完整策划案（包含所有角色、场景、提示词）。
"""

        return self._call_api(user_prompt)

    def generate_from_novel(self, novel_chapter: str, episode_count: int = 12,
                             total_episodes: int = 80) -> Dict[str, Any]:
        """
        从小说章节改编为短剧策划案
        Args:
            novel_chapter: 小说章节内容
            episode_count: 每部剧集数
            total_episodes: 总集数
        Returns:
            策划案JSON
        """
        user_prompt = f"""请将以下小说章节改编为短剧策划案：

小说内容：
{novel_chapter}

改编要求：
- 保留核心冲突和精彩台词
- 将叙述转化为短剧场景格式
- 每集必须有开头钩子（0-3秒）和结尾悬念
- 对话要口语化、有张力
- 场景精简，每集不超过6个场景
- 每部 {episode_count} 集，总共 {total_episodes} 集
- 每集时长约2分钟

请生成第1集的完整策划案（包含所有角色、场景、提示词）。
"""

        return self._call_api(user_prompt, system_prompt=self.NOVEL_SYSTEM_PROMPT)

    def generate_with_research(self, theme: str, genre: str = "玄幻修仙",
                                episode_count: int = 12,
                                total_episodes: int = 80,
                                research_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        基于调研结果生成策划案（完整流程）
        Args:
            theme: 故事主题
            genre: 题材类型
            episode_count: 每部剧集数
            total_episodes: 总集数
            research_result: TrendResearcher.research()返回的结果
        Returns:
            策划案JSON
        """
        if not research_result:
            return self.generate_from_theme(theme, genre, episode_count, total_episodes)

        # 提取调研洞察
        insight = research_result.get("deepseek_insight", {})
        if insight:
            research_text = f"""

【市场调研结果】
{insight.get('raw_insight', '') if isinstance(insight, dict) else str(insight)}
"""
        else:
            # 只有本地分析，没有DeepSeek洞察
            local = research_result.get("local_analysis", {})
            hot_kws = local.get("hot_keywords", [])
            research_text = f"""

【本地调研结果】
热门关键词：
""" + "\n".join([f"- {kw['keyword']}: {kw['frequency']}次" for kw in hot_kws[:10]])

        return self.generate_from_theme(
            theme=theme,
            genre=genre,
            episode_count=episode_count,
            total_episodes=total_episodes,
            research_context=research_text,
        )

    def _call_api(self, user_prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """调用DeepSeek API，确保返回标准JSON结构"""
        messages = [
            {"role": "system", "content": system_prompt or self.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        extra_params = {}
        if self.thinking_enabled:
            extra_params["extra_body"] = {
                "thinking": {"type": "enabled"},
            }

        max_retries = 5
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
                # 去除code fence
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()

                result = json.loads(content)

                # 校验并标准化结构
                normalized = self._normalize_structure(result)
                return normalized

            except Exception as e:
                print(f"[EpisodeGenerator] 第{attempt + 1}次尝试失败: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    raise RuntimeError(f"策划案生成失败，已重试{max_retries}次: {e}")

    def _normalize_structure(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化JSON结构，兼容DeepSeek可能返回的不同字段名
        将所有变体转换为标准格式
        """
        # 1. 标准化 project 字段
        project = data.get("project", {})
        if not project or not project.get("title"):
            # 尝试 project_info
            pi = data.get("project_info", {})
            if pi:
                project = {}
                for k, v in pi.items():
                    nk = k.replace(" ", "_").replace("-", "_")
                    project[nk] = v
                data["project"] = project

        project = data.get("project", {})

        # 标准化 logline/synopsis
        if not project.get("logline"):
            ss = data.get("story_synopsis", {})
            if isinstance(ss, dict):
                project["logline"] = ss.get("logline", project.get("logline", ""))
                project["synopsis"] = ss.get("synopsis", project.get("synopsis", ""))
            else:
                project["logline"] = project.get("logline", "")
                project["synopsis"] = project.get("synopsis", "")

        # 2. 标准化 episodes 字段
        episodes = data.get("episodes", [])
        if not episodes:
            episodes = data.get("episode_outline", [])
            if episodes:
                data["episodes"] = episodes

        # 3. 标准化每个 episode
        for ep in episodes:
            if not ep.get("hook"):
                ep["hook"] = ep.get("cliffhanger", ep.get("hook", ""))

            for scene in ep.get("scenes", []):
                if isinstance(scene.get("props"), list):
                    scene["props"] = "、".join(scene["props"])

        # 4. 标准化角色
        for char in data.get("characters", []):
            img_prompts = char.get("image_prompts")
            if isinstance(img_prompts, dict):
                char["image_prompts"] = img_prompts.get("base", "")
                if "variants" in img_prompts:
                    char["variants"] = img_prompts["variants"]

            if char.get("variants") and isinstance(char["variants"], list):
                new_variants = {}
                for v in char["variants"]:
                    if isinstance(v, dict):
                        new_variants[v.get("name", "unknown")] = v.get("image_prompt", "")
                char["variants"] = new_variants

            if isinstance(char.get("wardrobe"), str):
                items = [s.strip() for s in char["wardrobe"].split('，') if s.strip()]
                char["wardrobe"] = items if len(items) > 1 else [char["wardrobe"]]

        return data

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
