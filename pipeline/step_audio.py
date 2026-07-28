"""Pipeline步骤4: TTS音频生成（已迁移至 Mossland TTS）"""

import os
import urllib.request
import urllib.error
import json
from pathlib import Path
from typing import Dict, Any, List
import asyncio


def get_api_key_from_env():
    """从环境变量获取 MOSS_API_KEY"""
    key = os.environ.get("MOSS_API_KEY")
    if key:
        return key

    # 确定项目根目录
    base_dir = Path(__file__).parent.parent

    # 搜索 .env_moss（多个位置，按优先级排序）
    env_moss_search_paths = [
        base_dir / "story_generator" / ".env_moss",  # story_generator/.env_moss
        base_dir / ".env_moss",                      # 项目根/.env_moss
        str(base_dir.parent / ".env_moss"),          # 上级目录
        str(Path.home() / ".moss_tts_key.txt"),      # 用户主目录
    ]

    for p in env_moss_search_paths:
        path_obj = Path(p) if isinstance(p, str) else Path(p)
        if path_obj.exists():
            with open(path_obj, "r", encoding="utf-8") as f:
                content = f.read()
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("MOSS_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"\'')
                        if key:
                            return key

    # 尝试从通用 .env 读取
    env_search_paths = [
        base_dir / ".env",                           # 项目根/.env
        base_dir / "story_generator" / ".env",       # story_generator/.env
    ]

    for env_path in env_search_paths:
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("MOSS_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"\'')

    return None


class AudioGenerator:
    """TTS音频生成器（使用Mossland TTS）"""

    # 默认配置
    API_BASE = "https://api.mosi.cn/v1/audio"

    def __init__(self, output_dir: str, narrator_voice_id: str = None,
                 dialogue_voice_id: str = None, speed: float = None):
        self.output_dir = Path(output_dir) / "audio"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 首先获取 API Key
        api_key = get_api_key_from_env()
        if not api_key:
            raise RuntimeError("未找到MOSS_API_KEY，请设置环境变量或在.env_moss文件中配置")

        self.api_key = api_key

        # 加载语音配置：从 .env_moss > API 默认 > 硬编码 fallback
        default_voice_id = "cfff6856-8f17-4eaf-aed6-e1ff99d7241c"  # 萧逸，Mossland 默认
        default_speed = 1.2

        # 优先读取 .env_moss 中的配置
        config_paths = [
            Path(__file__).parent.parent / "story_generator" / ".env_moss",
            Path(__file__).parent.parent / ".env_moss",
        ]
        for cfg_path in config_paths:
            if cfg_path.exists():
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("TTS_VOICE_ID="):
                                v = line.split("=", 1)[1].strip().strip('"\'')
                                if v:
                                    default_voice_id = v
                            if line.startswith("TTS_SPEED="):
                                s = line.split("=", 1)[1].strip()
                                if s:
                                    default_speed = float(s)
                except Exception:
                    pass

        # 其次尝试通过 API 获取可用语音列表
        try:
            url = f"{self.API_BASE}/voices"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))
            voices = data.get("data", [])
            if voices:
                default_voice_id = voices[0].get("id", default_voice_id)
        except Exception:
            pass

        # 最终确定语音和语速
        self.narrator_voice_id = narrator_voice_id or default_voice_id
        self.dialogue_voice_id = dialogue_voice_id or default_voice_id
        self.speed = speed or default_speed

        print(f"[TTS] AudioGenerator 初始化成功")
        print(f"  Voice ID: {self.narrator_voice_id[:12]}...")
        print(f"  Speed: {self.speed}x")

    def _synthesize(self, text: str, voice_id: str, output_file: str) -> Dict[str, Any]:
        """调用Mossland TTS API合成音频"""
        url = f"{self.API_BASE}/speech"

        payload = {
            "model": "moss-tts",
            "input": text,
            "voice_id": voice_id,
            "speed": self.speed,
        }

        print(f"[TTS] 合成文本长度: {len(text)} 字, 语音角色: {voice_id[:12]}...")

        try:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            })

            with urllib.request.urlopen(req, timeout=60) as resp:
                audio_data = resp.read()

            with open(output_file, "wb") as f:
                f.write(audio_data)

            duration_bytes = len(audio_data)
            est_duration_sec = duration_bytes * 8 / 96000

            print(f"  已保存: {output_file} ({est_duration_sec:.1f}s, {len(audio_data)/1024:.1f}KB)")
            return {
                "file": str(output_file),
                "size": len(audio_data),
                "duration_sec": est_duration_sec,
            }

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            raise RuntimeError(f"Mossland TTS API错误 {e.code}: {err_body[:500]}")
        except Exception as e:
            raise RuntimeError(f"Mossland TTS请求失败: {str(e)}")

    async def generate_narration(self, text: str, scene_num: int,
                                 episode_num: int) -> str:
        """生成旁白音频（使用旁白语音角色）"""
        filename = f"scene_{scene_num:02d}_narration_ep{episode_num}.mp3"
        filepath = self.output_dir / filename

        print(f"[TTS] 旁白 场景{scene_num}: {text[:40]}...")

        result = await asyncio.to_thread(
            self._synthesize, text, self.narrator_voice_id, str(filepath)
        )

        return result["file"]

    async def generate_dialogue(self, text: str, character: str,
                                scene_num: int, episode_num: int) -> str:
        """生成角色台词音频（使用角色语音角色）"""
        filename = f"scene_{scene_num:02d}_{character}_dialogue_ep{episode_num}.mp3"
        filepath = self.output_dir / filename

        print(f"[TTS] 台词 [{character}] 场景{scene_num}: {text[:40]}...")

        result = await asyncio.to_thread(
            self._synthesize, text, self.dialogue_voice_id, str(filepath)
        )

        return result["file"]

    async def generate_all_audio(self, scenes: List[Dict],
                                  episode_num: int) -> Dict[str, List[str]]:
        """
        批量生成所有场景的音频
        Returns:
            {"narration": [path1, ...], "dialogue": [path1, ...]}
        """
        results = {"narration": [], "dialogue": []}

        async def process_task(coro):
            try:
                return await coro
            except Exception as e:
                print(f"[错误] 音频生成失败: {e}")
                return None

        tasks = []

        for idx, scene in enumerate(scenes, 1):
            narration_text = scene.get("narration", "")
            if narration_text:
                task = self.generate_narration(narration_text, idx, episode_num)
                tasks.append(task)

            for line in scene.get("dialogues", []):
                text = line.get("text", "")
                char_name = line.get("character", "未知")
                if text:
                    task = self.generate_dialogue(text, char_name, idx, episode_num)
                    tasks.append(task)

        responses = await asyncio.gather(*tasks, return_exceptions=False)

        for res in responses:
            if res:
                if "_narration_" in res:
                    results["narration"].append(res)
                elif "_dialogue_" in res:
                    results["dialogue"].append(res)

        return results
