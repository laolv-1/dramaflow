"""Mossland TTS CLI 测试工具

测试 Mossland 语音合成 API，验证：
1. 不同文本长度的积分消耗
2. 可用语音角色列表
3. 单角色/多角色配音（短剧场景）
4. 音频文件导出

用法:
    python tts_test.py --text "你好测试" --voice-id <id>
    python tts_test.py --list-voices
    python tts_test.py --drama-scene episodes.json --output-dir ./audio
"""

import argparse
import json
import time
import os
import sys
from pathlib import Path
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def make_request(url, api_key, data=None, method="GET"):
    """发送 HTTP 请求（使用 urllib 绕过 requests 的 header 校验问题）"""
    # 严格保留 ASCII printable (32-126)，剔除所有不可见/中文/特殊字符
    clean_key = ''.join(c for c in api_key if 32 <= ord(c) <= 126)
    auth_header = "Bearer " + clean_key
    headers = {"Authorization": auth_header}
    if data:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")
    else:
        body = None

    req = Request(url, data=body, headers=headers, method=method)
    try:
        resp = urlopen(req, timeout=120)
        return resp
    except HTTPError as e:
        try:
            body_err = e.read().decode("utf-8", errors="replace")
        except:
            body_err = str(e)
        print(f"[!] HTTP {e.code}: {body_err[:500]}")
        return None
    except Exception as e:
        print(f"[!] 请求失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_api_key():
    """从环境变量或配置文件获取 API Key"""
    # 1. 环境变量
    key = os.environ.get("MOSS_API_KEY")
    if key:
        return key

    # 2. 专用配置文件（纯文本，只存 key）
    config_paths = [
        ".env_moss",
        str(Path.home() / ".moss_tts_key.txt"),
    ]
    for p in config_paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                key = ''.join(c for c in f.read().strip() if 32 <= ord(c) <= 126)
                if key:
                    return key

    # 3. 通用 .env 文件，解析 MOSS_API_KEY=xxx
    for env_path in [".env", "../.env"]:
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    if k.strip() == "MOSS_API_KEY":
                        return v.strip().strip("\"'")

    return None


API_BASE = "https://api.mosi.cn/v1/audio"
DEFAULT_VOICE_ID = "cfff6856-8f17-4eaf-aed6-e1ff99d7241c"  # 萧逸
MODEL = "moss-tts"


def list_voices(api_key: str):
    """列出所有可用语音角色"""
    print("[*] 正在获取语音角色列表...")
    url = f"{API_BASE}/voices"

    resp = make_request(url, api_key)
    if resp is None:
        return []

    data = json.loads(resp.read().decode("utf-8"))
    voices = data.get("data", [])
    has_more = data.get("has_more", False)
    next_cursor = data.get("next_cursor", "")

    print(f"\n{'='*60}")
    print(f"  可用语音角色: {len(voices)} 个 {'(还有更多...)' if has_more else ''}")
    print(f"{'='*60}\n")

    for i, v in enumerate(voices, 1):
        vid = v.get("id", "?")
        name = v.get("name", "?")
        created = v.get("created_at", 0)
        if created > 1000000000:
            dt = datetime.fromtimestamp(created).strftime("%Y-%m-%d %H:%M")
        else:
            dt = "-"
        print(f"  {i:3d}. {name:<15s} [{vid[:12]}...] (创建: {dt})")

    print(f"\n{'='*60}")
    print("  复制完整 voice_id 用于配音:")
    print(f"{'='*60}")
    for v in voices[:5]:
        print(f'  --voice-id "{v["id"]}"  # {v["name"]}')

    return voices


def synthesize(api_key: str, text: str, voice_id: str = DEFAULT_VOICE_ID,
               output_file: str = None, speed: float = 1.0):
    """合成一段文本为音频"""
    url = f"{API_BASE}/speech"
    payload = {
        "model": MODEL,
        "input": text,
        "voice_id": voice_id,
        "speed": speed,
    }

    print(f"[*] 开始合成...")
    print(f"    文本长度: {len(text)} 字")
    print(f"    语音角色: {voice_id[:12]}...")
    print(f"    语速: {speed}x")

    start = time.time()
    resp = make_request(url, api_key, data=payload, method="POST")
    elapsed = time.time() - start

    if resp is None:
        return None

    audio_data = resp.read()

    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"output_{timestamp}.mp3"

    with open(output_file, "wb") as f:
        f.write(audio_data)

    duration_bytes = len(audio_data)
    est_duration_sec = duration_bytes * 8 / 96000

    print(f"\n[OK] 合成成功!")
    print(f"    耗时: {elapsed:.1f}s")
    print(f"    文件大小: {len(audio_data)/1024:.1f} KB")
    print(f"    估算音频时长: {est_duration_sec:.1f}s")
    print(f"    输出: {output_file}")

    return {
        "file": output_file,
        "size": len(audio_data),
        "duration_sec": est_duration_sec,
        "elapsed": elapsed,
    }


def test_credit_consumption(api_key: str, voice_id: str = DEFAULT_VOICE_ID):
    """测试不同长度的积分消耗"""
    print(f"\n{'='*60}")
    print("  积分消耗测试")
    print(f"{'='*60}\n")

    test_cases = [
        ("短句(10字)", "你好，这是一个测试。"),
        ("台词(28字)", "清晨的阳光透过窗帘洒在房间里，李明缓缓睁开眼睛。"),
        ("场景(80字)", """旁白：清晨的阳光透过窗帘洒在房间里，李明缓缓睁开眼睛，看着天花板发呆。
台词：喂，你是哪位？
旁白：对方沉默了片刻，说道：我是来改变你命运的人。
台词：我不会相信你的鬼话。
旁白：就在这时，门铃响了。"""),
    ]

    results = []
    for name, text in test_cases:
        result = synthesize(api_key, text, voice_id)
        if result:
            results.append({
                "name": name,
                "chars": len(text),
                "file": result["file"],
                "size_kb": result["size"] / 1024,
                "duration_s": result["duration_sec"],
                "elapsed_s": result["elapsed"],
                "speed_factor": len(text) / result["elapsed"] if result["elapsed"] > 0 else 0,
            })
        print()
        time.sleep(1)

    # 汇总
    print(f"\n{'='*60}")
    print("  测试汇总")
    print(f"{'='*60}")
    print(f"  {'场景':<10s} {'字数':>6s} {'文件大小':>10s} {'耗时':>8s} {'速度':>10s}")
    print(f"  {'-'*10} {'-'*6} {'-'*10} {'-'*8} {'-'*10}")
    for r in results:
        print(f"  {r['name']:<10s} {r['chars']:>6d} {r['size_kb']:>8.1f}KB {r['elapsed_s']:>7.1f}s {r['chars']/r['elapsed_s']:>8.1f}字/s")
    print(f"{'='*60}")


def test_multi_voice_drama(api_key: str, output_dir: str = "./drama_audio"):
    """测试多角色配音（模拟一集短剧）"""
    os.makedirs(output_dir, exist_ok=True)

    script = [
        {"role": "旁白", "text": "第一章：命运的转折", "voice": "旁白声"},
        {"role": "李明", "text": "这到底是什么情况？", "voice": "青年男声"},
        {"role": "小王", "text": "你看到了吗？天空那道光！", "voice": "好友男声"},
        {"role": "李明", "text": "看到了...我心里有种不好的预感。", "voice": "青年男声"},
        {"role": "旁白", "text": "此时的李明并不知道，这一切才刚刚开始。", "voice": "旁白声"},
    ]

    print(f"[*] 多角色配音测试")
    print(f"    输出目录: {output_dir}\n")

    results = []
    for i, scene in enumerate(script, 1):
        print(f"  [{i}/{len(script)}] {scene['role']}: {scene['text'][:30]}...")
        outfile = os.path.join(output_dir, f"scene_{i:02d}_{scene['role']}.mp3")
        result = synthesize(api_key, scene["text"], DEFAULT_VOICE_ID, outfile)
        if result:
            results.append(result)
        time.sleep(1)

    print(f"\n[OK] 多角色配音完成! 共 {len(results)} 段音频")
    print(f"    输出目录: {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Mossland TTS CLI 测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 列出所有语音角色
  python tts_test.py --list-voices

  # 合成一段文本
  python tts_test.py --text "你好世界" --voice-id <id>

  # 积分消耗测试
  python tts_test.py --test-credits

  # 多角色配音测试
  python tts_test.py --drama-test --output-dir ./audio

  # 使用环境变量设置 API Key
  export MOSS_API_KEY="sk-xxxx"
  python tts_test.py --text "测试"
        """,
    )

    parser.add_argument("--api-key", help="Mossland API Key (或设环境变量 MOSS_API_KEY)")
    parser.add_argument("--list-voices", action="store_true", help="列出所有可用语音角色")
    parser.add_argument("--text", help="要合成的文本")
    parser.add_argument("--voice-id", default=DEFAULT_VOICE_ID, help=f"语音角色ID (默认: {DEFAULT_VOICE_ID[:20]}...)")
    parser.add_argument("--output", "-o", help="输出音频文件路径")
    parser.add_argument("--speed", type=float, default=1.0, help="语速 (0.5-2.0, 默认: 1.0)")
    parser.add_argument("--test-credits", action="store_true", help="测试不同长度的积分消耗")
    parser.add_argument("--drama-test", action="store_true", help="多角色配音测试")
    parser.add_argument("--output-dir", default="./drama_audio", help="多角色配音输出目录")

    args = parser.parse_args()

    # 获取 API Key
    api_key = args.api_key or get_api_key()
    if not api_key:
        print("[!] 未找到 API Key")
        print("    方式1: --api-key sk-xxxx")
        print("    方式2: 设置环境变量 MOSS_API_KEY=sk-xxxx")
        print("    方式3: 创建 .env 文件，写入 MOSS_API_KEY=sk-xxxx")
        sys.exit(1)

    # 执行命令
    if args.list_voices:
        list_voices(api_key)
    elif args.test_credits:
        test_credit_consumption(api_key)
    elif args.drama_test:
        test_multi_voice_drama(api_key, args.output_dir)
    elif args.text:
        result = synthesize(api_key, args.text, args.voice_id, args.output, args.speed)
        if not result:
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
