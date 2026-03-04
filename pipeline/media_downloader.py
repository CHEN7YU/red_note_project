"""
pipeline/media_downloader.py
=============================
下载 Reddit 帖子附带的图片/视频素材，去水印后存到 topic 目录。
"""

import os
import re
import subprocess
from pathlib import Path

import httpx

from .config import FFMPEG_BIN


def download_reddit_media(post: dict, output_dir: str) -> list[str]:
    """
    从 Reddit 帖子下载图片/视频素材。
    
    Args:
        post: Reddit topic dict (需要 url, media_url, is_video 字段)
        output_dir: 保存到的目录 (e.g. output/20260304/topic_1/media/)
    
    Returns:
        下载成功的文件路径列表
    """
    os.makedirs(output_dir, exist_ok=True)
    downloaded = []

    media_url = post.get("media_url", "")
    post_url = post.get("url", "")
    is_video = post.get("is_video", False)

    # 收集所有可能的媒体 URL
    urls_to_try = []

    if media_url:
        urls_to_try.append(media_url)

    # Reddit 图片直链
    if "i.redd.it" in media_url or "i.imgur.com" in media_url:
        urls_to_try = [media_url]  # 直接用
    elif "v.redd.it" in media_url or is_video:
        # Reddit 视频需要用 yt-dlp
        return _download_video_ytdlp(post_url or media_url, output_dir)
    elif any(ext in media_url.lower() for ext in [".jpg", ".png", ".gif", ".webp", ".jpeg"]):
        urls_to_try = [media_url]
    elif "gallery" in post_url:
        # Reddit gallery — 多图帖
        urls_to_try = _extract_gallery_urls(post_url)

    # 下载图片
    for i, url in enumerate(urls_to_try[:5]):  # 最多5张
        try:
            ext = _guess_ext(url)
            filename = f"media_{i+1}{ext}"
            filepath = os.path.join(output_dir, filename)

            if _download_file(url, filepath):
                downloaded.append(filepath)
                print(f"    📥 下载: {filename}")
        except Exception as e:
            print(f"    ⚠️ 下载失败 {url[:50]}: {e}")

    # 如果原帖链接指向外部文章，尝试抓文章内的 OG 图片
    if not downloaded and media_url and not any(x in media_url for x in ["reddit.com", "redd.it"]):
        og_img = _extract_og_image(media_url)
        if og_img:
            filepath = os.path.join(output_dir, f"og_image{_guess_ext(og_img)}")
            if _download_file(og_img, filepath):
                downloaded.append(filepath)
                print(f"    📥 下载 OG 图片: {Path(filepath).name}")

    if not downloaded:
        print(f"    ℹ️ 无可下载的媒体素材")

    return downloaded


def _download_video_ytdlp(url: str, output_dir: str) -> list[str]:
    """用 yt-dlp 下载 Reddit 视频"""
    try:
        import yt_dlp
    except ImportError:
        print("    ⚠️ yt-dlp 未安装")
        return []

    output_path = os.path.join(output_dir, "video.mp4")
    downloaded = []

    class MyLogger:
        def debug(self, msg): pass
        def warning(self, msg): pass
        def error(self, msg): print(f"    ⚠️ yt-dlp: {msg[:80]}")

    def hook(d):
        if d["status"] == "finished":
            downloaded.append(d.get("filename", output_path))

    opts = {
        "format": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "merge_output_format": "mp4",
        "outtmpl": output_path,
        "noplaylist": True,
        "logger": MyLogger(),
        "progress_hooks": [hook],
        "socket_timeout": 20,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        if downloaded:
            print(f"    📥 视频下载: {Path(downloaded[0]).name}")
            return downloaded
        if os.path.isfile(output_path):
            return [output_path]
    except Exception as e:
        print(f"    ⚠️ 视频下载失败: {str(e)[:80]}")

    return []


def _download_file(url: str, filepath: str, timeout: int = 15) -> bool:
    """下载单个文件"""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            r = client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })
            if r.status_code == 200 and len(r.content) > 1000:  # 至少 1KB
                with open(filepath, "wb") as f:
                    f.write(r.content)
                return True
    except Exception:
        pass
    return False


def _guess_ext(url: str) -> str:
    """猜测文件扩展名"""
    url_lower = url.lower().split("?")[0]
    for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov"]:
        if url_lower.endswith(ext):
            return ext
    if "image" in url_lower or "photo" in url_lower:
        return ".jpg"
    return ".jpg"


def _extract_gallery_urls(gallery_url: str) -> list[str]:
    """从 Reddit gallery 帖子提取所有图片 URL"""
    try:
        # Reddit gallery JSON
        json_url = gallery_url.rstrip("/") + ".json"
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            r = client.get(json_url, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return []
            data = r.json()

        # 提取 media_metadata
        if isinstance(data, list):
            data = data[0].get("data", {}).get("children", [{}])[0].get("data", {})
        elif isinstance(data, dict):
            data = data.get("data", {}).get("children", [{}])[0].get("data", {})

        metadata = data.get("media_metadata", {})
        urls = []
        for media_id, info in metadata.items():
            if info.get("status") == "valid" and info.get("s", {}).get("u"):
                img_url = info["s"]["u"].replace("&amp;", "&")
                urls.append(img_url)
        return urls
    except Exception:
        return []


def _extract_og_image(page_url: str) -> str | None:
    """从网页提取 Open Graph 图片"""
    try:
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            r = client.get(page_url, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return None
        match = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', r.text)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None
