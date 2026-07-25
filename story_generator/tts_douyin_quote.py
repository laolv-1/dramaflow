#!/usr/bin/env python3
"""
抖音励志语录 TTS 生成工具
--------------------------------
流程：
1. 用预设音色合成一段参考音频（如果还没有克隆音色）
2. 提交到 moss-voice-generator 创建自定义音色
3. 用克隆音色生成励志语录音频

典型使用场景：茶桌背景图 + TTS配音经典语录 短视频
"""

import os
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path


# ---------------------------------------------------------------------------
# Mossland TTS Client（简化版，依赖 generator.py 中的完整实现）
# ---------------------------------------------------------------------------

class DouyinTTS:
    MOSS_API_BASE = "https://api.mosi.cn/v1"
    DEFAULT_VOICE_ID = "06f9aa7a-654d-4821-8d67-108377968c35"
    MODEL = "moss-tts"
    KEY_VAR = "MOSS_API_KEY"

    def __init__(self, api_key=None):
        self.api_key = api_key or self._load_key()
        self.default_voice_id = self.DEFAULT_VOICE_ID

    # ---- helpers ---------------------------------------------------------

    def _load_key(self) -> str:
        key = os.environ.get(self.KEY_VAR)
        if key:
            return key
        for p in [".env_moss", str(Path.home() / ".moss_tts_key.txt")]:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    raw = "".join(c for c in f.read().strip() if 32 <= ord(c) <= 126)
                    # 跳过 TTS_VOICE_ID=xxx 这种非 key 行
                    for line in raw.splitlines():
                        if line.startswith("MOSS_API_KEY="):
                            return line.split("=", 1)[1].strip()
                    if raw and "MOSS_API_KEY" not in raw:
                        # .env_moss 里直接就是 key
                        return raw
        return ""

    def _post_json(self, endpoint, payload):
        url = self.MOSS_API_BASE + endpoint
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            return json.loads(resp.read().decode()), resp.read()
        except urllib.error.HTTPError as e:
            err = e.read().decode(errors="replace")
            raise RuntimeError(f"TTS API [{endpoint}] HTTP {e.code}: {err[:300]}")

    def _synthesize_raw(self, payload):
        """合成音频，返回原始字节（不解析 JSON）"""
        url = self.MOSS_API_BASE + "/audio/speech"
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=120)
        return resp.read()

    def _post_audio_file(self, endpoint, audio_bytes, mime_type="audio/wav"):
        """Multipart POST 音频文件到 voice cloning 接口"""
        boundary = b"----DouyinTTSGenBoundaRY"
        body = (
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="audio_sample"; filename="ref.wav"\r\n'
            b"Content-Type: " + mime_type.encode() + b"\r\n\r\n"
        ) + audio_bytes + b"\r\n--" + boundary + b"--\r\n"

        req = urllib.request.Request(
            self.MOSS_API_BASE + endpoint,
            data=body,
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err = e.read().decode()
            raise RuntimeError(f"TTS API [{endpoint}] HTTP {e.code}: {err[:300]}")

    def _get_json(self, endpoint):
        url = self.MOSS_API_BASE + endpoint
        req = urllib.request.Request(url,
            headers={"Authorization": f"Bearer {self.api_key}"})
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err = e.read().decode()
            raise RuntimeError(f"TTS API [{endpoint}] HTTP {e.code}: {err[:300]}")

    # ---- public API ------------------------------------------------------

    def synthesize(self, text, output_file, voice_id=None, speed=1.0):
        """用预设或克隆音色合成 TTS 音频"""
        vid = voice_id or self.default_voice_id
        payload = {
            "model": self.MODEL,
            "input": text,
            "voice_id": vid,
            "speed": speed,
        }
        raw = self._synthesize_raw(payload)
        os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
        with open(output_file, "wb") as f:
            f.write(raw)
        est_sec = len(raw) * 8 / 128000
        print(f"  [TTS] 合成完成: {len(raw)} bytes, ~{est_sec:.1f}s -> {output_file}")
        return {"file": output_file, "bytes": len(raw), "duration_sec": round(est_sec, 1)}

    def list_voices(self):
        """列出所有可用音色（预设+克隆）"""
        result = self._get_json("/audio/voices")
        voices = result.get("data", [])
        return voices

    def clone_voice(self, audio_bytes, mime_type="audio/wav"):
        """
        通过上传音频样本创建自定义音色
        Returns: voice_id string
        """
        result = self._post_audio_file("/audio/voices", audio_bytes, mime_type)
        voice_id = result.get("id")
        print(f"  [VoiceGen] 新音色创建成功: {voice_id}")
        return voice_id

    def generate_reference_audio(self, text, output_file=None):
        """生成一段参考音频用于 voice cloning"""
        if output_file is None:
            output_file = "temp_ref_temp.wav"
        return self.synthesize(text, output_file)

    # ---- 高阶方法: 一键式 workflow ----------------------------------------

    def make_douyin_quote(self, text, output_file="douyin_quote.mp3",
                          use_cloned_voice=False, speed=1.0):
        """
        一键生成抖音励志语录音频

        Args:
            text: 文案内容（建议80-150字，中年男声口吻）
            output_file: 输出音频路径
            use_cloned_voice: 是否尝试用克隆音色（需要先有可用的克隆voice_id）
            speed: 语速
        """
        print(f"{'='*50}")
        print(f" 抖音励志语录 TTS 生成")
        print(f"{'='*50}")
        print(f"文案长度: {len(text)} chars")
        print(f"语速: {speed}")

        voice_id = None
        if use_cloned_voice:
            # 查找已有克隆音色
            try:
                voices = self.list_voices()
                cloned = [v for v in voices if v.get("id") != self.DEFAULT_VOICE_ID]
                if cloned:
                    voice_id = cloned[-1]["id"]
                    print(f"使用最近克隆音色: {voice_id[:20]}...")
                else:
                    print("没有克隆音色，将使用预设音色")
            except Exception as e:
                print(f"无法获取音色列表: {e}，将使用预设音色")

        return self.synthesize(text, output_file, voice_id=voice_id, speed=speed)


# ---------------------------------------------------------------------------
# 预设语录模板库
# ---------------------------------------------------------------------------

QUOTE_TEMPLATES = {
    "茶桌励志": (
        "我叫{name}，今年{age}。{past_hardship}亲戚笑我说你{mock_question}我没吭声，就咬着牙干了。"
        "{current_success}人生没有白走的路，每一步都算数。\n"
        "只要你肯下狠心，老天爷从不辜负老实人。"
    ),
    "工地逆袭": (
        "三十岁那年我还在工地搬砖，媳妇跟我说了一句话，让我泪流满面。\n"
        "她说你没房没车，咱家连个像样的客厅都没有。我没说话，蹲在门口抽了半包烟。\n"
        "可后来我用一双手、一副肩膀，{years}年打下来一套房。\n"
        "生活不是看你起点多高，而是看你有没有咬牙不认输的劲头。"
    ),
    "农村奋斗": (
        "我是农村出来的孩子，高考落榜那年回家种地。村里人都说我这辈子完了。\n"
        "我没理会，白天种地晚上学技术，三年后搞起了大棚种植。\n"
        "现在我有自己的农场，请了十几个工人。\n"
        "我想对所有人说，只要你肯干，老天爷从不亏待努力的人。"
    ),
}


def sample_quote(template_name="茶桌励志", **kwargs):
    """获取预设语录模板的示例文本"""
    if template_name not in QUOTE_TEMPLATES:
        raise ValueError(f"未知模板: {template_name}，可选: {list(QUOTE_TEMPLATES.keys())}")
    # 合并 kwargs（用户传的参数优先）
    defaults = {
        "name": "李明", "age": "三十八",
        "past_hardship": "从工地辞职那天兜里只剩八百块钱。",
        "mock_question": "跑回来种地，图啥？",
        "current_success": "十年后我建了三个大棚，给儿子买了两套房。",
        "years": "十",
    }
    defaults.update(kwargs)
    text = QUOTE_TEMPLATES[template_name].format(**defaults)
    return text


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="抖音励志语录 TTS 生成工具")
    parser.add_argument("-t", "--text", help="文案内容（文字）")
    parser.add_argument("-o", "--output", default="douyin_quote.mp3", help="输出文件路径")
    parser.add_argument("-s", "--speed", type=float, default=1.0, help="语速（0.5-2.0）")
    parser.add_argument("--clone", action="store_true", help="使用克隆音色（需先有克隆音色）")
    parser.add_argument("--template", choices=list(QUOTE_TEMPLATES.keys()),
                        help="使用预设语录模板")
    parser.add_argument("--make-ref", action="store_true", help="生成一段参考音频用于语音克隆")
    args = parser.parse_args()

    tts = DouyinTTS()

    # 模式1：生成参考音频用于 voice cloning
    if args.make_ref:
        ref_text = ("你好，我是李明，今年三十八岁。我做工程已经十年了，"
                    "从一个小包工头做到现在有十几个人跟着我干。"
                    "创业这条路不容易，但只要肯吃苦、讲诚信，总能熬出头。"
                    "希望我的故事能给你们一些启发和动力。")
        out = "temp_ref_cloning.wav"
        tts.generate_reference_audio(ref_text, out)
        print(f"\n参考音频已生成: {out}")
        print("下一步: 上传此音频进行 voice cloning:")
        print(f"  python {sys.argv[0]} --upload {out}")
        sys.exit(0)

    # 模式2：直接使用预设模板
    if args.template:
        args.text = sample_quote(args.template)
        print(f"使用模板: {args.template}")

    # 如果没有文案
    if not args.text:
        print("错误: 必须提供 -t/--text 文案内容 或 --template 模板名")
        parser.print_help()
        sys.exit(1)

    # 生成
    result = tts.make_douyin_quote(
        text=args.text,
        output_file=args.output,
        use_cloned_voice=args.clone,
        speed=args.speed,
    )
    print(f"\n完成! 文件: {result['file']}")
