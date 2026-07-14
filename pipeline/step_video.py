"""Pipeline步骤3: 图生视频"""

import time
import hashlib
from pathlib import Path
from typing import Dict, Any, List
from adapters.base import BaseAdapter


class VideoGenerator:
    """图生视频生成器"""

    def __init__(self, adapter: BaseAdapter, output_dir: str, delay: float = 2.0):
        self.adapter = adapter
        self.output_dir = Path(output_dir) / "videos"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.delay = delay  # 防限流间隔

    def _make_filename(self, scene_name: str, episode_num: int) -> str:
        """生成唯一文件名（基于场景名hash，避免重复）"""
        hash_str = f"{episode_num}_{scene_name}_{time.time()}"
        short_hash = hashlib.md5(hash_str.encode()).hexdigest()[:8]
        return f"ep{episode_num}_{short_hash}.mp4"

    async def generate_scene_video(self, scene: Dict[str, Any],
                                    image_path: str,
                                    episode_num: int) -> str:
        """
        生成单个场景的视频
        Args:
            scene: {"name": "雨夜天桥", "video_prompt": "运镜描述"}
            image_path: 输入图片路径（场景图或角色+场景的合成图）
            episode_num: 集数
        Returns:
            本地视频文件路径
        """
        filename = self._make_filename(scene["name"], episode_num)
        filepath = self.output_dir / filename

        prompt = scene.get("video_prompt", "")
        print(f"[视频生成] 场景: {scene['name']}")
        print(f"  图片: {Path(image_path).name}")
        print(f"  运镜: {prompt[:60] if prompt else '(无)'}...")

        result = await self.adapter.generate_video(
            image_path=image_path,
            prompt=prompt,
            duration=scene.get("duration", 5),
        )

        # 下载视频
        import aiohttp
        video_url = result["url"]
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url) as resp:
                with open(filepath, "wb") as f:
                    f.write(await resp.read())

        print(f"  已保存: {filepath}")
        return str(filepath)

    async def generate_all_videos(self, scenes: List[Dict],
                                   image_map: Dict[str, str],
                                   episode_num: int) -> List[str]:
        """
        批量生成所有场景视频
        Args:
            scenes: 场景列表
            image_map: {scene_name: image_path} 场景名到图片路径的映射
            episode_num: 集数
        Returns:
            视频文件路径列表
        """
        video_paths = []

        for scene in scenes:
            name = scene["name"]
            if name not in image_map:
                print(f"  [警告] 场景 '{name}' 没有对应的图片，跳过")
                continue

            video_path = await self.generate_scene_video(scene, image_map[name], episode_num)
            video_paths.append(video_path)
            time.sleep(self.delay)  # 防限流

        return video_paths
