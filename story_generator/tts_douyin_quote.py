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

    def make_douyin_quote(self, text, output_file="douyin_quote.mp3", speed=1.0):
        """一键生成抖音语录音频"""
        vid = self.default_voice_id
        print(f"{'='*50}")
        print(f" 抖音语录 TTS 生成")
        print(f"{'='*50}")
        print(f"文案长度: {len(text)} chars | 语速: {speed} | 音色: {vid[:20]}...")
        return self.synthesize(text, output_file, voice_id=vid, speed=speed)


# ---------------------------------------------------------------------------
# 预设语录模板库 - 深夜茶桌旁说真话的中年男人风（短/刺/金句）
# 结构: {维度标签: [语录列表]}, API 每次随机返回一条
# 原则：不说教、不叙事。每条40-70字，自包含一句或两句对仗。
#       禁用网上泛滥的金句，只写让人心头一紧的原创短句。
# ---------------------------------------------------------------------------

QUOTE_TEMPLATES = {
    # D1: 起点低/被看不起 — "我不认命"的态度
    "扎心励志": [
        (
            "你去同学聚会上转一圈就知道了。当年垫底的那个，现在主动敬你酒。\n"
            "不是他突然有了地位，是你终于学会了不低头。\n"
            "没人注意你的时候，把腰杆挺直了走，这才是给自己长脸。"
        ),
        (
            "小时候以为长大就能改变世界，后来发现能改变的只是工资到账的速度。\n"
            "可你也没认输——每个月账单来，该还的还是照样按时打过去。\n"
            "这就是普通人最硬的骨头：知道结果，不躲。"
        ),
        (
            "你站在会议室后排发言的时候，别人不会因为你声音小而忽视你。\n"
            "但你要是因为没人听就不开口，那这次以后你永远都只能在后排坐着。\n"
            "开口了，至少有一次被打断后还能继续说的面子。"
        ),
    ],

    # D2: 咬牙硬扛 — "痛但不喊"的状态
    "翻身语录": [
        (
            "凌晨两点从医院走廊长椅上醒来的时候你会明白——\n"
            "这世上大部分难熬的事，都是一个人咬着牙捱过来的。\n"
            "你没喊疼，不是因为不疼，是因为喊了也没人替你难受。"
        ),
        (
            "你银行卡里的余额，比你身边的人都诚实。\n"
            "它告诉你谁是在意你这个人，谁只是在意你能帮什么忙。\n"
            "看懂了就别去追问，默默把该存的存好。"
        ),
        (
            "体检报告上多出来的那个箭头，比任何鸡汤都管用。\n"
            "它让你突然就决定：明天开始少熬一个夜，多走两千步。\n"
            "身体不会骗人，你糊弄它一次它就记一次账。"
        ),
    ],

    # D3: 孤军奋战 — "身后空无一人所以不能倒"
    "沉默行动": [
        (
            "给父母打电话说'挺好的'那一刻，你把胃里的酸水咽回去了。\n"
            "这不是撒谎，是你终于懂得：他们能承受的最坏的，就是你知道。\n"
            "报喜不报忧这件事，做久了就成了习惯和担当。"
        ),
        (
            "孩子交学费的那张单子你翻了三遍——\n"
            "第一遍确认数字没看错，第二遍算算这个月还剩多少，\n"
            "第三遍折起来塞进钱包，就像把一场无声的风暴收起来。"
        ),
        (
            "你在电梯里整理领带的那三十秒，不是在臭美——\n"
            "你是在把一个刚被骂了一顿的自己，重新拼成能见人形的样子。\n"
            "然后门开了，推出去，接着演那个情绪稳定的成年人。"
        ),
    ],
}


# ============================================================
# 语录生成器 — 深夜茶桌旁说真话的中年男人
# System Prompt 集成版本：根据维度动态生成原创语录
# ============================================================

_DIMENSION_LABELS = {
    "D1": "起点低/被看不起",
    "D2": "咬牙硬扛",
    "D3": "孤军奋战",
    "D4": "沉默行动",
    "D5": "现实刺痛",
    "D6": "翻身路上",
    "D7": "中年清醒",
    "D8": "父子之间",
    "D9": "夫妻之间",
    "D10": "一个人的日常",
}

_GENERATION_PROMPTS = {
    "D1": (
        "一个起点很低、从小被看不起的人。他经历过：成绩单最后一名被点名、亲戚饭桌上被 comparison、领导开会拿他当反面典型。"
        "他说出来的话要像从牙缝里挤出来的，不是鸡汤。"
        "输出格式：【第X条】(每条约40-70字)。"
        "修辞要求：对仗/对比/反转至少用一种。"
        "禁止词：没有人能替、我命由我不由天、不逼自己、半生归来仍少年、今天你爱答不理、没有伞的孩子、既然选择了远方。"
        "风格：像在深夜茶桌旁跟自己说真话。"
    ),
    "D2": (
        "一个咬牙硬扛的中年人。他经历过：连续加班72小时、医院走廊过夜、给孩子交费时算了四遍。"
        "他不喊疼，因为他知道喊了也没人替。"
        "输出格式：【第X条】(每条约40-70字)。"
        "修辞要求：必须用对比或反转。"
        "禁止词：熬过就好了、成功属于坚持的人、吃得苦中苦。"
        "风格：钝刀子割肉的感觉——不流血但疼。"
    ),
    "D3": (
        "一个孤军奋战的人。身后空无一人，所以不能倒。"
        "经历过：客户跑路只剩自己、团队解散自己兼三个人的活、过年没人约。"
        "输出格式：【第X条】(每条约40-70字)。"
        "修辞要求：对仗为主。"
        "禁止词：一个人也能发光、孤独是强者的宿命。"
        "风格：不是悲情，是认清后的平静前行。"
    ),
    "D4": (
        "一个沉默行动的人。不说只做。"
        "经历过：被质疑能力后用结果回应、被人说空话后用行动证明。"
        "输出格式：【第X条】(每条约40-70字)。"
        "修辞要求：对比+反转。"
        "禁止词：用行动说话、做给你看、不说话。"
        "风格：少说多做的人，话从不在嘴上但在手上。"
    ),
    "D5": (
        "一个被现实刺痛过并改变的人。"
        "经历过：体检报告异常项、银行卡余额告急、被信任的人背刺。"
        "输出格式：【第X条】(每条约40-70字)。"
        "修辞要求：反转。"
        "禁止词：吃一堑长一智、被打醒、痛过成长。"
        "风格：刺痛之后的清醒——不是愤怒，是明白了。"
    ),
    "D6": (
        "一个还在翻身路上的人。还没到顶但已经在爬。"
        "经历过：从谷底爬起来第一步、第一次赚到超出预期的钱、第一次被人尊重。"
        "输出格式：【第X条】(每条约40-70字)。"
        "修辞要求：对仗。"
        "禁止词：翻身、逆袭、成功、暴富。"
        "风格：在路上的人最踏实，不在山顶但在上坡。"
    ),
    "D7": (
        "一个中年清醒的人。看透但不消极。"
        "经历过：见过老板破产、朋友翻脸、父母老去。"
        "输出格式：【第X条】(每条约40-70字)。"
        "修辞要求：对比。"
        "禁止词：中年危机、佛系、躺平、看破红尘。"
        "风格：像泡了一壶陈年老茶——苦过回甘。"
    ),
    "D8": (
        "一个理解父亲责任感的儿子。"
        "经历过：发现父亲藏起来的药单、看到父亲记账本、父亲戒烟后咳嗽的清晨。"
        "输出格式：【第X条】(每条约40-70字)。"
        "修辞要求：对仗+反转。"
        "禁止词：父爱如山、父亲伟大、感恩。"
        "风格：理解但不煽情，像一个男人对另一个男人说话。"
    ),
    "D9": (
        "一个经历婚姻沉默和默契的人。"
        "经历过：结婚十年不再说我爱你、吵架后各自刷手机但都记得给对方留一盏灯。"
        "输出格式：【第X条】(每条约40-70字)。"
        "修辞要求：对比。"
        "禁止词：婚姻是坟墓、白头偕老、執子之手。"
        "风格：婚姻里的沉默不是不爱了，是太懂了。"
    ),
    "D10": (
        "一个享受孤独但也承受孤独的人。"
        "经历过：深夜一个人坐在车里不上楼、凌晨刷招聘软件、手机1%电量的焦虑、戒烟后咳嗽的清晨。"
        "输出格式：【第X条】(每条约40-70字)。"
        "修辞要求：反转或对比。"
        "禁止词：享受孤独、一个人也很好、孤独是种生活。"
        "风格：孤独但不矫情，像深夜茶桌上的一杯凉透了的茶。"
    ),
}


def generate_quotes_by_dimension(dimensions, count_per_dim=5):
    """
    根据维度标签生成原创语录（通过 LLM API）
    Args:
        dimensions: 维度标签列表，如 ["D1", "D3", "D5"]
        count_per_dim: 每个维度生成几条（建议1-3条）
    Returns:
        list of generated quote texts
    """
    # 此函数后续会对接 LLM API（DeepSeek/Claude），这里返回占位
    # 调用示例：generate_quotes_by_dimension(["D1", "D7"], count_per_dim=1)
    raise NotImplementedError("需要配置 DeepSeek API key 使用自动生成功能")


def sample_quote(template_name="扎心励志", randomize=True, dimension=None, **kwargs):
    """获取预设语录模板的示例文本
    Args:
        template_name: 模板名称（如'扎心励志''翻身语录''沉默行动'）
        randomize: 是否随机选择（True=每次随机一条）
        dimension: 可选，维度标签（如'D1'），用于 LLM 动态生成
    """
    import random
    if template_name not in QUOTE_TEMPLATES:
        raise ValueError(f"未知模板: {template_name}，可选: {list(QUOTE_TEMPLATES.keys())}")
    versions = QUOTE_TEMPLATES[template_name]
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
