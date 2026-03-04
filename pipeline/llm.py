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
    翻译 + 本土化改写 + 生成多个标题方向。
    返回 {translated_title, rewritten_titles: [...], short_script, tags: [...]}
    """
    src = "英文" if source_lang == "en" else "中文"
    tgt = "中文" if target_lang == "zh" else "英文"
    platform = "小红书/抖音" if target_lang == "zh" else "TikTok/YouTube Shorts"

    prompt = f"""你是一个资深跨文化社交媒体内容创作者。

请将以下{src}热点内容改写为适合{platform}发布的{tgt}版本。

原标题：{title}
{"背景信息：" + context if context else ""}

要求：
1. 不是直译，而是本土化改写，让{tgt}读者觉得自然有趣
2. 融入{platform}平台的表达风格和流行用语
3. 保留核心信息差价值

请返回 JSON（不要 markdown 代码块）：
{{
    "translated_title": "直译标题",
    "rewritten_titles": ["改写标题1（钩子型）", "改写标题2（争议型）", "改写标题3（实用型）"],
    "short_script": "60秒短视频脚本（口语化，包含开头钩子、正文、结尾CTA，不超过200字）",
    "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"],
    "image_text_content": "图文帖正文（300-500字，适合{platform}图文格式）"
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
    生成短视频脚本。
    返回 {hook, body, cta, full_script, estimated_duration}
    """
    lang = "中文" if language == "zh" else "English"
    platform = "抖音/小红书" if language == "zh" else "TikTok/YouTube Shorts"

    prompt = f"""你是一个{platform}短视频脚本专家。

请为以下话题生成一个{duration_seconds}秒的短视频口播脚本（{lang}）。

话题：{title}
{"背景：" + context if context else ""}

脚本结构要求：
- 开头钩子（前3秒必须抓住注意力）
- 正文（核心信息，口语化）
- 结尾CTA（引导互动）

请返回 JSON（不要 markdown 代码块）：
{{
    "hook": "开头钩子（1-2句话）",
    "body": "正文内容",
    "cta": "结尾引导语",
    "full_script": "完整脚本（直接可以念的口播文本）",
    "estimated_duration": {duration_seconds}
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
