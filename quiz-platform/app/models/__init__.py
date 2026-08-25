"""数据模型：Question / Paper / Record。"""
from app.models.question import Question, QuestionType, QTYPE_LABELS, normalize_qtype
from app.models.paper import Paper, PaperQuestion, SectionConfig
from app.models.record import AnswerSubmit, GradedItem, Record

__all__ = [
    "Question",
    "QuestionType",
    "QTYPE_LABELS",
    "normalize_qtype",
    "Paper",
    "PaperQuestion",
    "SectionConfig",
    "AnswerSubmit",
    "GradedItem",
    "Record",
]
