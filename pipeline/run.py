"""
pipeline/run.py
===============
主入口：编排完整管线。
用法:
    python -m pipeline daily             # ⭐ 每日一键生成（拓取+评分+改写+配音）
    python -m pipeline fetch             # 仅拓取热点
    python -m pipeline score             # 拓取 + LLM 评分
    python -m pipeline translate         # 拓取 + 评分 + 翻译改写
    python -m pipeline matrix            # 全赛道双向矩阵
    python -m pipeline video <url>       # 处理单个视频
    python -m pipeline test              # 快速测试各模块
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


def cmd_daily():
    """
    每日一键生成：专注 lifestyle 赛道
    输出结构: output/{date}/daily_report.md + topic_N/{xiaohongshu.md, douyin_script.md, audio.mp3, subtitle.srt}
    """
    today = datetime.now().strftime("%Y%m%d")
    track = "lifestyle"
    day_dir = OUTPUT_DIR / today
    day_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 60)
    print(f"📅 每日内容生产 ({today}) — 赛道: 海外生活技巧")
    print("=" * 60)

    # Step 1: 抓取 lifestyle 赛道
    hotspots = cmd_fetch(track)

    # Step 2: 评分 Top 15 → 取 Top 5
    all_topics = hotspots.get("west", [])
    valid = [t for t in all_topics if len(t.get("title", "")) > 15]
    print(f"\n📊 LLM 评分 ({len(valid)} 条有效)...")
    scored = batch_score_topics(valid, max_count=15)
    good = [t for t in scored if t.get("llm_score", {}).get("total_score", 0) >= 5.0]
    top5 = good[:5]

    if not top5:
        print("⚠️ 今日无高质量选题（评分均低于5），跳过")
        return []

    # Step 3: 翻译改写
    results = []
    for i, topic in enumerate(top5, 1):
        title = topic["title"]
        print(f"\n✍️ [{i}/{len(top5)}] 改写: {title[:50]}...")
        rewrite = translate_and_rewrite(title, source_lang="en", target_lang="zh")
        script = generate_video_script(
            rewrite.get("rewritten_titles", [title])[0],
            language="zh",
        )
        results.append({
            "original": topic,
            "rewrite": rewrite,
            "script": script,
        })

    # Step 4: 生成内容文件 + 下载素材 + TTS + 字幕
    print(f"\n📦 生成内容 + 下载素材 + 配音 + 字幕...")
    try:
        from .tts_azure import tts_clone_voice
        use_clone = True
    except ImportError:
        print("  ⚠️ Azure Speech SDK 未安装，降级到 edge-tts")
        use_clone = False

    from .media_downloader import download_reddit_media, search_related_images

    for i, item in enumerate(results, 1):
        topic_dir = day_dir / f"topic_{i}"
        topic_dir.mkdir(parents=True, exist_ok=True)
        item["topic_dir"] = str(topic_dir)

        print(f"\n── Topic {i} ──")

        # -- 下载原帖素材 --
        media_dir = topic_dir / "media"
        media_dir.mkdir(exist_ok=True)
        print(f"  📥 下载素材...")
        media_files = download_reddit_media(item["original"], str(media_dir))

        # 如果原帖无素材(纯文本帖), 在网上搜索相似主题的图片
        if not media_files:
            title = item["original"].get("title", "")
            # 用原帖英文标题搜索相关图片
            print(f"  🔍 搜索相关图片...")
            media_files = search_related_images(title, str(media_dir), count=5)

        item["media_files"] = media_files

        # -- 小红书图文 --
        r = item.get("rewrite", {})
        xhs_md = []
        titles = r.get("rewritten_titles", [])
        xhs_md.append(f"# {titles[0] if titles else '未命名'}\n")
        xhs_md.append(f"**标题备选：**\n")
        for t in titles:
            xhs_md.append(f"- {t}")
        xhs_md.append(f"\n**标签：** {' '.join('#' + t for t in r.get('tags', []))}\n")
        xhs_md.append(f"\n---\n")
        xhs_md.append(r.get("image_text_content", ""))
        # 配图建议
        media_sug = r.get("media_suggestions", [])
        if media_sug:
            xhs_md.append(f"\n\n---\n**配图建议：**")
            for ms in media_sug:
                xhs_md.append(f"- {ms}")
        # 已下载的素材
        if media_files:
            xhs_md.append(f"\n\n**已下载素材（media/ 文件夹）：**")
            for mf in media_files:
                xhs_md.append(f"- {Path(mf).name}")
        with open(topic_dir / "xiaohongshu.md", "w", encoding="utf-8") as f:
            f.write("\n".join(xhs_md))

        # -- 抖音视频脚本 --
        s = item.get("script", {})
        dy_md = []
        dy_md.append(f"# 抖音视频脚本\n")
        dy_md.append(f"**开头钩子（前3秒）：** {s.get('hook', '')}\n")
        dy_md.append(f"\n**正文：**\n{s.get('body', '')}\n")
        dy_md.append(f"\n**结尾CTA：** {s.get('cta', '')}\n")
        # 画面提示
        visual_cues = s.get("visual_cues", [])
        if visual_cues:
            dy_md.append(f"\n**画面提示：**")
            for vc in visual_cues:
                dy_md.append(f"- {vc}")
        # 已下载的素材
        if media_files:
            dy_md.append(f"\n\n**可用素材（media/ 文件夹）：**")
            for mf in media_files:
                dy_md.append(f"- {Path(mf).name}")
        dy_md.append(f"\n\n---\n")
        dy_md.append(f"**完整脚本（直接念）：**\n")
        dy_md.append(s.get("full_script", ""))
        with open(topic_dir / "douyin_script.md", "w", encoding="utf-8") as f:
            f.write("\n".join(dy_md))

        # -- 配音 --
        script_text = s.get("full_script", "")
        if script_text:
            audio_path = str(topic_dir / "audio.mp3")
            if use_clone:
                ok = tts_clone_voice(script_text, audio_path, "zh")
                if not ok:
                    text_to_speech(script_text, audio_path, "zh")
            else:
                text_to_speech(script_text, audio_path, "zh")
            item["audio_path"] = audio_path

            # -- 字幕 SRT --
            srt_path = str(topic_dir / "subtitle.srt")
            _generate_srt_from_script(script_text, srt_path)
            item["subtitle_path"] = srt_path

    # Step 5: 保存 JSON 数据
    json_path = DATA_DIR / f"daily_{today}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Step 6: 生成总览报告
    report_path = day_dir / "daily_report.md"
    md = [f"# 📅 每日内容 ({today})\n"]
    md.append(f"> 赛道: 海外生活技巧 | 来源: Reddit | 共 {len(results)} 条\n")
    md.append(f"\n## 目录结构\n```")
    md.append(f"output/{today}/")
    md.append(f"├── daily_report.md          ← 你正在看的")
    for i in range(1, len(results) + 1):
        md.append(f"├── topic_{i}/")
        md.append(f"│   ├── xiaohongshu.md    ← 小红书图文（复制发布）")
        md.append(f"│   ├── douyin_script.md  ← 抖音脚本")
        md.append(f"│   ├── audio.mp3         ← 配音（你的声音）")
        md.append(f"│   └── subtitle.srt      ← 字幕")
    md.append(f"```\n")

    for i, item in enumerate(results, 1):
        o = item["original"]
        r = item.get("rewrite", {})
        s = item.get("script", {})
        sc = o.get("llm_score", {})
        titles = r.get("rewritten_titles", [""])

        md.append(f"\n---\n")
        md.append(f"## 选题 {i}: {titles[0]}\n")
        md.append(f"| 评分 | 信息差 | 爆款 | 受众 | 原帖 |")
        md.append(f"|---|---|---|---|---|")
        md.append(f"| **{sc.get('total_score', '?')}** | {sc.get('info_gap_score', '?')} | {sc.get('viral_structure_score', '?')} | {sc.get('audience_match_score', '?')} | [{o['title'][:50]}]({o.get('url', '')}) |\n")
        md.append(f"**建议角度:** {sc.get('suggested_angle', '')}\n")
        md.append(f"**标题备选:** {' / '.join(titles)}\n")
        md.append(f"**标签:** {' '.join('#' + t for t in r.get('tags', []))}\n")
        md.append(f"**视频钩子:** {s.get('hook', '')}\n")
        md.append(f"\n📂 **文件:** `output/{today}/topic_{i}/`\n")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"\n{'=' * 60}")
    print(f"✅ 每日内容生成完成！")
    print(f"   📁 输出目录: output/{today}/")
    print(f"   📄 总览报告: output/{today}/daily_report.md")
    print(f"   📂 内容文件: output/{today}/topic_1~{len(results)}/")
    print(f"   📊 数据备份: data/daily_{today}.json")
    print(f"{'=' * 60}")

    return results


def _generate_srt_from_script(text: str, output_path: str, chars_per_sec: float = 4.5):
    """从脚本文本生成 SRT 字幕文件（按标点分句，估算时间）"""
    import re as _re
    # 按标点分句
    sentences = _re.split(r'(?<=[。！？.!?\n])\s*', text)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 1]

    lines = []
    t = 0.0
    for i, sent in enumerate(sentences, 1):
        duration = max(len(sent) / chars_per_sec, 1.5)  # 最短 1.5 秒
        start = _format_srt_ts(t)
        end = _format_srt_ts(t + duration)
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(sent)
        lines.append("")
        t += duration + 0.15  # 句间间隔

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _format_srt_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


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
    elif command == "daily":
        cmd_daily()
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
            print("用法: python -m pipeline video <url>")
            return
        cmd_video(args[1])
    elif command == "full":
        cmd_daily()
    else:
        print(f"未知命令: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
