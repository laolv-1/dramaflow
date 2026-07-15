"""DramaFlow Story Generator - CLI入口

用法:
    python -m story_generator.main init              # 初始化配置
    python -m story_generator.main story "故事内容"  # 从故事文本生成
    python -m story_generator.main theme "主题" --genre "都市"  # 从主题生成
    python -m story_generator.main list              # 列出已生成策划案
"""

import argparse
import json
import sys
from pathlib import Path

# 添加项目根目录到PATH
sys.path.insert(0, str(Path(__file__).parent))

from generator import EpisodeGenerator
from key_manager import KeyManager


def cmd_init(args):
    """初始化配置"""
    km = KeyManager()
    print("[初始化] 配置管理器")
    print(f"\n当前API Key状态:")
    for provider, status in km.list_providers().items():
        icon = "✅" if status else "❌"
        print(f"  {icon} {provider}")

    print(f"\n请输入你的 DeepSeek API Key:")
    print(f"(可在 https://platform.deepseek.com/api_keys 获取)")
    api_key = input("> ").strip()
    if api_key:
        km.set_key("deepseek", api_key)
        print("✅ DeepSeek API Key 已保存")

    print(f"\n请输入你的 Agnes AI API Key:")
    print(f"(已在 .env 中设置的可跳过)")
    agnes_key = input("> ").strip()
    if agnes_key:
        km.set_key("agnes", agnes_key)
        print("✅ Agnes AI API Key 已保存")


def cmd_story(args):
    """从故事文本生成策划案"""
    story_text = args.story
    if not story_text:
        print("[错误] 请提供故事文本")
        sys.exit(1)

    print(f"[Story Generator] 正在生成策划案...")
    print(f"  故事: {story_text[:50]}...")

    gen = EpisodeGenerator(model="deepseek-v4-flash", thinking_enabled=False)

    result = gen.generate_from_story(story_text=story_text)

    # 保存到output目录
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    episode_num = result.get("episode", 1)
    filename = f"episode_{episode_num:03d}.json"
    filepath = output_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 策划案已保存到: {filepath}")
    print(f"  角色数: {len(result.get('characters', []))}")
    print(f"  场景数: {len(result.get('scenes', []))}")


def cmd_theme(args):
    """从主题生成策划案"""
    theme = args.theme
    if not theme:
        print("[错误] 请提供故事主题")
        sys.exit(1)

    print(f"[Story Generator] 正在生成策划案...")
    print(f"  主题: {theme}")
    print(f"  题材: {args.genre}")

    gen = EpisodeGenerator(model="deepseek-v4-flash", thinking_enabled=False)

    result = gen.generate_from_theme(theme=theme, genre=args.genre)

    # 保存到output目录
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    episode_num = result.get("episode", 1)
    filename = f"episode_{episode_num:03d}.json"
    filepath = output_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 策划案已保存到: {filepath}")
    print(f"  角色数: {len(result.get('characters', []))}")
    print(f"  场景数: {len(result.get('scenes', []))}")


def cmd_list(args):
    """列出已生成的策划案"""
    output_dir = Path(__file__).parent / "output"
    if not output_dir.exists():
        print("暂无已生成的策划案")
        return

    files = sorted(output_dir.glob("episode_*.json"))
    if not files:
        print("暂无已生成的策划案")
        return

    print(f"\n已生成的策划案 ({len(files)}个):")
    for f in files:
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        title = data.get("title", "未知")
        chars = len(data.get("characters", []))
        scenes = len(data.get("scenes", []))
        print(f"  {f.name} - {title} ({chars}角色, {scenes}场景)")


def cmd_keys(args):
    """管理API Key"""
    km = KeyManager()
    print("[API Key 管理]")

    if args.action == "list":
        print("\n当前状态:")
        for provider, status in km.list_providers().items():
            icon = "✅" if status else "❌"
            print(f"  {icon} {provider}")

    elif args.action == "set":
        provider = args.provider
        key = args.key
        try:
            km.set_key(provider, key)
            print(f"✅ {provider} API Key 已保存")
        except ValueError as e:
            print(f"[错误] {e}")

    elif args.action == "validate":
        results = km.validate_keys()
        print("\n验证结果:")
        for provider, valid in results.items():
            icon = "✅" if valid else "❌"
            print(f"  {icon} {provider}")


def main():
    parser = argparse.ArgumentParser(
        description="DramaFlow Story Generator - AI短剧策划案自动生成工具"
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # init 命令
    subparsers.add_parser("init", help="初始化配置")

    # story 命令
    story_parser = subparsers.add_parser("story", help="从故事文本生成策划案")
    story_parser.add_argument("story", type=str, help="故事文本")

    # theme 命令
    theme_parser = subparsers.add_parser("theme", help="从主题生成策划案")
    theme_parser.add_argument("theme", type=str, help="故事主题")
    theme_parser.add_argument("--genre", type=str, default="都市", help="题材类型")

    # list 命令
    subparsers.add_parser("list", help="列出已生成的策划案")

    # keys 命令
    keys_parser = subparsers.add_parser("keys", help="管理API Key")
    keys_parser.add_argument("action", choices=["list", "set", "validate"],
                              help="操作: list/set/validate")
    keys_parser.add_argument("--provider", type=str, help="服务商名称（set时需要）")
    keys_parser.add_argument("--key", type=str, help="API Key（set时需要）")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "story":
        cmd_story(args)
    elif args.command == "theme":
        cmd_theme(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "keys":
        cmd_keys(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
