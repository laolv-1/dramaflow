"""Pipeline步骤5: 视频合成（FFmpeg封装）"""

import json
import os
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional


class VideoSynthesizer:
    """视频合成器 - 基于FFmpeg"""

    def __init__(self, output_dir: str, ffmpeg_path: str = None,
                 target_resolution: str = "1080x1920"):
        self.output_dir = Path(output_dir) / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.target_resolution = target_resolution  # 竖屏9:16
        self.ffmpeg_path = ffmpeg_path or self._find_ffmpeg()
        self.ffprobe_path = self._find_ffprobe()

    def _find_ffmpeg(self) -> str:
        """查找FFmpeg可执行文件"""
        candidates = [
            "ffmpeg",  # 系统PATH
            r"D:/Account_Forge/市场调研/工具/ffmpeg_temp/ffmpeg-8.1.2-essentials_build/bin/ffmpeg.exe",
            r"D:\Account_Forge\AI-CanvasPro\AI-CanvasPro-windows\AI CanvasPro\resources\runtime\ffmpeg\bin\ffmpeg.exe",
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
        return "ffmpeg"  # 依赖系统PATH

    def _find_ffprobe(self) -> str:
        """查找ffprobe"""
        candidates = [
            "ffprobe",
            r"D:/Account_Forge/市场调研/工具/ffmpeg_temp/ffmpeg-8.1.2-essentials_build/bin/ffprobe.exe",
            r"D:\Account_Forge\AI-CanvasPro\AI-CanvasPro-windows\AI CanvasPro\resources\runtime\ffmpeg\bin\ffprobe.exe",
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
        return "ffprobe"

    def _run_ffmpeg(self, cmd: List[str], timeout: int = 300) -> bool:
        """执行FFmpeg命令"""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                print(f"  [FFmpeg错误] {result.stderr}")
                return False
            return True
        except FileNotFoundError:
            print(f"  [错误] 找不到FFmpeg: {self.ffmpeg_path}")
            return False
        except subprocess.TimeoutExpired:
            print(f"  [错误] FFmpeg超时 ({timeout}s)")
            return False

    def convert_to_vertical(self, input_video: str, output_video: str) -> bool:
        """
        横版视频转竖屏（居中+黑边上下填充）
        参考现有episode_synthesize_ep1.py的实现
        """
        # 解析目标分辨率
        w, h = map(int, self.target_resolution.split("x"))

        cmd = [
            self.ffmpeg_path, "-y",
            "-i", input_video,
            "-vf", (
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
                f"format=yuv420p"
            ),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-an",
            output_video,
        ]
        return self._run_ffmpeg(cmd, timeout=120)

    def replace_audio(self, video_path: str, audio_path: str,
                       output_path: str) -> bool:
        """替换视频音频轨"""
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        return self._run_ffmpeg(cmd, timeout=120)

    def concatenate_videos(self, video_paths: List[str],
                            output_path: str) -> bool:
        """
        拼接多个视频
        使用concat demuxer（需要先创建列表文件）
        """
        # 创建concat列表文件
        list_file = self.output_dir / "_concat_list.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for vp in video_paths:
                # 使用绝对路径，转义反斜杠
                abs_path = str(Path(vp).resolve()).replace("\\", "/")
                f.write(f"file '{abs_path}'\n")

        cmd = [
            self.ffmpeg_path, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c:v", "libx264",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            "-crf", "22",
            output_path,
        ]
        success = self._run_ffmpeg(cmd, timeout=300)
        list_file.unlink(missing_ok=True)
        return success

    def add_subtitle(self, video_path: str, subtitle_path: str,
                      output_path: str) -> bool:
        """
        添加字幕（ASS格式）
        PlayResX=1080, PlayResY=1920
        """
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", video_path,
            "-vf", f"subtitles={subtitle_path}",
            "-c:a", "copy",
            "-preset", "fast",
            "-crf", "22",
            output_path,
        ]
        return self._run_ffmpeg(cmd, timeout=300)

    def gen_output_filename(self, episode_num: int, suffix: str = "") -> str:
        """生成唯一输出文件名（gen_YYYYMMDD_NNNN格式）"""
        import datetime
        today = datetime.datetime.now().strftime("%Y%m%d")
        seq_file = self.output_dir / ".gen_seq_state.json"

        # 读取序列号
        seq = 0
        if seq_file.exists():
            try:
                with open(seq_file, "r") as f:
                    data = json.load(f)
                    seq = data.get(today, 0)
            except (json.JSONDecodeError, IOError):
                seq = 0
        seq += 1

        # 保存序列号
        with open(seq_file, "w") as f:
            json.dump({today: seq}, f)

        name = f"gen_{today}_{seq:04d}"
        if suffix:
            name += f"_{suffix}"
        return f"{name}.mp4"

    def synthesize_episode_sync(self, video_paths: List[str],
                                audio_paths: List[str],
                                subtitles: Optional[List[Dict]],
                                episode_num: int) -> str:
        """
        完整合成流程（同步版本）
        1. 音频替换到每个视频
        2. 拼接所有视频
        3. 添加字幕（可选）
        """
        print(f"\n[视频合成] 开始合成第{episode_num}集")
        print(f"  视频数: {len(video_paths)}")
        print(f"  音频数: {len(audio_paths)}")

        processed_videos = []

        # Step 1: 为每个场景视频替换音频并转竖屏
        for idx, video_path in enumerate(video_paths):
            print(f"  处理场景 {idx + 1}/{len(video_paths)}...")

            basename = Path(video_path).stem
            vertical_path = self.output_dir / f"{basename}_vertical.mp4"
            audio_replaced = self.output_dir / f"{basename}_audio.mp4"

            # 转竖屏
            if not self.convert_to_vertical(video_path, str(vertical_path)):
                print(f"  [错误] 竖屏转换失败，跳过场景{idx + 1}")
                continue

            # 替换音频（取对应音频片段）
            if audio_paths:
                # 简单处理：用第一个音频替换所有
                audio_file = audio_paths[0]
                if not self.replace_audio(str(vertical_path), audio_file, str(audio_replaced)):
                    print(f"  [错误] 音频替换失败")
                    continue
            else:
                # 无音频，直接复制竖屏版本
                import shutil
                shutil.copy2(str(vertical_path), str(audio_replaced))
                audio_replaced = vertical_path

            processed_videos.append(str(audio_replaced))

        # Step 2: 拼接所有场景
        output_filename = self.gen_output_filename(episode_num, "final")
        output_path = self.output_dir / output_filename

        print(f"  [拼接] {len(processed_videos)}个场景 -> {output_filename}")
        if not self.concatenate_videos(processed_videos, str(output_path)):
            print("  [错误] 视频拼接失败")
            return ""

        print(f"\n  [完成] 成品: {output_path}")
        return str(output_path)

    async def synthesize_episode(self, video_paths: List[str],
                                  audio_paths: List[str],
                                  subtitles: Optional[List[Dict]],
                                  episode_num: int) -> str:
        """完整合成流程（异步包装）"""
        return self.synthesize_episode_sync(video_paths, audio_paths, subtitles, episode_num)

        # Step 2: 拼接所有场景
        output_filename = self.gen_output_filename(episode_num, "final")
        output_path = self.output_dir / output_filename

        print(f"  [拼接] {len(processed_videos)}个场景 -> {output_filename}")
        if not self.concatenate_videos(processed_videos, str(output_path)):
            print("  [错误] 视频拼接失败")
            return ""

        # Step 3: 添加字幕（可选）
        if subtitles:
            ass_path = self._build_ass_file(subtitles)
            subtitle_output = self.output_dir / f"{output_filename.with_suffix('.subs.mp4')}"
            if self.add_subtitle(str(output_path), str(ass_path), str(subtitle_output)):
                output_path = subtitle_output
                print("  [字幕] 已添加")

        print(f"\n  [完成] 成品: {output_path}")
        return str(output_path)

    def _build_ass_file(self, subtitles: List[Dict]) -> str:
        """构建ASS字幕文件"""
        ass_content = """[Script Info]
Title: Short Drama Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        for sub in subtitles:
            start_s = sub.get("start", 0)
            end_s = sub.get("end", start_s + 3)
            text = sub.get("text", "")

            # 转换为ASS时间格式 HH:MM:SS.cc
            start_h = int(start_s // 3600)
            start_m = int((start_s % 3600) // 60)
            start_sec = int(start_s % 60)
            start_cc = int((start_s % 1) * 100)

            end_h = int(end_s // 3600)
            end_m = int((end_s % 3600) // 60)
            end_sec = int(end_s % 60)
            end_cc = int((end_s % 1) * 100)

            ass_line = (
                f"Dialogue: 0,{start_h:02d}:{start_m:02d}:{start_sec:02d}.{start_cc:02d},"
                f"{end_h:02d}:{end_m:02d}:{end_sec:02d}.{end_cc:02d},"
                f"Default,,0,0,0,,{text}\n"
            )
            ass_content += ass_line

        ass_path = self.output_dir / "subtitles.ass"
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        return str(ass_path)
