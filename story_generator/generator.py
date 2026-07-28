"""策划案生成器 - 调用DeepSeek API生成完整短剧策划案"""

import os
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

try:
    from openai import OpenAI
except ImportError:
    raise ImportError("请安装 openai: pip install openai")

from key_manager import KeyManager


class TTSClient:
    """Mossland TTS 客户端 - 使用 urllib 避免 requests 的 header 校验问题"""

    API_BASE = "https://api.mosi.cn/v1/audio"
    DEFAULT_VOICE_ID = "fa435ac6-416a-4676-b138-a6ff8380e7cf"
    MODEL = "moss-tts"

    def __init__(self, api_key: Optional[str] = None, voice_id: str = DEFAULT_VOICE_ID,
                 speed: float = 1.0, model: str = MODEL, api_base: str = API_BASE):
        self.api_base = api_base
        self.default_voice_id = voice_id
        self.default_speed = speed
        self._api_key = api_key or self._load_api_key()

    def _load_api_key(self) -> str:
        """从环境变量或配置文件获取 API Key"""
        key = os.environ.get("MOSS_API_KEY")
        if key:
            return key
        config_paths = [
            ".env_moss",
            str(Path.home() / ".moss_tts_key.txt"),
        ]
        for p in config_paths:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        if k.strip() == "MOSS_API_KEY":
                            key = v.strip().strip("\"'")
                            if key:
                                return key
                # 兼容：如果文件没有key=value格式，再试原始读取方式
                with open(p, "r", encoding="utf-8") as f:
                    raw = ''.join(c for c in f.read().strip() if 32 <= ord(c) <= 126)
                    if raw and "=" not in raw:
                        key = raw
                        if key:
                            return key
        for env_path in [".env", "../.env"]:
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        if k.strip() == "MOSS_API_KEY":
                            return v.strip().strip("\"'")
        raise ValueError("未找到 MOSS_API_KEY，请先配置 Mossland TTS API Key")

    def _make_request(self, url: str, data: Optional[Dict] = None, method: str = "GET"):
        """发送 HTTP 请求"""
        clean_key = ''.join(c for c in self._api_key if 32 <= ord(c) <= 126)
        headers = {"Authorization": "Bearer " + clean_key}
        if data:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data).encode("utf-8")
        else:
            body = None

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            return resp
        except urllib.error.HTTPError as e:
            try:
                body_err = e.read().decode("utf-8", errors="replace")
            except Exception:
                body_err = str(e)
            print(f"[TTS] HTTP {e.code}: {body_err[:500]}")
            return None
        except Exception as e:
            print(f"[TTS] 请求失败: {e}")
            return None

    def synthesize(self, text: str, output_file: str, voice_id: Optional[str] = None,
                   speed: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """合成一段文本为音频"""
        url = f"{self.api_base}/speech"
        payload = {
            "model": self.MODEL,
            "input": text,
            "voice_id": voice_id or self.default_voice_id,
            "speed": speed or self.default_speed,
        }

        resp = self._make_request(url, data=payload, method="POST")
        if resp is None:
            return None

        audio_data = resp.read()

        with open(output_file, "wb") as f:
            f.write(audio_data)

        est_duration_sec = len(audio_data) * 8 / 96000
        return {
            "file": output_file,
            "size": len(audio_data),
            "duration_sec": est_duration_sec,
        }

    def list_voices(self) -> Optional[list]:
        """列出所有可用语音角色"""
        url = f"{self.api_base}/voices"
        resp = self._make_request(url)
        if resp is None:
            return None
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("data", [])


class EpisodeGenerator:
    """
    策划案生成器

    输入：小说章节 / 故事主题 / 题材类型 / 调研结果
    输出：结构化JSON策划案（可直接被DramaFlow读取）

    模型策略：
    - 调研分析：deepseek-v4-pro（需要推理能力）
    - 策划案生成：deepseek-v4-flash（结构化输出，成本低）
    """

    # 爆款短剧核心规则（不含固定受众，受众从用户输入动态获取）
    VIRAL_RULES_TEMPLATE = """

【爆款短剧核心规则 - 必须严格遵守】
1. 题材公式：{genre_formula}
2. 节奏标准：每集{duration}，无注水内容，每8-12秒一个情绪点
3. 钩子体系：
   - 开头3秒：视觉冲击或戏剧性台词（决定滑走率）
   - 集尾3-5秒：最大悬念（触发下一集点击）
   - 每3集一次重大反转，每10集一次高潮
4. 情绪工程：每集必须有情绪曲线（平静→紧张→反转→释放→悬念）
5. 微反转：每集至少2-3个迷你反转，不只是大情节反转
6. 台词标准：每集至少1句可传播的金句/爽句
7. 受众定位：{audience}
"""

    # 题材公式映射（根据题材动态选择）
    GENRE_FORMULAS = {
        "玄幻修仙": "重生+复仇+修仙 = 最高完播率",
        "都市": "职场+逆袭+情感 = 最高付费转化",
        "言情": "甜宠+虐恋+反转 = 最高互动率",
        "悬疑": "推理+反转+揭秘 = 最高留存率",
        "科幻": "未来+危机+生存 = 最高讨论度",
        "动漫": "热血+成长+羁绊 = 最高粉丝粘性",
        "历史": "权谋+争霸+传奇 = 最高完播率",
        "恐怖": "惊悚+解谜+逃生 = 最高分享率",
        "其他": "强冲突+快节奏+情绪张力 = 最高完播率",
    }

    # 默认系统prompt（原创方向/故事文本用）
    SYSTEM_PROMPT = """你是一个专业的短剧编剧和策划师。你的任务是为用户的故事生成完整的短剧策划案。

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

    # 小说改编专用prompt
    NOVEL_PROMPT = """你是一个专业的短剧编剧和策划师。你的任务是将小说内容改编为短剧策划案。

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
                             research_context: Optional[str] = None,
                             genre: str = "其他",
                             target_audience: Optional[str] = None) -> Dict[str, Any]:
        """
        从故事文本生成完整策划案
        Args:
            story_text: 故事文本（小说章节、故事大纲等）
            episode_count: 每部剧集数
            total_episodes: 总集数
            research_context: 调研结果文本（可选，注入到prompt中）
            genre: 题材类型（动态选择爆款公式）
            target_audience: 目标受众（从用户输入获取，不硬编码）
        Returns:
            策划案JSON
        """
        viral_rules = self._build_viral_rules(genre, target_audience)
        user_prompt = f"""请为以下故事生成完整的短剧策划案：

故事内容：
{story_text}
{'【市场趋势参考】' + research_context if research_context else ''}

要求：
- 每部 {episode_count} 集
- 总共 {total_episodes} 集
- 每集时长约2分钟
- 题材：{genre}
{f'- 目标受众：{target_audience}' if target_audience else ''}
{viral_rules}
请生成第1集的完整策划案（包含所有角色、场景、提示词）。
"""

        return self._call_api(user_prompt)

    def generate_from_theme(
        self,
        theme: str,
        genre: str = "其他",
        episode_count: int = 12,
        total_episodes: int = 80,
        research_context: Optional[str] = None,
        target_audience: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        从故事主题生成策划案
        """
        viral_rules = self._build_viral_rules(genre, target_audience)
        user_prompt = f"""请基于以下主题生成完整的短剧策划案：

- 题材：{genre}
- 主题：{theme}
- 每部 {episode_count} 集
- 总共 {total_episodes} 集
- 每集时长约2分钟
{f'- 目标受众：{target_audience}' if target_audience else ''}
{research_context + '\n' if research_context else ''}{viral_rules}
请生成第1集的完整策划案（包含所有角色、场景、提示词）。
"""
        return self._call_api(user_prompt)

    def generate_outline(self, theme: str, genre: str = "其他",
                         total_episodes: int = 80,
                         research_context: Optional[str] = None,
                         target_audience: Optional[str] = None) -> Dict[str, Any]:
        """
        生成完整故事大纲（每集1-2句话概括核心事件）
        Args:
            theme: 故事主题
            genre: 题材类型
            total_episodes: 总集数（默认80）
            research_context: 调研结果文本（可选）
            target_audience: 目标受众（可选）
        Returns:
            包含 project + characters + outline 的JSON
        """
        viral_rules = self._build_viral_rules(genre, target_audience)
        outline_prompt = f"""请为以下短剧生成完整的故事大纲（共{total_episodes}集）：

- 题材：{genre}
- 主题：{theme}
{f'- 目标受众：{target_audience}' if target_audience else ''}
{research_context + '\n' if research_context else ''}
{viral_rules}

请为每一集生成一句核心事件概括（1-2句话），描述该集的关键剧情发展。

【极其重要】你必须严格按照以下JSON结构输出，字段名和层级不能有任何偏差：

```json
{{
  "project": {{
    "title": "剧名",
    "genre": "题材类型",
    "target_audience": "目标受众",
    "episode_duration": "每集时长",
    "total_episodes": {total_episodes},
    "visual_style": "视觉风格",
    "logline": "一句话简介",
    "synopsis": "故事梗概（300-500字）"
  }},
  "characters": [
    {{
      "name": "角色中文名",
      "age": "年龄",
      "gender": "性别",
      "occupation": "身份/职业",
      "personality": "性格关键词",
      "appearance": "外貌详细描写",
      "wardrobe": ["造型1描述", "造型2描述"],
      "backstory": "背景故事",
      "image_prompts": "英文版角色图片提示词"
    }}
  ],
  "outline": [
    {{"episode_number": 1, "summary": "第一集核心事件概括"}},
    {{"episode_number": 2, "summary": "第二集核心事件概括"}},
    ...
  ]
}}
```

注意：
- outline 数组必须包含全部 {total_episodes} 集
- 每集 summary 用1-2句话概括核心事件
- 所有角色和项目信息必须完整填写
"""
        system_prompt = f"""你是一个专业的短剧编剧和策划师。你的任务是为故事生成完整的短剧策划案大纲。

【极其重要】你必须严格按照以下JSON结构输出，字段名和层级不能有任何偏差：

```json
{{
  "project": {{
    "title": "剧名（必填）",
    "genre": "题材类型",
    "target_audience": "目标受众",
    "episode_duration": "每集时长（如：2分钟）",
    "total_episodes": 总集数（数字）,
    "visual_style": "视觉风格",
    "logline": "一句话简介",
    "synopsis": "故事梗概（300-500字）"
  }},
  "characters": [
    {{
      "name": "角色中文名",
      "age": "年龄（数字）",
      "gender": "性别",
      "occupation": "身份/职业",
      "personality": "性格关键词，用箭头分隔",
      "appearance": "外貌详细描写",
      "wardrobe": ["造型1描述", "造型2描述"],
      "backstory": "背景故事",
      "image_prompts": "英文版角色图片提示词",
      "variants": {{
        "变体名": "变体的英文图片提示词"
      }}
    }}
  ],
  "outline": [
    {{"episode_number": 1, "summary": "第一集核心事件概括（1-2句话）"}},
    {{"episode_number": 2, "summary": "第二集核心事件概括（1-2句话）"}}
  ]
}}
```

【极其重要的字段名约束】
- 项目信息字段必须用：project.title, project.genre, project.target_audience, project.episode_duration, project.total_episodes, project.visual_style, project.logline, project.synopsis
- 大纲必须用：outline（数组），每集包含 episode_number + summary
- wardrobe 必须是数组格式 ["造型1", "造型2"]
- variants 必须是对象格式 {{"变体名": "提示词字符串"}}
- image_prompts 必须是字符串（英文提示词）
- 所有字段都必须有值，不要省略任何字段
- 不要使用任何不在上述Schema中定义的字段名
"""
        return self._call_api(outline_prompt, system_prompt=system_prompt)

    def generate_continuation(
        self,
        prev_episode_json: Dict[str, Any],
        target_episode_number: int,
    ) -> Dict[str, Any]:
        """
        基于已有策划案生成续集（第N集）
        Args:
            prev_episode_json: 包含 project + characters + 前N-1集episodes的完整JSON
            target_episode_number: 要生成的集数（如2）
        Returns:
            完整策划案JSON（保持相同结构，episodes数组包含所有集）
        """
        project = prev_episode_json.get("project", {})
        title = project.get("title", "未命名")
        genre = project.get("genre", "其他")
        total_eps = project.get("total_episodes", 80)
        episode_count = project.get("episode_count", 12)
        characters = prev_episode_json.get("characters", [])
        existing_eps = prev_episode_json.get("episodes", [])

        # 提取前N-1集的剧情摘要（给LLM上下文）
        prev_summary_parts = []
        for ep in existing_eps:
            ep_num = ep.get("episode_number", "?")
            ep_title = ep.get("title", "")
            # 提取场景摘要
            scenes = ep.get("scenes", [])
            scene_summaries = []
            for s in scenes[:3]:  # 只取前3个场景的action
                action = s.get("action", "")[:200]
                if action:
                    scene_summaries.append(action)
            summary = f"第{ep_num}集《{ep_title}》: {'; '.join(scene_summaries[:2])}"
            prev_summary_parts.append(summary)

        prev_summary = "\n".join(prev_summary_parts[-6:])  # 最近6集

        # 构建角色信息摘要
        char_summary = "\n".join(
            f"- {c.get('name', '?')}: {c.get('personality', '')} | {c.get('backstory', '')[:100]}"
            for c in characters[:5]
        )

        # 注入故事大纲（如果存在）
        outline_section = ""
        outline_list = prev_episode_json.get("outline", [])
        if outline_list:
            # 找到目标集的大纲摘要
            target_outline = None
            for item in outline_list:
                if item.get("episode_number") == target_episode_number:
                    target_outline = item.get("summary", "")
                    break
            if target_outline:
                outline_section = f"""
【故事大纲 - 第{target_episode_number}集目标】
{target_outline}"""

        # 构建system prompt（继承已有结构）
        system_prompt = f"""你是一个专业的短剧编剧。你已经为短剧《{title}》生成了前{target_episode_number - 1}集的内容。

现在需要生成第{target_episode_number}集。

【保持角色一致性】
{char_summary}

【前情提要】
{prev_summary}{outline_section}

【输出要求】
- 必须保持与前{target_episode_number - 1}集相同的结构和字段名
- 只生成第{target_episode_number}集的完整内容（包含所有角色、场景、提示词）
- 延续前情的剧情，同时设置新的悬念钩子
- 必须严格按照以下JSON结构输出：
```json
{{
  "episode_number": {target_episode_number},
  "title": "第{target_episode_number}集聚落",
  "hook": "本集结尾悬念钩子",
  "scenes": [
    {{
      "scene_id": 1,
      "slugline": "场景编号. 内/外景 地点 日/夜 镜头类型",
      "name": "scene_english_name",
      "location": "地点",
      "time": "day或night",
      "weather": "天气",
      "mood": "dark或warm或tense或sad或joyful或mysterious",
      "props": "关键道具描述（字符串）",
      "characters_present": ["角色1", "角色2"],
      "action": "动作描写",
      "narration": "旁白文本",
      "narration_voice": "旁白声线推荐",
      "narration_rate": "语速推荐",
      "dialogues": [
        {{"character": "角色名", "text": "台词内容", "voice": "声线", "rate": "语速", "pitch": "音高"}}
      ],
      "image_prompt": "场景图片英文提示词",
      "video_prompt": "视频运镜英文提示词",
      "transition": "fade_in或fade_out或cut或slide_left等"
    }}
  ]
}}
```
注意：只输出上述JSON对象，不要包含project/characters等已有字段。
"""

        user_prompt = f"""请为短剧《{title}》生成第{target_episode_number}集的完整策划案。

题材：{genre}
总集数：{total_eps}
每部集数：{episode_count}

要求：
- 延续前情剧情，保持角色性格一致
- 每集至少3-5个场景
- 开头要有承接上集的钩子
- 结尾设置新的悬念（触发下一集点击）
- 每集至少1句可传播的金句/爽句
- 每集至少2-3个迷你反转
"""

        # 调用API后合并到完整结构中
        new_ep = self._call_api(user_prompt, system_prompt=system_prompt)

        # 将新生成的集数合并到完整结构中
        full_result = json.loads(json.dumps(prev_episode_json))  # deep copy
        ep_list = full_result.get("episodes", [])

        # 检查是否已存在该集数
        existing_nums = {ep.get("episode_number") for ep in ep_list}
        if target_episode_number not in existing_nums:
            # 确保新集数有正确的结构
            if "episode_number" in new_ep:
                del new_ep["episode_number"]  # _normalize会处理
            new_ep["episode_number"] = target_episode_number
            ep_list.append(new_ep)
            # 按集数排序
            ep_list.sort(key=lambda x: x.get("episode_number", 0))
            full_result["episodes"] = ep_list

        return full_result

    def _build_viral_rules(self, genre: str, target_audience: Optional[str] = None) -> str:
        """根据题材和目标受众动态构建爆款规则"""
        formula = self.GENRE_FORMULAS.get(genre, self.GENRE_FORMULAS["其他"])
        audience = target_audience or f"{genre}题材对应的目标受众"
        return self.VIRAL_RULES_TEMPLATE.format(
            genre_formula=formula,
            audience=audience,
            duration="1-2分钟",
        )

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

        return self._call_api(user_prompt, system_prompt=self.NOVEL_PROMPT)

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

        # 提取调研洞察（兼容多种数据结构）
        deepseek = research_result.get("deepseek_insight", {})
        if deepseek and isinstance(deepseek, dict) and deepseek.get("raw_insight"):
            research_text = f"""

【市场调研结果】
{deepseek['raw_insight']}"""
        else:
            # 使用本地分析结果（hot_words + word/count）
            local = research_result.get("local_analysis", {})
            hot_words = local.get("hot_words", [])
            if hot_words:
                research_text = f"""

【市场调研结果】
热门关键词：
""" + "\n".join([f"- {w.get('word','')}: {w.get('count',0)}次" for w in hot_words[:10]])
            else:
                research_text = ""

        return self.generate_from_theme(
            theme=theme,
            genre=genre,
            episode_count=episode_count,
            total_episodes=total_episodes,
            research_context=research_text,
            target_audience=None,  # 由LLM根据题材和调研结果动态推断
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

    def synthesize_episode(self, ep_json: Dict[str, Any], output_dir: str,
                           tts_client: Optional[TTSClient] = None) -> list:
        """合成单集所有音频（旁白 + 台词）

        Args:
            ep_json: 单集的 episode JSON 数据
            output_dir: 音频输出目录
            tts_client: TTS客户端（可选，不传则用默认配置）

        Returns:
            音频文件列表 [{file, size, duration_sec, role, text}, ...]
        """
        if tts_client is None:
            try:
                tts_client = TTSClient()
            except ValueError:
                print("[TTS] 未配置 MOSS_API_KEY，跳过音频合成")
                return []

        os.makedirs(output_dir, exist_ok=True)
        ep_num = ep_json.get("episode_number", "?")
        audio_files = []

        scenes = ep_json.get("scenes", [])
        for scene in scenes:
            scene_id = scene.get("scene_id", "?")
            slugline = scene.get("slugline", "")

            # 1. 合成旁白
            narration = scene.get("narration", "")
            if narration and narration.strip():
                voice = scene.get("narration_voice", "")
                rate = scene.get("narration_rate", "")
                safe_slug = "".join(c if c not in '\\/:*?"<>|' else '_' for c in slugline)[:20]
                outfile = os.path.join(output_dir, f"ep{ep_num}_scene{scene_id}_{safe_slug}_narration.mp3")

                tts_kwargs = {}
                if voice:
                    # 尝试从 voices 列表中匹配名字
                    voice_id = self._match_voice_id(tts_client, voice)
                    if voice_id:
                        tts_kwargs["voice_id"] = voice_id
                if rate:
                    try:
                        tts_kwargs["speed"] = float(rate)
                    except (ValueError, TypeError):
                        pass

                result = tts_client.synthesize(narration, outfile, **tts_kwargs)
                if result:
                    result["role"] = "旁白"
                    result["text"] = narration
                    audio_files.append(result)
                    print(f"[TTS] 旁白: {narration[:30]}... → {result['file']}")

            # 2. 合成台词
            dialogues = scene.get("dialogues", [])
            for dlg in dialogues:
                if not isinstance(dlg, dict):
                    continue
                text = dlg.get("text", "")
                if not text.strip():
                    continue
                character = dlg.get("character", "unknown")
                safe_slug = "".join(c if c not in '\\/:*?"<>|' else '_' for c in character)[:20]
                outfile = os.path.join(output_dir, f"ep{ep_num}_scene{scene_id}_{safe_slug}.mp3")

                tts_kwargs = {}
                voice = dlg.get("voice", "")
                if voice:
                    voice_id = self._match_voice_id(tts_client, voice)
                    if voice_id:
                        tts_kwargs["voice_id"] = voice_id
                rate = dlg.get("rate", "")
                if rate:
                    try:
                        tts_kwargs["speed"] = float(rate)
                    except (ValueError, TypeError):
                        pass

                result = tts_client.synthesize(text, outfile, **tts_kwargs)
                if result:
                    result["role"] = character
                    result["text"] = text
                    audio_files.append(result)
                    print(f"[TTS] {character}: {text[:30]}... → {result['file']}")

        return audio_files

    def _match_voice_id(self, tts_client: TTSClient, voice_name: str) -> Optional[str]:
        """根据声线名称匹配语音角色 ID"""
        try:
            voices = tts_client.list_voices()
            if voices:
                for v in voices:
                    if v.get("name") == voice_name:
                        return v.get("id")
        except Exception:
            pass
        return None

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
