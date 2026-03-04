# 🔥 跨境热点内容创作工具包

## 项目说明
本项目用于抓取欧美与中国大陆之间的"信息差"热点话题，并自动生成适合小红书和抖音发布的图文/视频文案。

## 目录结构
```
├── content/
│   ├── west_to_china/          # 欧美热点→国内发布（信息差内容）
│   │   ├── 01_kim_hamilton.md  # 卡戴珊×汉密尔顿官宣恋情
│   │   ├── 02_super_bowl_halftime.md  # 超级碗中场秀
│   │   ├── 03_lindsey_vonn.md  # 林赛·沃恩冬奥摔伤
│   │   ├── 04_moltbook_ai.md   # AI社交网络Moltbook
│   │   ├── 05_project_hail_mary.md  # 《挽救计划》电影预告
│   │   └── 06_jd_vance_booed.md  # 万斯冬奥被嘘
│   └── china_to_west/          # 国内热点→海外发布
│       ├── 01_harbin_winter_swim.md
│       ├── 02_poker_skateboard.md
│       └── 03_wuxia_city.md
├── scripts/
│   └── content_generator.py    # 内容生成自动化脚本
├── templates/
│   ├── xiaohongshu_template.md # 小红书模板
│   └── douyin_template.md      # 抖音模板
└── assets/
    └── image_sources.md        # 素材来源汇总
```

## 使用方法
1. 查看 `content/` 目录下的成品内容，直接复制粘贴发布
2. 运行 `scripts/content_generator.py` 进行自动化内容生成
3. 根据 `templates/` 中的模板格式进行二次创作
4. 参考 `assets/image_sources.md` 获取配图素材

### 命令行示例
- `python scripts/content_generator.py`：抓取并生成（默认 `mixed` 赛道）
- `python scripts/content_generator.py --fetch`：仅抓取
- `python scripts/content_generator.py --gen`：仅从缓存生成
- `python scripts/content_generator.py --fetch --track entertainment`：娱乐赛道抓取
- `python scripts/content_generator.py --gen --track sports`：体育赛道生成
- `python scripts/content_generator.py --fetch --track entertainment --strict-track`：严格娱乐赛道抓取（无回退）
- `python scripts/content_generator.py --gen --track news --strict-track`：严格新闻赛道生成（无回退）

### 赛道参数
- `--track mixed`：综合（默认）
- `--track entertainment`：娱乐明星/影视音乐
- `--track sports`：体育/赛事/电竞
- `--track news`：社会新闻/国际政治
- `--track tech`：科技/AI/互联网

### 严格模式
- `--strict-track`：开启后按赛道强过滤，不回退综合候选；适合垂类账号

## 本期热点汇总（2026年2月第2周）

### 🇺🇸→🇨🇳 欧美火→国内发（6个话题）
| # | 话题 | 爆款指数 | 平台建议 |
|---|------|---------|---------|
| 1 | 卡戴珊×汉密尔顿超级碗官宣恋情 | ⭐⭐⭐⭐⭐ | 小红书+抖音 |
| 2 | 超级碗Bad Bunny中场秀（Gaga/婚礼/跳楼） | ⭐⭐⭐⭐⭐ | 抖音（视频） |
| 3 | 林赛·沃恩撕裂ACL坚持冬奥比赛摔倒 | ⭐⭐⭐⭐ | 抖音（正能量） |
| 4 | Moltbook：全AI用户社交网络 | ⭐⭐⭐⭐ | 小红书（科技） |
| 5 | 《挽救计划》电影终极预告片 | ⭐⭐⭐⭐ | 小红书+抖音 |
| 6 | 万斯冬奥开幕式被全场嘘（96K赞） | ⭐⭐⭐⭐ | 抖音 |

### 🇨🇳→🇺🇸 国内火→海外发（3个话题）
| # | 话题 | 爆款指数 | 平台建议 |
|---|------|---------|---------|
| 1 | 哈尔滨冬泳极限挑战 | ⭐⭐⭐⭐⭐ | TikTok/Instagram |
| 2 | 1000张扑克牌做滑板（391万播放） | ⭐⭐⭐⭐⭐ | TikTok |
| 3 | 万岁山武侠城春节沉浸式体验 | ⭐⭐⭐⭐ | TikTok/YouTube |
