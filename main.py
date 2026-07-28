#!/usr/bin/env python3
"""
语录短视频全流程：DeepSeek 金句 → Mossland TTS → FFmpeg 竖屏视频

用法:
    python main.py                              # 全自动一句
    python main.py --template 扎心励志           # 指定模板
    python main.py --text "自定义文案"           # 自定义文案
    python main.py --skip-tts                    # 跳过配音（用已有音频）
    python main.py --skip-image                  # 跳过图片生成（用已有茶桌图）
"""

import argparse
import asyncio
import os
import sys
import subprocess
import time
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from tts_douyin_quote import DouyinTTS, sample_quote, QUOTE_TEMPLATES

# ── 配置 ──────────────────────────────────────────────────────
DEFAULT_VOICE_ID = "1a956cdd-d697-425e-b432-6d76a1d0b720"  # 选定男声
TTS_SPEED = 0.9
TTS_INSTRUCTION = "一个有力、自然的成年男声，语气沉稳坚定，略带沙哑质感，说话有力量感"
OUTPUT_DIR = BASE_DIR / "output" / "quote_videos"


# ── 工具函数 ──────────────────────────────────────────────────

def find_ffmpeg() -> str:
    candidates = [
        "ffmpeg",
        r"D:/Account_Forge/AI-CanvasPro/AI-CanvasPro-windows/AI CanvasPro/resources/runtime/ffmpeg/bin/ffmpeg.exe",
        r"D:/Account_Forge/市场调研/工具/ffmpeg_temp/ffmpeg-8.1.2-essentials_build/bin/ffmpeg.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return "ffmpeg"


def get_moss_key() -> str:
    key = os.environ.get("MOSS_API_KEY", "")
    if key:
        return key
    for p in [BASE_DIR / "story_generator" / ".env_moss", BASE_DIR / ".env_moss"]:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("MOSS_API_KEY="):
                        return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def get_deepseek_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.split("=", 1)[1].strip()
    return ""


# ── Step 2: 茶桌背景图（Pillow 本地生成，无API调用）────────────

def generate_teatable_image() -> str:
    """用 Pillow 生成深色茶桌背景图，1080x1920 竖屏"""
    from PIL import Image, ImageDraw, ImageFilter

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = str(OUTPUT_DIR / "teatable_bg.jpg")

    # 检查是否已有生成的图片
    existing = OUTPUT_DIR / "teatable_bg.jpg"
    if existing.exists():
        print(f"  使用已有茶桌图: {existing}")
        return str(existing)

    print(f"  [Pillow] 生成茶桌背景图...")
    img = Image.new("RGB", (1080, 1920), (20, 18, 15))
    draw = ImageDraw.Draw(img)

    # 茶桌椭圆桌面
    draw.ellipse([100, 1400, 980, 1920], fill=(45, 35, 25), outline=(60, 48, 35), width=2)
    # 茶杯
    cx, cy = 540, 1550
    draw.ellipse([cx - 35, cy - 30, cx + 35, cy + 30], fill=(80, 70, 55))
    draw.ellipse([cx - 25, cy - 22, cx + 25, cy + 22], fill=(50, 42, 32))
    draw.ellipse([cx - 20, cy - 18, cx + 20, cy + 10], fill=(120, 80, 40))
    # 热气
    for i in range(3):
        sy = cy - 50 - i * 30
        sx = cx - 10 + i * 20
        steam = Image.new("RGBA", img.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(steam)
        sd.ellipse([sx - 18 - 3 * i, sy - 12 - 2 * i, sx + 18 + 3 * i, sy + 12 + 2 * i],
                    fill=(180, 170, 150, 20 - i * 5))
        img = Image.alpha_composite(img.convert("RGBA"), steam).convert("RGB")
    # 暖光渐变
    for y in range(0, 1920, 2):
        for x in range(0, 1080, 2):
            d = ((x - 200) ** 2 + (y - 100) ** 2) ** 0.5
            if d < 800:
                f = max(0, 1 - d / 800) * 0.08
                r, g, b = img.getpixel((x, y))
                img.putpixel((x, y), (min(255, int(r + 255 * f)),
                                       min(255, int(g + 230 * f)),
                                       min(255, int(b + 180 * f))))
    img = img.filter(ImageFilter.GaussianBlur(radius=1))
    img.save(out_path, quality=95)
    print(f"  茶桌图生成完成: {out_path} ({os.path.getsize(out_path) // 1024}KB)")
    return out_path


# ── 核心流程 ──────────────────────────────────────────────────

async def step1_generate_quote(text: str = None, template: str = None) -> str:
    if text:
        print(f"[Step 1/3] 使用自定义文案 ({len(text)}字)")
        return text
    print(f"[Step 1/3] DeepSeek 生成金句...")
    quote = sample_quote(template or "扎心励志", randomize=True)
    print(f"  金句: {quote[:80]}...")
    return quote


async def step2_generate_image(skip: bool = False) -> str:
    print(f"[Step 2/3] {'跳过生图' if skip else '生成茶桌背景图'}...")
    return generate_teatable_image()


def step3_generate_audio(quote: str, skip: bool = False) -> str:
    if skip:
        print("[Step 3/3] 跳过配音（--skip-tts）")
        return ""
    print(f"[Step 3/3] Mossland TTS 合成配音...")
    print(f"  音色: {DEFAULT_VOICE_ID[:12]}... | 语速: {TTS_SPEED}x")
    print(f"  声音描述: {TTS_INSTRUCTION}")

    moss_key = get_moss_key()
    if not moss_key:
        print("  [错误] 未找到 MOSS_API_KEY")
        return ""

    tts = DouyinTTS(api_key=moss_key)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    audio_path = str(OUTPUT_DIR / f"quote_audio_{ts}.mp3")
    try:
        result = tts.synthesize(text=quote, output_file=audio_path,
                                 voice_id=DEFAULT_VOICE_ID, speed=TTS_SPEED,
                                 instruction=TTS_INSTRUCTION)
        print(f"  配音完成: {result['file']}")
        return result["file"]
    except Exception as e:
        print(f"  [错误] TTS 失败: {e}")
    return ""


async def main():
    parser = argparse.ArgumentParser(description="语录短视频全流程生成")
    parser.add_argument("--text", help="自定义文案（不指定则用 DeepSeek 生成）")
    parser.add_argument("--template", choices=list(QUOTE_TEMPLATES.keys()),
                        default="扎心励志", help="语录模板（默认: 扎心励志）")
    parser.add_argument("--skip-image", action="store_true", help="跳过图片生成")
    parser.add_argument("--skip-tts", action="store_true", help="跳过 Mossland TTS 配音")
    parser.add_argument("--audio", help="使用本地音频（跳过配音）")
    args = parser.parse_args()

    sep = "=" * 55
    print(f"\n{sep}")
    print(f"  语录短视频流水线")
    print(f"{sep}")

    quote = await step1_generate_quote(args.text, args.template)
    image_path = generate_teatable_image() if not args.skip_image else ""
    audio_path = args.audio or step3_generate_audio(quote, args.skip_tts)

    # Step 4: FFmpeg 合成
    if image_path and audio_path:
        print(f"\n  [合成] 图片 + 音频 → 竖屏视频...")
        ffmpeg = find_ffmpeg()
        ts = int(time.time())
        video_path = str(OUTPUT_DIR / f"quote_video_{ts}.mp4")
        cmd = [
            ffmpeg, "-y", "-loop", "1", "-i", image_path, "-i", audio_path,
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k", "-shortest", video_path,
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                               encoding="utf-8", errors="replace")
            if r.returncode == 0:
                size_mb = os.path.getsize(video_path) / (1024 * 1024)
                print(f"  [完成] 成品视频: {video_path} ({size_mb:.1f}MB)")
            else:
                print(f"  [FFmpeg错误] {r.stderr[-300:]}")
        except Exception as e:
            print(f"  [错误] 合成失败: {e}")

    print(f"{sep}\n")


if __name__ == "__main__":
    asyncio.run(main())
