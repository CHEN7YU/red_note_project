"""
pipeline/video_processor.py
============================
视频处理模块：下载 → 去水印 → 去字幕 → 重编码去重 → 生成新字幕 → 合成。
全部基于 FFmpeg + yt-dlp + Whisper + edge-tts，本地运行零成本。
"""

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from .config import (
    AUDIO_DIR,
    FFMPEG_BIN,
    FFPROBE_BIN,
    OUTPUT_DIR,
    SUBTITLE_DIR,
    VIDEO_BRIGHTNESS,
    VIDEO_CONTRAST,
    VIDEO_CRF,
    VIDEO_CROP_PX,
    VIDEO_DIR,
    VIDEO_MAX_DURATION,
    VIDEO_RESOLUTION,
    VIDEO_SATURATION,
    VIDEO_SPEED_FACTOR,
    TTS_VOICE_EN,
    TTS_VOICE_ZH,
    WHISPER_MODEL,
)


# ── 视频信息 ────────────────────────────────────────────────

def get_video_info(video_path: str) -> dict:
    """用 ffprobe 获取视频信息"""
    cmd = [
        FFPROBE_BIN, "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return json.loads(result.stdout)
    except Exception as e:
        print(f"  ⚠️ ffprobe 失败: {e}")
        return {}


def get_duration(video_path: str) -> float:
    """获取视频时长（秒）"""
    info = get_video_info(video_path)
    try:
        return float(info.get("format", {}).get("duration", 0))
    except (ValueError, TypeError):
        return 0.0


# ── 视频下载 ────────────────────────────────────────────────

def download_video(url: str, output_dir: str | None = None, max_duration: int = 120) -> str | None:
    """
    用 yt-dlp Python API 下载视频。
    返回下载后的文件路径，失败返回 None。
    """
    try:
        import yt_dlp
    except ImportError:
        print("  ⚠️ yt-dlp 未安装，请运行: pip install yt-dlp")
        return None

    if output_dir is None:
        output_dir = str(VIDEO_DIR / "downloads")
    os.makedirs(output_dir, exist_ok=True)

    output_template = os.path.join(output_dir, "%(id)s.%(ext)s")
    downloaded_file = None

    class MyLogger:
        def debug(self, msg): pass
        def warning(self, msg): pass
        def error(self, msg): print(f"  ⚠️ yt-dlp: {msg}")

    def progress_hook(d):
        nonlocal downloaded_file
        if d["status"] == "finished":
            downloaded_file = d.get("filename", "")
            print(f"  📥 下载完成: {Path(downloaded_file).name}")

    opts = {
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "noplaylist": True,
        "max_filesize": 100 * 1024 * 1024,  # 100MB
        "no_overwrites": True,
        "logger": MyLogger(),
        "progress_hooks": [progress_hook],
        "socket_timeout": 30,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        # 查找实际输出文件 (合并后可能是 .mp4)
        if downloaded_file and os.path.isfile(downloaded_file):
            return downloaded_file

        # 搜索最新 mp4
        files = sorted(Path(output_dir).glob("*.mp4"), key=os.path.getmtime, reverse=True)
        if files:
            return str(files[0])

        print("  ⚠️ 下载后未找到视频文件")
        return None
    except Exception as e:
        print(f"  ❌ yt-dlp 下载失败: {e}")
        return None


# ── FFmpeg 视频处理 ─────────────────────────────────────────

def strip_metadata(input_path: str, output_path: str) -> bool:
    """清除视频所有元数据"""
    cmd = [
        FFMPEG_BIN, "-y", "-i", input_path,
        "-map_metadata", "-1",
        "-fflags", "+bitexact",
        "-c", "copy",
        output_path,
    ]
    return _run_ffmpeg(cmd, "清除元数据")


def re_encode_video(
    input_path: str,
    output_path: str,
    speed_factor: float | None = None,
    crop_px: int | None = None,
    brightness: float | None = None,
    contrast: float | None = None,
    saturation: float | None = None,
    target_width: int | None = None,
    target_height: int | None = None,
) -> bool:
    """
    重新编码视频，可组合多种去重变换：
    - 重编码（改二进制指纹）
    - 微调速度
    - 裁切边缘
    - 色调微调
    - 分辨率微调
    """
    speed_factor = speed_factor or VIDEO_SPEED_FACTOR
    crop_px = crop_px if crop_px is not None else VIDEO_CROP_PX
    brightness = brightness or VIDEO_BRIGHTNESS
    contrast = contrast or VIDEO_CONTRAST
    saturation = saturation or VIDEO_SATURATION

    vf_parts = []

    # 裁切边缘
    if crop_px > 0:
        vf_parts.append(f"crop=in_w-{crop_px*2}:in_h-{crop_px*2}:{crop_px}:{crop_px}")

    # 色调微调
    vf_parts.append(f"eq=brightness={brightness}:contrast={contrast}:saturation={saturation}")

    # 速度微调
    if speed_factor != 1.0:
        vf_parts.append(f"setpts={1/speed_factor}*PTS")

    # 分辨率
    if target_width and target_height:
        vf_parts.append(f"scale={target_width}:{target_height}")
    else:
        # 微调分辨率（偏移 2 像素规避指纹）
        vf_parts.append("scale=trunc(iw/2)*2-2:trunc(ih/2)*2-2")

    vf_str = ",".join(vf_parts)

    cmd = [
        FFMPEG_BIN, "-y", "-i", input_path,
        "-vf", vf_str,
        "-c:v", "libx264", "-crf", str(VIDEO_CRF),
        "-preset", "medium",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-map_metadata", "-1",
        "-fflags", "+bitexact",
    ]

    # 音频速度同步
    if speed_factor != 1.0:
        cmd.extend(["-af", f"atempo={speed_factor}"])

    cmd.append(output_path)
    return _run_ffmpeg(cmd, "重编码去重")


def crop_watermark(
    input_path: str,
    output_path: str,
    top: int = 0,
    bottom: int = 0,
    left: int = 0,
    right: int = 0,
) -> bool:
    """裁切视频边缘区域（去除固定位置水印）"""
    if top == 0 and bottom == 0 and left == 0 and right == 0:
        shutil.copy2(input_path, output_path)
        return True

    vf = f"crop=in_w-{left}-{right}:in_h-{top}-{bottom}:{left}:{top}"
    cmd = [
        FFMPEG_BIN, "-y", "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264", "-crf", str(VIDEO_CRF),
        "-c:a", "copy",
        output_path,
    ]
    return _run_ffmpeg(cmd, "裁切水印")


def extract_audio(input_path: str, output_path: str | None = None) -> str | None:
    """从视频提取音频"""
    if output_path is None:
        stem = Path(input_path).stem
        output_path = str(AUDIO_DIR / f"{stem}.wav")

    cmd = [
        FFMPEG_BIN, "-y", "-i", input_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        output_path,
    ]
    if _run_ffmpeg(cmd, "提取音频"):
        return output_path
    return None


def burn_subtitles(input_path: str, subtitle_path: str, output_path: str) -> bool:
    """将字幕硬嵌入视频"""
    # 路径中的反斜杠和冒号需要转义
    safe_sub = subtitle_path.replace("\\", "/").replace(":", "\\:")
    cmd = [
        FFMPEG_BIN, "-y", "-i", input_path,
        "-vf", f"subtitles='{safe_sub}'",
        "-c:v", "libx264", "-crf", str(VIDEO_CRF),
        "-c:a", "copy",
        output_path,
    ]
    return _run_ffmpeg(cmd, "嵌入字幕")


def replace_audio(video_path: str, audio_path: str, output_path: str) -> bool:
    """替换视频音频轨"""
    cmd = [
        FFMPEG_BIN, "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        "-map", "0:v:0", "-map", "1:a:0",
        "-shortest",
        output_path,
    ]
    return _run_ffmpeg(cmd, "替换音频")


def _run_ffmpeg(cmd: list[str], desc: str) -> bool:
    """执行 FFmpeg 命令"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            print(f"  ✅ {desc}: 成功")
            return True
        else:
            stderr = result.stderr[-300:] if result.stderr else "无错误信息"
            print(f"  ❌ {desc}: 失败\n     {stderr}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  ❌ {desc}: 超时")
        return False
    except FileNotFoundError:
        print(f"  ❌ {desc}: FFmpeg 未找到，请安装 FFmpeg")
        return False


# ── Whisper 语音识别 ────────────────────────────────────────

def transcribe_audio(audio_path: str, language: str | None = None) -> dict | None:
    """
    用 Whisper 识别音频，返回带时间戳的结果。
    返回: {text, language, segments: [{start, end, text}]}
    """
    try:
        import whisper
    except ImportError:
        print("  ⚠️ whisper 未安装，请运行: pip install openai-whisper")
        return None

    print(f"  🎤 Whisper 识别中 (模型: {WHISPER_MODEL})...")
    model = whisper.load_model(WHISPER_MODEL)
    result = model.transcribe(
        audio_path,
        language=language,
        verbose=False,
    )

    segments = []
    for seg in result.get("segments", []):
        segments.append({
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"].strip(),
        })

    output = {
        "text": result["text"],
        "language": result.get("language", ""),
        "segments": segments,
    }
    print(f"  ✅ Whisper: 识别完成, 语言={output['language']}, 段落={len(segments)}")
    return output


def segments_to_srt(segments: list[dict], output_path: str) -> str:
    """将 Whisper segments 转为 SRT 字幕文件"""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _format_srt_time(seg["start"])
        end = _format_srt_time(seg["end"])
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(seg["text"])
        lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  ✅ SRT 字幕已保存: {output_path}")
    return output_path


def _format_srt_time(seconds: float) -> str:
    """秒转 SRT 时间格式 HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ── TTS 语音合成 ────────────────────────────────────────────

async def _tts_async(text: str, voice: str, output_path: str):
    """edge-tts 异步合成"""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def text_to_speech(text: str, output_path: str, language: str = "zh") -> str | None:
    """
    用 edge-tts（免费）将文本转语音。
    language: "zh" 或 "en"
    """
    voice = TTS_VOICE_ZH if language == "zh" else TTS_VOICE_EN
    try:
        asyncio.run(_tts_async(text, voice, output_path))
        print(f"  ✅ TTS: {language} 语音已生成 → {output_path}")
        return output_path
    except Exception as e:
        print(f"  ❌ TTS 失败: {e}")
        return None


# ── 完整视频处理管线 ────────────────────────────────────────

def process_video_pipeline(
    source_url: str,
    output_name: str,
    new_script_zh: str | None = None,
    new_script_en: str | None = None,
    watermark_crop: dict | None = None,
) -> dict:
    """
    完整视频处理管线：
    1. 下载原视频
    2. 裁切水印区域
    3. 提取音频 → Whisper 识别 → 生成字幕
    4. 重编码（去重：速度/色调/裁切/分辨率微调/元数据清除）
    5. （可选）用 TTS 生成新配音替换
    6. 嵌入新字幕
    7. 输出中文版 + 英文版

    返回 {zh_video, en_video, transcript, status}
    """
    result = {"status": "started", "zh_video": None, "en_video": None, "transcript": None}

    work_dir = Path(tempfile.mkdtemp(prefix="vidpipe_"))
    print(f"\n🎬 视频处理管线启动: {output_name}")
    print(f"   工作目录: {work_dir}")

    try:
        # Step 1: 下载
        print("\n── Step 1: 下载视频 ──")
        downloaded = download_video(source_url, str(work_dir))
        if not downloaded:
            result["status"] = "download_failed"
            return result

        # Step 2: 裁切水印
        print("\n── Step 2: 裁切水印 ──")
        crop = watermark_crop or {"top": 0, "bottom": 80, "left": 0, "right": 0}
        cropped = str(work_dir / "cropped.mp4")
        crop_watermark(downloaded, cropped, **crop)

        # Step 3: 提取音频 + 识别
        print("\n── Step 3: 语音识别 ──")
        audio = extract_audio(cropped, str(work_dir / "audio.wav"))
        if audio:
            transcript = transcribe_audio(audio)
            result["transcript"] = transcript
        else:
            transcript = None

        # Step 4: 重编码去重
        print("\n── Step 4: 重编码去重 ──")
        deduped = str(work_dir / "deduped.mp4")
        re_encode_video(cropped, deduped)

        # Step 5 & 6: 生成中文版（新配音 + 新字幕）
        if new_script_zh:
            print("\n── Step 5a: 生成中文版 ──")
            zh_audio = str(work_dir / "tts_zh.mp3")
            tts_ok = text_to_speech(new_script_zh, zh_audio, "zh")

            if tts_ok:
                zh_with_audio = str(work_dir / "zh_audio.mp4")
                replace_audio(deduped, zh_audio, zh_with_audio)
            else:
                zh_with_audio = deduped

            # 中文字幕
            zh_srt = str(work_dir / "zh.srt")
            _write_simple_srt(new_script_zh, zh_srt)

            zh_final = str(VIDEO_DIR / f"{output_name}_zh.mp4")
            burn_subtitles(zh_with_audio, zh_srt, zh_final)
            result["zh_video"] = zh_final

        # 英文版
        if new_script_en:
            print("\n── Step 5b: 生成英文版 ──")
            en_audio = str(work_dir / "tts_en.mp3")
            tts_ok = text_to_speech(new_script_en, en_audio, "en")

            if tts_ok:
                en_with_audio = str(work_dir / "en_audio.mp4")
                replace_audio(deduped, en_audio, en_with_audio)
            else:
                en_with_audio = deduped

            en_srt = str(work_dir / "en.srt")
            _write_simple_srt(new_script_en, en_srt)

            en_final = str(VIDEO_DIR / f"{output_name}_en.mp4")
            burn_subtitles(en_with_audio, en_srt, en_final)
            result["en_video"] = en_final

        # 如果没有新脚本，只输出去重版本
        if not new_script_zh and not new_script_en:
            final = str(VIDEO_DIR / f"{output_name}.mp4")
            shutil.copy2(deduped, final)
            result["zh_video"] = final

        result["status"] = "success"
        print(f"\n✅ 视频处理完成: {output_name}")

    except Exception as e:
        result["status"] = f"error: {e}"
        print(f"\n❌ 视频处理失败: {e}")

    finally:
        # 清理临时文件
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass

    return result


def _write_simple_srt(text: str, output_path: str, duration_per_line: float = 3.0):
    """从纯文本生成简单的 SRT 字幕（按句子分段）"""
    # 按标点分句
    sentences = re.split(r'[。！？.!?\n]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    lines = []
    t = 0.0
    for i, sent in enumerate(sentences, 1):
        start = _format_srt_time(t)
        t += duration_per_line
        end = _format_srt_time(t)
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(sent)
        lines.append("")
        t += 0.2  # 小间隔

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
