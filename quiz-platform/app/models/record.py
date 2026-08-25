"""历史记录数据模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class AnswerSubmit(BaseModel):
    """提交的作答项。"""

    question_id: int
    user_answer: str = ""


class GradedItem(BaseModel):
    """判卷后的单题结果。status: correct / wrong / pending。"""

    question_id: int
    question: str = ""
    user_answer: str = ""
    correct_answer: str = ""
    status: str = "pending"  # correct / wrong / pending
    score: float = 0
    explanation: str = ""
    comment: str = ""


class Record(BaseModel):
    """一次答题记录。"""

    id: int | None = None
    paper_id: str = ""
    title: str = ""
    subject: str = ""
    answers: list[GradedItem] = Field(default_factory=list)
    score: float = 0
    total_score: float = 0
    correct_count: int = 0
    wrong_count: int = 0
    pending_count: int = 0
    status: str = "graded"  # graded / pending
    created_at: str = ""
