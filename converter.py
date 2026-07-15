"""策划案转换器 - 将 story_generator 输出的 JSON 转换为 DramaFlow pipeline 输入格式

story_generator 输出:
  {"project": {...}, "characters": [...], "episodes": [{"episode_number": 1, "scenes": [...]}]}

DramaFlow pipeline 期望:
  {"episode": 1, "title": "...", "characters": [{"name": "...", "prompt": "..."}], "scenes": [{"name": "...", "prompt": "..."}]}
"""

import re
import json
from pathlib import Path
from typing import Dict, Any, List


def chinese_to_snake(name: str) -> str:
    """将中文名转换为英文snake_case标识符"""
    # 如果已经是英文snake_case，直接返回
    if re.match(r'^[a-z][a-z0-9_]*$', name):
        return name
    # 中文名保留原始字符串作为key前缀，但用下划线连接
    cleaned = re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')
    return cleaned.lower()


def convert_story_generator_json(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 story_generator 的 episode_XXX.json 格式转换为 DramaFlow pipeline 格式
    """
    # 提取第一集数据
    episodes = input_data.get("episodes", [])
    if not episodes:
        raise ValueError("策划案中未发现 episodes 字段")

    episode_data = episodes[0]
    project = input_data.get("project", {})

    # 转换角色列表
    converted_characters = []
    for char in input_data.get("characters", []):
        char_name = char.get("name", "unknown")
        snake_name = chinese_to_snake(char_name)
        variant = char.get("variants", {}).get("默认", {})

        # 取第一个变体的 image_prompt，或使用主 image_prompts
        image_prompt = char.get("image_prompts", "")
        if char.get("variants"):
            # 取第一个可用的变体
            first_variant_name = next(iter(char["variants"]))
            first_variant = char["variants"][first_variant_name]
            if isinstance(first_variant, dict):
                image_prompt = first_variant.get("image_prompt", image_prompt)
            else:
                image_prompt = first_variant

        converted_char = {
            "name": snake_name,
            "variant": first_variant_name if char.get("variants") else "默认",
            "prompt": image_prompt,
            # 保留原始中文名用于音频生成
            "_chinese_name": char_name,
        }
        converted_characters.append(converted_char)

    # 转换场景列表
    converted_scenes = []
    for idx, scene in enumerate(episode_data.get("scenes", []), 1):
        scene_name = scene.get("name", f"scene_{idx}")

        # 构建对话列表（兼容已有格式）
        dialogues = []
        for d in scene.get("dialogues", []):
            dialogue = {
                "character": d.get("character", "未知"),
                "text": d.get("text", ""),
            }
            # 保留TTS参数但不影响pipeline
            if "rate" in d:
                dialogue["rate"] = d["rate"]
            if "pitch" in d:
                dialogue["pitch"] = d["pitch"]
            dialogues.append(dialogue)

        converted_scene = {
            "name": scene_name,
            "prompt": scene.get("image_prompt", ""),
            "video_prompt": scene.get("video_prompt", ""),
            "narration": scene.get("narration", ""),
            "dialogues": dialogues,
            "duration": scene.get("duration", 5),
            # 保留额外信息用于字幕生成
            "_slugline": scene.get("slugline", ""),
            "_location": scene.get("location", ""),
            "_time": scene.get("time", "day"),
            "_weather": scene.get("weather", ""),
            "_mood": scene.get("mood", ""),
            "_transition": scene.get("transition", "cut"),
        }
        converted_scenes.append(converted_scene)

    result = {
        "episode": episode_data.get("episode_number", 1),
        "title": episode_data.get("title", f"第1集"),
        "genre": project.get("genre", ""),
        "logline": project.get("logline", ""),
        "characters": converted_characters,
        "scenes": converted_scenes,
    }

    return result


def convert_json_file(json_path: str) -> Dict[str, Any]:
    """从文件路径读取并转换"""
    path = Path(json_path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return convert_story_generator_json(data)


def convert_and_save(input_path: str, output_path: str = None):
    """转换并保存到指定文件"""
    converted = convert_json_file(input_path)

    if output_path is None:
        # 默认保存到同目录下的 converted_XXX.json
        p = Path(input_path)
        output_path = str(p.parent / f"converted_{p.stem}.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(converted, f, ensure_ascii=False, indent=2)

    return output_path, converted


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python converter.py <input.json> [output.json]")
        print("示例: python converter.py story_generator/output/episode_001.json")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"[Converter] 读取: {input_file}")
    output_path, data = convert_and_save(input_file, output_file)
    print(f"[Converter] 已保存: {output_path}")
    print(f"[Converter] 角色数: {len(data['characters'])}")
    print(f"[Converter] 场景数: {len(data['scenes'])}")
    print(f"[Converter] 集数: {data['episode']} - {data['title']}")
