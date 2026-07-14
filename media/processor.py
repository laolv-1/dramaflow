"""FFmpeg/Pillow媒体处理封装"""

import subprocess
import os
from pathlib import Path
from typing import Optional, Tuple, Dict, Any


class FFmpegProcessor:
    """轻量级FFmpeg封装，解决路径问题的虚拟路径方案"""

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg = ffmpeg_path
        self.ffprobe = self._find_ffprobe()

    def _find_ffprobe(self) -> str:
        """查找ffprobe"""
        # 同ffmpeg路径
        if os.path.dirname(self.ffmpeg):
            base = os.path.dirname(self.ffmpeg)
            candidate = os.path.join(base, "ffprobe.exe" if self.ffmpeg.endswith(".exe") else "ffprobe")
            if os.path.exists(candidate):
                return candidate
        return "ffprobe"

    def probe(self, video_path: str) -> Dict[str, Any]:
        """
        查询视频信息
        Returns: {duration, width, height, fps, has_audio}
        """
        cmd = [
            self.ffprobe, "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate",
            "-show_entries", "format=duration",
            "-of", "json",
            video_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                encoding="utf-8", errors="replace")
        if result.returncode != 0:
            return {}

        data = eval(result.stdout)  # 简单解析
        streams = data.get("streams", [{}])[0]
        fmt = data.get("format", {})

        # 解析FPS
        fps = 30
        fr = streams.get("r_frame_rate", "")
        if "/" in fr:
            num, den = fr.split("/")
            fps = int(num) / int(den) if int(den) > 0 else 30

        avg_fr = streams.get("avg_frame_rate", "")
        if "/" in avg_fr:
            num, den = avg_fr.split("/")
            avg_fps = int(num) / int(den) if int(den) > 0 else fps
            if avg_fps > 0:
                fps = avg_fps

        duration = float(fmt.get("duration", 0))

        return {
            "width": streams.get("width", 0),
            "height": streams.get("height", 0),
            "fps": fps,
            "duration": duration,
            "has_audio": False,  # 需要另外检测
        }

    def probe_audio(self, video_path: str) -> bool:
        """检测视频是否有音频轨"""
        cmd = [
            self.ffprobe, "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "default=nw=1:nk=1",
            video_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                encoding="utf-8", errors="replace")
        return "audio" in result.stdout

    def get_duration(self, video_path: str) -> float:
        """获取视频时长（秒）"""
        cmd = [
            self.ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1",
            video_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                encoding="utf-8", errors="replace")
        return float(result.stdout.strip()) if result.returncode == 0 else 0


class ImageProcessor:
    """Pillow图片处理封装"""

    @staticmethod
    def resize_keep_aspect(path: str, max_width: int, max_height: int,
                            output_path: Optional[str] = None) -> str:
        """等比例缩放图片"""
        from PIL import Image
        img = Image.open(path)
        ratio = min(max_width / img.width, max_height / img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)

        if output_path is None:
            base, ext = os.path.splitext(path)
            output_path = f"{base}_resized{ext}"

        img.save(output_path, quality=85)
        return output_path

    @staticmethod
    def to_jpg(path: str, output_path: str) -> str:
        """转换为JPEG格式（处理PNG透明度等）"""
        from PIL import Image
        img = Image.open(path)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(output_path, "JPEG", quality=90)
        return output_path

    @staticmethod
    def get_info(path: str) -> Dict[str, Any]:
        """获取图片信息"""
        from PIL import Image
        img = Image.open(path)
        return {
            "width": img.width,
            "height": img.height,
            "format": img.format,
            "mode": img.mode,
        }
