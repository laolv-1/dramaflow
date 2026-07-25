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
    # 抖音语录默认男声（沉稳有力，带货/励志风格）
    QUOTE_DEFAULT_VOICE = "06f9aa7a-654d-4821-8d67-108377968c35"
    # 克隆音色 ID（通过 POST /v1/audio/voices 创建）
    CLONED_VOICE_ID = "25a57cf4-7257-4229-87d1-3f3623266f6a"
    MODEL = "moss-tts"
    KEY_VAR = "MOSS_API_KEY"

    def __init__(self, api_key=None):
        self.api_key = api_key or self._load_key()
        self.default_voice_id = self.QUOTE_DEFAULT_VOICE

    # ---- helpers ---------------------------------------------------------

    def _load_key(self) -> str:
        key = os.environ.get(self.KEY_VAR)
        if key:
            return key
        for p in [".env_moss", str(Path.home() / ".moss_tts_key.txt")]:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("MOSS_API_KEY="):
                            return line.split("=", 1)[1].strip().strip("\"'")
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
                          speed=1.0, force_cloned_voice=False):
        """
        一键生成抖音语录音频

        Args:
            text: 文案内容（建议80-200字）
            output_file: 输出音频路径
            speed: 语速（推荐 0.9 沉稳有力）
            force_cloned_voice: 强制使用克隆音色
        """
        print(f"{'='*50}")
        print(f" 抖音语录 TTS 生成")
        print(f"{'='*50}")
        print(f"文案长度: {len(text)} chars")
        print(f"语速: {speed}")

        # 优先使用克隆音色（带货/励志风格需要男声）
        if force_cloned_voice:
            voice_id = self.CLONED_VOICE_ID
            print(f"使用克隆音色: {voice_id[:20]}...")
        else:
            # 尝试用克隆音色，如果失败则回退到默认男声
            try:
                voices = self.list_voices()
                cloned = [v for v in voices if v.get("id") == self.CLONED_VOICE_ID]
                if cloned:
                    voice_id = self.CLONED_VOICE_ID
                    print(f"检测到克隆音色: {voice_id[:20]}...")
                else:
                    voice_id = self.default_voice_id
                    print(f"使用默认男声: {voice_id[:20]}...")
            except Exception as e:
                voice_id = self.default_voice_id
                print(f"无法获取音色列表，使用默认男声: {e}")

        return self.synthesize(text, output_file, voice_id=voice_id, speed=speed)


# ---------------------------------------------------------------------------
# 预设语录模板库 - 直白扎心励志风（带货/短视频/茶桌背景）
# 结构: {模板名: [文案列表]}, API 每次随机返回一条
# ---------------------------------------------------------------------------

QUOTE_TEMPLATES = {
    "扎心励志": [
        (
            "没有人帮你，你就自己帮自己。\n"
            "你连睡觉都在刷手机，凭什么比别人强？\n"
            "不逼自己一把，你永远不知道自己多优秀。\n"
            "别抱怨了，成年人的世界没有容易二字。\n"
            "想，都是问题；做，才有答案。"
        ),
        (
            "你穷不是因为没有机会，是因为你不努力。\n"
            "弱者的眼泪只会被嘲笑，强者的汗水才会换来尊重。\n"
            "今天你看不起我，明天你会高攀不起。\n"
            "没人扶你的时候，自己要站直。\n"
            "不吃苦，苦一辈子；吃苦一阵，苦一时。\n"
            "别等了，等什么都没了。"
        ),
        (
            "你以为的舒适区，其实是牢笼。\n"
            "别人在拼命，你在刷剧；别人在成长，你在抱怨。\n"
            "十年后，你会感谢现在拼命的自己。\n"
            "不要假装很努力，结果不会陪你演戏。\n"
            "你现在的每一分努力，都是未来的底气。"
        ),
    ],
    "翻身语录": [
        (
            "你现在偷的懒，都会变成打脸的巴掌。\n"
            "别在最该拼搏的年纪选择了安逸。\n"
            "你现在的舒服，是你未来的痛苦。\n"
            "没有人会同情一个不努力的人。\n"
            "成功没有快车道，失败没有后路。"
        ),
        (
            "你不好好拼，就有人替你拼爹。\n"
            "这个世界从不公平，但你可以改变自己的位置。\n"
            "别等了，等你有钱了，机会早没了。\n"
            "现在不玩命，将来命玩你。\n"
            "怕苦的人永远只能吃苦。"
        ),
        (
            "人生最可怕的敌人是自己。\n"
            "你害怕失败，所以不敢开始。\n"
            "可你知道更惨的是什么吗？是连开始都不敢。\n"
            "不逼自己一次，你永远不知道自己能走多远。\n"
            "与其羡慕别人，不如做自己。"
        ),
    ],
    "搞钱思维": [
        (
            "穷人存钱，富人投资，你选哪个？\n"
            "你的工资永远追不上通胀，不学习就是不赚钱。\n"
            "你以为的稳定，是最大的风险。\n"
            "你不理财，财就不理你——别找借口说没钱可理。\n"
            "钱不是省出来的，是赚出来的。"
        ),
        (
            "你舍不得花钱学习，一辈子就只能花冤枉钱。\n"
            "穷人的时间不值钱，富人的时间才值钱。\n"
            "不投资大脑的人，最穷。\n"
            "你以为的省钱，其实是在亏钱。\n"
            "花小钱投资自己，比花大钱买虚荣强。"
        ),
        (
            "打工永远打不出财富自由。\n"
            "你的收入只能覆盖开支，那多余的钱去哪了？\n"
            "不思考钱生钱的事，一辈子都在为钱发愁。\n"
            "富人买资产，穷人买负债。\n"
            "你不创造被动收入，就只能一直工作到死。"
        ),
    ],
}


def sample_quote(template_name="扎心励志", randomize=True, **kwargs):
    """获取预设语录模板的示例文本
    Args:
        template_name: 模板名称
        randomize: 是否随机选择（True=每次随机一条，False=固定第一条）
    """
    import random
    if template_name not in QUOTE_TEMPLATES:
        raise ValueError(f"未知模板: {template_name}，可选: {list(QUOTE_TEMPLATES.keys())}")
    versions = QUOTE_TEMPLATES[template_name]
    # versions 现在是列表，不是字符串
    if isinstance(versions, list):
        if randomize and len(versions) > 1:
            text = random.choice(versions)
        else:
            text = versions[0]
    else:
        text = versions
    return text.format(**kwargs) if kwargs else text


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="抖音励志语录 TTS 生成工具")
    parser.add_argument("-t", "--text", help="文案内容（文字）")
    parser.add_argument("-o", "--output", default="douyin_quote.mp3", help="输出文件路径")
    parser.add_argument("-s", "--speed", type=float, default=1.0, help="语速（0.5-2.0）")
    parser.add_argument("--force-clone", action="store_true", help="强制使用克隆音色（优先于默认男声）")
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
        force_cloned_voice=args.force_clone,
        speed=args.speed,
    )
    print(f"\n完成! 文件: {result['file']}")
