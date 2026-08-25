"""判卷调度：三档策略。"""
from __future__ import annotations

from app.config import load_config
from app.grader.answer_checker import check_answer
from app.grader.llm_client import grade_with_llm
from app.models.question import QuestionType
from app.models.paper import Paper
from app.models.record import AnswerSubmit, GradedItem, Record


def grade_paper(
    paper: Paper,
    answers: list[AnswerSubmit],
) -> Record:
    """判卷：档位1 直接比对 → 档位2 LLM → 档位3 待补充。

    返回 Record（未持久化，由 history 模块保存）。
    """
    cfg = load_config()
    ans_map = {a.question_id: a.user_answer for a in answers}
    items: list[GradedItem] = []
    score = 0.0
    correct = wrong = pending = 0

    for pq in paper.questions:
        q = pq.question
        user_answer = ans_map.get(q.id, "")
        item = GradedItem(
            question_id=q.id,
            question=q.question,
            user_answer=user_answer,
            correct_answer=q.correct_answer or "（暂无参考答案）",
            explanation=q.explanation or "",
            status="pending",
            score=0,
        )

        if q.has_answer():
            if q.qtype in (QuestionType.essay, QuestionType.thinking):
                # 简答/思考题：有参考答案也不做文本精确比对，归 pending 人工核对
                item.status = "pending"
                item.comment = "简答/思考题参考答案需人工核对"
            else:
                # 档位1：题库自带答案 → 直接比对
                ok, comment = check_answer(q, user_answer)
                item.status = "correct" if ok else "wrong"
                item.comment = comment
                item.score = pq.score if ok else 0
        elif q.qtype.value in ("essay", "thinking") and cfg["enable_llm_grading"]:
            # 档位2：大模型辅助判卷（可配置开关）
            try:
                ok, comment = grade_with_llm(q, user_answer, cfg["llm"])
                item.status = "correct" if ok else "wrong"
                item.comment = comment
                item.score = pq.score if ok else 0
            except Exception as exc:  # noqa: BLE001 - 降级到档位3
                item.status = "pending"
                item.comment = f"LLM 判卷不可用（{exc}），请自行核对"
        else:
            # 档位3：无答案 → 提示用户自查/补充答案
            item.status = "pending"
            item.comment = "暂无参考答案，请自行核对或补充答案"

        if item.status == "correct":
            correct += 1
            score += item.score
        elif item.status == "wrong":
            wrong += 1
        else:
            pending += 1
        items.append(item)

    return Record(
        paper_id=paper.id,
        title=paper.title,
        subject=paper.subject,
        answers=items,
        score=round(score, 2),
        total_score=round(paper.total_score, 2),
        correct_count=correct,
        wrong_count=wrong,
        pending_count=pending,
        status="graded" if pending == 0 else "pending",
    )
