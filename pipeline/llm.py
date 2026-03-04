# -*- coding: utf-8 -*-
"""
pipeline/llm.py
===============
LLM 模块：通过 Azure OpenAI 完成翻译、改写、评分、脚本生成。
使用 GPT-4.1-nano（分类评分）和 GPT-4.1-mini（翻译改写）控制成本。
支持两种认证方式：API Key（如果启用）或 Azure AD（DefaultAzureCredential）。
"""

import json
import os

from openai import AzureOpenAI

from .config import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_ENDPOINT,
    LLM_MODEL_HEAVY,
    LLM_MODEL_LIGHT,
)


def _get_client() -> AzureOpenAI:
    """获取 Azure OpenAI 客户端（优先 API Key，否则用 Azure AD）"""
    if not AZURE_OPENAI_ENDPOINT:
        raise ValueError(
            "请设置环境变量 AZURE_OPENAI_ENDPOINT\n"
            '例如: set AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/'
        )

    # 如果有 API Key 且资源允许，用 Key 认证
    if AZURE_OPENAI_API_KEY:
        try:
            client = AzureOpenAI(
                azure_endpoint=AZURE_OPENAI_ENDPOINT,
                api_key=AZURE_OPENAI_API_KEY,
                api_version=AZURE_OPENAI_API_VERSION,
            )
            return client
        except Exception:
            pass

    # 否则使用 Azure AD 认证（DefaultAzureCredential）
    try:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
        return AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            azure_ad_token_provider=token_provider,
            api_version=AZURE_OPENAI_API_VERSION,
        )
    except ImportError:
        raise ValueError(
            "API Key 认证不可用，且 azure-identity 未安装。\n"
            "请运行: pip install azure-identity"
        )
    except Exception as e:
        raise ValueError(f"Azure AD 认证失败: {e}")


def _chat(messages: list[dict], model: str = LLM_MODEL_HEAVY, temperature: float = 0.7) -> str:
    """调用 Azure OpenAI Chat Completion"""
    client = _get_client()
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=2000,
    )
    return response.choices[0].message.content.strip()


# ── 信息差评分 ──────────────────────────────────────────────

def score_topic(title: str, platform: str, language: str) -> dict:
    """
    用 LLM 评分一个话题的跨语言信息差潜力（改进版 v2）。
    改进点：
    1. 评估目标市场已有覆盖程度（信息差是否真实存在）
    2. 爆款结构评分（数字冲击/冲突/反转/恐惧/贪婪）
    3. 使用 mini 模型提升判断力
    4. 评分区分度更大（严格打分）
    """
    direction = "C2E" if language == "zh" else "E2C"
    target_lang = "英文" if language == "zh" else "中文"
    source_lang = "中文" if language == "zh" else "英文"

    if direction == "E2C":
        target_platforms = "小红书、抖音、B站、微博"
        audience_desc = "中国年轻用户（18-35岁）"
    else:
        target_platforms = "TikTok、YouTube Shorts、Reddit、X"
        audience_desc = "欧美英语用户"

    prompt = f"""你是一个资深跨语言社交媒体内容专家，长期活跃在中英文双平台。
你需要严格评估以下话题从{source_lang}搬到{target_lang}平台（{target_platforms}）的真实爆款潜力。

话题：{title}
来源平台：{platform}
原语言：{source_lang}

请从以下5个维度各打1-10分，然后给出加权总分：

1. **信息差真实度**（权重30%）：这个话题在{target_lang}平台（{target_platforms}）是否真的还没有人做过？
   - 10分：完全空白，{target_lang}世界几乎没人讨论
   - 5分：有一些讨论但缺少好的内容形式
   - 1分：已经被做烂了，到处都是同类内容

2. **爆款结构**（权重25%）：标题/内容是否具备天然的传播结构？
   - 有数字冲击（如"180→82000"）？
   - 有冲突/反转/悬念？
   - 能在3秒内抓住注意力？
   - 有恐惧/贪婪/好奇心驱动？

3. **受众匹配**（权重20%）：{audience_desc}是否真的在乎这个话题？
   - 10分：直接相关，人人都会点
   - 1分：太小众或文化隔阂太大

4. **内容可执行性**（权重15%）：能否快速做成短视频/图文？
   - 有没有可用的画面、截图、数据？
   - 是否需要大量解释背景？

5. **时效性**（权重10%）：这个话题的热度窗口还有多久？
   - 10分：持续性话题，几周内都有热度
   - 1分：已过时或仅限一天

请返回 JSON（不要 markdown 代码块）：
{{
    "info_gap_score": 1-10,
    "viral_structure_score": 1-10,
    "audience_match_score": 1-10,
    "executability_score": 1-10,
    "timeliness_score": 1-10,
    "total_score": 加权总分（保留1位小数），
    "score": 取整后的总分（1-10整数），
    "reason": "2-3句话，说明为什么推荐或不推荐，重点指出信息差是否真实存在",
    "category": "tech/entertainment/society/lifestyle/other",
    "content_type": "趋势/故事/观点/工具/挑战",
    "emotion": "惊讶/共鸣/争议/实用/娱乐",
    "suggested_angle": "建议的切入角度（一句话）",
    "risk": "潜在风险（如文化误读、政策敏感、已被做烂等），没有则写'无'"
}}

注意：请严格打分！不要所有话题都给7-8分。真正好的给9-10，平庸的给4-6，不适合的给1-3。"""

    try:
        result = _chat(
            [{"role": "user", "content": prompt}],
            model=LLM_MODEL_HEAVY,  # 升级到 mini，判断力更强
            temperature=0.3,
        )
        # 清理可能的 markdown 格式
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[-1]
        if result.endswith("```"):
            result = result.rsplit("```", 1)[0]
        result = result.strip()

        parsed = json.loads(result)
        parsed["direction"] = direction
        return parsed
    except Exception as e:
        print(f"  ⚠️ 评分失败: {e}")
        return {"score": 0, "reason": str(e), "direction": direction, "category": "other"}


# ── 批量话题分类（用于 CN→EN 赛道分配） ─────────────────────

def classify_topics_batch(titles: list[str], track_names: list[str]) -> list[str]:
    """
    用 LLM 一次性对多个话题分类到赛道。
    输入: titles=["话题1", "话题2", ...], track_names=["tech", "entertainment", ...]
    输出: ["tech", "society", "lifestyle", ...] 与 titles 等长
    """
    if not titles:
        return []

    tracks_str = ", ".join(track_names)
    titles_numbered = "\n".join(f"{i+1}. {t[:60]}" for i, t in enumerate(titles[:50]))

    prompt = f"""请将以下中文话题分别分类到最匹配的赛道。

可用赛道: {tracks_str}

话题列表:
{titles_numbered}

直接返回 JSON 数组，每个元素是对应话题的赛道名（不要解释），如:
["{track_names[0]}", "{track_names[1]}", ...]"""

    try:
        result = _chat(
            [{"role": "user", "content": prompt}],
            model=LLM_MODEL_LIGHT,  # nano 最便宜
            temperature=0.1,
        )
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[-1]
        if result.endswith("```"):
            result = result.rsplit("```", 1)[0]
        result = result.strip()

        categories = json.loads(result)
        # 验证长度
        if len(categories) != len(titles):
            # 补齐或截断
            categories = (categories + ["other"] * len(titles))[:len(titles)]
        # 验证每个值在 track_names 中
        valid = set(track_names + ["other"])
        categories = [c if c in valid else "other" for c in categories]
        return categories
    except Exception as e:
        print(f"  ⚠️ 批量分类失败: {e}")
        return ["other"] * len(titles)


# ── 翻译改写 ────────────────────────────────────────────────

def translate_and_rewrite(
    title: str,
    context: str = "",
    source_lang: str = "en",
    target_lang: str = "zh",
) -> dict:
    """
    翻译 + 本土化改写 + 生成干货内容（v2: 具体步骤+案例+数据）
    """
    src = "英文" if source_lang == "en" else "中文"
    tgt = "中文" if target_lang == "zh" else "英文"
    platform = "小红书/抖音" if target_lang == "zh" else "TikTok/YouTube Shorts"

    prompt = f"""你是一个在{platform}上有50万粉丝的知识博主, 擅长把海外信息差内容做成爆款.

原始话题({src}): {title}
{'补充背景: ' + context if context else ''}

请改写为{tgt}版本.

关键要求(必须遵守):
1. 具体 > 笼统: 不要说'要注意XXX', 要说'第一步打开XX, 第二步搜索XX, 你会看到XX'
2. 举例 > 道理: 必须包含至少1个具体案例/场景/数字, 不能全是空话
3. 步骤化: 正文必须有清晰的1/2/3步骤或要点, 读者一眼能扫到重点
4. 标题不要震惊体: 不用'惊了''竟然', 用具体信息+好奇心缺口
5. 像朋友分享经验, 不像营销号讲道理

请返回 JSON(不要 markdown 代码块):
{{
    "translated_title": "直译标题",
    "rewritten_titles": [
        "标题1(分享型: 像朋友分享经验)",
        "标题2(数字型: 包含具体数字)",
        "标题3(教程型: 像教程标题)"
    ],
    "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"],
    "image_text_content": "小红书图文正文(400-600字), 要求: 必须包含具体操作步骤(用1/2/3编号), 必须举至少1个真实案例, 必须有可操作的结论, 像朋友聊天的语气, 结尾引导互动",
    "media_suggestions": ["建议配图1的描述", "建议配图2", "建议配图3"]
}}"""

    try:
        result = _chat(
            [{"role": "user", "content": prompt}],
            model=LLM_MODEL_HEAVY,
            temperature=0.8,
        )
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[-1]
        if result.endswith("```"):
            result = result.rsplit("```", 1)[0]
        result = result.strip()

        return json.loads(result)
    except Exception as e:
        print(f"  ⚠️ 翻译改写失败: {e}")
        return {
            "translated_title": title,
            "rewritten_titles": [title],
            "short_script": "",
            "tags": [],
            "error": str(e),
        }


# ── 视频脚本生成 ────────────────────────────────────────────

def generate_video_script(
    title: str,
    context: str = "",
    language: str = "zh",
    duration_seconds: int = 45,
) -> dict:
    """
    生成短视频脚本 v2: 教程式, 有步骤, 干货优先
    """
    lang = "中文" if language == "zh" else "English"
    platform = "抖音/小红书" if language == "zh" else "TikTok/YouTube Shorts"

    prompt = f"""你是一个{platform}上的知识博主, 视频风格是'像朋友教你一个技巧'.

话题: {title}
{'背景: ' + context if context else ''}

请生成一个{duration_seconds}秒的短视频脚本({lang}), 要求:
1. 前3秒必须制造好奇心缺口(不要用'你知道吗'这种老套开头, 用具体场景或问题)
2. 正文必须有步骤: 第一步XX, 第二步XX, 像在手把手教
3. 必须举一个具体例子: 用真实场景或数据说明效果
4. 不要讲道理, 要讲方法
5. 像对面坐着朋友在聊天, 不要播音腔

请返回 JSON(不要 markdown 代码块):
{{
    "hook": "开头钩子(具体场景开头)",
    "body": "正文(必须包含具体步骤和案例)",
    "cta": "结尾(引导评论互动)",
    "full_script": "完整可直接念的脚本(含钩子+正文+CTA, 控制在{duration_seconds}秒内)",
    "visual_cues": ["画面提示1", "画面提示2", "画面提示3"]
}}"""

    try:
        result = _chat(
            [{"role": "user", "content": prompt}],
            model=LLM_MODEL_HEAVY,
            temperature=0.9,
        )
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[-1]
        if result.endswith("```"):
            result = result.rsplit("```", 1)[0]
        result = result.strip()

        return json.loads(result)
    except Exception as e:
        print(f"  ⚠️ 脚本生成失败: {e}")
        return {"hook": "", "body": "", "cta": "", "full_script": "", "error": str(e)}


# ── 批量评分 ────────────────────────────────────────────────

def batch_score_topics(topics: list[dict], max_count: int = 20) -> list[dict]:
    """
    批量评分话题，返回按 total_score 排序的结果。
    每条 topic 需要有 title, platform, language 字段。
    """
    scored = []
    for i, topic in enumerate(topics[:max_count]):
        title = topic.get("title", "")
        platform = topic.get("platform", "unknown")
        language = topic.get("language", "en")

        print(f"  📊 评分 [{i+1}/{min(len(topics), max_count)}]: {title[:50]}...")
        score_result = score_topic(title, platform, language)
        topic["llm_score"] = score_result
        scored.append(topic)

    # 按加权总分排序（优先 total_score，fallback score）
    scored.sort(
        key=lambda x: x.get("llm_score", {}).get("total_score", x.get("llm_score", {}).get("score", 0)),
        reverse=True,
    )
    return scored
