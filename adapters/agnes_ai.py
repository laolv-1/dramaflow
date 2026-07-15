"""Agnes AI 适配器 - 对接 agnes-ai.com API"""

import asyncio
import aiohttp
from typing import Dict, Any, Optional
from adapters.base import BaseAdapter


class AgnesAIAdapter(BaseAdapter):
    """Agnes AI 服务提供商适配器"""

    NAME = "Agnes AI"
    API_BASE = "https://apihub.agnes-ai.com/v1"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("AGNES_API_KEY", "")
        if not self.api_key:
            raise ValueError("API Key未设置，请设置AGNES_API_KEY环境变量或在config.yaml中配置")

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        调用文生图API（带重试机制）
        """
        size = kwargs.get("size", "2K")
        extra_body = {"response_format": "url"}

        payload = {
            "model": "agnes-image-2.1-flash",
            "prompt": prompt,
            "extra_body": extra_body,
        }
        if kwargs.get("negative_prompt"):
            payload["negative_prompt"] = kwargs["negative_prompt"]

        max_retries = 3
        for attempt in range(max_retries):
            try:
                timeout = aiohttp.ClientTimeout(total=120)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        f"{self.API_BASE}/images/generations",
                        headers=self._get_headers(),
                        json=payload,
                    ) as resp:
                        result = await resp.json()
                        if "data" in result and len(result["data"]) > 0:
                            return {"url": result["data"][0]["url"], "model": "agnes-image-2.1-flash"}
                        elif "error" in result:
                            raise RuntimeError(f"图片生成失败: {result['error']}")
                        else:
                            raise RuntimeError(f"图片生成返回异常: {result}")
            except (aiohttp.ClientConnectionError, aiohttp.ServerDisconnectedError, asyncio.TimeoutError) as e:
                if attempt < max_retries - 1:
                    wait_time = 3 * (attempt + 1)
                    print(f"  [重试] 连接失败: {e}, {wait_time}秒后重试...")
                    await asyncio.sleep(wait_time)
                else:
                    raise RuntimeError(f"图片生成失败，已重试{max_retries}次: {e}")

    async def generate_video(self, image_url: str = "", image_path: str = "",
                              prompt: str = "", duration: int = 5) -> Dict[str, Any]:
        """
        调用图生视频API
        Args:
            image_url: 输入图片URL
            image_path: 本地图片路径（优先使用这个，会先上传）
            prompt: 运镜/动作描述（英文）
            duration: 视频时长（秒）
        Returns:
            {"url": "视频URL", "task_id": "任务ID"} 或 {"url": "视频URL"}（同步完成）
        """
        final_image_url = image_url

        # 如果有本地图片路径，先上传
        if image_path and not image_url:
            final_image_url = await self.upload_image(image_path)

        if not final_image_url and not image_path:
            raise ValueError("需要提供image_url或image_path")

        payload = {
            "model": "agnes-video-v2.0",
            "extra_body": {"response_format": "url"},
        }
        if final_image_url:
            payload["image_url"] = final_image_url
        if prompt:
            payload["prompt"] = prompt

        async with aiohttp.ClientSession() as session:
            # 提交任务
            async with session.post(
                f"{self.API_BASE}/videos",
                headers=self._get_headers(),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                result = await resp.json()

                # 情况1: 同步完成，直接返回结果
                if "data" in result and len(result["data"]) > 0:
                    return {"url": result["data"][0]["url"]}

                # 情况2: 异步任务，需要轮询
                if "task_id" in result:
                    task_id = result["task_id"]
                    video_url = await self._poll_video_task(session, task_id)
                    return {"url": video_url, "task_id": task_id}

                raise RuntimeError(f"视频生成提交失败: {result}")

    async def _poll_video_task(self, session: aiohttp.ClientSession,
                                task_id: str) -> str:
        """轮询异步视频任务"""
        import asyncio
        url = f"{self.API_BASE}/videos/{task_id}"
        max_wait = 600  # 10分钟
        interval = 10   # 10秒

        for _ in range(max_wait // interval):
            await asyncio.sleep(interval)
            async with session.get(url, headers=self._get_headers()) as resp:
                status = await resp.json()

            if status.get("status") == "completed":
                if "data" in status and len(status["data"]) > 0:
                    return status["data"][0]["url"]
                raise RuntimeError(f"视频任务完成但未返回结果: {task_id}")
            elif status.get("status") == "failed":
                raise RuntimeError(f"视频任务失败: {task_id} - {status.get('error', '未知')}")
            # status == "queued" or "in_progress"，继续等待

        raise TimeoutError(f"视频生成超时 ({max_wait}s): {task_id}")

    async def upload_image(self, image_path: str) -> str:
        """上传本地图片到Agnes AI，返回在线URL"""
        with open(image_path, "rb") as f:
            file_data = f.read()

        payload = aiohttp.FormData()
        payload.add_field("purpose", "video_input")
        payload.add_field("image", file_data, filename="image.jpg", content_type="image/jpeg")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.API_BASE}/uploads",
                headers=self._get_headers(),
                data=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                result = await resp.json()
                if "url" in result:
                    return result["url"]
                raise RuntimeError(f"图片上传失败: {result}")

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "name": self.NAME,
            "image_model": "agnes-image-2.1-flash",
            "video_model": "agnes-video-v2.0",
            "tts": "edge-tts (Microsoft)",
            "image_size": "2K",
            "video_duration": "5s",
            "video_resolution": "1280x720 (原生)",
        }
