"""
pipeline/config.py
==================
全局配置：API keys、路径、模型选择、成本控制参数。
所有 secrets 从环境变量读取，绝不硬编码。
"""

import os
from pathlib import Path

# ── 加载 .env 文件 ──────────────────────────────────────────
_root = Path(__file__).resolve().parent.parent
_env_file = _root / ".env"
if _env_file.exists():
    try:
        for line in open(_env_file, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass

# ── 项目根目录 ──────────────────────────────────────────────
ROOT_DIR = _root
DATA_DIR = ROOT_DIR / "data"
CACHE_DIR = ROOT_DIR / ".cache"
OUTPUT_DIR = ROOT_DIR / "output"
VIDEO_DIR = OUTPUT_DIR / "videos"
AUDIO_DIR = OUTPUT_DIR / "audio"
SUBTITLE_DIR = OUTPUT_DIR / "subtitles"
LOG_DIR = ROOT_DIR / "logs"

for d in [DATA_DIR, CACHE_DIR, OUTPUT_DIR, VIDEO_DIR, AUDIO_DIR, SUBTITLE_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Azure OpenAI ────────────────────────────────────────────
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

# 成本优先模型选择（部署名称使用连字符，非圆点）
LLM_MODEL_HEAVY = os.getenv("LLM_MODEL_HEAVY", "gpt-4-1-mini")   # 翻译改写
LLM_MODEL_LIGHT = os.getenv("LLM_MODEL_LIGHT", "gpt-4-1-nano")   # 分类评分

# ── Reddit API ──────────────────────────────────────────────
REDDIT_USER_AGENT = "InfoGapBot/1.0 (by u/your_reddit_username)"

# ── YouTube Data API v3 ────────────────────────────────────
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

# ── FFmpeg ──────────────────────────────────────────────────
FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")
FFPROBE_BIN = os.getenv("FFPROBE_BIN", "ffprobe")

# ── edge-tts 免费 TTS ──────────────────────────────────────
TTS_VOICE_ZH = "zh-CN-XiaoxiaoNeural"
TTS_VOICE_EN = "en-US-AriaNeural"

# ── Whisper 本地模型 ────────────────────────────────────────
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "turbo")  # tiny/base/small/medium/turbo

# ── 视频处理参数 ────────────────────────────────────────────
VIDEO_MAX_DURATION = 60          # Shorts 最长 60 秒
VIDEO_RESOLUTION = (1080, 1920)  # 竖屏 9:16
VIDEO_CRF = 23                   # x264 质量参数
VIDEO_SPEED_FACTOR = 1.03        # 微调速度（规避指纹）
VIDEO_BRIGHTNESS = 0.03          # 微调亮度
VIDEO_CONTRAST = 1.02            # 微调对比度
VIDEO_SATURATION = 1.05          # 微调饱和度
VIDEO_CROP_PX = 8                # 四边裁切像素

# ── 成本控制 ────────────────────────────────────────────────
MONTHLY_BUDGET_USD = 200.0
DAILY_LLM_CALL_LIMIT = 100      # 每日 LLM 调用上限
DAILY_VIDEO_LIMIT = 10           # 每日视频处理上限

# ── 热点抓取 ────────────────────────────────────────────────
FETCH_INTERVAL_MINUTES = 60
WEST_MIN_SCORE = 20000
WEST_MIN_COMMENTS = 200
CHINA_MIN_HEAT = 100  # 万

# ── 内容赛道（扩大版 v2） ──────────────────────────────────
TRACKS = {
    "tech": {
        "west_subreddits": [
            "technology", "futurology", "artificial", "MachineLearning",
            "programming", "gadgets", "cybersecurity", "singularity",
            "InternetIsBeautiful", "webdev", "datascience", "robotics",
        ],
        "west_keywords": [
            "ai", "openai", "chatgpt", "gpt", "claude", "gemini", "llm",
            "tesla", "apple", "nvidia", "startup", "robot", "chip", "quantum",
            "coding", "software", "app", "browser", "hack", "cyber", "data",
        ],
        "china_keywords": [
            "AI", "人工智能", "大模型", "芯片", "科技", "自动驾驶", "机器人",
            "算力", "量子", "开源", "编程", "黑客", "网络安全", "5G", "算法",
            "数据", "智能", "GPT", "模型", "创业", "融资", "互联网",
        ],
    },
    "entertainment": {
        "west_subreddits": [
            "entertainment", "movies", "television", "music", "popculturechat",
            "fauxmoi", "Celebs", "boxoffice", "netflix", "marvelstudios",
            "gaming", "anime", "kpop", "hiphopheads",
        ],
        "west_keywords": [
            "celebrity", "movie", "trailer", "netflix", "disney", "grammy", "oscars",
            "album", "concert", "box office", "anime", "game", "kpop", "marvel",
            "star wars", "taylor swift", "drake", "beyonce", "eminem",
        ],
        "china_keywords": [
            "明星", "电影", "综艺", "热播", "音乐", "演唱会", "票房",
            "剧", "恋爱", "选秀", "偶像", "春晚", "导演", "演员", "歌手",
            "动漫", "游戏", "直播", "粉丝", "追星", "热搜", "八卦",
        ],
    },
    "society": {
        "west_subreddits": [
            "news", "worldnews", "politics", "geopolitics",
            "economics", "law", "environment", "climate",
            "TrueReddit", "neutralnews",
        ],
        "west_keywords": [
            "president", "election", "government", "policy", "ukraine", "war",
            "iran", "china", "trump", "congress", "supreme court", "nato",
            "climate", "immigration", "rights", "protest", "scandal",
        ],
        "china_keywords": [
            "两会", "政策", "社会", "调查", "热议", "官方", "通报",
            "警方", "发布", "改革", "外交", "国际", "经济", "就业",
            "房价", "教育", "医疗", "人口", "养老", "公平", "维权",
        ],
    },
    "lifestyle": {
        "west_subreddits": [
            # 核心：生活技巧
            "LifeProTips", "lifehacks", "YouShouldKnow", "coolguides",
            # 效率/自律
            "productivity", "selfimprovement", "getdisciplined", "DecidingToBeBetter",
            # 冷知识/涨见识
            "Damnthatsinteresting", "todayilearned", "explainlikeimfive", "interestingasfuck",
            # 省钱/理财
            "Frugal", "povertyfinance", "BuyItForLife",
            # 心理/关系
            "socialskills", "confidence", "dating_advice",
            # 健康
            "loseit", "bodyweightfitness", "sleep",
            # 极简/整理
            "minimalism", "declutter", "organizing",
        ],
        "west_keywords": [
            "life pro tip", "lpt", "life hack", "you should know", "til",
            "productivity", "habit", "morning routine", "mindset", "discipline",
            "budget", "save money", "minimalist", "mental health",
            "workout", "diet", "sleep", "meditation", "journal",
            "side hustle", "cool guide", "interesting", "social skill",
            "confidence", "relationship", "organize", "declutter",
        ],
        "china_keywords": [
            "效率", "自律", "成长", "情绪", "心理", "生活方式", "早起",
            "省钱", "理财", "存钱", "健身", "减肥", "护肤", "穿搭",
            "做饭", "租房", "搬家", "断舍离", "独居", "副业", "焦虑",
            "内卷", "躺平", "摆烂", "养生", "冥想",
        ],
    },
    "finance": {
        "west_subreddits": [
            "wallstreetbets", "stocks", "investing", "CryptoCurrency",
            "personalfinance", "financialindependence", "economy",
        ],
        "west_keywords": [
            "stock", "market", "crypto", "bitcoin", "invest", "recession",
            "inflation", "fed", "interest rate", "ipo", "earnings",
            "portfolio", "etf", "dividend", "real estate",
        ],
        "china_keywords": [
            "股市", "基金", "理财", "房价", "比特币", "加密", "A股",
            "牛市", "熊市", "涨停", "跌停", "美联储", "利率", "通胀",
            "经济", "消费", "收入", "工资", "存款", "贷款", "投资",
        ],
    },
    "food_travel": {
        "west_subreddits": [
            "food", "FoodPorn", "Cooking", "travel", "solotravel",
            "EatCheapAndHealthy", "AskCulinary", "streetfood",
        ],
        "west_keywords": [
            "recipe", "restaurant", "travel", "food", "cooking", "street food",
            "michelin", "ramen", "sushi", "bbq", "vegan", "coffee",
            "hidden gem", "budget travel", "backpack",
        ],
        "china_keywords": [
            "美食", "探店", "种草", "旅行", "攻略", "打卡", "网红店",
            "火锅", "奶茶", "烧烤", "小吃", "特产", "民宿", "自驾",
            "出片", "拍照", "小众", "宝藏", "推荐", "测评",
        ],
    },
}
