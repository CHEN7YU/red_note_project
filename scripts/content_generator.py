"""
跨境热点内容抓取 & 自动生成工具
=============================
用于自动抓取欧美和中国的社交媒体热点，进行信息差分析，
并生成适合小红书和抖音发布的图文/视频文案。

使用方法：
    python content_generator.py          # 抓取最新热点
    python content_generator.py --fetch  # 仅抓取不生成
    python content_generator.py --gen    # 从缓存生成内容
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from math import log
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError
from html.parser import HTMLParser

# ============================================================
# 配置区
# ============================================================

OUTPUT_DIR = Path(__file__).parent.parent / "content"
CACHE_DIR = Path(__file__).parent.parent / ".cache"

HOT_WINDOW_HOURS = 24
WEST_MIN_SCORE = 25000
WEST_MIN_COMMENTS = 300
CHINA_MIN_HEAT_WAN = 120

LOW_QUALITY_PATTERNS = [
    r"^\W+$",
    r"^\d+(\.\d+)?\s*万热度$",
    r"^who('|’)s your favorite",
    r"^guess which",
]

WEST_ALLOWED_SUBREDDITS = {
    "news", "worldnews", "politics", "sports", "soccer", "nba", "nfl",
    "technology", "futurology", "entertainment", "movies", "television",
    "music", "popculturechat", "fauxmoi", "business", "science"
}

WEST_HIGH_VALUE_KEYWORDS = [
    "super bowl", "oscars", "grammy", "billboard", "netflix", "disney",
    "movie", "trailer", "celebrity", "president", "trump", "biden",
    "election", "war", "fbi", "tesla", "apple", "openai", "chatgpt",
    "ai", "nasa", "olympic", "world cup", "u.s.", "ukraine"
]

NOISE_KEYWORDS = [
    "hamburger", "burger", "whopper", "guide", "cool guide", "my dad", "mouse",
    "testicular", "省钱", "补贴", "元买", "替代品", "教程", "实战", "面试题",
    "框架", "趋势前瞻", "全栈", "实盘"
]

TRACK_PROFILES = {
    "mixed": {
        "west_subreddits": set(),
        "west_keywords": [],
        "china_keywords": [],
    },
    "entertainment": {
        "west_subreddits": {"entertainment", "movies", "television", "music", "fauxmoi", "popculturechat"},
        "west_keywords": ["celebrity", "movie", "trailer", "music", "album", "netflix", "disney", "grammy", "oscars", "super bowl", "halftime"],
        "china_keywords": ["明星", "电影", "票房", "综艺", "演唱会", "热播", "剧", "艺人", "音乐", "娱乐"],
    },
    "sports": {
        "west_subreddits": {"sports", "nba", "nfl", "soccer"},
        "west_keywords": ["nba", "nfl", "soccer", "olympic", "world cup", "super bowl", "championship", "final", "athlete"],
        "china_keywords": ["体育", "比赛", "联赛", "冠军", "足球", "篮球", "冬奥", "奥运", "中超", "国足", "电竞"],
    },
    "news": {
        "west_subreddits": {"news", "worldnews", "politics", "law"},
        "west_keywords": ["president", "election", "war", "fbi", "government", "policy", "sen.", "trump", "biden", "ukraine", "israel"],
        "china_keywords": ["两会", "政策", "发布", "通报", "警方", "调查", "国际", "外交", "社会", "官方"],
    },
    "tech": {
        "west_subreddits": {"technology", "futurology", "science", "business"},
        "west_keywords": ["ai", "openai", "chatgpt", "tesla", "apple", "google", "nvidia", "chip", "startup", "nasa", "robot"],
        "china_keywords": ["ai", "人工智能", "大模型", "芯片", "机器人", "科技", "发布会", "算力", "自动驾驶", "互联网"],
    },
}

# 抓取来源配置
WESTERN_SOURCES = {
    "google_trends_us": {
        "url": "https://trends.google.com/trending?geo=US",
        "name": "Google Trends (US)",
        "type": "trends",
    },
    "reddit_popular": {
        "url": "https://www.reddit.com/r/popular/.json",
        "name": "Reddit Popular",
        "type": "reddit",
    },
    "buzzfeed_trending": {
        "url": "https://www.buzzfeed.com/trending",
        "name": "BuzzFeed Trending",
        "type": "webpage",
    },
}

CHINA_SOURCES = {
    "tophub": {
        "url": "https://tophub.today/",
        "name": "今日热榜",
        "type": "webpage",
    },
    "weibo_hot": {
        "url": "https://weibo.com/ajax/side/hotSearch",
        "name": "微博热搜",
        "type": "api",
    },
}

# 小红书文案模板
XHS_TEMPLATE = """# 📱 {title}

## 🔥 爆款指数：{rating}

## 📋 话题背景
{background}

## 📲 素材来源
{sources}

---

## 🔴 小红书文案（图文笔记）

### 标题（选一个）：
{titles}

### 正文：
```
{content}
```

### 配图建议：
{images}

### 标签：
```
{tags}
```
"""

# 抖音文案模板
DOUYIN_TEMPLATE = """
---

## 🎵 抖音文案（视频脚本）

### 视频类型：{video_type}

### 脚本：
```
{script}
```

### 抖音标签：
```
{tags}
```

### BGM建议：
{bgm}
"""


# ============================================================
# 工具函数
# ============================================================

class SimpleHTMLTextExtractor(HTMLParser):
    """简单的HTML文本提取器"""
    
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self._skip = False
    
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'):
            self._skip = True
    
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self._skip = False
    
    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self.text_parts.append(text)
    
    def get_text(self):
        return '\n'.join(self.text_parts)


def fetch_url(url: str, timeout: int = 15) -> str:
    """抓取URL内容"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='ignore')
    except (URLError, Exception) as e:
        print(f"  ⚠️ 抓取失败 {url}: {e}")
        return ""


def extract_text(html: str) -> str:
    """从HTML中提取纯文本"""
    parser = SimpleHTMLTextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.get_text()


def save_cache(name: str, data: dict):
    """保存抓取缓存"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{name}_{datetime.now().strftime('%Y%m%d')}.json"
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  💾 缓存已保存: {cache_file.name}")


def load_cache(name: str) -> dict | None:
    """加载今日缓存"""
    cache_file = CACHE_DIR / f"{name}_{datetime.now().strftime('%Y%m%d')}.json"
    if cache_file.exists():
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def is_low_quality_title(title: str) -> bool:
    """标题低质判定（过短、纯数字热度、泛问答等）"""
    t = re.sub(r"\s+", " ", (title or "")).strip()
    if not t or len(t) < 8:
        return True
    lower = t.lower()
    for pattern in LOW_QUALITY_PATTERNS:
        if re.search(pattern, lower):
            return True
    return False


def normalize_dedupe_key(title: str) -> str:
    """用于去重的标题归一化"""
    t = (title or "").lower()
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"[^\w\u4e00-\u9fff]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def dedupe_topics(topics: list[dict], score_key: str) -> list[dict]:
    """按标题去重，保留评分更高的一条"""
    picked = {}
    for topic in topics:
        key = normalize_dedupe_key(topic.get("title", ""))
        if not key:
            continue
        old = picked.get(key)
        if not old or topic.get(score_key, 0) > old.get(score_key, 0):
            picked[key] = topic
    return list(picked.values())


def parse_heat_wan(text: str) -> int | None:
    """从标题中提取“万热度”数值"""
    m = re.search(r"(\d+(?:\.\d+)?)\s*万热度", text)
    if not m:
        m = re.search(r"(\d+(?:\.\d+)?)\s*万", text)
    if not m:
        return None
    try:
        return int(float(m.group(1)))
    except ValueError:
        return None


def western_hot_score(topic: dict) -> float:
    """西方话题热度评分：点赞+评论，取对数稳定量级"""
    score = max(topic.get("score", 0), 0)
    comments = max(topic.get("num_comments", 0), 0)
    return log(score + 1) * 0.7 + log(comments + 1) * 0.3


def has_high_value_signal(title: str, subreddit: str = "") -> bool:
    """判断是否属于更可能可传播的热点主题"""
    lower = (title or "").lower()
    sub = (subreddit or "").lower()

    if any(noise in lower for noise in NOISE_KEYWORDS):
        return False

    if sub in WEST_ALLOWED_SUBREDDITS:
        return True

    return any(k in lower for k in WEST_HIGH_VALUE_KEYWORDS)


def filter_western_hotspots(topics: list[dict]) -> list[dict]:
    """筛选24小时内的高热欧美话题"""
    now_utc = datetime.utcnow().timestamp()
    min_created = now_utc - HOT_WINDOW_HOURS * 3600

    filtered = []
    for topic in topics:
        created_utc = topic.get("created_utc", 0)
        score = topic.get("score", 0)
        comments = topic.get("num_comments", 0)
        title = topic.get("title", "")
        subreddit = topic.get("subreddit", "")

        if created_utc and created_utc < min_created:
            continue
        if score < WEST_MIN_SCORE or comments < WEST_MIN_COMMENTS:
            continue
        if is_low_quality_title(title):
            continue
        if not has_high_value_signal(title, subreddit):
            continue

        topic["hot_score"] = western_hot_score(topic)
        filtered.append(topic)

    if len(filtered) < 10:
        for topic in topics:
            score = topic.get("score", 0)
            comments = topic.get("num_comments", 0)
            title = topic.get("title", "")
            subreddit = topic.get("subreddit", "")
            if score < int(WEST_MIN_SCORE * 0.65):
                continue
            if comments < int(WEST_MIN_COMMENTS * 0.65):
                continue
            if is_low_quality_title(title):
                continue
            if not has_high_value_signal(title, subreddit):
                continue
            topic["hot_score"] = western_hot_score(topic)
            filtered.append(topic)

    filtered = dedupe_topics(filtered, "hot_score")
    filtered.sort(key=lambda x: x.get("hot_score", 0), reverse=True)
    return filtered[:30]


def filter_china_hotspots(topics: list[dict]) -> list[dict]:
    """筛选高热中文话题，优先保留有热度值的内容"""
    filtered = []

    for topic in topics:
        title = topic.get("title", "")
        heat_wan = topic.get("heat_wan")
        lower = title.lower()

        if is_low_quality_title(title):
            continue
        if not any('\u4e00' <= c <= '\u9fff' for c in title):
            continue
        if any(noise in lower for noise in NOISE_KEYWORDS):
            continue
        if heat_wan is not None and heat_wan < CHINA_MIN_HEAT_WAN:
            continue

        topic["hot_score"] = float(heat_wan if heat_wan is not None else 0)
        filtered.append(topic)

    filtered = dedupe_topics(filtered, "hot_score")
    filtered.sort(key=lambda x: x.get("hot_score", 0), reverse=True)
    return filtered[:30]


def parse_track_arg(args: list[str]) -> str:
    """解析赛道参数 --track"""
    track = "mixed"
    if "--track" in args:
        idx = args.index("--track")
        if idx + 1 < len(args):
            track = args[idx + 1].strip().lower()

    for arg in args:
        if arg.startswith("--track="):
            track = arg.split("=", 1)[1].strip().lower()

    if track not in TRACK_PROFILES:
        print(f"  ⚠️ 未知赛道 '{track}'，将使用 mixed")
        return "mixed"
    return track


def parse_strict_track_arg(args: list[str]) -> bool:
    """解析严格赛道参数 --strict-track"""
    return "--strict-track" in args


def apply_track_filter(
    western_topics: list[dict],
    chinese_topics: list[dict],
    track: str,
    strict_track: bool = False,
) -> tuple[list[dict], list[dict]]:
    """按赛道过滤中西方话题"""
    if track == "mixed":
        return western_topics, chinese_topics

    profile = TRACK_PROFILES[track]
    west_subreddits = profile["west_subreddits"]
    west_keywords = [k.lower() for k in profile["west_keywords"]]
    china_keywords = profile["china_keywords"]

    west_filtered = []
    for topic in western_topics:
        title = topic.get("title", "").lower()
        subreddit = topic.get("subreddit", "").lower()
        if subreddit in west_subreddits or any(k in title for k in west_keywords):
            west_filtered.append(topic)

    china_filtered = []
    for topic in chinese_topics:
        title = topic.get("title", "")
        lower = title.lower()
        if any(k in title for k in china_keywords) or any(k.lower() in lower for k in china_keywords):
            china_filtered.append(topic)

    if not west_filtered and not strict_track:
        print(f"  ⚠️ 赛道[{track}]西方话题不足，回退到综合候选前5条")
        west_filtered = western_topics[:5]
    if not china_filtered and not strict_track:
        print(f"  ⚠️ 赛道[{track}]国内话题不足，回退到综合候选前5条")
        china_filtered = chinese_topics[:5]

    mode_text = "strict" if strict_track else "soft"
    print(f"  🎯 赛道过滤[{track}/{mode_text}] 西方: {len(west_filtered)} / 国内: {len(china_filtered)}")
    return west_filtered, china_filtered


# ============================================================
# 抓取模块
# ============================================================

def parse_reddit_topics(raw: str) -> list[dict]:
    """解析Reddit JSON到统一话题结构"""
    if not raw:
        return []
    try:
        data = json.loads(raw)
        topics = []
        for post in data.get('data', {}).get('children', []):
            d = post.get('data', {})
            topics.append({
                'title': d.get('title', ''),
                'subreddit': d.get('subreddit', ''),
                'score': d.get('score', 0),
                'url': f"https://reddit.com{d.get('permalink', '')}",
                'num_comments': d.get('num_comments', 0),
                'created_utc': d.get('created_utc', 0),
            })
        return topics
    except json.JSONDecodeError:
        return []


def fetch_reddit_popular(subreddits: list[str] | None = None) -> list[dict]:
    """抓取Reddit热门话题（可按subreddit定向）"""
    topics = []

    if subreddits:
        print(f"📡 抓取 Reddit 定向版块: {', '.join(subreddits)}")
        for sub in subreddits:
            raw = fetch_url(f"https://www.reddit.com/r/{sub}/hot/.json?limit=12")
            topics.extend(parse_reddit_topics(raw))
    else:
        print("📡 抓取 Reddit 热门...")
        raw = fetch_url("https://www.reddit.com/r/popular/.json?limit=25")
        topics.extend(parse_reddit_topics(raw))

    topics = dedupe_topics(topics, "score")
    topics.sort(key=lambda x: x.get('score', 0), reverse=True)
    print(f"  ✅ 获取 {len(topics)} 个话题")
    return topics


def fetch_google_trends() -> list[dict]:
    """抓取Google Trends热搜词"""
    print("📡 抓取 Google Trends...")
    raw = fetch_url("https://trends.google.com/trending?geo=US&hours=168")
    if not raw:
        return []
    
    text = extract_text(raw)
    # 简单提取趋势关键词
    topics = []
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if any(kw in line for kw in ['Active', '1,000%', '400%']):
            # 尝试提取关键词
            parts = line.split()
            if len(parts) >= 2:
                topic = ' '.join(parts[:3]).strip()
                topics.append({'keyword': topic, 'raw': line})
    
    print(f"  ✅ 获取 {len(topics)} 个趋势词")
    return topics


def fetch_tophub() -> list[dict]:
    """抓取今日热榜"""
    print("📡 抓取 今日热榜...")
    raw = fetch_url("https://tophub.today/")
    if not raw:
        return []
    
    text = extract_text(raw)
    # 提取微博热搜等关键榜单
    topics = []
    lines = text.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if re.match(r'^\d+\s+.+', line) and len(line) > 5 and len(line) < 120:
            m = re.match(r'^(\d+)\s+(.+)$', line)
            if not m:
                continue
            rank = int(m.group(1))
            raw_title = m.group(2).strip()
            heat_wan = parse_heat_wan(raw_title)
            cleaned_title = re.sub(r'\s*\d+(?:\.\d+)?\s*万热度.*$', '', raw_title).strip()
            cleaned_title = re.sub(r'\s*\d+(?:\.\d+)?\s*万.*$', '', cleaned_title).strip()
            topics.append({
                'title': cleaned_title or raw_title,
                'source': '今日热榜',
                'rank': rank,
                'heat_wan': heat_wan,
            })
    
    print(f"  ✅ 获取 {len(topics)} 个话题")
    return topics[:80]


def fetch_weibo_hot() -> list[dict]:
    """抓取微博热搜"""
    print("📡 抓取 微博热搜...")
    raw = fetch_url("https://weibo.com/ajax/side/hotSearch")
    if not raw:
        return []

    try:
        data = json.loads(raw)
        realtime = data.get("data", {}).get("realtime", [])
        topics = []
        for i, item in enumerate(realtime, 1):
            title = item.get("word", "") or item.get("note", "")
            if not title:
                continue
            num = item.get("num") or 0
            try:
                heat_wan = int(num / 10000) if num else None
            except Exception:
                heat_wan = None
            topics.append({
                "title": title,
                "source": "微博热搜",
                "rank": i,
                "heat_wan": heat_wan,
            })
        print(f"  ✅ 获取 {len(topics)} 个话题")
        return topics
    except json.JSONDecodeError:
        print("  ⚠️ 微博热搜 JSON解析失败")
        return []


def fetch_baidu_hot() -> list[dict]:
    """抓取百度热搜（作为中文源回退）"""
    print("📡 抓取 百度热搜...")
    raw = fetch_url("https://top.baidu.com/board?tab=realtime")
    if not raw:
        return []

    try:
        marker = "<!--s-data:"
        start = raw.find(marker)
        if start < 0:
            return []
        start += len(marker)
        end = raw.find("-->", start)
        if end < 0:
            return []

        payload = raw[start:end].strip()
        data = json.loads(payload)
        cards = data.get("data", {}).get("cards", [])
        if not cards:
            return []

        content = cards[0].get("content", [])
        topics = []
        for i, item in enumerate(content, 1):
            title = item.get("query", "")
            if not title:
                continue
            hot_score_raw = item.get("hotScore")
            try:
                hot_score = int(hot_score_raw) if hot_score_raw is not None else 0
            except Exception:
                hot_score = 0

            topics.append({
                "title": title,
                "source": "百度热搜",
                "rank": i,
                "heat_wan": int(hot_score / 10000) if hot_score > 0 else None,
            })

        print(f"  ✅ 获取 {len(topics)} 个话题")
        return topics
    except Exception:
        print("  ⚠️ 百度热搜解析失败")
        return []


# ============================================================
# 分析模块
# ============================================================

def analyze_information_gap(western: list, chinese: list) -> dict:
    """分析东西方信息差"""
    print("\n🔍 分析信息差...")
    
    result = {
        'west_to_china': [],  # 西方热门但中国未报道
        'china_to_west': [],  # 中国热门但西方不知道
        'timestamp': datetime.now().isoformat(),
    }
    
    # 简单关键词匹配判定信息差（在高热候选中进一步筛选）
    chinese_text = ' '.join([t.get('title', '') for t in chinese]).lower()
    western_text = ' '.join([t.get('title', '') for t in western]).lower()
    
    for topic in western:
        title = topic.get('title', '')
        # 检查这个话题在中国榜单上是否出现
        title_words = title.lower().split()
        match_count = sum(1 for w in title_words if w in chinese_text and len(w) > 3)
        if match_count < 2:  # 信息差较大
            result['west_to_china'].append({
                **topic,
                'gap_score': 1.0 - (match_count / max(len(title_words), 1))
            })
    
    for topic in chinese:
        title = topic.get('title', '')
        if not any(c in western_text for c in title if '\u4e00' <= c <= '\u9fff'):
            result['china_to_west'].append({
                **topic,
                'gap_score': 0.9
            })
    
    # 按信息差分数排序
    result['west_to_china'].sort(
        key=lambda x: (x.get('gap_score', 0), x.get('hot_score', 0)),
        reverse=True,
    )
    result['china_to_west'].sort(
        key=lambda x: (x.get('gap_score', 0), x.get('hot_score', 0)),
        reverse=True,
    )
    
    print(f"  📊 西→东信息差话题: {len(result['west_to_china'])} 个")
    print(f"  📊 东→西信息差话题: {len(result['china_to_west'])} 个")
    
    return result


# ============================================================
# 内容生成模块
# ============================================================

def generate_xhs_content(topic: dict, direction: str = "west_to_china") -> str:
    """生成小红书图文内容"""
    title = topic.get('title', '未知话题')
    score = topic.get('score', 0)
    
    # 根据热度计算爆款指数
    if score > 50000:
        rating = "⭐⭐⭐⭐⭐"
    elif score > 10000:
        rating = "⭐⭐⭐⭐"
    elif score > 5000:
        rating = "⭐⭐⭐"
    else:
        rating = "⭐⭐"
    
    content = XHS_TEMPLATE.format(
        title=title,
        rating=rating,
        background=f"- 来源: {'欧美社交媒体' if direction == 'west_to_china' else '中国社交媒体'}\n- 热度: {score}",
        sources=f"- Reddit/Twitter/BuzzFeed 等平台\n- URL: {topic.get('url', 'N/A')}",
        titles=f"1. 「{title}」\n2. 「独家｜{title}」\n3. 「全网都在说的{title}」",
        content=f"【待二次创作】\n\n话题核心：{title}\n\n请根据具体内容进行文案撰写",
        images="1. 核心事件截图\n2. 人物/场景照片\n3. 网友评论翻译截图\n...",
        tags=f"#信息差 #欧美热点 #热点话题 #{title.split()[0] if title.split() else '热搜'}",
    )
    
    return content


def generate_report(gap_data: dict) -> str:
    """生成热点报告"""
    d = datetime.now()
    now = f"{d.year}年{d.month}月{d.day}日"
    
    report = f"""# 📊 跨境热点信息差报告
## 报告日期：{now}

---

## 🇺🇸→🇨🇳 欧美热点（国内未报道）

| # | 话题 | 热度 | 信息差指数 | 来源 |
|---|------|------|-----------|------|
"""
    
    for i, topic in enumerate(gap_data['west_to_china'][:15], 1):
        title = topic.get('title', '')[:40]
        score = topic.get('score', 'N/A')
        gap = f"{topic.get('gap_score', 0):.1%}"
        source = topic.get('subreddit', 'web')
        report += f"| {i} | {title} | {score} | {gap} | {source} |\n"
    
    report += f"""
---

## 🇨🇳→🇺🇸 国内热点（海外未知）

| # | 话题 | 信息差指数 | 来源 |
|---|------|-----------|------|
"""
    
    for i, topic in enumerate(gap_data['china_to_west'][:15], 1):
        title = topic.get('title', '')[:40]
        gap = f"{topic.get('gap_score', 0):.1%}"
        source = topic.get('source', '综合')
        report += f"| {i} | {title} | {gap} | {source} |\n"
    
    return report


# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 60)
    print("🔥 跨境热点内容抓取 & 生成工具")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    
    mode = "all"
    track = parse_track_arg(sys.argv[1:])
    strict_track = parse_strict_track_arg(sys.argv[1:])
    print(f"🎛️ 赛道: {track} ({'strict' if strict_track else 'soft'})")

    if len(sys.argv) > 1:
        if "--fetch" in sys.argv:
            mode = "fetch"
        elif "--gen" in sys.argv:
            mode = "gen"
    
    # Step 1: 抓取热点
    if mode in ("all", "fetch"):
        print("\n📡 Step 1: 抓取热点数据...")
        print("-" * 40)
        
        west_track_subs = sorted(TRACK_PROFILES[track]["west_subreddits"]) if track != "mixed" else None
        western_topics = fetch_reddit_popular(west_track_subs)
        # google_trends = fetch_google_trends()
        chinese_topics = fetch_tophub() + fetch_weibo_hot() + fetch_baidu_hot()

        western_topics = filter_western_hotspots(western_topics)
        chinese_topics = filter_china_hotspots(chinese_topics)
        western_topics, chinese_topics = apply_track_filter(
            western_topics,
            chinese_topics,
            track,
            strict_track,
        )
        print(f"  🔥 西方高热候选: {len(western_topics)}")
        print(f"  🔥 国内高热候选: {len(chinese_topics)}")
        
        # 缓存数据
        all_data = {
            'western': western_topics,
            'chinese': chinese_topics,
            'track': track,
            'strict_track': strict_track,
            'timestamp': datetime.now().isoformat(),
        }
        save_cache('hotspots', all_data)
    
    if mode == "fetch":
        print("\n✅ 数据抓取完成！使用 --gen 生成内容。")
        return
    
    # Step 2: 加载数据
    if mode == "gen":
        print("\n📂 加载缓存数据...")
        all_data = load_cache('hotspots')
        if not all_data:
            print("  ❌ 未找到今日缓存，请先运行 --fetch")
            return
        western_topics = all_data['western']
        chinese_topics = all_data['chinese']

        # 对历史缓存再做一次新版高热过滤，确保生成质量
        western_topics = filter_western_hotspots(western_topics)
        chinese_topics = filter_china_hotspots(chinese_topics)
        western_topics, chinese_topics = apply_track_filter(
            western_topics,
            chinese_topics,
            track,
            strict_track,
        )
        print(f"  🔥 西方高热候选: {len(western_topics)}")
        print(f"  🔥 国内高热候选: {len(chinese_topics)}")
    
    # Step 3: 分析信息差
    print("\n🔍 Step 2: 分析信息差...")
    print("-" * 40)
    gap_data = analyze_information_gap(western_topics, chinese_topics)
    
    # Step 4: 生成报告
    print("\n📝 Step 3: 生成内容...")
    print("-" * 40)
    
    report = generate_report(gap_data)
    report_path = OUTPUT_DIR / f"report_{datetime.now().strftime('%Y%m%d')}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"  📊 报告已生成: {report_path}")
    
    # Step 5: 生成top话题的内容
    generated_dir = OUTPUT_DIR / f"generated_{datetime.now().strftime('%Y%m%d')}"
    generated_dir.mkdir(parents=True, exist_ok=True)
    
    for i, topic in enumerate(gap_data['west_to_china'][:5], 1):
        content = generate_xhs_content(topic, "west_to_china")
        filepath = generated_dir / f"west_{i:02d}_{topic.get('title', 'unknown')[:20].replace(' ', '_')}.md"
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✅ 已生成: {filepath.name}")
    
    for i, topic in enumerate(gap_data['china_to_west'][:5], 1):
        content = generate_xhs_content(topic, "china_to_west")
        filepath = generated_dir / f"china_{i:02d}_{topic.get('title', 'unknown')[:20]}.md"
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✅ 已生成: {filepath.name}")
    
    # 完成
    print("\n" + "=" * 60)
    print("🎉 完成！")
    print(f"📁 报告位置: {report_path}")
    print(f"📁 生成内容: {generated_dir}")
    print(f"\n💡 提示:")
    print(f"   - 查看 content/west_to_china/ 获取已撰写的成品内容")
    print(f"   - 查看 content/china_to_west/ 获取反向内容")
    print(f"   - 查看 templates/ 获取创作模板")
    print(f"   - 查看 assets/image_sources.md 获取素材来源")
    print("=" * 60)


if __name__ == "__main__":
    main()
