"""DramaFlow 网页版策划案生成器

启动方式:
    python web_app.py

然后浏览器访问: http://localhost:5000
"""

import os
import sys
import json
import time
import re
import threading
from pathlib import Path
from typing import Optional
from generator import EpisodeGenerator
from trend_researcher import TrendResearcher
from key_manager import KeyManager

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

_generation_status = {
    "running": False,
    "progress": "",
    "percentage": 0,
    "result": None,
    "error": None,
}

_cached_plans = []

_research_status = {
    "running": False,
    "progress": "",
    "percentage": 0,
    "result": None,
    "error": None,
}

# 缓存最后一次调研结果（供生成策划案时使用）
_cached_research_result = None
    """递归查找任意键名的值，兼容各种字段名变体"""
    if not isinstance(data, dict):
        return default
    # 先尝试直接匹配
    for k in keys:
        if k in data:
            return data[k]
    # 模糊匹配（忽略大小写、下划线、连字符）
    def normalize(k):
        return re.sub(r'[_\-\s]', '', k.lower())
    target = normalize(keys[0]) if keys else ''
    for k, v in data.items():
        if normalize(k) == target and v:
            return v
    return default


def _extract_title(data):
    """从任意结构的JSON中提取剧名"""
    # 常见路径
    title = _find(data, "project.title", default=_find(data.get("project", {}), "title", default=None))
    if title:
        return title
    # 从 project_info 找
    pi = data.get("project_info", {})
    if isinstance(pi, dict):
        title = _find(pi, "title", "剧名", "name", default=None)
        if title:
            return title
    # 从 episodes 中找
    for ep_key in ["episodes", "episode_outline"]:
        eps = data.get(ep_key, [])
        if isinstance(eps, list) and eps:
            t = _find(eps[0], "title", "剧名", "episode_title", default=None)
            if t:
                return t
    return "未命名"


def _extract_project_info(data):
    """从任意结构中抽取项目信息"""
    project = data.get("project", {}) or {}
    project_info = data.get("project_info", {}) or {}

    info = {}
    # 合并两个可能的对象
    combined = {**project_info, **project}

    info["title"] = _find(project, "title", default=_find(project_info, "title", default="未命名"))
    info["genre"] = _find(combined, "genre", "题材", default="-")
    info["target_audience"] = _find(combined, "target_audience", "受众", default="-")
    info["episode_duration"] = _find(combined, "episode_duration", "每集时长", default="-")
    info["total_episodes"] = _find(combined, "total_episodes", "总集数", default="-")
    info["visual_style"] = _find(combined, "visual_style", "视觉风格", default="-")

    # logline / one_line_intro
    info["logline"] = (_find(project, "logline", default=None) or
                       _find(project_info, "one_line_intro", "logline", default=None) or
                       _find(data.get("story_synopsis", {}), "logline", default=None))
    info["synopsis"] = (_find(project, "synopsis", default=None) or
                        _find(project_info, "synopsis", default=None) or
                        _find(data.get("story_synopsis", {}), "synopsis", default=None))

    return info


def _extract_characters(data):
    """提取角色列表"""
    chars = data.get("characters", [])
    if not chars or not isinstance(chars, list):
        return []
    result = []
    for c in chars:
        if not isinstance(c, dict):
            continue
        char = {
            "name": c.get("name", "未知"),
            "age": c.get("age", "-"),
            "gender": c.get("gender", "-"),
            "occupation": c.get("occupation", "-"),
            "personality": c.get("personality", "-"),
            "appearance": c.get("appearance", ""),
            "backstory": c.get("backstory", ""),
        }
        # wardrobe: 可能是列表、字符串
        w = c.get("wardrobe", "")
        if isinstance(w, list):
            char["wardrobe"] = w
        elif isinstance(w, str) and w and w.strip():
            # 尝试用中文标点分割
            for sep in ['；', ';', '。', '；', '；']:
                parts = [s.strip() for s in w.split(sep) if s.strip()]
                if len(parts) > 1:
                    char["wardrobe"] = parts
                    break
            else:
                char["wardrobe"] = [w]
        else:
            char["wardrobe"] = []

        # image_prompts: 可能是字符串、对象
        ip = c.get("image_prompts", "")
        if isinstance(ip, dict):
            char["image_prompt_default"] = ip.get("base", "")
            char["variants"] = ip.get("variants", {})
        elif isinstance(ip, str) and ip:
            char["image_prompt_default"] = ip
            char["variants"] = {}
        else:
            char["image_prompt_default"] = ""
            char["variants"] = {}

        # variants 可能是列表
        v = char["variants"]
        if isinstance(v, list):
            new_v = {}
            for item in v:
                if isinstance(item, dict):
                    new_v[item.get("name", "unknown")] = item.get("image_prompt", "")
            char["variants"] = new_v
        elif not isinstance(v, dict):
            char["variants"] = {}

        result.append(char)
    return result


def _extract_episodes(data):
    """提取分集大纲 — 兼容 episodes / episode_outline / episode_1 等各种字段名"""
    # 先找 episodes 数组
    episodes = data.get("episodes", [])
    if not episodes or not isinstance(episodes, list):
        # 再找 episode_outline
        episodes = data.get("episode_outline", [])
    if not episodes or not isinstance(episodes, list):
        # 最后找 episode_1, episode_2 等
        for key in data:
            if key.startswith("episode_") and key != "episodes":
                val = data[key]
                if isinstance(val, dict) and "scenes" in val:
                    # 转为标准格式
                    val["episode_number"] = val.get("episode_number", int(key.split("_")[-1]))
                    episodes = [val]
                    break
                elif isinstance(val, list):
                    episodes = val
                    break

    if not episodes or not isinstance(episodes, list):
        return []

    result = []
    for ep in episodes:
        if not isinstance(ep, dict):
            continue
        scene_list = ep.get("scenes", [])
        if not scene_list:
            continue

        scenes = []
        for s in scene_list:
            if not isinstance(s, dict):
                continue
            scene = {
                "scene_id": s.get("scene_id", ""),
                "slugline": s.get("slugline", ""),
                "name": s.get("name", ""),
                "location": s.get("location", "-"),
                "time": s.get("time", "-"),
                "weather": s.get("weather", "-"),
                "mood": s.get("mood", ""),
                "props": s.get("props", "-"),
                "characters_present": s.get("characters_present", []),
                "action": s.get("action", ""),
                "narration": s.get("narration", ""),
                "narration_voice": s.get("narration_voice", ""),
                "narration_rate": s.get("narration_rate", ""),
                "dialogues": s.get("dialogues", []),
                "image_prompt": s.get("image_prompt", ""),
                "video_prompt": s.get("video_prompt", ""),
                "transition": s.get("transition", "cut"),
            }
            # props 可能是列表
            if isinstance(scene["props"], list):
                scene["props"] = "、".join(scene["props"])
            scenes.append(scene)

        result.append({
            "episode_number": ep.get("episode_number", 1),
            "title": ep.get("title", ep.get("episode_title", "")),
            "hook": ep.get("hook", ep.get("cliffhanger", "")),
            "scenes": scenes,
        })
    return result


def _extract_production(data):
    """提取制作规格"""
    ps = data.get("production_specs", {}) or {}
    return {
        "resolution": ps.get("resolution", "1080x1920 (竖屏9:16)"),
        "frame_rate": ps.get("frame_rate", "24fps"),
        "segment_duration": ps.get("segment_duration", "5秒"),
    }


def _generate_markdown(project_info, characters, episodes, production):
    """从标准化数据生成Markdown字符串"""
    md = []
    title = project_info.get("title", "未命名")

    md.append(f"# 《{title}》")
    md.append("")
    md.append("> **短剧项目策划案**")
    md.append("")
    md.append("---")
    md.append("")

    # 一、项目概况
    md.append("## 一、项目概况")
    md.append("")
    md.append("| 项目 | 内容 |")
    md.append("|------|------|")
    md.append(f"| **剧名** | {project_info.get('title', '-')}|")
    md.append(f"| **题材** | {project_info.get('genre', '-')}|")
    md.append(f"| **目标受众** | {project_info.get('target_audience', '-')}|")
    md.append(f"| **总集数** | {project_info.get('total_episodes', '-')}|")
    md.append(f"| **每集时长** | {project_info.get('episode_duration', '-')}|")
    md.append(f"| **视觉风格** | {project_info.get('visual_style', '-')}|")
    md.append(f"| **分辨率** | {production.get('resolution', '-')}|")
    md.append(f"| **帧率** | {production.get('frame_rate', '-')}|")
    md.append("")

    if project_info.get("logline"):
        md.append("### 一句话简介")
        md.append("")
        md.append(f"> {project_info['logline']}")
        md.append("")

    if project_info.get("synopsis"):
        md.append("### 故事梗概")
        md.append("")
        md.append(project_info["synopsis"])
        md.append("")

    # 二、角色设定
    md.append("---")
    md.append("")
    md.append("## 二、角色设定")
    md.append("")

    mood_map = {
        'dark': '压抑黑暗', 'warm': '温暖', 'tense': '紧张激烈',
        'sad': '悲凉绝望', 'joyful': '希望昂扬', 'mysterious': '神秘未知'
    }

    for idx, char in enumerate(characters, 1):
        md.append(f"### {idx}.{char.get('name', '未知')}")
        md.append("")
        md.append("| 属性 | 详情 |")
        md.append("|------|------|")
        md.append(f"| **年龄** | {char.get('age', '-')}|")
        md.append(f"| **性别** | {char.get('gender', '-')}|")
        md.append(f"| **身份** | {char.get('occupation', '-')}|")
        md.append(f"| **性格** | {char.get('personality', '-')}|")
        md.append(f"| **背景故事** | {char.get('backstory', '-')}|")
        md.append("")

        if char.get('appearance'):
            md.append("#### 外貌特征")
            md.append("")
            md.append(char['appearance'])
            md.append("")

        if char.get('wardrobe'):
            md.append("#### 服装造型")
            md.append("")
            md.append("| 阶段 | 造型描述 |")
            md.append("|------|----------|")
            for i, item in enumerate(char['wardrobe'], 1):
                md.append(f"| **造型{i}** | {item}|")
            md.append("")

        md.append("#### 画面提示词")
        md.append("")
        variants = char.get('variants', {})
        if variants:
            for vname, vprompt in variants.items():
                md.append(f"- **{vname}**: {vprompt}")
        default_prompt = char.get('image_prompt_default', '')
        if default_prompt:
            md.append("")
            md.append(f"- **默认**: {default_prompt}")
        md.append("")
        md.append("---")
        md.append("")

    # 三、分集大纲
    md.append("")
    md.append("## 三、分集大纲")
    md.append("")

    for ep in episodes:
        ep_num = ep.get('episode_number', 1)
        ep_title = ep.get('title', '')
        hook = ep.get('hook', '')

        md.append(f"### 第{ep_num}集《{ep_title}》")
        md.append("")
        if hook:
            md.append(f"> **本集钩子**：{hook}")
            md.append("")

        meta = [
            f"**集数**：第{ep_num}集 / 共{project_info.get('total_episodes', 80)}集",
            f"**标题**：{ep_title}",
            f"**时长**：约{project_info.get('episode_duration', '2分钟')}",
            f"**场景数量**：{len(ep.get('scenes', []))}个",
        ]
        md.append("\n".join(meta))
        md.append("")
        md.append("---")
        md.append("")

        for scene in ep.get('scenes', []):
            sid = scene.get('scene_id', '')
            sname = scene.get('name', '')
            slugline = scene.get('slugline', '')

            display_name = sname.replace('_', ' ') if sname else f"场景{sid}"
            md.append(f"#### 场景{sid}：{display_name}")
            md.append("")

            md.append("| 字段 | 内容 |")
            md.append("|------|------|")
            md.append(f"| **场景编号** | {sid}|")
            md.append(f"| **地点** | {scene.get('location', '-')}|")
            md.append(f"| **时间** | {scene.get('time', '-')}|")
            md.append(f"| **天气** | {scene.get('weather', '-')}|")
            md.append(f"| **氛围** | {mood_map.get(scene.get('mood', ''), scene.get('mood', '-'))}|")
            md.append(f"| **道具** | {scene.get('props', '-')}|")
            chars_p = ', '.join(scene.get('characters_present', []))
            md.append(f"| **出场人物** | {chars_p}|")
            md.append("")

            if scene.get('action'):
                md.append(f"**剧情**：{scene['action']}")
                md.append("")

            md.append(f"*旁白*：{scene.get('narration', '（无）')}")
            md.append("")

            dialogues = scene.get('dialogues', [])
            if dialogues:
                md.append("**台词**：")
                md.append("")
                for d in dialogues:
                    if isinstance(d, dict):
                        md.append(f"> **{d.get('character', '')}**：{d.get('text', '')}")
                md.append("")
            else:
                md.append("**台词**：（无）")
                md.append("")

            if scene.get('image_prompt'):
                md.append(f"**画面提示**：{scene['image_prompt']}")
                md.append("")

            if scene.get('video_prompt'):
                md.append(f"**运镜**：{scene['video_prompt']}")
                md.append("")

            md.append(f"**转场**：{scene.get('transition', 'cut（硬切）')}")
            md.append("")
            md.append("---")
            md.append("")

    # 四、制作规格
    md.append("")
    md.append("## 四、制作规格")
    md.append("")
    md.append("| 参数 | 标准 |")
    md.append("|------|------|")
    md.append(f"| **分辨率** | {production.get('resolution', '-')}|")
    md.append(f"| **帧率** | {production.get('frame_rate', '-')}|")
    md.append(f"| **分段时长** | {production.get('segment_duration', '-')}|")
    md.append(f"| **视觉风格** | {project_info.get('visual_style', '-')}|")
    md.append("")
    md.append("---")
    md.append("")
    md.append("*策划案生成完毕*")
    md.append("")

    return "\n".join(md)


def _generate_worker(generator: EpisodeGenerator, user_prompt: str, prompt_type: str, research_result: Optional[dict] = None):
    """后台线程执行生成任务"""
    _generation_status["running"] = True
    _generation_status["progress"] = "正在生成策划案..."
    _generation_status["percentage"] = 20

    try:
        if research_result:
            _generation_status["progress"] = "基于调研结果生成策划案..."
            result = generator.generate_with_research(
                theme=user_prompt,
                genre="玄幻修仙",
                episode_count=12,
                total_episodes=80,
                research_result=research_result,
            )
        elif prompt_type == "story":
            result = generator.generate_from_story(user_prompt, episode_count=12, total_episodes=80)
        else:
            result = generator.generate_from_theme(user_prompt, genre="玄幻修仙", episode_count=12, total_episodes=80)

        _generation_status["progress"] = "正在保存策划案..."
        _generation_status["percentage"] = 80

        # 提取剧名（兼容各种字段名）
        title = _extract_title(result)
        if not title or title == "未命名":
            title = "未命名"

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)
        filename = f"{timestamp}_{safe_title}.json"
        filepath = OUTPUT_DIR / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        # 生成Markdown策划案
        md_filename = f"{timestamp}_{safe_title}_策划案.md"
        md_filepath = OUTPUT_DIR / md_filename

        # 标准化提取数据
        project_info = _extract_project_info(result)
        characters = _extract_characters(result)
        episodes = _extract_episodes(result)
        production = _extract_production(result)

        # 生成Markdown
        md_content = _generate_markdown(project_info, characters, episodes, production)
        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write(md_content)

        _generation_status["percentage"] = 100
        _generation_status["result"] = {
            "title": project_info.get("title", title),
            "filename": filename,
            "filepath": str(filepath),
            "md_filename": md_filename,
            "characters": len(characters),
            "scenes": sum(len(ep.get("scenes", [])) for ep in episodes),
        }

        _refresh_plan_list()

    except Exception as e:
        _generation_status["error"] = str(e)
        _generation_status["progress"] = f"生成失败: {e}"
        _generation_status["percentage"] = 0
        import traceback
        traceback.print_exc()

    finally:
        _generation_status["running"] = False


def _refresh_plan_list():
    """刷新已生成策划案列表"""
    global _cached_plans
    _cached_plans = []
    for f in sorted(OUTPUT_DIR.glob("*_策划案.md")):
        _cached_plans.append({
            "name": f.stem,
            "filename": f.name,
            "size": f.stat().st_size,
            "path": str(f),
        })


def _research_worker(user_idea: str):
    """后台线程执行调研任务"""
    global _research_status, _cached_research_result
    _research_status["running"] = True
    _research_status["progress"] = "正在调研热门榜..."
    _research_status["percentage"] = 10

    try:
        researcher = TrendResearcher(config_dir=str(BASE_DIR))

        _research_status["progress"] = "抓取抖音/快手热榜..."
        _research_status["percentage"] = 20

        _research_status["progress"] = "抓取TikTok/YouTube热门..."
        _research_status["percentage"] = 40

        _research_status["progress"] = "本地数据整理..."
        _research_status["percentage"] = 60

        result = researcher.research(user_idea=user_idea, use_deepseek=True)

        _research_status["progress"] = "正在生成调研摘要..."
        _research_status["percentage"] = 80

        _cached_research_result = result
        _research_status["result"] = {
            "id": result.get("id", ""),
            "timestamp": result.get("timestamp", ""),
            "sources_covered": result.get("local_analysis", {}).get("sources_covered", 0),
            "hot_keywords": result.get("local_analysis", {}).get("hot_keywords", [])[:10],
            "deepseek_insight": result.get("deepseek_insight", {}).get("raw_insight", ""),
            "user_idea": user_idea,
        }
        _research_status["percentage"] = 100
        _research_status["progress"] = "调研完成"

    except Exception as e:
        _research_status["error"] = str(e)
        _research_status["progress"] = f"调研失败: {e}"
        _research_status["percentage"] = 0
        import traceback
        traceback.print_exc()
    finally:
        _research_status["running"] = False


@app.route("/")
def index():
    _refresh_plan_list()
    return render_template("index.html", plans=_cached_plans)


@app.route("/api/status")
def get_status():
    return jsonify(_generation_status)


@app.route("/api/research", methods=["POST"])
def research():
    """启动热门榜调研"""
    if _research_status["running"]:
        return jsonify({"error": "调研任务正在进行中，请稍后再试"})

    data = request.json
    user_idea = data.get("idea", "").strip()

    thread = threading.Thread(
        target=_research_worker,
        args=(user_idea,),
        daemon=True,
    )
    thread.start()
    return jsonify({"success": True, "message": "调研任务已启动"})


@app.route("/api/research_status")
def research_status():
    """查询调研进度"""
    return jsonify(_research_status)


@app.route("/api/research_cache")
def research_cache():
    """获取缓存的调研结果"""
    if _cached_research_result:
        return jsonify({
            "success": True,
            "result": _cached_research_result.get("result"),
        })
    return jsonify({"success": False, "message": "暂无缓存的调研结果"})


@app.route("/api/generate", methods=["POST"])
def generate():
    if _generation_status["running"]:
        return jsonify({"error": "已有生成任务正在进行中，请稍后再试"})

    data = request.json
    prompt_type = data.get("type", "theme")
    prompt_text = data.get("prompt", "").strip()
    use_research = data.get("use_research", False)

    if not prompt_text:
        return jsonify({"error": "请输入故事主题或内容"})

    km = KeyManager(config_dir=str(BASE_DIR))
    api_key = km.get_key("deepseek")
    if not api_key:
        return jsonify({"error": "未配置DeepSeek API Key，请先在设置页面配置"})

    try:
        # 如果有调研结果，用pro做分析；否则用flash生成策划案
        if use_research and _cached_research_result:
            # 先用pro做分析（实际上调研时已经分析过了，这里直接生成）
            gen = EpisodeGenerator(model="deepseek-v4-flash", thinking_enabled=False)
            gen.client = type(gen.client)(api_key=api_key, base_url="https://api.deepseek.com")

            thread = threading.Thread(
                target=_generate_worker,
                args=(gen, prompt_text, prompt_type, _cached_research_result),
                daemon=True,
            )
        else:
            gen = EpisodeGenerator(model="deepseek-v4-flash", thinking_enabled=False)
            gen.client = type(gen.client)(api_key=api_key, base_url="https://api.deepseek.com")

            thread = threading.Thread(
                target=_generate_worker,
                args=(gen, prompt_text, prompt_type, None),
                daemon=True,
            )
        thread.start()

        return jsonify({"success": True, "message": "生成任务已启动"})
    except Exception as e:
        return jsonify({"error": f"启动失败: {str(e)}"})


@app.route("/api/save_key", methods=["POST"])
def save_key():
    data = request.json
    key_value = data.get("key", "").strip()
    if not key_value:
        return jsonify({"error": "API Key不能为空"})
    km = KeyManager(config_dir=str(BASE_DIR))
    km.set_key("deepseek", key_value)
    return jsonify({"success": True, "message": "API Key 已保存"})


@app.route("/api/plan_list")
def plan_list():
    _refresh_plan_list()
    return jsonify({"plans": _cached_plans})


@app.route("/api/download/<path:filename>")
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename)


if __name__ == "__main__":
    print("=" * 50)
    print("  DramaFlow 网页版策划案生成器")
    print("  浏览器访问: http://localhost:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)
