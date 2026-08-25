"""变式出题 / AI 文本整理：调用智谱 LLM 生成相似题或整理杂乱文本。"""
from __future__ import annotations

import json
import re

from app.llm.zhipu_client import chat_completion
from app.models.question import Question

_VARIANT_SYSTEM = (
    "你是出题老师。根据给定题目生成指定数量的同题型变式题："
    "保持考点与难度相当，只改变数值、选项顺序、具体表述或情境，"
    "不得改变知识点。只输出一个 JSON 数组，不要输出 Markdown 代码块或其他文字。"
    "每项格式："
    '{"question":"题干","options":["A. ...","B. ..."],'
    '"correct_answer":"...","explanation":"..."}'
)


def generate_variants(
    question: Question,
    count: int = 3,
    llm_cfg: dict | None = None,
) -> list[dict]:
    """生成变式题列表（LLM 输出 JSON 数组，解析失败抛 RuntimeError）。"""
    cfg = llm_cfg or {}
    # 题干里的图片标记用占位文本代替（文本模型无法看图）
    q_text = re.sub(r"【图:[^】]+】", "（原题含图片，变式保留图片占位）", question.question)
    user = (
        f"题型：{question.qtype.value}\n"
        f"题目：{q_text}\n"
        f"选项：{json.dumps(question.options, ensure_ascii=False)}\n"
        f"答案：{question.correct_answer}\n"
        f"解析：{question.explanation}\n"
        f"请生成 {count} 道变式题。"
    )
    content = chat_completion(
        [
            {"role": "system", "content": _VARIANT_SYSTEM},
            {"role": "user", "content": user},
        ],
        base_url=cfg.get("base_url", ""),
        api_key=cfg.get("api_key", ""),
        model=cfg.get("model", ""),
        temperature=0.8,
        timeout=int(cfg.get("timeout") or 60),
        retries=4,
    )
    return _parse_variant_json(content)


def _parse_variant_json(content: str) -> list[dict]:
    """从模型输出中提取 JSON 数组（容忍前后缀与代码块包裹）。"""
    text = content.strip()
    # 去掉可能的 markdown 代码块包裹（```json ... ```）
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("[")
    end = text.rfind("]") + 1
    if start < 0 or end <= start:
        raise RuntimeError(f"变式生成返回格式异常: {content[:120]}")
    try:
        raw = json.loads(text[start:end])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"变式生成 JSON 解析失败: {content[:120]}") from exc
    if not isinstance(raw, list):
        raise RuntimeError("变式生成结果不是数组")
    items: list[dict] = []
    for it in raw[:10]:
        if not isinstance(it, dict) or not str(it.get("question") or "").strip():
            continue
        items.append(
            {
                "question": str(it["question"]).strip(),
                "options": [
                    str(o).strip()
                    for o in (it.get("options") or [])
                    if str(o).strip()
                ],
                "correct_answer": str(it.get("correct_answer") or "").strip(),
                "explanation": str(it.get("explanation") or "").strip(),
            }
        )
    if not items:
        raise RuntimeError("变式生成结果为空")
    return items


_ORGANIZE_SYSTEM = (
    "你是试卷文本整理助手。把用户提供的杂乱文本整理成规范题目列表，"
    "保留原题号、题型关键词、选项和答案行，修正断行与噪声；"
    "公式用 $...$ 表示。只输出整理后的文本，不要解释、不要加评论。"
)


def organize_text(
    text: str,
    subject: str = "",
    course: str = "",
    llm_cfg: dict | None = None,
) -> str:
    """AI 整理：杂文 → 规范题目文本（供正则解析/预览后入库）。"""
    cfg = llm_cfg or {}
    user = (
        f"学科：{subject or '未知'}\n"
        f"来源：{course or '-'}\n"
        "原文如下：\n"
        "----\n"
        f"{text[:12000]}\n"
        "----"
    )
    return chat_completion(
        [
            {"role": "system", "content": _ORGANIZE_SYSTEM},
            {"role": "user", "content": user},
        ],
        base_url=cfg.get("base_url", ""),
        api_key=cfg.get("api_key", ""),
        model=cfg.get("model", ""),
        temperature=0.2,
        timeout=int(cfg.get("timeout") or 60),
    )
