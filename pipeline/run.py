"""
pipeline/run.py
===============
主入口：编排完整管线。
用法:
    python -m pipeline.run fetch          # 仅抓取热点
    python -m pipeline.run score          # 抓取 + LLM 评分
    python -m pipeline.run translate      # 抓取 + 评分 + 翻译改写    python -m pipeline matrix         # 全赛道双向矩阵 (EN→CN + CN→EN × 4赛道 × Top5)    python -m pipeline.run video <url>    # 处理单个视频
    python -m pipeline.run full           # 完整管线
    python -m pipeline.run test           # 快速测试各模块
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR, OUTPUT_DIR, VIDEO_DIR
from .fetcher import (
    fetch_all_hotspots, fetch_reddit, fetch_weibo_hot,
    fetch_baidu_hot, fetch_zhihu_hot, fetch_douyin_hot, fetch_bilibili_hot,
    fetch_xiaohongshu_hot, fetch_x_trending, fetch_tiktok_trending, fetch_youtube_trending,
)
from .llm import batch_score_topics, score_topic, classify_topics_batch, translate_and_rewrite, generate_video_script
from .video_processor import (
    download_video,
    re_encode_video,
    extract_audio,
    transcribe_audio,
    segments_to_srt,
    text_to_speech,
    process_video_pipeline,
    get_duration,
)


def cmd_fetch(track: str = "tech"):
    """抓取热点"""
    result = fetch_all_hotspots(track=track)

    # 保存结果
    today = datetime.now().strftime("%Y%m%d")
    out_file = DATA_DIR / f"hotspots_{today}_{track}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n💾 热点数据已保存: {out_file}")
    return result


def cmd_score(track: str = "tech"):
    """抓取 + 评分"""
    hotspots = cmd_fetch(track)

    # 合并所有话题
    all_topics = hotspots.get("west", []) + hotspots.get("china", [])

    # 预筛选：去掉太短的标题
    valid = [t for t in all_topics if len(t.get("title", "")) > 10]
    print(f"\n📊 开始 LLM 评分 ({len(valid)} 条有效话题)...")

    scored = batch_score_topics(valid, max_count=20)

    # 保存
    today = datetime.now().strftime("%Y%m%d")
    out_file = DATA_DIR / f"scored_{today}_{track}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(scored, f, ensure_ascii=False, indent=2)

    # 打印 top10
    print(f"\n🏆 Top 10 跨语言潜力话题 (v2 多维评分):")
    print("─" * 70)
    for i, t in enumerate(scored[:10], 1):
        s = t.get("llm_score", {})
        total = s.get("total_score", s.get("score", 0))
        gap = s.get("info_gap_score", "?")
        viral = s.get("viral_structure_score", "?")
        aud = s.get("audience_match_score", "?")
        print(f"  {i:2d}. [{total}分] [{s.get('direction', '?')}] {t['title'][:60]}")
        print(f"      信息差:{gap} 爆款结构:{viral} 受众匹配:{aud} | {s.get('emotion', '')}")
        print(f"      {s.get('reason', 'N/A')[:80]}")
        if s.get("suggested_angle"):
            print(f"      💡 角度: {s.get('suggested_angle', '')[:60]}")
        if s.get("risk") and s.get("risk") != "无":
            print(f"      ⚠️ 风险: {s.get('risk', '')[:60]}")

    print(f"\n💾 评分结果已保存: {out_file}")
    return scored


def cmd_translate(track: str = "tech"):
    """抓取 + 评分 + 翻译改写 top5"""
    scored = cmd_score(track)
    top5 = scored[:5]

    results = []
    for i, topic in enumerate(top5, 1):
        title = topic["title"]
        lang = topic.get("language", "en")
        direction = topic.get("llm_score", {}).get("direction", "E2C")

        target_lang = "zh" if direction == "E2C" else "en"
        source_lang = "en" if direction == "E2C" else "zh"

        print(f"\n✍️ [{i}/5] 翻译改写: {title[:50]}...")
        rewrite = translate_and_rewrite(title, source_lang=source_lang, target_lang=target_lang)
        script = generate_video_script(
            rewrite.get("rewritten_titles", [title])[0],
            language=target_lang,
        )

        result = {
            "original": topic,
            "rewrite": rewrite,
            "script": script,
        }
        results.append(result)

        # 打印
        print(f"  📝 改写标题: {rewrite.get('rewritten_titles', ['N/A'])[0]}")
        print(f"  🎬 脚本钩子: {script.get('hook', 'N/A')[:60]}")

    # 保存
    today = datetime.now().strftime("%Y%m%d")
    out_file = DATA_DIR / f"translated_{today}_{track}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n💾 翻译改写结果已保存: {out_file}")
    return results


def cmd_video(url: str):
    """处理单个视频"""
    name = datetime.now().strftime("%Y%m%d_%H%M%S")
    result = process_video_pipeline(
        source_url=url,
        output_name=name,
        new_script_zh="这是一个测试视频。我们正在验证自动化视频处理管线是否能正常工作。",
        new_script_en="This is a test video. We are verifying the automated video processing pipeline.",
    )
    print(f"\n📹 视频处理结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
    return result


def cmd_test():
    """快速测试各模块是否正常工作"""
    print("=" * 60)
    print("🧪 系统模块测试")
    print("=" * 60)

    results = {}

    # Test 1: FFmpeg
    print("\n── Test 1: FFmpeg ──")
    import subprocess
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        ver = r.stdout.split("\n")[0] if r.returncode == 0 else "NOT FOUND"
        results["ffmpeg"] = "✅" if r.returncode == 0 else "❌"
        print(f"  {results['ffmpeg']} FFmpeg: {ver[:60]}")
    except FileNotFoundError:
        results["ffmpeg"] = "❌"
        print(f"  ❌ FFmpeg 未安装")

    # Test 2: yt-dlp
    print("\n── Test 2: yt-dlp ──")
    try:
        import yt_dlp
        results["yt-dlp"] = "✅"
        print(f"  ✅ yt-dlp {yt_dlp.version.__version__}")
    except ImportError:
        results["yt-dlp"] = "❌"
        print(f"  ❌ yt-dlp 未安装")

    # Test 3: edge-tts
    print("\n── Test 3: edge-tts ──")
    try:
        import edge_tts
        results["edge-tts"] = "✅"
        print(f"  ✅ edge-tts 已导入")
    except ImportError:
        results["edge-tts"] = "❌"
        print(f"  ❌ edge-tts 未安装")

    # Test 4: httpx (for fetcher)
    print("\n── Test 4: httpx ──")
    try:
        import httpx
        results["httpx"] = "✅"
        print(f"  ✅ httpx {httpx.__version__}")
    except ImportError:
        results["httpx"] = "❌"
        print(f"  ❌ httpx 未安装")

    # Test 5: openai SDK
    print("\n── Test 5: openai SDK ──")
    try:
        import openai
        results["openai"] = "✅"
        print(f"  ✅ openai {openai.__version__}")
    except ImportError:
        results["openai"] = "❌"
        print(f"  ❌ openai 未安装")

    # Test 6: Azure OpenAI 环境变量
    print("\n── Test 6: Azure OpenAI 配置 ──")
    from .config import AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY
    if AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY:
        results["azure_config"] = "✅"
        print(f"  ✅ Endpoint: {AZURE_OPENAI_ENDPOINT[:40]}...")
    else:
        results["azure_config"] = "⚠️"
        print(f"  ⚠️ 环境变量未设置 (AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY)")
        print(f"     LLM 功能将不可用，其他模块正常")

    # Test 7: Whisper
    print("\n── Test 7: Whisper ──")
    try:
        import whisper
        results["whisper"] = "✅"
        print(f"  ✅ whisper 已导入")
    except ImportError:
        results["whisper"] = "⚠️"
        print(f"  ⚠️ whisper 未安装 (可选，用于语音识别)")

    # Test 8: Reddit API
    print("\n── Test 8: Reddit API 连通性 ──")
    try:
        r = httpx.get(
            "https://www.reddit.com/r/technology/hot.json?limit=1",
            headers={"User-Agent": "TestBot/1.0"},
            timeout=10,
            follow_redirects=True,
        )
        if r.status_code == 200 and "data" in r.json():
            results["reddit"] = "✅"
            print(f"  ✅ Reddit API 正常")
        else:
            results["reddit"] = "❌"
            print(f"  ❌ Reddit API 返回 {r.status_code}")
    except Exception as e:
        results["reddit"] = "❌"
        print(f"  ❌ Reddit API 错误: {e}")

    # 汇总
    print("\n" + "=" * 60)
    print("📊 测试汇总")
    print("─" * 60)
    all_ok = True
    for name, status in results.items():
        print(f"  {status} {name}")
        if status == "❌":
            all_ok = False

    if all_ok:
        print("\n✅ 所有核心模块正常！可以开始使用。")
    else:
        print("\n⚠️ 部分模块缺失，请按提示安装。")

    return results


def _cn_category_map(category: str) -> set:
    """将 B站/知乎 原生分类映射到我们的赛道名"""
    c = category.lower()
    mapping = {
        "tech": {"科技", "数码", "计算机", "互联网", "人工智能", "编程", "软件"},
        "entertainment": {"影视", "音乐", "综艺", "娱乐", "动画", "番剧", "游戏", "鬼畜"},
        "society": {"社会", "政治", "时政", "国际", "军事", "法律", "教育"},
        "lifestyle": {"生活", "美食", "旅行", "时尚", "运动", "健康", "心理"},
        "finance": {"财经", "股票", "基金", "经济", "理财", "商业"},
        "food_travel": {"美食", "旅游", "探店", "vlog"},
    }
    result = set()
    for track, keywords in mapping.items():
        if any(kw in c for kw in keywords):
            result.add(track)
    return result


def cmd_matrix(top_n: int = 5):
    """
    全赛道双向矩阵：每个赛道 × 每个方向(EN→CN, CN→EN) × Top N
    输出一份完整的矩阵报告到 data/matrix_{date}.md 和 .json
    """
    from .config import TRACKS

    all_tracks = list(TRACKS.keys())
    today = datetime.now().strftime("%Y%m%d")

    print(f"\n🔮 全赛道双向矩阵 (Top {top_n} × {len(all_tracks)} 赛道 × 2 方向)")
    print("=" * 70)

    # Step 1: 抓取所有数据（一次性，最大化数据源）
    print("\n── Step 1: 抓取热点 ──")

    # 西方：r/popular + 每个赛道的专属 subreddit
    west_all = fetch_reddit(subreddits=["popular", "all"], limit=100)
    all_subs_flat = set()
    for track_cfg in TRACKS.values():
        all_subs_flat.update(track_cfg.get("west_subreddits", []))
    # 分批抓，每批最多 10 个 subreddit
    sub_list = list(all_subs_flat)
    for i in range(0, len(sub_list), 8):
        batch = sub_list[i:i+8]
        extra = fetch_reddit(subreddits=batch, limit=50)
        west_all.extend(extra)

    # 西方额外：X + TikTok + YouTube
    west_all += fetch_x_trending()
    west_all += fetch_tiktok_trending()
    west_all += fetch_youtube_trending()

    # 中国：微博 + 百度 + 知乎 + 抖音 + B站 + 小红书
    china_all = (fetch_weibo_hot() + fetch_baidu_hot() + fetch_zhihu_hot()
                + fetch_douyin_hot() + fetch_bilibili_hot() + fetch_xiaohongshu_hot())

    # 去重
    seen_west = set()
    west_deduped = []
    for t in west_all:
        key = t.get("title", "").lower().strip()[:60]
        if key not in seen_west and len(t.get("title", "")) > 10:
            seen_west.add(key)
            west_deduped.append(t)

    seen_cn = set()
    china_deduped = []
    for t in china_all:
        key = t.get("title", "").strip()[:20]
        if key not in seen_cn and len(t.get("title", "")) > 5:
            seen_cn.add(key)
            china_deduped.append(t)

    print(f"\n📊 去重后：西方 {len(west_deduped)} 条, 中国 {len(china_deduped)} 条")

    # Step 1.5: 用 LLM 批量分类中文话题到赛道（一次调用，成本极低）
    print("\n── Step 1.5: LLM 批量分类中文话题 ──")
    cn_titles = [t.get("title", "") for t in china_deduped]
    cn_categories = classify_topics_batch(cn_titles, all_tracks)
    for t, cat in zip(china_deduped, cn_categories):
        t["auto_track"] = cat
    # 统计
    from collections import Counter
    track_dist = Counter(cn_categories)
    print(f"  📊 中文话题赛道分布: {dict(track_dist)}")

    # Step 2: 对每个赛道分双向评分
    matrix = {}

    for track_name, track_cfg in TRACKS.items():
        print(f"\n{'='*60}")
        print(f"📂 赛道: {track_name}")
        print(f"{'='*60}")

        west_kw = [k.lower() for k in track_cfg.get("west_keywords", [])]
        china_kw = track_cfg.get("china_keywords", [])
        west_subs = {s.lower() for s in track_cfg.get("west_subreddits", [])}

        # 筛选该赛道的西方话题
        track_west = []
        for t in west_deduped:
            title_lower = t.get("title", "").lower()
            sub = t.get("subreddit", "").lower()
            if sub in west_subs or any(kw in title_lower for kw in west_kw):
                track_west.append(t)

        # 筛选该赛道的中国话题（优先用 LLM 分类结果）
        track_china = [t for t in china_deduped if t.get("auto_track") == track_name]

        # 如果 LLM 分类不够，补充关键词匹配
        if len(track_china) < top_n * 2:
            used_titles = {t.get("title", "") for t in track_china}
            for t in china_deduped:
                if t.get("title", "") in used_titles:
                    continue
                title = t.get("title", "")
                if any(kw in title for kw in china_kw):
                    track_china.append(t)
                    used_titles.add(title)

        # 如果赛道筛选太少，只对西方补充
        if len(track_west) < top_n:
            remaining = [t for t in west_deduped if t not in track_west]
            remaining.sort(key=lambda x: x.get("score", 0), reverse=True)
            track_west.extend(remaining[:top_n * 2 - len(track_west)])

        # CN 如果仍不够，不再从通用池补充（避免赛道重叠）
        print(f"  赛道筛选: 西方 {len(track_west)} 条, 中国 {len(track_china)} 条")

        # EN→CN 评分
        print(f"\n  → EN→CN (评分 {min(len(track_west), top_n*2)} 条)...")
        e2c_scored = []
        for i, t in enumerate(track_west[:top_n * 2]):
            print(f"    📊 [{i+1}] {t['title'][:50]}...")
            s = score_topic(t["title"], t.get("platform", "reddit"), "en")
            t_copy = {**t, "llm_score": s}
            e2c_scored.append(t_copy)

        e2c_scored.sort(key=lambda x: x.get("llm_score", {}).get("total_score", 0), reverse=True)
        e2c_top = e2c_scored[:top_n]

        # CN→EN 评分 — 让 LLM 评分后按 category 过滤该赛道
        print(f"\n  ← CN→EN (评分 {min(len(track_china), top_n*2)} 条)...")
        c2e_scored = []
        for i, t in enumerate(track_china[:top_n * 2]):
            print(f"    📊 [{i+1}] {t['title'][:50]}...")
            s = score_topic(t["title"], t.get("platform", "weibo"), "zh")
            t_copy = {**t, "llm_score": s}
            c2e_scored.append(t_copy)

        # 优先选 LLM 分类与当前赛道匹配的，然后再补其他
        c2e_on_track = [t for t in c2e_scored if t.get("llm_score", {}).get("category", "") == track_name]
        c2e_off_track = [t for t in c2e_scored if t.get("llm_score", {}).get("category", "") != track_name]
        c2e_combined = c2e_on_track + c2e_off_track
        c2e_combined.sort(key=lambda x: (
            1 if x.get("llm_score", {}).get("category", "") == track_name else 0,
            x.get("llm_score", {}).get("total_score", 0),
        ), reverse=True)
        c2e_top = c2e_combined[:top_n]

        matrix[track_name] = {
            "e2c": e2c_top,
            "c2e": c2e_top,
        }

    # Step 3: 保存 JSON
    json_path = DATA_DIR / f"matrix_{today}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=2)

    # Step 4: 生成 Markdown 报告
    md_lines = [
        f"# 🔮 中英文信息差矩阵 ({today})\n",
        f"> 全赛道 × 双向 × Top {top_n}\n",
    ]

    track_names_cn = {
        "tech": "🖥️ 科技",
        "entertainment": "🎬 娱乐",
        "society": "🏛️ 社会/政治",
        "lifestyle": "🌱 生活方式",
        "finance": "💰 财经",
        "food_travel": "🍜 美食旅行",
    }

    for track_name, data in matrix.items():
        cn_name = track_names_cn.get(track_name, track_name)
        md_lines.append(f"\n## {cn_name}\n")

        # EN→CN
        md_lines.append("### EN → CN (英文热点搬到中文平台)\n")
        md_lines.append("| # | 总分 | 信息差 | 爆款 | 受众 | 话题 | 建议角度 |")
        md_lines.append("|---|---|---|---|---|---|---|")
        for i, t in enumerate(data["e2c"], 1):
            s = t.get("llm_score", {})
            md_lines.append(
                f"| {i} | **{s.get('total_score', '?')}** | {s.get('info_gap_score', '?')} | "
                f"{s.get('viral_structure_score', '?')} | {s.get('audience_match_score', '?')} | "
                f"{t['title'][:60]} | {s.get('suggested_angle', '')[:40]} |"
            )
        md_lines.append("")

        # CN→EN
        md_lines.append("### CN → EN (中文热点搬到英文平台)\n")
        md_lines.append("| # | 总分 | 信息差 | 爆款 | 受众 | 话题 | 建议角度 |")
        md_lines.append("|---|---|---|---|---|---|---|")
        for i, t in enumerate(data["c2e"], 1):
            s = t.get("llm_score", {})
            md_lines.append(
                f"| {i} | **{s.get('total_score', '?')}** | {s.get('info_gap_score', '?')} | "
                f"{s.get('viral_structure_score', '?')} | {s.get('audience_match_score', '?')} | "
                f"{t['title'][:60]} | {s.get('suggested_angle', '')[:40]} |"
            )
        md_lines.append("")

    md_path = DATA_DIR / f"matrix_{today}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"\n{'='*70}")
    print(f"✅ 矩阵生成完成！")
    print(f"   📄 Markdown: {md_path}")
    print(f"   📊 JSON: {json_path}")
    print(f"{'='*70}")

    return matrix


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return

    command = args[0].lower()
    track = "tech"  # 默认赛道

    # 解析 --track 参数
    for i, a in enumerate(args):
        if a == "--track" and i + 1 < len(args):
            track = args[i + 1]

    if command == "test":
        cmd_test()
    elif command == "fetch":
        cmd_fetch(track)
    elif command == "score":
        cmd_score(track)
    elif command == "translate":
        cmd_translate(track)
    elif command == "matrix":
        cmd_matrix()
    elif command == "video":
        if len(args) < 2:
            print("用法: python -m pipeline.run video <url>")
            return
        cmd_video(args[1])
    elif command == "full":
        cmd_translate(track)
    else:
        print(f"未知命令: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
