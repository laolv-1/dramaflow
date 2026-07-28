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
import re
import threading
import urllib.request
import urllib.error
from pathlib import Path


# ---------------------------------------------------------------------------
# Mossland TTS Client（简化版，依赖 generator.py 中的完整实现）
# ---------------------------------------------------------------------------

class DouyinTTS:
    MOSS_API_BASE = "https://api.mosi.cn/v1"
    DEFAULT_VOICE_ID = "fa435ac6-416a-4676-b138-a6ff8380e7cf"
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
        """用预设或克隆音色合成 TTS 音频（moss-tts 8B 模型）"""
        vid = voice_id or self.default_voice_id
        payload = {
            "model": self.MODEL,
            "input": text,
            "voice_id": vid,
            "response_format": "mp3",
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
# 语录池 — 按需生成，逐条追加
# ============================================================
_quote_pool = []
_pool_lock = threading.Lock()
_pool_built = False


def _build_quote_pool(force=False):
    """构建/扩充语录池"""
    global _quote_pool, _pool_built

    with _pool_lock:
        if len(_quote_pool) >= 15 and not force:
            return _quote_pool  # 已有足够语录

        print(f"  [QuotePool] 正在通过 LLM 生成语录 (当前 {len(_quote_pool)} 条)...")
        try:
            dim_pool = ["D1", "D2", "D3", "D4"]
            # 每次只生成5条（避免超时）
            batch_size = min(5, 15 - len(_quote_pool))
            selected_dims = [dim_pool[i % len(dim_pool)] for i in range(batch_size)]
            raw = generate_quotes_by_dimension(selected_dims, count_per_dim=1)

            # 多策略解析 LLM 返回的语录
            new_quotes = []
            if '【第' in raw:
                parts = re.split(r'【第\d+条】', raw)[1:]
                new_quotes = [q.strip() for q in parts if q.strip()]
            elif re.search(r'第[一二三四五六七八九十\d]+条', raw):
                parts = re.split(r'第[一二三四五六七八九十\d]+条\s*[:：]?\s*', raw)
                new_quotes = [q.strip() for q in parts if q.strip()]
            else:
                # 按空行分割，每条应该至少50字
                blocks = re.split(r'\n\s*\n', raw)
                new_quotes = [b.strip() for b in blocks if len(b.strip()) >= 40]

            if not new_quotes:
                # LLM 可能返回了一条长文本
                new_quotes = [raw.strip()] if raw.strip() else []

            _quote_pool.extend(new_quotes[:batch_size])
            print(f"  [QuotePool] LLM 生成了 {len(new_quotes)} 条，池中现有 {len(_quote_pool)} 条")
            if len(_quote_pool) >= 15:
                _pool_built = True
        except Exception as e:
            print(f"  [QuotePool] LLM 失败 ({e})，回退到硬编码")
            import traceback
            traceback.print_exc()
            if not _quote_pool:
                _quote_pool = _get_hardcoded_pool()
            _pool_built = False

    return _quote_pool


def _get_hardcoded_pool():
    """硬编码回退语录池"""
    all_versions = []
    for versions in QUOTE_TEMPLATES.values():
        all_versions.extend(versions)
    return list(all_versions) if all_versions else [
        "没有人帮你，你就自己帮自己。想都是问题，做才有答案。",
        "你在电梯里整理领带的那三十秒，是在把刚被骂了一顿的自己重新拼成人形。",
        "体检报告上多出来的那个箭头，比任何鸡汤都管用。",
        "凌晨两点从医院走廊醒来的时候——这世上大部分难熬的事，都是一咬牙捱过来的。",
        "孩子交学费那张单子你翻了三遍——把无声的风暴折起来，塞进钱包。",
    ]

_DIMENSION_LABELS = {
    "D1": "低谷救赎",
    "D2": "改名改命",
    "D3": "认知觉醒",
    "D4": "品茶悟道",
}


_GENERATION_PROMPTS = {
    "D1": (
        "标签：低谷救赎。\n"
        "情绪核：跌到最底，才知道什么是真的。\n"
        "写法要点：不要写怎么爬起来的，写\"跌到底的那一刻看到了什么\"。\n"
        "用茶桌隐喻：一杯茶见底了，才知道杯底有行字。\n"
        "字数：120-180字（约30秒口播）。"
    ),
    "D2": (
        "标签：改名改命。\n"
        "情绪核：你不是改了一个名字，是决定换一种活法。\n"
        "写法要点：写那个决定性的瞬间——是什么让你决定不再做原来的自己。\n"
        "茶桌旁的决定：茶凉了可以续，人走错了可以回头。\n"
        "字数：120-180字（约30秒口播）。"
    ),
    "D3": (
        "标签：认知觉醒。\n"
        "情绪核：人不是慢慢变好的，是一瞬间醒过来的。\n"
        "写法要点：写那个\"开窍\"的瞬间——之前想不通的，突然通透了。\n"
        "就像喝茶的第一口觉得苦，第五口才尝到回甘。\n"
        "字数：120-180字（约30秒口播）。"
    ),
    "D4": (
        "标签：品茶悟道。\n"
        "情绪核：茶桌上没有新鲜事，但每壶茶都能泡出新道理。\n"
        "写法要点：用茶的全过程映射人生——洗茶、泡茶、斟茶、品茶、回味。\n"
        "茶宠被热水浇了八年才养出包浆，人也是。\n"
        "字数：120-180字（约30秒口播）。"
    ),
}


def generate_quotes_by_dimension(dimensions, count_per_dim=1):
    """通过 DeepSeek API 生成原创语录"""
    # 获取 DeepSeek key
    base_dir = Path(__file__).parent.parent.parent / ".env"
    if not base_dir.exists():
        base_dir = Path(__file__).parent / ".env"
    if not base_dir.exists():
        return _sample_hardcoded_quote()

    ds_key = None
    with open(base_dir, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("DEEPSEEK_API_KEY="):
                ds_key = line.split("=", 1)[1].strip()
                break

    if not ds_key:
        return _sample_hardcoded_quote()

    total_count = sum(count_per_dim for _ in dimensions)

    # 构建每个维度的提示
    dim_prompts = []
    for d in dimensions:
        label = _DIMENSION_LABELS.get(d, d)
        gen_prompt = _GENERATION_PROMPTS.get(d, "")
        dim_prompts.append(f"\n{d}={label}\n{gen_prompt}")

    prompt = (
        f"请用以下维度各写{count_per_dim}条语录，共{total_count}条：\n\n"
        + "".join(dim_prompts)
    )

    system_prompt = (
        "你是\"艾公\"风格的金句写手。核心：一句话就是一把刀。不说故事，不说教，只说结论。\n\n"
        "主题：低谷救赎 · 改名改命 · 认知觉醒 · 品茶悟道\n\n"
        f"输出格式：每次必须输出 {total_count} 条独立语录，格式：\n\n"
        "【第X条】\n(80-130字)\n\n"
        "写作铁律：\n"
        '1. 全程"你"——像指着鼻子对一个人说话\n'
        "2. 每句8-20字。不要长句。\n"
        "3. 开头第一个字就要用力——\"你记住\"、\"听好\"、\"别装了\"、\"摔碎了就是摔碎了\"\n"
        "4. 必须有反转。前一句把你按下去，后一句把你拽起来。\n"
        "5. 茶/杯/壶做隐喻，但不要绕——直接说。\n"
        "6. 禁用任何网上泛滥的金句。\n"
        "7. 结尾不要升华。戛然而止。\n"
        "8. 越短越有力。\n\n"
        f"直接输出 {total_count} 条。不要解释，不要多余格式。"
    )

    try:
        payload = json.dumps({
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.9,
            "max_tokens": 2000,
        }).encode()

        req = urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {ds_key}", "Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=60)
        result = json.loads(resp.read().decode())
        content = result["choices"][0]["message"]["content"]
        print(f"  [LLM] 生成 {total_count} 条语录，长度: {len(content)} chars")
        return content
    except Exception as e:
        print(f"  [LLM] 生成失败: {e}，回退到硬编码文案")
        return _sample_hardcoded_quote()


def _sample_hardcoded_quote():
    """LLM 不可用时回退到硬编码文案"""
    import random
    all_versions = []
    for versions in QUOTE_TEMPLATES.values():
        all_versions.extend(versions)
    if not all_versions:
        return "没有人帮你，你就自己帮自己。想都是问题，做才有答案。"
    return random.choice(all_versions)


def sample_quote(template_name="扎心励志", randomize=True, dimension=None, llm=True, **kwargs):
    """获取语录 — 优先从池子里随机拿"""
    # 触发池子构建（如果有 LLM 能力）
    _build_quote_pool()

    import random
    if _quote_pool:
        return random.choice(_quote_pool)

    # 硬编码回退
    if template_name not in QUOTE_TEMPLATES:
        raise ValueError(f"未知模板: {template_name}")
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
