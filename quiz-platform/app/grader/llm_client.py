"""档位2：大模型辅助判卷（可选，配置后启用）。"""
from __future__ import annotations

import json

from app.llm.zhipu_client import chat_completion
from app.models.question import Question


def parse_llm_verdict(content: str) -> bool | None:
    """解析 LLM 判卷结论：先匹配否定词，再匹配肯定词，
    避免 “不正确” 因包含 “正确” 被误判为正确。"""
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    verdict = lines[0] if lines else ""
    negative = ("不正确", "不完全对", "不完全", "错误", "错", "否", "×")
    positive = ("正确", "对", "√", "是")
    if any(k in verdict for k in negative):
        return False
    if any(k in verdict for k in positive):
        return True
    return None


def grade_with_llm(
    question: Question,
    user_answer: str,
    llm_cfg: dict,
) -> tuple[bool, str]:
    """调用 OpenAI 兼容接口判卷，返回 (是否正确, 点评)。

    失败时抛异常，由调用方降级到档位3。
    """
    base_url = (llm_cfg.get("base_url") or "").rstrip("/")
    api_key = llm_cfg.get("api_key") or ""
    model = llm_cfg.get("model") or ""
    timeout = int(llm_cfg.get("timeout") or 20)
    if not base_url or not api_key or not model:
        raise RuntimeError("LLM 配置不完整（base_url/api_key/model）")

    content = chat_completion(
        [
            {
                "role": "system",
                "content": (
                    "你是判卷老师。根据题目和标准答案判断学生答案是否正确。"
                    "第一行只输出「对」或「错」，第二行起给出简短点评。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"题目：{question.question}\n"
                    f"选项：{json.dumps(question.options, ensure_ascii=False)}\n"
                    f"学生答案：{user_answer}\n"
                ),
            },
        ],
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=0,
        timeout=timeout,
    )
    verdict = parse_llm_verdict(content)
    if verdict is None:
        raise RuntimeError(f"LLM 返回格式无法解析: {content[:100]}")
    return verdict, content
