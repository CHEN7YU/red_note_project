"""
pipeline/fetcher.py
===================
热点抓取模块：从 Reddit / 微博 / 百度 等平台获取热点数据。
输出统一格式的 topic 字典列表。
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.request import Request, urlopen

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import httpx

from .config import (
    CACHE_DIR,
    REDDIT_USER_AGENT,
    TRACKS,
    WEST_MIN_COMMENTS,
    WEST_MIN_SCORE,
)


# ── 工具函数 ────────────────────────────────────────────────

def _http_get(url: str, headers: dict | None = None, timeout: int = 15) -> str:
    """HTTP GET with browser-like headers to avoid 403"""
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    if headers:
        default_headers.update(headers)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            r = client.get(url, headers=default_headers)
            r.raise_for_status()
            return r.text
    except Exception as e:
        print(f"  ⚠️ GET 失败 {url}: {e}")
        return ""


def _http_get_json(url: str, headers: dict | None = None, timeout: int = 15) -> dict | list | None:
    """HTTP GET 返回 JSON"""
    text = _http_get(url, headers, timeout)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _save_cache(name: str, data):
    """保存日级缓存"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    path = CACHE_DIR / f"{name}_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


# ── Reddit 抓取 ─────────────────────────────────────────────

def fetch_reddit(subreddits: list[str] | None = None, limit: int = 50) -> list[dict]:
    """
    抓取 Reddit 热帖。
    返回统一格式：[{title, score, num_comments, subreddit, url, created_utc, platform}]
    """
    if not subreddits:
        subreddits = ["popular"]

    all_topics = []
    for sub in subreddits:
        url = f"https://www.reddit.com/r/{sub}/hot.json?limit={limit}"
        headers = {"User-Agent": REDDIT_USER_AGENT}
        data = _http_get_json(url, headers)
        if not data or "data" not in data:
            print(f"  ⚠️ Reddit r/{sub} 无数据")
            continue

        for child in data["data"].get("children", []):
            post = child.get("data", {})
            topic = {
                "title": post.get("title", ""),
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "subreddit": post.get("subreddit", sub),
                "url": f"https://reddit.com{post.get('permalink', '')}",
                "created_utc": post.get("created_utc", 0),
                "platform": "reddit",
                "language": "en",
                "media_url": post.get("url", ""),
                "is_video": post.get("is_video", False),
            }
            all_topics.append(topic)
        time.sleep(1)  # 避免 rate limit

    print(f"  ✅ Reddit: 抓取 {len(all_topics)} 条")
    _save_cache("reddit", all_topics)
    return all_topics


# ── 微博热搜 ────────────────────────────────────────────────

def fetch_weibo_hot() -> list[dict]:
    """
    抓取微博热搜。
    返回统一格式：[{title, heat, url, platform}]
    """
    url = "https://weibo.com/ajax/side/hotSearch"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://weibo.com/",
    }
    data = _http_get_json(url, headers)
    if not data:
        print("  ⚠️ 微博热搜接口无返回")
        return []

    realtime = data.get("data", {}).get("realtime", [])
    topics = []
    for item in realtime:
        word = item.get("word", "")
        raw_hot = item.get("raw_hot", 0) or item.get("num", 0)
        heat_wan = round(raw_hot / 10000, 1) if raw_hot else 0

        topics.append({
            "title": word,
            "heat": heat_wan,
            "url": f"https://s.weibo.com/weibo?q=%23{word}%23",
            "platform": "weibo",
            "language": "zh",
            "category": item.get("category", ""),
            "label_name": item.get("label_name", ""),
        })

    print(f"  ✅ 微博: 抓取 {len(topics)} 条")
    _save_cache("weibo", topics)
    return topics


# ── 百度热搜 ────────────────────────────────────────────────

def fetch_baidu_hot() -> list[dict]:
    """
    抓取百度热搜。
    """
    url = "https://top.baidu.com/board?tab=realtime"
    html = _http_get(url)
    if not html:
        print("  ⚠️ 百度热搜无返回")
        return []

    topics = []
    # 从 JSON 块提取
    pattern = r'"word":"(.*?)".*?"hotScore":"?(\d+)"?'
    matches = re.findall(pattern, html)
    for word, score in matches:
        heat_wan = round(int(score) / 10000, 1) if score else 0
        topics.append({
            "title": word,
            "heat": heat_wan,
            "url": f"https://www.baidu.com/s?wd={word}",
            "platform": "baidu",
            "language": "zh",
        })

    print(f"  ✅ 百度: 抓取 {len(topics)} 条")
    _save_cache("baidu", topics)
    return topics


# ── tophub 通用解析器 ────────────────────────────────────────

def _parse_tophub_page(url: str, platform: str) -> list[dict]:
    """通用 tophub.today 页面解析器（含 cookie 处理）"""
    # tophub 有 Cloudflare 保护，需要先获取 cookie
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            # 先访问主页获取 cookie
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
            # Get cookies from homepage first
            client.get("https://tophub.today/", headers=headers)
            time.sleep(0.5)
            # Then fetch the actual page
            headers["Referer"] = "https://tophub.today/"
            r = client.get(url, headers=headers)
            r.raise_for_status()
            html = r.text
    except Exception as e:
        print(f"  ⚠️ tophub 抓取失败 {url}: {e}")
        return []

    if not html:
        return []

    topics = []
    patterns = [
        r'<td[^>]*class="al"[^>]*>\s*<a[^>]*>([^<]+)</a>',
        r'<a[^>]*href="[^"]*"[^>]*target="_blank"[^>]*>\s*([^<]{5,})</a>',
    ]

    matches = []
    for pattern in patterns:
        matches = re.findall(pattern, html)
        if len(matches) >= 5:
            break

    heat_matches = re.findall(r'(\d+)\s*万热度', html)

    for i, title in enumerate(matches[:50]):
        title = title.strip()
        if len(title) < 5 or title.startswith("http"):
            continue
        heat = float(heat_matches[i]) if i < len(heat_matches) else max(50 - i, 1)
        topics.append({
            "title": title,
            "heat": heat,
            "url": "",
            "platform": platform,
            "language": "zh",
        })

    return topics


# ── 知乎热榜 ────────────────────────────────────────────────

def fetch_zhihu_hot() -> list[dict]:
    """抓取知乎热榜（通过第三方聚合 API）"""
    # 使用免费的知乎热榜 API
    apis = [
        "https://api.vvhan.com/api/hotlist/zhihuHot",
        "https://api.oioweb.cn/api/common/HotList?type=zhihu",
    ]

    for api_url in apis:
        data = _http_get_json(api_url)
        if data:
            topics = []
            # 不同 API 格式不同
            items = data if isinstance(data, list) else data.get("data", data.get("result", []))
            if isinstance(items, dict):
                items = items.get("data", [])
            for i, item in enumerate(items[:50] if isinstance(items, list) else []):
                title = item.get("title", "") or item.get("name", "") or str(item)
                heat = item.get("hot", 0) or item.get("hotNum", 0) or (50 - i)
                if isinstance(heat, str):
                    heat = int(re.sub(r'[^\d]', '', heat) or '0')
                if len(str(title)) > 5:
                    topics.append({
                        "title": str(title),
                        "heat": heat,
                        "url": item.get("url", item.get("link", "")),
                        "platform": "zhihu",
                        "language": "zh",
                    })
            if topics:
                print(f"  ✅ 知乎: 抓取 {len(topics)} 条")
                _save_cache("zhihu", topics)
                return topics

    # Fallback: tophub
    topics = _parse_tophub_page("https://tophub.today/n/mproPpoq6O", "zhihu")
    print(f"  ✅ 知乎: 抓取 {len(topics)} 条")
    if topics:
        _save_cache("zhihu", topics)
    return topics


# ── 抖音热点 ────────────────────────────────────────────────

def fetch_douyin_hot() -> list[dict]:
    """抓取抖音热搜"""
    apis = [
        "https://api.vvhan.com/api/hotlist/douyinHot",
        "https://api.oioweb.cn/api/common/HotList?type=douyin",
    ]

    for api_url in apis:
        data = _http_get_json(api_url)
        if data:
            topics = []
            items = data if isinstance(data, list) else data.get("data", data.get("result", []))
            if isinstance(items, dict):
                items = items.get("data", [])
            for i, item in enumerate(items[:30] if isinstance(items, list) else []):
                title = item.get("title", "") or item.get("name", "") or str(item)
                heat = item.get("hot", 0) or item.get("hotNum", 0) or (30 - i)
                if isinstance(heat, str):
                    heat = int(re.sub(r'[^\d]', '', heat) or '0')
                if len(str(title)) > 3:
                    topics.append({
                        "title": str(title),
                        "heat": heat,
                        "url": item.get("url", ""),
                        "platform": "douyin",
                        "language": "zh",
                    })
            if topics:
                print(f"  ✅ 抖音: 抓取 {len(topics)} 条")
                _save_cache("douyin", topics)
                return topics

    topics = _parse_tophub_page("https://tophub.today/n/DpQvNABoNE", "douyin")
    print(f"  ✅ 抖音: 抓取 {len(topics)} 条")
    if topics:
        _save_cache("douyin", topics)
    return topics


# ── B站热榜 ─────────────────────────────────────────────────

def fetch_bilibili_hot() -> list[dict]:
    """抓取B站热门（通过官方 API）"""
    url = "https://api.bilibili.com/x/web-interface/popular?ps=50&pn=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://www.bilibili.com/",
    }
    data = _http_get_json(url, headers)
    if not data or data.get("code") != 0:
        print("  ⚠️ B站 API 失败，尝试 tophub")
        topics = _parse_tophub_page("https://tophub.today/n/74KvxwokxM", "bilibili")
        print(f"  ✅ B站(tophub): 抓取 {len(topics)} 条")
        return topics

    topics = []
    for item in data.get("data", {}).get("list", []):
        stat = item.get("stat", {})
        topics.append({
            "title": item.get("title", ""),
            "heat": round(stat.get("view", 0) / 10000, 1),
            "url": f"https://www.bilibili.com/video/{item.get('bvid', '')}",
            "platform": "bilibili",
            "language": "zh",
            "category": item.get("tname", ""),
        })

    print(f"  ✅ B站: 抓取 {len(topics)} 条")
    _save_cache("bilibili", topics)
    return topics


# ── 小红书热搜 ──────────────────────────────────────────────

def fetch_xiaohongshu_hot() -> list[dict]:
    """抓取小红书热搜"""
    apis = [
        "https://api.vvhan.com/api/hotlist/xiaohongshuHot",
        "https://api.oioweb.cn/api/common/HotList?type=xiaohongshu",
    ]
    for api_url in apis:
        data = _http_get_json(api_url)
        if data:
            topics = []
            items = data if isinstance(data, list) else data.get("data", data.get("result", []))
            if isinstance(items, dict):
                items = items.get("data", [])
            for i, item in enumerate(items[:30] if isinstance(items, list) else []):
                title = item.get("title", "") or item.get("name", "") or str(item)
                heat = item.get("hot", 0) or item.get("hotNum", 0) or (30 - i)
                if isinstance(heat, str):
                    heat = int(re.sub(r'[^\d]', '', heat) or '0')
                if len(str(title)) > 3:
                    topics.append({
                        "title": str(title),
                        "heat": heat,
                        "url": item.get("url", ""),
                        "platform": "xiaohongshu",
                        "language": "zh",
                    })
            if topics:
                print(f"  ✅ 小红书: 抓取 {len(topics)} 条")
                _save_cache("xiaohongshu", topics)
                return topics

    topics = _parse_tophub_page("https://tophub.today/n/LGMo5e1vxE", "xiaohongshu")
    print(f"  ✅ 小红书: 抓取 {len(topics)} 条")
    if topics:
        _save_cache("xiaohongshu", topics)
    return topics


# ── X (Twitter) 热搜 ───────────────────────────────────────

def fetch_x_trending() -> list[dict]:
    """抓取 X/Twitter 趋势"""
    # 尝试免费趋势 API
    apis = [
        "https://api.vvhan.com/api/hotlist/wbHot",  # 有时也含国际趋势
    ]

    # 直接用 trends24 或 getdaytrends 抓
    for url in ["https://getdaytrends.com/united-states/", "https://trends24.in/united-states/"]:
        html = _http_get(url)
        if html:
            topics = []
            # 多种可能的 HTML 结构
            matches = re.findall(r'<a[^>]*class="[^"]*trend[^"]*"[^>]*>([^<]+)</a>', html)
            if not matches:
                matches = re.findall(r'<span[^>]*>(\#[A-Za-z]\w{2,})</span>', html)
            if not matches:
                matches = re.findall(r'>(\#[A-Za-z]\w{3,})<', html)
            for i, title in enumerate(matches[:30]):
                title = title.strip()
                if len(title) >= 3:
                    topics.append({
                        "title": title,
                        "heat": 30 - i,
                        "url": f"https://x.com/search?q={title}",
                        "platform": "x_twitter",
                        "language": "en",
                    })
            if topics:
                print(f"  ✅ X/Twitter: 抓取 {len(topics)} 条")
                _save_cache("x_twitter", topics)
                return topics

    topics = _parse_tophub_page("https://tophub.today/n/Kqo3OMOlNE", "x_twitter")
    for t in topics:
        t["language"] = "en"
    print(f"  ✅ X/Twitter: 抓取 {len(topics)} 条")
    if topics:
        _save_cache("x_twitter", topics)
    return topics


# ── TikTok 趋势 ────────────────────────────────────────────

def fetch_tiktok_trending() -> list[dict]:
    """抓取 TikTok 趋势"""
    # TikTok Creative Center 的趋势数据
    # 尝试 TikTok 自己的公开 JSON
    trend_url = "https://ads.tiktok.com/creative_radar_api/v1/popular_trend/hashtag/list?period=7&limit=30&country_code=US"
    data = _http_get_json(trend_url)
    if data and data.get("data"):
        topics = []
        for item in data["data"].get("list", data["data"].get("hashtag_list", [])):
            name = item.get("hashtag_name", "") or item.get("name", "")
            views = item.get("video_views", 0) or item.get("publish_cnt", 0)
            if name:
                topics.append({
                    "title": f"#{name}" if not name.startswith("#") else name,
                    "heat": views,
                    "url": f"https://www.tiktok.com/tag/{name}",
                    "platform": "tiktok",
                    "language": "en",
                })
        if topics:
            print(f"  ✅ TikTok: 抓取 {len(topics)} 条")
            _save_cache("tiktok", topics)
            return topics

    # Fallback: tophub
    topics = _parse_tophub_page("https://tophub.today/n/xMG7Hoq6eE", "tiktok")
    for t in topics:
        t["language"] = "en"
    print(f"  ✅ TikTok: 抓取 {len(topics)} 条")
    if topics:
        _save_cache("tiktok", topics)
    return topics


# ── YouTube 趋势 ───────────────────────────────────────────

def fetch_youtube_trending() -> list[dict]:
    """抓取 YouTube 热门视频 + Shorts（优先 YouTube Data API v3，无 key 则跳过）"""
    from .config import YOUTUBE_API_KEY

    topics = []

    if YOUTUBE_API_KEY:
        # 用官方 API 抓 Most Popular videos
        for video_category in ["0", "28", "24"]:  # 0=全部, 28=科技, 24=娱乐
            api_url = (
                f"https://www.googleapis.com/youtube/v3/videos"
                f"?part=snippet,statistics&chart=mostPopular"
                f"&regionCode=US&maxResults=15"
                f"&videoCategoryId={video_category}"
                f"&key={YOUTUBE_API_KEY}"
            )
            data = _http_get_json(api_url)
            if data and "items" in data:
                for item in data["items"]:
                    snippet = item.get("snippet", {})
                    stats = item.get("statistics", {})
                    title = snippet.get("title", "")
                    views = int(stats.get("viewCount", 0))
                    vid = item.get("id", "")
                    # 检查是否是 Short (描述或标签含 #Shorts)
                    desc = snippet.get("description", "")
                    tags = snippet.get("tags", [])
                    is_short = "#shorts" in desc.lower() or "#shorts" in " ".join(tags).lower()

                    if title and len(title) > 5:
                        topics.append({
                            "title": title,
                            "heat": round(views / 10000, 1),
                            "url": f"https://www.youtube.com/watch?v={vid}",
                            "platform": "youtube_shorts" if is_short else "youtube",
                            "language": "en",
                            "category": snippet.get("categoryId", ""),
                            "is_short": is_short,
                        })
            time.sleep(0.3)

        # 去重
        seen = set()
        deduped = []
        for t in topics:
            if t["title"] not in seen:
                seen.add(t["title"])
                deduped.append(t)
        topics = deduped

    if not topics:
        # 无 API key 时 fallback
        topics = _parse_tophub_page("https://tophub.today/n/74KvxwDkxM", "youtube")

    for t in topics:
        t["language"] = "en"
    print(f"  ✅ YouTube: 抓取 {len(topics)} 条" + (f" (含Shorts)" if any(t.get("is_short") for t in topics) else ""))
    if topics:
        _save_cache("youtube", topics)
    return topics


# ── 统一抓取入口 ────────────────────────────────────────────

def fetch_all_hotspots(track: str = "tech") -> dict:
    """
    抓取所有热点源，返回 {west: [...], china: [...]}
    """
    track_config = TRACKS.get(track, TRACKS["tech"])
    subreddits = track_config.get("west_subreddits", ["popular"])

    print(f"\n🔍 开始抓取热点 (赛道: {track})")
    print("─" * 50)

    # 西方平台
    west = fetch_reddit(subreddits=subreddits)
    west += fetch_x_trending()
    west += fetch_tiktok_trending()
    west += fetch_youtube_trending()

    # 中文平台
    china_weibo = fetch_weibo_hot()
    china_baidu = fetch_baidu_hot()
    china_zhihu = fetch_zhihu_hot()
    china_douyin = fetch_douyin_hot()
    china_bilibili = fetch_bilibili_hot()
    china_xhs = fetch_xiaohongshu_hot()

    result = {
        "west": west,
        "china": china_weibo + china_baidu + china_zhihu + china_douyin + china_bilibili + china_xhs,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "track": track,
    }

    _save_cache("all_hotspots", result)
    total_cn = len(result["china"])
    print(f"\n📊 汇总: 西方 {len(west)} 条, 中国 {total_cn} 条")
    return result
