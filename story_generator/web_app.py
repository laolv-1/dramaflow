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
from flask import Flask, render_template, request, jsonify, send_from_directory,send_file
from typing import Optional
from generator import EpisodeGenerator, TTSClient
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


def _find(data, *keys, default=None):
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


def _continue_worker(generator: EpisodeGenerator, prev_data: dict, target_episode: int, config_dir: str):
    """后台线程执行续集生成任务
    Args:
        generator: EpisodeGenerator实例
        prev_data: 已有策划案的完整JSON数据
        target_episode: 要生成的集数
        config_dir: 配置文件目录
    """
    _generation_status["running"] = True
    _generation_status["progress"] = f"正在生成第{target_episode}集..."
    _generation_status["percentage"] = 20

    try:
        result = generator.generate_continuation(prev_data, target_episode)

        _generation_status["progress"] = "正在保存策划案..."
        _generation_status["percentage"] = 80

        title = _extract_title(result)
        if not title or title == "未命名":
            title = "未命名"

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c if c not in '\\/:*?"<>|' else '_' for c in title)
        ep_str = f"Ep{target_episode:02d}"
        filename = f"{timestamp}_{safe_title}_{ep_str}.json"
        filepath = OUTPUT_DIR / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        # 生成Markdown策划案
        md_filename = f"{timestamp}_{safe_title}_{ep_str}_策划案.md"
        md_filepath = OUTPUT_DIR / md_filename

        project_info = _extract_project_info(result)
        characters = _extract_characters(result)
        episodes = _extract_episodes(result)
        production = _extract_production(result)

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
            "episode": target_episode,
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


def _generate_worker(generator: EpisodeGenerator, user_prompt: str, input_type: str, genre: str,
                      target_audience: Optional[str], research_result: Optional[dict]):
    """后台线程执行生成任务

    Args:
        generator: EpisodeGenerator实例
        user_prompt: 用户输入（主题或小说内容）
        input_type: "theme"=原创方向, "story"=故事文本, "novel"=小说改编
        genre: 题材类型（动态传入）
        target_audience: 目标受众（可选）
        research_result: 调研结果（可选，仅对theme模式生效）
    """
    _generation_status["running"] = True
    _generation_status["progress"] = "正在生成策划案..."
    _generation_status["percentage"] = 20

    try:
        if input_type == "novel":
            # 小说改编模式
            result = generator.generate_from_novel(user_prompt, episode_count=12, total_episodes=80)
        elif research_result:
            _generation_status["progress"] = "基于调研结果生成策划案..."
            result = generator.generate_with_research(
                theme=user_prompt,
                genre=genre,
                episode_count=12,
                total_episodes=80,
                research_result=research_result,
                target_audience=target_audience,
            )
        elif input_type == "story":
            result = generator.generate_from_story(
                user_prompt, episode_count=12, total_episodes=80, genre=genre, target_audience=target_audience
            )
        else:
            result = generator.generate_from_theme(
                user_prompt, genre=genre, episode_count=12, total_episodes=80, target_audience=target_audience
            )

        _generation_status["progress"] = "正在保存策划案..."
        _generation_status["percentage"] = 80

        # 提取剧名（兼容各种字段名）
        title = _extract_title(result)
        if not title or title == "未命名":
            title = "未命名"

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c if c not in '\\/:*?"<>|' else '_' for c in title)
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


def _outline_worker(generator: EpisodeGenerator, theme: str, genre: str,
                     target_audience: Optional[str], research_result: Optional[dict],
                     config_dir: str):
    """后台线程执行大纲生成任务"""
    _generation_status["running"] = True
    _generation_status["progress"] = "正在生成故事大纲..."
    _generation_status["percentage"] = 20

    try:
        result = generator.generate_outline(
            theme=theme,
            genre=genre,
            total_episodes=80,
            research_context=str(research_result) if research_result else None,
            target_audience=target_audience,
        )

        _generation_status["progress"] = "正在保存大纲..."
        _generation_status["percentage"] = 80

        title = _extract_title(result)
        if not title or title == "未命名":
            title = "未命名"

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c if c not in '\\/:*?"<>|' else '_' for c in title)
        filename = f"{timestamp}_{safe_title}_Outline.json"
        filepath = OUTPUT_DIR / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        _generation_status["percentage"] = 100
        _generation_status["result"] = {
            "title": title,
            "filename": filename,
            "filepath": str(filepath),
            "outline_count": len(result.get("outline", [])),
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
    """刷新已生成策划案列表（只显示JSON源文件，因为只有JSON才能生成续集）"""
    global _cached_plans
    _cached_plans = []
    for f in sorted(OUTPUT_DIR.glob("*.json")):
        # 跳过 research_ 开头的调研文件
        if f.name.startswith("research_"):
            continue
        # 跳过旧格式转换文件
        if f.name in ("converted_episode_001.json", "episode_001.json", "output.lnk"):
            continue
        _cached_plans.append({
            "name": f.stem,
            "filename": f.name,
            "size": f.stat().st_size,
        })


def _research_worker(user_topic: str, category: str = "all"):
    """后台线程执行调研任务
    Args:
        user_topic: 调研主题/话题
        category: 调研类别 "hotlist"/"trend"/"industry"/"community"/"youtube"/"all"
    """
    global _research_status, _cached_research_result
    _research_status["running"] = True
    _research_status["progress"] = "正在调研行业数据..."
    _research_status["percentage"] = 10

    try:
        researcher = TrendResearcher(config_dir=str(BASE_DIR))

        category_name = {"hotlist": "热点排行榜", "trend": "搜索趋势", "industry": "行业数据",
                         "community": "内容社区", "youtube": "YouTube", "all": "全量"}[category]
        _research_status["progress"] = f"抓取{category_name}数据源..."
        _research_status["percentage"] = 20

        _research_status["progress"] = "本地数据整理..."
        _research_status["percentage"] = 50

        result = researcher.research(
            user_topic=user_topic,
            category=category,
            use_deepseek=True,
        )

        _research_status["progress"] = "正在生成调研摘要..."
        _research_status["percentage"] = 80

        _cached_research_result = result
        _research_status["result"] = {
            "id": result.get("id", ""),
            "timestamp": result.get("timestamp", ""),
            "sources_covered": result.get("local_analysis", {}).get("sources_covered", 0),
            "hot_words": result.get("local_analysis", {}).get("hot_words", [])[:10],
            "deepseek_insight": result.get("deepseek_insight", {}).get("raw_insight", ""),
            "user_topic": user_topic,
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
    """启动行业数据调研"""
    if _research_status["running"]:
        return jsonify({"error": "调研任务正在进行中，请稍后再试"})

    data = request.json
    user_topic = data.get("topic", "").strip()
    category = data.get("category", "all")  # hotlist / trend / industry / community / youtube / all

    thread = threading.Thread(
        target=_research_worker,
        args=(user_topic, category),
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
            "result": _cached_research_result,
        })
    return jsonify({"success": False, "message": "暂无缓存的调研结果"})


@app.route("/api/research_recommend", methods=["POST"])
def research_recommend():
    """基于调研结果生成推荐主题和题材"""
    if not _cached_research_result:
        return jsonify({"success": False, "message": "暂无缓存的调研结果，请先完成调研"})

    km = KeyManager(config_dir=str(BASE_DIR))
    api_key = km.get_key("deepseek")
    if not api_key:
        return jsonify({"error": "未配置DeepSeek API Key"})

    research = _cached_research_result

    # 提取调研数据
    deepseek_insight = research.get("deepseek_insight", {})
    if isinstance(deepseek_insight, dict):
        insight_text = deepseek_insight.get("raw_insight", "")
    else:
        insight_text = str(deepseek_insight) if deepseek_insight else ""

    local_analysis = research.get("local_analysis", {})
    hot_words = local_analysis.get("hot_words", [])
    hot_words_text = "\n".join([f"- {w.get('word','')}: {w.get('count',0)}次" for w in hot_words[:10]])

    user_topic = research.get("user_topic", "通用短剧趋势")

    prompt = f"""你是一个短剧策划师。刚完成了一次市场调研，调研主题：{user_topic}。

【热门关键词】
{hot_words_text}

【趋势分析】
{insight_text}

请根据以上调研数据，推荐3-5个最适合做短剧策划的主题方案。每个方案必须包含：
1. 题材类型（从以下选择：战神、龙王、赘婿、修仙、玄幻、异能、重生、穿越、逆袭、霸总、甜宠、虐恋、萌宝、宫斗、宅斗、都市、古装、悬疑、科幻、奇幻、历史、权谋、神医、其他）
2. 主题名称（简短有力，吸引眼球）
3. 推荐理由（结合调研数据，1-2句话说明为什么这个主题能爆）

【极其重要】你必须严格按照以下JSON格式输出，不要输出任何其他内容：
```json
[
  {{"genre": "题材", "theme": "主题名称", "reason": "推荐理由"}},
  {{"genre": "题材", "theme": "主题名称", "reason": "推荐理由"}}
]
```"""

    try:
        client = __import__('generator').generator.OpenAI(
            api_key=api_key, base_url="https://api.deepseek.com"
        )
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[
                {"role": "system", "content": "你是一个专业的短剧策划师，擅长根据市场数据推荐爆款主题。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            stream=False,
        )
        content = response.choices[0].message.content
        # 去除code fence
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        recommendations = json.loads(content)
        return jsonify({"success": True, "recommendations": recommendations})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/generate", methods=["POST"])
def generate():
    if _generation_status["running"]:
        return jsonify({"error": "已有生成任务正在进行中，请稍后再试"})

    data = request.json
    input_type = data.get("inputType", "theme")  # theme / novel
    prompt_text = data.get("prompt", "").strip()
    use_research = data.get("useResearch", False)
    genre = data.get("genre", "其他")  # 题材类型
    target_audience = data.get("targetAudience", None)  # 目标受众（可选）

    if not prompt_text:
        return jsonify({"error": "请输入故事主题或小说内容"})

    km = KeyManager(config_dir=str(BASE_DIR))
    api_key = km.get_key("deepseek")
    if not api_key:
        return jsonify({"error": "未配置DeepSeek API Key，请先在设置页面配置"})

    try:
        gen = EpisodeGenerator(model="deepseek-v4-flash", thinking_enabled=False)
        gen.client = type(gen.client)(api_key=api_key, base_url="https://api.deepseek.com")

        if input_type == "novel":
            # 小说改编模式：不需要调研
            thread = threading.Thread(
                target=_generate_worker,
                args=(gen, prompt_text, "novel", genre, target_audience, None),
                daemon=True,
            )
        elif input_type == "theme" and use_research and _cached_research_result:
            # 原创方向 + 调研结果
            thread = threading.Thread(
                target=_generate_worker,
                args=(gen, prompt_text, "theme", genre, target_audience, _cached_research_result),
                daemon=True,
            )
        else:
            # 原创方向，无调研
            thread = threading.Thread(
                target=_generate_worker,
                args=(gen, prompt_text, "theme", genre, target_audience, None),
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


@app.route("/api/generate_outline", methods=["POST"])
def generate_outline():
    """生成故事大纲"""
    if _generation_status["running"]:
        return jsonify({"error": "已有生成任务正在进行中，请稍后再试"})

    data = request.json
    prompt_text = data.get("prompt", "").strip()
    use_research = data.get("useResearch", False)
    genre = data.get("genre", "其他")
    target_audience = data.get("targetAudience", None)

    if not prompt_text:
        return jsonify({"error": "请输入故事主题"})

    km = KeyManager(config_dir=str(BASE_DIR))
    api_key = km.get_key("deepseek")
    if not api_key:
        return jsonify({"error": "未配置DeepSeek API Key，请先在设置页面配置"})

    try:
        gen = EpisodeGenerator(model="deepseek-v4-flash", thinking_enabled=False)
        gen.client = type(gen.client)(api_key=api_key, base_url="https://api.deepseek.com")

        research_result = _cached_research_result if (use_research and _cached_research_result) else None

        thread = threading.Thread(
            target=_outline_worker,
            args=(gen, prompt_text, genre, target_audience, research_result, str(BASE_DIR)),
            daemon=True,
        )
        thread.start()

        return jsonify({"success": True, "message": "大纲生成任务已启动"})
    except Exception as e:
        return jsonify({"error": f"启动失败: {str(e)}"})


@app.route("/api/continue_episode", methods=["POST"])
def continue_episode():
    """续集生成：基于已有策划案生成下一集"""
    if _generation_status["running"]:
        return jsonify({"error": "已有生成任务正在进行中，请稍后再试"})

    data = request.json
    filename = data.get("filename", "")
    target_episode = data.get("target_episode", 1)

    if not filename:
        return jsonify({"error": "请提供策划案文件名"})

    filepath = OUTPUT_DIR / filename
    if not Path(filepath).exists():
        return jsonify({"error": f"策划案文件不存在: {filename}"})

    km = KeyManager(config_dir=str(BASE_DIR))
    api_key = km.get_key("deepseek")
    if not api_key:
        return jsonify({"error": "未配置DeepSeek API Key"})

    try:
        # 读取已有策划案JSON
        with open(filepath, "r", encoding="utf-8") as f:
            prev_data = json.load(f)

        gen = EpisodeGenerator(model="deepseek-v4-flash", thinking_enabled=False)
        gen.client = type(gen.client)(api_key=api_key, base_url="https://api.deepseek.com")

        thread = threading.Thread(
            target=_continue_worker,
            args=(gen, prev_data, target_episode, str(BASE_DIR)),
            daemon=True,
        )
        thread.start()
        return jsonify({"success": True, "message": "续集生成任务已启动"})
    except Exception as e:
        return jsonify({"error": f"启动失败: {str(e)}"})


@app.route("/api/plan_detail/<path:filename>")
def plan_detail(filename):
    """获取单个策划案的完整JSON详情"""
    try:
        filepath = OUTPUT_DIR / filename
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/open_output_dir", methods=["POST"])
def open_output_dir():
    """一键打开策划案输出目录"""
    import subprocess
    try:
        subprocess.Popen(f'explorer "{OUTPUT_DIR}"', shell=True)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/download/<path:filename>")
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename)


# ========== TTS 相关 API ==========

# TTS 配置持久化
_TTS_SETTINGS_FILE = BASE_DIR / ".env_moss"

def _save_tts_setting(key: str, value: str):
    """保存 TTS 配置到 .env_moss 文件"""
    # 读取现有内容
    existing = {}
    if os.path.exists(_TTS_SETTINGS_FILE):
        with open(_TTS_SETTINGS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                existing[k.strip()] = v.strip().strip("\"'")
    existing[key] = value
    with open(_TTS_SETTINGS_FILE, "w", encoding="utf-8") as f:
        for k, v in existing.items():
            f.write(f"{k}={v}\n")


def _load_tts_settings() -> Dict[str, str]:
    """加载 TTS 配置"""
    voice_id = TTSClient.DEFAULT_VOICE_ID
    speed = "1.0"
    if os.path.exists(_TTS_SETTINGS_FILE):
        with open(_TTS_SETTINGS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "TTS_VOICE_ID":
                    voice_id = v.strip().strip("\"'")
                elif k.strip() == "TTS_SPEED":
                    speed = v.strip().strip("\"'")
    return {"voice_id": voice_id, "speed": speed}


def _get_tts_client() -> TTSClient:
    """创建 TTSClient 实例（从 .env_moss 读取配置）"""
    settings = _load_tts_settings()
    try:
        return TTSClient(
            voice_id=settings["voice_id"],
            speed=float(settings["speed"]),
        )
    except ValueError:
        raise ValueError("未配置 MOSS_API_KEY，请先设置 Mossland TTS API Key")


@app.route("/api/tts_settings", methods=["GET"])
def get_tts_settings():
    """获取 TTS 配置"""
    settings = _load_tts_settings()
    return jsonify({"success": True, **settings})


@app.route("/api/tts_settings", methods=["POST"])
def save_tts_settings():
    """保存 TTS 配置"""
    data = request.json
    if "voice_id" in data:
        _save_tts_setting("TTS_VOICE_ID", data["voice_id"])
    if "speed" in data:
        _save_tts_setting("TTS_SPEED", str(data["speed"]))
    return jsonify({"success": True})


@app.route("/api/tts_voices")
def get_tts_voices():
    """列出 Mossland 可用语音角色"""
    try:
        client = _get_tts_client()
        voices = client.list_voices()
        if voices is None:
            return jsonify({"success": False, "error": "获取语音列表失败"})
        return jsonify({"success": True, "voices": voices})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


_tts_progress = {"running": False, "progress": "", "percentage": 0, "total": 0, "done": 0, "result": None, "error": None}


@app.route("/api/synthesize_episode", methods=["POST"])
def synthesize_episode():
    """批量合成策划案中所有音频"""
    if _tts_progress["running"]:
        return jsonify({"error": "TTS 合成任务正在进行中，请稍后再试"})

    data = request.json
    filename = data.get("filename", "")
    if not filename:
        return jsonify({"error": "请提供策划案文件名"})

    filepath = OUTPUT_DIR / filename
    if not Path(filepath).exists():
        return jsonify({"error": f"策划案文件不存在: {filename}"})

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
    except Exception as e:
        return jsonify({"error": f"读取文件失败: {e}"})

    def _tts_worker():
        global _tts_progress
        _tts_progress["running"] = True
        _tts_progress["progress"] = "正在初始化..."
        _tts_progress["percentage"] = 0

        try:
            client = _get_tts_client()
            project = plan_data.get("project", {}) or {}
            title = project.get("title", "未命名")
            safe_title = "".join(c if c not in '\\/:*?"<>|' else '_' for c in title)

            # 创建输出目录
            audio_dir = BASE_DIR / "output" / "audio" / safe_title
            audio_dir.mkdir(parents=True, exist_ok=True)

            episodes = plan_data.get("episodes", [])
            if not episodes:
                # 尝试 outline 格式
                outline = plan_data.get("outline", [])
                if outline:
                    _tts_progress["error"] = "当前文件格式不支持 TTS 合成，请先展开为完整分集策划案"
                    _tts_progress["running"] = False
                    return
                _tts_progress["error"] = "策划案中没有找到 episodes 数据"
                _tts_progress["running"] = False
                return

            # 计算总任务数
            total_items = 0
            for ep in episodes:
                for scene in ep.get("scenes", []):
                    if scene.get("narration", "").strip():
                        total_items += 1
                    for dlg in scene.get("dialogues", []):
                        if isinstance(dlg, dict) and dlg.get("text", "").strip():
                            total_items += 1

            _tts_progress["total"] = total_items
            _tts_progress["done"] = 0
            all_audio_files = []

            for ep in episodes:
                ep_num = ep.get("episode_number", "?")
                _tts_progress["progress"] = f"正在合成第{ep_num}集..."

                scenes = ep.get("scenes", [])
                for scene in scenes:
                    # 合成旁白
                    narration = scene.get("narration", "")
                    if narration and narration.strip():
                        slugline = scene.get("slugline", "")
                        safe_slug = "".join(c if c not in '\\/:*?"<>|' else '_' for c in slugline)[:20]
                        outfile = str(audio_dir / f"ep{ep_num}_scene{scene.get('scene_id', '?')}_{safe_slug}_narration.mp3")
                        result = client.synthesize(narration, outfile)
                        if result:
                            result["role"] = "旁白"
                            result["text"] = narration
                            result["episode"] = ep_num
                            all_audio_files.append(result)
                            _tts_progress["done"] += 1
                            _tts_progress["percentage"] = int(_tts_progress["done"] / max(total_items, 1) * 100)
                            time.sleep(0.5)

                    # 合成台词
                    for dlg in scene.get("dialogues", []):
                        if not isinstance(dlg, dict):
                            continue
                        text = dlg.get("text", "")
                        if not text.strip():
                            continue
                        character = dlg.get("character", "unknown")
                        safe_slug = "".join(c if c not in '\\/:*?"<>|' else '_' for c in character)[:20]
                        outfile = str(audio_dir / f"ep{ep_num}_scene{scene.get('scene_id', '?')}_{safe_slug}.mp3")
                        result = client.synthesize(text, outfile)
                        if result:
                            result["role"] = character
                            result["text"] = text
                            result["episode"] = ep_num
                            all_audio_files.append(result)
                            _tts_progress["done"] += 1
                            _tts_progress["percentage"] = int(_tts_progress["done"] / max(total_items, 1) * 100)
                            time.sleep(0.5)

            _tts_progress["progress"] = "合成完成！"
            _tts_progress["percentage"] = 100
            _tts_progress["result"] = {
                "audio_dir": str(audio_dir),
                "title": safe_title,
                "files": all_audio_files,
                "total": len(all_audio_files),
            }

        except Exception as e:
            _tts_progress["error"] = str(e)
            _tts_progress["progress"] = f"合成失败: {e}"
            _tts_progress["percentage"] = 0
            import traceback
            traceback.print_exc()
        finally:
            _tts_progress["running"] = False

    thread = threading.Thread(target=_tts_worker, daemon=True)
    thread.start()
    return jsonify({"success": True, "message": "TTS 合成任务已启动"})


# ========== 抖音语录 TTS 工具 ==========

_douyin_tasks = {}  # task_id -> {status, result}

_douyin_tts_module = None

def _get_douyin_mod():
    """Lazy import tts_douyin_quote module (once)"""
    global _douyin_tts_module
    if _douyin_tts_module is None:
        from tts_douyin_quote import DouyinTTS, QUOTE_TEMPLATES, sample_quote
        _douyin_tts_module = {
            "DouyinTTS": DouyinTTS,
            "QUOTE_TEMPLATES": QUOTE_TEMPLATES,
            "sample_quote": sample_quote,
        }
    return _douyin_tts_module


@app.route("/api/douyin_tts/templates")
def douyin_tts_templates():
    """获取预设语录模板列表"""
    mod = _get_douyin_mod()
    templates = {}
    for name in mod["QUOTE_TEMPLATES"]:
        try:
            templates[name] = mod["sample_quote"](name)
        except Exception:
            templates[name] = f"[{name}模板]"
    return jsonify({"templates": templates})


@app.route("/api/douyin_tts/randomize", methods=["POST"])
def douyin_tts_randomize():
    """刷新语录 — 随机选择同一模板下的另一条"""
    data = request.json or {}
    template_name = data.get("template", "").strip()
    if not template_name:
        return jsonify({"error": "必须提供 template"}), 400
    try:
        mod = _get_douyin_mod()
        text = mod["sample_quote"](template_name, randomize=True)
        return jsonify({"text": text, "length": len(text)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/douyin_tts/synthesize", methods=["POST"])
def douyin_tts_synthesize():
    """生成抖音语录音频（带进度查询）"""
    data = request.json or {}
    text = data.get("text", "").strip()
    template = data.get("template")
    output_name = data.get("output", "douyin_quote.mp3")
    speed = float(data.get("speed", 0.9))
    force_clone = bool(data.get("force_cloned_voice", True))

    if not text and not template:
        return jsonify({"error": "必须提供 text 或 template"}), 400

    if template:
        try:
            mod = _get_douyin_mod()
            text = mod["sample_quote"](template)
        except Exception as e:
            return jsonify({"error": f"模板错误: {e}"}), 400

    # 异步任务
    import uuid
    task_id = str(uuid.uuid4())[:8]
    _douyin_tasks[task_id] = {"status": "pending", "progress": 0, "message": ""}

    def _do_work():
        _douyin_tasks[task_id]["status"] = "running"
        _douyin_tasks[task_id]["progress"] = 20
        _douyin_tasks[task_id]["message"] = "正在生成音频..."
        try:
            mod = _get_douyin_mod()
            tts = mod["DouyinTTS"]()
            out_path = str(BASE_DIR / "output" / output_name)
            result = tts.make_douyin_quote(
                text=text, output_file=out_path,
                speed=speed, force_cloned_voice=force_clone,
            )
            _douyin_tasks[task_id]["status"] = "done"
            _douyin_tasks[task_id]["progress"] = 100
            _douyin_tasks[task_id]["message"] = "合成完成"
            _douyin_tasks[task_id]["result"] = {
                "file": out_path,
                "filename": os.path.basename(out_path),
                "bytes": result["bytes"],
                "duration_sec": result["duration_sec"],
            }
        except Exception as e:
            import traceback
            _douyin_tasks[task_id]["status"] = "error"
            tb = traceback.format_exc()
            msg = f"{str(e)}\n{tb}"
            print(f"[DOUBIN_TTS_ERROR] {msg}")
            _douyin_tasks[task_id]["message"] = msg[:2000]

    threading.Thread(target=_do_work, daemon=True).start()
    return jsonify({"task_id": task_id})


@app.route("/api/douyin_tts/status/<task_id>")
def douyin_tts_status(task_id):
    """查询抖音语录生成进度"""
    task = _douyin_tasks.get(task_id, {})
    return jsonify(task or {"status": "not_found"})


# ========== END: 抖音语录 TTS 工具 ==========


@app.route("/api/tts_status")
def tts_status():
    """查询 TTS 进度"""
    return jsonify(_tts_progress)


@app.route("/api/download_audio/<path:filename>")
def download_audio(filename):
    """下载音频文件"""
    audio_dir = BASE_DIR / "output" / "audio"
    return send_from_directory(audio_dir, filename)


if __name__ == "__main__":
    print("=" * 50)
    print("  DramaFlow 网页版策划案生成器")
    print("  浏览器访问: http://localhost:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)
