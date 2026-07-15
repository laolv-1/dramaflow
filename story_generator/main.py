"""DramaFlow Story Generator - CLI自动化工作流入口

用法:
    python main.py init                                    # 初始化配置
    python main.py story "故事内容"                        # 从故事文本生成
    python main.py theme "主题" --genre "都市"             # 从主题生成
    python main.py novel "小说内容"                        # 从小说改编
    python main.py research "题材方向"                     # 调研热门榜
    python main.py generate-theme "主题" --with-research   # 调研后生成
    python main.py list                                    # 列出已生成策划案
    python main.py keys list/set/validate                  # 管理API Key
"""

import argparse
import json
import sys
from pathlib import Path

# 添加项目根目录到PATH
sys.path.insert(0, str(Path(__file__).parent))

from generator import EpisodeGenerator
from trend_researcher import TrendResearcher
from key_manager import KeyManager


def cmd_init(args):
    """初始化配置"""
    km = KeyManager()
    print("[初始化] 配置管理器")
    print(f"\n当前API Key状态:")
    for provider, status in km.list_providers().items():
        icon = "[OK]" if status else "[NO]"
        print(f"  {icon} {provider}")

    print(f"\n请输入你的 DeepSeek API Key:")
    print(f"(可在 https://platform.deepseek.com/api_keys 获取)")
    api_key = input("> ").strip()
    if api_key:
        km.set_key("deepseek", api_key)
        print("[OK] DeepSeek API Key 已保存")

    print(f"\n请输入你的 Agnes AI API Key:")
    print(f"(已在 .env 中设置的可跳过)")
    agnes_key = input("> ").strip()
    if agnes_key:
        km.set_key("agnes", agnes_key)
        print("[OK] Agnes AI API Key 已保存")


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

    print(f"[OK] 策划案已保存到: {filepath}")
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

    _save_result(result)
    _print_summary(result)


def _save_result(result: dict):
    """保存策划案到output目录"""
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    title = result.get("project", {}).get("title", "unnamed")
    import re as _re
    safe_title = _re.sub(r'[\\/:*?"<>|]', '_', str(title))
    import time
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{safe_title}.json"
    filepath = output_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[OK] 策划案已保存到: {filepath}")
    return filepath


def _print_summary(result: dict):
    """打印策划案摘要"""
    project = result.get("project", {})
    chars = result.get("characters", [])
    eps = result.get("episodes", [])
    scenes_total = sum(len(ep.get("scenes", [])) for ep in eps)

    print(f"\n策划案摘要:")
    print(f"  剧名: {project.get('title', '未知')}")
    print(f"  题材: {project.get('genre', '-')}")
    print(f"  角色数: {len(chars)}")
    print(f"  分集数: {len(eps)}")
    print(f"  总场景数: {scenes_total}")


def cmd_novel(args):
    """从小说章节改编策划案"""
    novel_text = args.novel
    if not novel_text:
        print("[错误] 请提供小说内容")
        sys.exit(1)

    print(f"[Novel Adapter] 正在从小说改编策划案...")
    print(f"  内容: {novel_text[:80]}...")

    gen = EpisodeGenerator(model="deepseek-v4-flash", thinking_enabled=False)

    result = gen.generate_from_novel(novel_chapter=novel_text)

    _save_result(result)
    _print_summary(result)


def cmd_research(args):
    """调研热门榜"""
    idea = args.idea if hasattr(args, 'idea') and args.idea else ""
    print(f"[Trend Researcher] 开始调研...")
    if idea:
        print(f"  用户方向: {idea}")

    researcher = TrendResearcher(config_dir=str(Path(__file__).parent))
    result = researcher.research(user_idea=idea, use_deepseek=True)

    print("\n[调研完成]")
    local = result.get("local_analysis", {})
    print(f"  数据源: {local.get('sources_covered', 0)}/{local.get('total_sources', 0)}")
    print(f"  热门关键词TOP5:")
    for kw in local.get("hot_keywords", [])[:5]:
        print(f"    - {kw['keyword']}: {kw['frequency']}次")

    insight = result.get("deepseek_insight", {})
    if insight and isinstance(insight, dict):
        raw = insight.get("raw_insight", "")
        if raw:
            print("\n[趋势摘要]")
            # 过滤emoji避免GBK编码问题
            clean_raw = "".join(c for c in raw if ord(c) < 128 or c.isascii())
            print(clean_raw[:500])
            print("...")


def cmd_generate_with_research(args):
    """调研后基于结果生成策划案"""
    theme = args.theme
    if not theme:
        print("[错误] 请提供故事主题")
        sys.exit(1)

    print(f"[Research + Generate] 开始调研热门榜...")

    # Step 1: 调研
    researcher = TrendResearcher(config_dir=str(Path(__file__).parent))
    research_result = researcher.research(user_idea=theme, use_deepseek=True)

    # Step 2: 基于调研生成
    print(f"\n[Story Generator] 基于调研结果生成策划案...")
    genre = getattr(args, 'genre', '玄幻修仙') or '玄幻修仙'

    gen = EpisodeGenerator(model="deepseek-v4-flash", thinking_enabled=False)
    result = gen.generate_with_research(
        theme=theme,
        genre=genre,
        research_result=research_result,
    )

    _save_result(result)
    _print_summary(result)


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
            print(f"[OK] {provider} API Key 已保存")
        except ValueError as e:
            print(f"[错误] {e}")

    elif args.action == "validate":
        results = km.validate_keys()
        print("\n验证结果:")
        for provider, valid in results.items():
            icon = "[OK]" if valid else "[NO]"
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

    # novel 命令 - 从小说改编
    novel_parser = subparsers.add_parser("novel", help="从小说章节改编策划案")
    novel_parser.add_argument("novel", type=str, help="小说章节内容")

    # theme 命令
    theme_parser = subparsers.add_parser("theme", help="从主题生成策划案")
    theme_parser.add_argument("theme", type=str, help="故事主题")
    theme_parser.add_argument("--genre", type=str, default="玄幻修仙", help="题材类型")

    # research 命令 - 调研热门榜
    research_parser = subparsers.add_parser("research", help="调研短剧热门榜")
    research_parser.add_argument("idea", type=str, nargs="?", default="", help="用户题材方向（可选）")

    # generate-with-research 命令 - 调研后生成
    gr_parser = subparsers.add_parser("generate-with-research", help="调研热门榜后基于结果生成策划案")
    gr_parser.add_argument("theme", type=str, help="故事主题")
    gr_parser.add_argument("--genre", type=str, default="玄幻修仙", help="题材类型")

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
    elif args.command == "novel":
        cmd_novel(args)
    elif args.command == "theme":
        cmd_theme(args)
    elif args.command == "research":
        cmd_research(args)
    elif args.command == "generate-with-research":
        cmd_generate_with_research(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "keys":
        cmd_keys(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
