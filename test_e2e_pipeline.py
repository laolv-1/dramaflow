"""
端到端流水线测试 v3 - 2026-07-28
艾公金句风格：低谷救赎·认知觉醒·改名改命·品茶悟道
"""
import os, sys, json, time, asyncio, urllib.request, subprocess, re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
FFMPEG = r"D:\Account_Forge\AI-CanvasPro\AI-CanvasPro-windows\AI CanvasPro\resources\runtime\ffmpeg\bin\ffmpeg.exe"
OUTPUT_DIR = PROJECT_ROOT / "test_output"
OUTPUT_DIR.mkdir(exist_ok=True)


def load_keys():
    keys = {}
    for env_path in [
        PROJECT_ROOT / ".env",
        PROJECT_ROOT / "story_generator" / ".env",
        PROJECT_ROOT / "story_generator" / ".env_moss",
    ]:
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        keys[k.strip()] = v.strip().strip("\"'")
    return keys


def get_audio_duration(audio_path):
    result = subprocess.run(
        [FFMPEG, "-i", audio_path, "-f", "null", "-"],
        capture_output=True, text=True, timeout=30
    )
    for line in result.stderr.split("\n"):
        if "Duration" in line:
            parts = line.strip().split(",")[0]
            time_str = parts.split("Duration: ")[-1].strip()
            h, m, s = time_str.split(":")
            return float(s) + int(m) * 60 + int(h) * 3600
    return 5.0


# --- Step 1: DeepSeek 生成艾公金句 ---
def step1_generate_text(api_key):
    print("\n[Step 1/4] DeepSeek 生成艾公风格金句...")

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    prompt = """你是"艾公"风格的金句写手。

艾公金句的核心：一句话就是一把刀。不说故事，不说教，只说结论。

主题范围（每次选1-2个）：
- 低谷救赎：跌到最底才知道什么是真的
- 改名改命：你不是改了一个名字，是决定换一种活法
- 认知觉醒：人不是慢慢变好的，是一瞬间醒过来的
- 品茶悟道：茶凉了可以续，人走错了可以回头

写作铁律：
1. 全程"你"——像指着鼻子对一个人说话
2. 每句8-20字。不要长句。
3. 开头第一个字就要用力——"你记住"、"听好"、"别装了"、"摔碎了就是摔碎了"
4. 必须有反转。前一句把你按下去，后一句把你拽起来。
5. 茶/杯/壶做隐喻，但不要绕——直接说。
6. 禁用任何网上泛滥的金句。不逼自己、熬过就好、半生归来等全部禁用。
7. 结尾不要升华。戛然而止。
8. 字数80-130字（约20-25秒口播），越短越有力。

输出格式：
【语录正文】

【标题关键词：词1、词2、词3、词4】
"""

    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.85,
    )
    output = resp.choices[0].message.content.strip()
    print(f"  原始输出({len(output)}字):")
    print(f"  {output[:120]}...")
    return output


def parse_quote_output(output):
    """解析LLM输出，分离语录正文和标题关键词"""
    # 尝试解析【标题关键词】部分
    keywords = []
    text = output

    kw_match = re.search(r'【标题关键词[：:]\s*(.+?)】', output)
    if kw_match:
        kw_str = kw_match.group(1)
        keywords = [k.strip() for k in kw_str.split('、') if k.strip()]
        # 从正文中移除关键词部分
        text = output[:kw_match.start()].strip()

    # 移除【语录正文】标记
    text = re.sub(r'【语录正文】', '', text).strip()

    # 如果没有明确关键词，从正文取短词
    if not keywords:
        # 取每行第一个名词性短语（1-4字）
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            # 取第一个有意义的词群
            words = line.replace('——', '——').split('——')[0]
            words = words.replace('，', '，').split('，')[0] if '，' in words else words
            # 去掉标点
            import re as _re
            clean = _re.sub(r'[，。！？、；：""''「」—…\n\r\t]', '', words).strip()
            if 2 <= len(clean) <= 6:
                keywords.append(clean)
            if len(keywords) >= 4:
                break
    if not keywords:
        keywords = ["谷底", "碎杯", "换茶", "醒悟"]

    return text, keywords


# --- Step 2: Mossland TTS 合成音频（moss-tts 8B大模型） ---
def step2_synthesize_audio(text, api_key):
    print("\n[Step 2/4] Mossland TTS 合成音频...")

    # 使用 moss-tts (8B) 端点，不用 moss-voice-generator (1.7B)
    # - generations 端点小模型中文差：外国人腔 + 电音
    # - speech 端点大模型中文干净
    # - 语速放慢到0.85增加沉重感
    url = "https://api.mosi.cn/v1/audio/speech"
    payload = json.dumps({
        "model": "moss-tts",
        "input": text,
        "voice_id": "fa435ac6-416a-4676-b138-a6ff8380e7cf",
        "response_format": "mp3",
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST")

    audio_path = OUTPUT_DIR / "test_audio.mp3"
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        with open(audio_path, "wb") as f:
            f.write(resp.read())
        duration = get_audio_duration(str(audio_path))
        print(f"  音频: {audio_path} ({os.path.getsize(audio_path)/1024:.1f}KB, {duration:.1f}s)")
        return str(audio_path), duration
    except urllib.error.HTTPError as e:
        print(f"  TTS失败: HTTP {e.code}")
        return None, 0


# --- Step 3: Agnes 生成暗调茶桌配图 ---
async def step3_generate_image(api_key):
    print("\n[Step 3/4] Agnes API 生成暗调茶桌配图...")

    sys.path.insert(0, str(PROJECT_ROOT))
    from adapters.agnes_ai import AgnesAIAdapter

    adapter = AgnesAIAdapter(api_key=api_key)
    result = await adapter.generate_image(
        prompt="Dark moody Chinese tea table still life, dim ambient lighting, single warm spotlight on a Yixing clay teapot and small teacup, dark wooden table surface, subtle steam rising, deep shadows, chiaroscuro, contemplative atmosphere, cinematic mood, high contrast, dark background, 4K, photorealistic, vertical 9:16 composition",
        negative_prompt="bright, sunny, daytime, people, person, messy, colorful, flowers, garden, warm tone, happy",
        model="agnes-image-2.1-flash",
        size="2K",
    )

    if result and "url" in result:
        img_url = result["url"]
        print(f"  图片URL: {img_url}")
        img_path = OUTPUT_DIR / "test_bg.jpg"
        urllib.request.urlretrieve(img_url, img_path)
        print(f"  图片: {img_path} ({os.path.getsize(img_path)/1024:.1f}KB)")
        return str(img_path)
    else:
        print(f"  生图失败: {result}")
        return None


# --- Step 4: FFmpeg 合成视频 ---
def step4_compose_video(image_path, audio_path, duration):
    print("\n[Step 4/4] FFmpeg 合成视频...")

    if not image_path or not audio_path:
        print("  跳过：图片或音频缺失")
        return None

    video_path = OUTPUT_DIR / "test_final_v3.mp4"

    filter_complex = (
        f"scale=1080:1920:force_original_aspect_ratio=decrease,"
        f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
        f"format=yuv420p"
    )

    cmd = [
        FFMPEG, "-y",
        "-loop", "1",
        "-i", image_path,
        "-i", audio_path,
        "-c:v", "libx264",
        "-t", str(duration),
        "-pix_fmt", "yuv420p",
        "-vf", filter_complex,
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(video_path)
    ]

    print(f"  FFmpeg: 音频{duration:.1f}s -> {video_path.name}")
    subprocess.run(cmd, check=True, timeout=120)

    file_size = os.path.getsize(video_path)
    print(f"  成品视频: {video_path} ({file_size/1024:.1f}KB)")
    return str(video_path)


async def main():
    print("=" * 60)
    print("  艾公金句 · 低谷救赎")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    keys = load_keys()
    for k in ["DEEPSEEK_API_KEY", "AGNES_API_KEY", "MOSS_API_KEY"]:
        print(f"  {k}: {'有' if keys.get(k) else '无'}")

    if not all([keys.get("DEEPSEEK_API_KEY"), keys.get("AGNES_API_KEY"), keys.get("MOSS_API_KEY")]):
        print("\n[错误] Key不完整")
        return

    try:
        # Step 1: 生成文案 + 关键词
        raw_output = step1_generate_text(keys["DEEPSEEK_API_KEY"])
        quote_text, keywords = parse_quote_output(raw_output)
        print(f"\n  >>> 语录正文:")
        for line in quote_text.split('\n'):
            if line.strip():
                print(f"     {line.strip()}")
        print(f"\n  >>> 标题关键词: {' | '.join(keywords)}")

        # Step 2: 合成音频
        audio, duration = step2_synthesize_audio(quote_text, keys["MOSS_API_KEY"])
        if not audio:
            print("  音频合成失败，终止")
            return

        # Step 3: 生成配图
        image = await step3_generate_image(keys["AGNES_API_KEY"])
        if not image:
            print("  生图失败，使用默认图片继续")

        # Step 4: 合成视频
        video = step4_compose_video(image, audio, duration)

        print("\n" + "=" * 60)
        if video:
            print(f"  成品视频: {video}")
        else:
            print("  失败")
        print("=" * 60)

    except Exception as e:
        print(f"\n[错误] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
