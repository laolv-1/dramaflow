"""Short Drama Tool - CLI入口

用法:
    python -m main.py episode 2              # 生成第2集
    python -m main.py episode 2 --dry-run    # 预览模式（不调用API）
    python -m main.py episode 2 --skip-image # 跳过图片生成
    python -m main.py episode 2 --skip-video # 跳过视频生成
"""

import argparse
import asyncio
import os
import sys
import json
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()  # 自动加载 .env 文件
except ImportError:
    pass  # 没有python-dotenv则跳过

# 添加项目根目录到PATH
sys.path.insert(0, str(Path(__file__).parent))

from adapters.agnes_ai import AgnesAIAdapter
from pipeline.step_text import EpisodeParser, build_episode_info
from pipeline.step_image import ImageGenerator
from pipeline.step_video import VideoGenerator
from pipeline.step_audio import AudioGenerator
from pipeline.step_synthesize import VideoSynthesizer
from media.utils import VirtualPathManager, OutputFileNameGenerator


def parse_args():
    parser = argparse.ArgumentParser(description="Short Drama Tool - 云端自动化短剧工作流")
    parser.add_argument("command", choices=["episode"], help="命令")
    parser.add_argument("episode_num", type=int, help="集数")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不调用API")
    parser.add_argument("--skip-image", action="store_true", help="跳过图片生成")
    parser.add_argument("--skip-video", action="store_true", help="跳过视频生成")
    parser.add_argument("--skip-audio", action="store_true", help="跳过音频生成")
    parser.add_argument("--skip-synthesize", action="store_true", help="跳过视频合成")
    parser.add_argument("--config", type=str, default=None, help="配置文件路径")
    parser.add_argument("--output-dir", type=str, default=None, help="输出目录")
    parser.add_argument("--json", type=str, default=None, help="策划案JSON文件路径（覆盖 --episode）")
    return parser.parse_args()


def load_config(config_path: str = None) -> dict:
    """加载配置"""
    default_config = {
        "api_base": "https://apihub.agnes-ai.com/v1",
        "image_model": "agnes-image-2.1-flash",
        "video_model": "agnes-video-v2.0",
        "output_dir": "./output",
        "asset_dir": "./assets",
        "target_resolution": "1080x1920",
        "video_duration": 5,
        "fps": 25,
        "narrator_voice": "zh-CN-YunyangNeural",
        "dialogue_voice": "zh-CN-XiaoxiaoNeural",
        "request_delay": 2,
    }

    if config_path and os.path.exists(config_path):
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f)
        if user_config:
            default_config.update(user_config)

    return default_config


def get_sample_episode_info(episode_num: int) -> dict:
    """
    获取示例剧集信息（用于dry-run测试）
    实际使用时应从策划案或JSON文件加载
    """
    return {
        "episode": episode_num,
        "title": f"第{episode_num}集",
        "characters": [
            {
                "name": "lin_wanqing",
                "variant": "重生后",
                "prompt": (
                    "Chinese woman, early 20s, short black hair, professional black suit, "
                    "sharp determined eyes, cold lighting, cinematic composition, "
                    "realistic movie style, dark color tone, close-up portrait"
                ),
            },
            {
                "name": "zhao_mingxuan",
                "variant": "反派",
                "prompt": (
                    "Chinese man, early 30s, wearing suit and gold-rimmed glasses, "
                    "sinister smile, dimly lit office background, cinematic lighting, "
                    "realistic movie style, dark color tone, medium shot"
                ),
            },
            {
                "name": "su_ting",
                "variant": "绿茶闺蜜",
                "prompt": (
                    "Chinese woman, early 20s, pink outfit, sweet deceptive smile, "
                    "soft lighting, realistic movie style, close-up portrait"
                ),
            },
        ],
        "scenes": [
            {
                "name": "rainy_bridge",
                "prompt": (
                    "Rainy night, pedestrian bridge, Chinese woman in white dress "
                    "standing alone, heavy rain, city lights blurred in background, "
                    "cold blue tone, cinematic wide shot, dramatic atmosphere"
                ),
                "video_prompt": "Slow zoom in, camera shaking slightly, rain drops visible",
                "narration": "雨夜的天桥上，林晚晴独自一人站在栏杆边，冰冷的雨水打湿了她白色的连衣裙。",
                "dialogues": [],
            },
            {
                "name": "hospital_room",
                "prompt": (
                    "Hospital room, fluorescent lighting, Chinese woman waking up on hospital bed, "
                    "confused expression, medical equipment in background, "
                    "cold clinical tone, realistic movie style"
                ),
                "video_prompt": "Camera pans from ceiling to the woman's face",
                "narration": "她在一间医院病房里惊醒，心跳如鼓，镜子里的自己竟然回到了三年前。",
                "dialogues": [],
            },
            {
                "name": "dorm_room",
                "prompt": (
                    "University dormitory room, warm lighting, Chinese woman looking at her phone screen, "
                    "shocked expression on face, text messages visible on screen, "
                    "realistic movie style, medium shot"
                ),
                "video_prompt": "Close up on phone screen, then pan to shocked face",
                "narration": "手机屏幕上，是未婚夫和闺蜜的聊天记录——那些她死前从未发现的秘密。",
                "dialogues": [
                    {"character": "苏婷", "text": "你以为他真爱你？不过是个提款机罢了。"},
                ],
            },
        ],
    }


async def run_pipeline(adapter: AgnesAIAdapter, episode_info: dict,
                       vpath: VirtualPathManager, args: argparse.Namespace):
    """执行完整流水线"""
    episode_num = episode_info["episode"]
    dry_run = args.dry_run

    # 初始化变量
    video_paths = []
    all_audio = []

    print(f"\n{'='*60}")
    print(f"  Short Drama Tool - 第{episode_num}集")
    print(f"  {'[预览模式]' if dry_run else '[执行模式]'}")
    print(f"{'='*60}\n")

    # Step 1: 生成角色图片
    if not args.skip_image:
        print("[Step 1/4] 生成角色图片...")
        image_gen = ImageGenerator(adapter, vpath.resolve(vpath.images_dir).parent)

        character_paths = []
        for char in episode_info.get("characters", []):
            if dry_run:
                print(f"  [DRY-RUN] 将生成角色: {char['name']}")
                print(f"  [DRY-RUN] Prompt: {char['prompt'][:60]}...")
                character_paths.append(f"[DRY-RUN] character_{char['name']}.jpg")
            else:
                path = await image_gen.generate_character_image(char, episode_num)
                character_paths.append(path)
            await asyncio.sleep(2)  # 防限流

        print()

    # Step 2: 生成场景图片
    if not args.skip_image:
        print("[Step 2/4] 生成场景图片...")
        image_gen = ImageGenerator(adapter, vpath.resolve(vpath.images_dir).parent)

        scene_paths = {}
        for scene in episode_info.get("scenes", []):
            if dry_run:
                print(f"  [DRY-RUN] 将生成场景: {scene['name']}")
                print(f"  [DRY-RUN] Prompt: {scene['prompt'][:60]}...")
                scene_paths[scene["name"]] = f"[DRY-RUN] scene_{scene['name']}.jpg"
            else:
                path = await image_gen.generate_scene_image(scene, episode_num)
                scene_paths[scene["name"]] = path
            await asyncio.sleep(2)  # 防限流

        print()

    # Step 3: 图生视频
    if not args.skip_video:
        print("[Step 3/4] 生成场景视频...")
        video_gen = VideoGenerator(adapter, vpath.resolve(vpath.videos_dir).parent)

        video_paths = []
        image_map = scene_paths if not args.skip_image else {}
        for scene in episode_info.get("scenes", []):
            name = scene["name"]
            if name not in image_map:
                print(f"  [警告] 场景 '{name}' 没有对应的图片，跳过")
                continue

            if dry_run:
                print(f"  [DRY-RUN] 将生成场景视频: {name}")
                print(f"  [DRY-RUN] 运镜: {scene.get('video_prompt', '(无)')}")
                video_paths.append(f"[DRY-RUN] ep{episode_num}_{name}.mp4")
            else:
                path = await video_gen.generate_scene_video(scene, image_map[name], episode_num)
                video_paths.append(path)

        print()

    # Step 4: 生成音频
    if not args.skip_audio:
        print("[Step 4/4] 生成旁白和台词...")
        audio_gen = AudioGenerator(vpath.resolve(vpath.audio_dir).parent)

        audio_results = await audio_gen.generate_all_audio(
            episode_info.get("scenes", []), episode_num
        )

        all_audio = audio_results["narration"] + audio_results["dialogue"]
        print(f"  旁白: {len(audio_results['narration'])}段")
        print(f"  台词: {len(audio_results['dialogue'])}段")
        print()
    else:
        all_audio = []
        print()

    # Step 5: 视频合成
    if not dry_run and not args.skip_synthesize:
        print("[Step 5/5] 视频合成...")
        synthesizer = VideoSynthesizer(
            vpath.resolve(vpath.output_dir).parent,
            target_resolution="1080x1920",
        )

        if video_paths and all_audio:
            final = synthesizer.synthesize_episode_sync(
                video_paths, all_audio, None, episode_num
            )
            print(f"\n  成品视频: {final}")
        elif video_paths:
            print(f"\n  [提示] 无音频，仅拼接视频")
            print(f"  视频列表: {video_paths}")
        else:
            print(f"\n  [提示] 无视频或音频，跳过合成")
    elif dry_run:
        print("[DRY-RUN] 预览模式，跳过实际合成")
        print(f"  预计视频数: {len(video_paths)}")
        print(f"  预计音频数: {len(all_audio)}")

    print(f"\n{'='*60}")
    print(f"  第{episode_num}集 {'预览完成' if dry_run else '生成完成'}")
    print(f"{'='*60}\n")


def main():
    args = parse_args()

    # 加载配置
    config = load_config(args.config)

    # 获取API Key（优先级：环境变量 > .env文件 > config）
    api_key = os.environ.get("AGNES_API_KEY", "")
    if not api_key:
        # 尝试从 .env 文件读取
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            with open(env_path, "r") as f:
                for line in f:
                    if line.startswith("AGNES_API_KEY="):
                        api_key = line.split("=", 1)[1].strip()
                        break
    if not api_key:
        print("[错误] 未找到AGNES_API_KEY，请设置环境变量或在.env文件中配置")
        sys.exit(1)

    # 创建虚拟路径管理器
    base_dir = args.output_dir or config.get("output_dir", "./output")
    vpath = VirtualPathManager(base_dir)

    # 获取剧集信息（从JSON文件或默认示例）
    if args.json:
        from converter import convert_json_file
        print(f"[加载] 从策划案JSON: {args.json}")
        raw_data = convert_json_file(args.json)
        episode_info = raw_data
    else:
        episode_info = get_sample_episode_info(args.episode_num)

    # 创建适配器
    adapter = AgnesAIAdapter(api_key or "dummy-key-for-dry-run")

    # 执行流水线
    try:
        asyncio.run(run_pipeline(adapter, episode_info, vpath, args))
    except KeyboardInterrupt:
        print("\n[中断] 用户取消")
        sys.exit(1)
    except Exception as e:
        print(f"\n[错误] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
