"""Pipeline步骤1: 文本生成/解析"""

import yaml
import json
from pathlib import Path
from typing import Dict, Any, List, Optional


class EpisodeParser:
    """解析策划案/剧集数据，提取场景和角色信息"""

    def __init__(self, episode_info: Dict[str, Any]):
        """
        Args:
            episode_info: 剧集信息字典，格式参考episode_workflow_ep1.py中的EPISODE_INFO
        """
        self.info = episode_info

    def get_scenes(self) -> List[Dict[str, Any]]:
        """获取场景列表"""
        return self.info.get("scenes", [])

    def get_characters(self) -> List[Dict[str, Any]]:
        """获取角色列表"""
        return self.info.get("characters", [])

    def get_episode_number(self) -> int:
        return self.info.get("episode", 1)

    def get_title(self) -> str:
        return self.info.get("title", f"第{self.get_episode_number()}集")


def load_episode_from_file(filepath: str) -> EpisodeParser:
    """从JSON或YAML文件加载剧集信息"""
    path = Path(filepath)
    if path.suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif path.suffix in (".yaml", ".yml"):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    else:
        raise ValueError(f"不支持的文件格式: {path.suffix}")

    return EpisodeParser(data)


def build_episode_info(episode_num: int, title: str, scenes: List[Dict],
                        characters: List[Dict]) -> Dict[str, Any]:
    """构建剧集信息字典"""
    return {
        "episode": episode_num,
        "title": title,
        "scenes": scenes,
        "characters": characters,
    }
