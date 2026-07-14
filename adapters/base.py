# 适配器基类
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseAdapter(ABC):
    """所有AI服务提供商适配器的基类"""

    @abstractmethod
    async def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """生成图片"""
        pass

    @abstractmethod
    async def generate_video(self, image_url: str, prompt: str = "", **kwargs) -> Dict[str, Any]:
        """生成视频（图生视频）"""
        pass

    @abstractmethod
    async def upload_image(self, image_path: str) -> str:
        """上传本地图片，返回在线URL"""
        pass

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """返回模型能力信息"""
        pass
