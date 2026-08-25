"""试卷数据模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.question import Question, QuestionType


class SectionConfig(BaseModel):
    """自由组卷的板块配置：题型 + 数量 + 分值。"""

    qtype: QuestionType
    count: int = Field(1, ge=0, le=200)
    score: float = Field(5, ge=0)


class PaperQuestion(BaseModel):
    """试卷中的一道题（含该题分值）。"""

    question: Question
    score: float = 5


class Paper(BaseModel):
    """一份完整试卷。questions 为生成时的题目快照。"""

    id: str = ""
    title: str = ""
    subject: str = ""
    sections: list[SectionConfig] = Field(default_factory=list)
    questions: list[PaperQuestion] = Field(default_factory=list)
    total_score: float = 0
    created_at: str = ""

    @property
    def question_count(self) -> int:
        return len(self.questions)
