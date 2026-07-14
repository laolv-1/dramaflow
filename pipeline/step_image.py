"""Pipeline步骤2: 图片生成（角色图 + 场景图）"""

import os
import time
from pathlib import Path
from typing import Dict, Any, List
from adapters.base import BaseAdapter


class ImageGenerator:
    """AI图片生成器 - 生成角色图和场景图"""

    def __init__(self, adapter: BaseAdapter, output_dir: str):
        self.adapter = adapter
        self.output_dir = Path(output_dir) / "images"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_character_image(self, character: Dict[str, Any],
                                        episode_num: int) -> str:
        """
        生成角色图片
        Args:
            character: {"name": "林晚晴", "prompt": "英文提示词", "variant": "重生后"}
            episode_num: 集数
        Returns:
            本地图片文件路径
        """
        prompt = character["prompt"]
        filename = f"character_{character['name']}_{character.get('variant', '')}_ep{episode_num}.jpg"
        filepath = self.output_dir / filename

        print(f"[图片生成] 角色: {character['name']} - {character.get('variant', '默认')}")
        print(f"  Prompt: {prompt[:60]}...")

        result = await self.adapter.generate_image(prompt=prompt)
        url = result["url"]

        # 下载图片到本地
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                with open(filepath, "wb") as f:
                    f.write(await resp.read())

        print(f"  已保存: {filepath}")
        return str(filepath)

    async def generate_scene_image(self, scene: Dict[str, Any],
                                    episode_num: int) -> str:
        """
        生成场景图片
        Args:
            scene: {"name": "雨夜天桥", "prompt": "英文提示词"}
        Returns:
            本地图片文件路径
        """
        prompt = scene["prompt"]
        filename = f"scene_{scene['name']}_ep{episode_num}.jpg"
        filepath = self.output_dir / filename

        print(f"[图片生成] 场景: {scene['name']}")
        print(f"  Prompt: {prompt[:60]}...")

        result = await self.adapter.generate_image(prompt=prompt)
        url = result["url"]

        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                with open(filepath, "wb") as f:
                    f.write(await resp.read())

        print(f"  已保存: {filepath}")
        return str(filepath)

    async def generate_all_images(self, episode_info: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        批量生成所有图片和场景图
        Returns:
            {"characters": [path1, path2], "scenes": [path1, path2]}
        """
        episode_num = episode_info.get("episode", 1)
        results = {"characters": [], "scenes": []}

        # 生成角色图
        for char in episode_info.get("characters", []):
            path = await self.generate_character_image(char, episode_num)
            results["characters"].append(path)
            time.sleep(1)  # 防限流

        # 生成场景图
        for scene in episode_info.get("scenes", []):
            path = await self.generate_scene_image(scene, episode_num)
            results["scenes"].append(path)
            time.sleep(1)

        return results
