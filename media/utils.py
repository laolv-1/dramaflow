"""虚拟路径抽象 + 输出命名 + 文件管理"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional


class VirtualPathManager:
    """
    虚拟路径抽象层
    所有文件路径统一为相对格式，后端解析为绝对路径
    解决FFmpeg字幕路径解析bug的根本方案
    """

    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir).resolve()
        self._ensure_dirs()

    def _ensure_dirs(self):
        """确保必要的目录存在"""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / "images").mkdir(exist_ok=True)
        (self.base_dir / "videos").mkdir(exist_ok=True)
        (self.base_dir / "audio").mkdir(exist_ok=True)
        (self.base_dir / "output").mkdir(exist_ok=True)
        (self.base_dir / "temp").mkdir(exist_ok=True)

    def resolve(self, virtual_path: str) -> Path:
        """
        将虚拟路径解析为绝对路径
        例如: "output/gen_20260714_0001.mp4" -> /path/to/base/output/gen_20260714_0001.mp4
        """
        return self.base_dir / virtual_path

    def to_virtual(self, absolute_path: str) -> str:
        """
        将绝对路径转为虚拟路径（用于返回给前端/上层）
        例如: /path/to/base/output/file.mp4 -> output/file.mp4
        """
        abs_path = Path(absolute_path).resolve()
        try:
            return str(abs_path.relative_to(self.base_dir))
        except ValueError:
            return absolute_path

    @property
    def images_dir(self) -> str:
        return "images"

    @property
    def videos_dir(self) -> str:
        return "videos"

    @property
    def audio_dir(self) -> str:
        return "audio"

    @property
    def output_dir(self) -> str:
        return "output"

    @property
    def temp_dir(self) -> str:
        return "temp"


class OutputFileNameGenerator:
    """
    输出文件名序列号生成器
    格式: gen_YYYYMMDD_NNNN（每日递增，天然防冲突）
    参考AI-CanvasPro的实现
    """

    def __init__(self, state_file: str = ".gen_seq_state.json"):
        self.state_file = state_file
        self._seq = {}
        self._load()

    def _load(self):
        """加载序列号状态"""
        if os.path.exists(self.state_file):
            with open(self.state_file, "r") as f:
                self._seq = json.load(f)

    def _save(self):
        """原子写入序列号状态"""
        tmp = self.state_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._seq, f)
        os.fsync(f.fileno())
        os.replace(tmp, self.state_file)  # 原子替换

    def next(self, today: Optional[str] = None) -> str:
        """
        生成下一个序列号
        Args:
            today: YYYYMMDD格式的今天日期
        Returns:
            四位数字序列号 (0001, 0002, ...)
        """
        if today is None:
            import datetime
            today = datetime.datetime.now().strftime("%Y%m%d")

        seq = self._seq.get(today, 0) + 1
        self._seq[today] = seq
        self._save()
        return f"{seq:04d}"

    def generate_filename(self, prefix: str = "gen", extension: str = ".mp4",
                           today: Optional[str] = None) -> str:
        """生成完整文件名"""
        seq = self.next(today)
        return f"{prefix}_{seq}{extension}"


class FileDeduplicator:
    """
    文件去重机制
    通过URL hash (SHA256) 做输出文件去重
    避免同一远程URL被多次下载
    """

    def __init__(self, index_file: str = "_url_index.json"):
        self.index_file = index_file
        self._index = {}
        self._load()

    def _load(self):
        if os.path.exists(self.index_file):
            with open(self.index_file, "r") as f:
                self._index = json.load(f)

    def _save(self):
        tmp = self.index_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._index, f)
        os.fsync(f.fileno())
        os.replace(tmp, self.index_file)

    def is_duplicate(self, url: str) -> bool:
        """检查URL是否已下载过"""
        import hashlib
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        return url_hash in self._index

    def record_download(self, url: str, local_path: str):
        """记录下载"""
        import hashlib
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        self._index[url_hash] = local_path
        self._save()

    def get_cached_path(self, url: str) -> Optional[str]:
        """获取缓存的文件路径"""
        import hashlib
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        return self._index.get(url_hash)
