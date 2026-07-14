"""Pipeline步骤4: TTS音频生成"""

import os
import edge_tts
from pathlib import Path
from typing import Dict, Any, List


class AudioGenerator:
    """TTS音频生成器（使用Microsoft Edge TTS）"""

    # 默认声音配置
    DEFAULT_VOICE_NARRATOR = "zh-CN-YunyangNeural"  # 男声旁白
    DEFAULT_VOICE_DIALOGUE = "zh-CN-XiaoxiaoNeural"  # 女声台词

    def __init__(self, output_dir: str, narrator_voice: str = None,
                 dialogue_voice: str = None):
        self.output_dir = Path(output_dir) / "audio"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.narrator_voice = narrator_voice or self.DEFAULT_VOICE_NARRATOR
        self.dialogue_voice = dialogue_voice or self.DEFAULT_VOICE_DIALOGUE

    async def generate_narration(self, text: str, scene_num: int,
                                  episode_num: int) -> str:
        """生成旁白音频"""
        filename = f"scene_{scene_num:02d}_narration_ep{episode_num}.wav"
        filepath = self.output_dir / filename

        print(f"[TTS] 旁白 场景{scene_num}: {text[:40]}...")

        communicate = edge_tts.Communicate(text, self.narrator_voice)
        await communicate.save(str(filepath))

        print(f"  已保存: {filepath}")
        return str(filepath)

    async def generate_dialogue(self, text: str, character: str,
                                 scene_num: int, episode_num: int) -> str:
        """生成角色台词音频"""
        filename = f"scene_{scene_num:02d}_{character}_dialogue_ep{episode_num}.wav"
        filepath = self.output_dir / filename

        print(f"[TTS] 台词 [{character}] 场景{scene_num}: {text[:40]}...")

        communicate = edge_tts.Communicate(text, self.dialogue_voice)
        await communicate.save(str(filepath))

        print(f"  已保存: {filepath}")
        return str(filepath)

    async def generate_all_audio(self, scenes: List[Dict],
                                  episode_num: int) -> Dict[str, List[str]]:
        """
        批量生成所有场景的音频
        Returns:
            {"narration": [path1, ...], "dialogue": [path1, ...]}
        """
        results = {"narration": [], "dialogue": []}

        for idx, scene in enumerate(scenes, 1):
            # 旁白
            narration_text = scene.get("narration", "")
            if narration_text:
                path = await self.generate_narration(narration_text, idx, episode_num)
                results["narration"].append(path)

            # 台词（可选）
            for line in scene.get("dialogues", []):
                text = line.get("text", "")
                char_name = line.get("character", "未知")
                if text:
                    path = await self.generate_dialogue(text, char_name, idx, episode_num)
                    results["dialogue"].append(path)

        return results
