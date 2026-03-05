# 项目历程记录

> 自动生成于 2026-03-05，基于 git log 和 todo.md 实施日志

---

## 时间线总览

| 日期 | 阶段 | 关键事件 |
|---|---|---|
| 03-03 | 规划 | 创建 todo.md 行动计划，网络调研可行性 |
| 03-04 AM | 基建 | 创建 pipeline/ 模块，Azure 资源，LLM 部署 |
| 03-04 PM | 迭代 | 评分 v2，矩阵，数据源扩展，TTS 集成 |
| 03-04 EVE | 产出 | daily 命令，内容生成，图片搜索 |
| 03-05 | 发布 | X/Twitter 自动发布尝试（失败） |

---

## 详细记录

### ✅ 成功 & 保留的功能

| 功能 | 状态 | 说明 |
|---|---|---|
| **pipeline/ 模块化架构** | ✅ 生产中 | config / fetcher / llm / video_processor / run / tts_azure / media_downloader / publisher_x |
| **Azure OpenAI (GPT-4.1-mini/nano)** | ✅ 生产中 | (redacted), eastus, Azure AD 认证 |
| **Azure 预算 $200/月** | ✅ 生效 | (redacted)，50/80/100% 告警 |
| **Reddit 热点抓取** | ✅ 稳定 | ~1200 帖/次，覆盖 60+ subreddits |
| **微博热搜抓取** | ✅ 稳定 | weibo.com/ajax/side/hotSearch |
| **百度热搜抓取** | ✅ 稳定 | top.baidu.com HTML 解析 |
| **B站热门抓取** | ✅ 稳定 | 官方 API bilibili.com/x/web-interface/popular |
| **X/Twitter 趋势抓取** | ✅ 稳定 | getdaytrends.com HTML 解析 |
| **LLM 评分 v2（5维）** | ✅ 生产中 | 信息差/爆款结构/受众/可执行性/时效性，区分度好 |
| **LLM 翻译改写 v3** | ✅ 生产中 | 具体步骤+案例+数据，不再是"正确的废话" |
| **LLM 视频脚本 v2** | ✅ 生产中 | 教程式，有画面提示 visual_cues |
| **LLM 批量分类** | ✅ 生产中 | 一次 nano 调用分类全部中文话题到赛道 |
| **Azure Speech TTS（声音克隆）** | ✅ 生产中 | 你自己的声音，中文 + 英文 profile |
| **edge-tts 备用 TTS** | ✅ 备用 | Azure Speech 不可用时自动降级 |
| **FFmpeg 视频处理** | ✅ 可用 | 重编码去重/裁切水印/字幕嵌入/音频替换 |
| **yt-dlp 视频下载** | ✅ 可用 | Python API 模式，支持 1000+ 平台 |
| **Whisper 语音识别** | ✅ 可用 | 本地 GPU，支持中英文（可选安装） |
| **Google Images 图片搜索** | ✅ 生产中 | 为纯文本帖子搜索相关参考图 |
| **每日管线 `daily` 命令** | ✅ 生产中 | 一键：抓取→评分→改写→配音→字幕→图片→报告 |
| **输出目录结构** | ✅ 规范化 | output/{date}/topic_N/{xiaohongshu.md, douyin_script.md, audio.mp3, subtitle.srt, media/} |
| **6 赛道配置** | ✅ 完成 | tech/entertainment/society/lifestyle/finance/food_travel |
| **矩阵命令 `matrix`** | ✅ 可用 | 全赛道×双向×Top5 |
| **成本控制** | ✅ ~$3.44/月 | 远低于 $200 预算（使用率 1.7%） |

### ❌ 失败 & 废弃

| 尝试 | 状态 | 原因 |
|---|---|---|
| **X/Twitter 自动发布** | ❌ 失败 | Free tier 已取消（402 Payment Required），Basic tier $100/月不值得 |
| **tophub.today 数据抓取** | ❌ 被封 | Cloudflare 403 保护，即使加 cookie/好 headers 也无法绕过 |
| **vvhan.com 热榜 API** | ❌ 不可用 | DNS 解析失败 (Errno 11001) |
| **oioweb.cn 热榜 API** | ❌ 不可用 | 持续 502 Bad Gateway |
| **知乎直接 API** | ❌ 被封 | 401 Authorization Required |
| **TikTok Creative Center API** | ❌ 无数据 | 返回 200 但 data 为空，需要认证 |
| **YouTube HTML 解析** | ❌ 无法用 | JS 渲染 SPA，raw HTML 无视频标题 |
| **YouTube Data API v3** | ⏸️ 暂停 | 需要 GCP 付费方式，用户选择不做 |
| **Bing Images 搜索** | ❌ 失败 | JS 渲染，HTML 中无图片 URL |
| **DuckDuckGo 图片搜索** | ❌ 失败 | vqd token 获取不到 |
| **Pixabay 图片搜索** | ❌ 被封 | 403 Forbidden |
| **Unsplash Source 随机图** | ❌ 废弃 | 用户要求搜索相关图而非随机图 |
| **Azure OpenAI Key 认证** | ❌ 被禁 | 订阅策略 disableLocalAuth=true，改用 Azure AD |
| **评分 v1（单维度）** | ❌ 废弃 | 区分度差，所有话题 7-8 分 |
| **LLM 内容 v1（泛泛而谈）** | ❌ 废弃 | "正确的废话"，无具体步骤/案例 |
| **旧 fetcher（纯 Reddit）** | ❌ 被替换 | 扩展为 10+ 数据源 |
| **旧 output 平铺结构** | ❌ 废弃 | 改为 output/{date}/topic_N/ 层级结构 |

### ⚠️ 部分成功 / 不稳定

| 功能 | 状态 | 说明 |
|---|---|---|
| **知乎热榜（tophub 备用）** | ⚠️ 不稳定 | tophub 被封后无可用源 |
| **抖音热搜（tophub 备用）** | ⚠️ 不稳定 | 同上 |
| **小红书热搜** | ⚠️ 不稳定 | 同上 |
| **TikTok 趋势** | ⚠️ 不稳定 | Creative Center API 需认证 |
| **YouTube 趋势** | ⚠️ 暂停 | 等 GCP API key |
| **CN→EN 赛道分类** | ⚠️ 有改善 | LLM 批量分类后好转，但中文热搜仍以两会/政治为主 |
| **Google Images 搜索** | ⚠️ 可能不稳定 | 依赖 Google HTML 结构，可能被反爬 |

### 🔧 技术 Bug 修复记录

| Bug | 修复 | commit |
|---|---|---|
| Windows 终端 Unicode emoji 崩溃 | `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` | 31ab2a9 |
| f-string 全角括号 SyntaxError | 替换 `（）` 为 `()` + 添加 UTF-8 BOM | 1919561 |
| f-string 多余 `""""""` 导致编译失败 | 删除多余三引号 | 1919561 |
| `.env` 环境变量在子进程中丢失 | config.py 启动时自动加载 `.env` | 1919561 |
| tophub 被 Cloudflare 封 | 加 cookie session 处理（仍失败），标记为不可用 | 1e4076f |
| yt-dlp CLI 不在 PATH | 改用 Python API 模式 `import yt_dlp` | 31ab2a9 |
| PowerShell `"""` 转义问题 | 用脚本文件替代 inline Python | 多处 |

---

## Git Commit 历史

| # | Hash | 日期 | 说明 |
|---|---|---|---|
| 1 | 31ab2a9 | 03-04 15:29 | feat: 完整管线 — 抓取/评分v2/翻译/视频处理/矩阵 |
| 2 | 1e4076f | 03-04 15:53 | fix: YouTube API v3, HTTP headers, tophub cookie |
| 3 | 200b1b6 | 03-04 17:00 | feat: Azure Speech TTS 声音克隆, daily 命令 |
| 4 | 03b800b | 03-04 17:53 | feat: v3 内容质量 — 具体 prompts, 素材下载, 目录重组 |
| 5 | b8ab330 | 03-04 18:01 | chore: 清理旧输出, 更新 .gitignore |
| 6 | 1919561 | 03-04 19:49 | fix: .env 自动加载, f-string 编码修复 |
| 7 | 6bf0b18 | 03-04 22:32 | feat: Google Images 参考图搜索 |
| 8 | 5f96461 | 03-04 22:32 | feat: 测试脚本 |

---

## 当前稳定数据源

| 平台 | 方式 | 日均数据量 | 稳定性 |
|---|---|---|---|
| Reddit | 官方 JSON API | ~1200 帖 | ⭐⭐⭐ |
| 微博 | ajax API | ~50 条 | ⭐⭐⭐ |
| 百度 | HTML 解析 | ~50 条 | ⭐⭐⭐ |
| B站 | 官方 API | ~50 条 | ⭐⭐⭐ |
| X/Twitter | getdaytrends.com | ~14 条 | ⭐⭐ |

## 当前月成本

| 项目 | 月成本 |
|---|---|
| Azure OpenAI (GPT-4.1-mini/nano) | ~$1.56 |
| Azure Speech TTS | ~$1.88 |
| **合计** | **~$3.44** |
| 预算 | $200 |
| 使用率 | 1.7% |
