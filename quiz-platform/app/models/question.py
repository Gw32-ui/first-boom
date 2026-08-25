"""题目数据模型。"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class QuestionType(str, Enum):
    """题型枚举（新值 + 兼容旧值映射）。"""

    single_choice = "single_choice"      # 单选题
    multiple_choice = "multiple_choice"  # 多选题
    blank = "blank"                      # 填空题
    judge = "judge"                      # 判断题
    essay = "essay"                      # 简答题
    calc = "calc"                        # 计算题
    thinking = "thinking"                # 思考题


QTYPE_LABELS: dict[QuestionType, str] = {
    QuestionType.single_choice: "单选题",
    QuestionType.multiple_choice: "多选题",
    QuestionType.blank: "填空题",
    QuestionType.judge: "判断题",
    QuestionType.essay: "简答题",
    QuestionType.calc: "计算题",
    QuestionType.thinking: "思考题",
}

# 旧版本库中使用的题型值 → 新枚举
LEGACY_QTYPE_MAP: dict[str, QuestionType] = {
    "single": QuestionType.single_choice,
    "multi": QuestionType.multiple_choice,
    "multiple": QuestionType.multiple_choice,
    "blank": QuestionType.blank,
    "judge": QuestionType.judge,
    "essay": QuestionType.essay,
    "calc": QuestionType.calc,
    "thinking": QuestionType.thinking,
}

ANSWER_PLACEHOLDER = "（待补充答案）"


def normalize_qtype(value: str | QuestionType | None) -> QuestionType:
    """把任意题型写法规范化为枚举值。"""
    if isinstance(value, QuestionType):
        return value
    if not value:
        return QuestionType.blank
    v = str(value).strip().lower()
    if v in LEGACY_QTYPE_MAP:
        return LEGACY_QTYPE_MAP[v]
    try:
        return QuestionType(v)
    except ValueError:
        return QuestionType.blank


class Question(BaseModel):
    """一道题。correct_answer 为空或「待补充答案」表示暂无标准答案。"""

    id: int | None = None
    subject: str = ""
    course: str = ""
    doc_id: int | None = None
    page_no: int = 0
    topic: str = ""
    qtype: QuestionType = QuestionType.blank
    question: str
    options: list[str] = Field(default_factory=list)
    correct_answer: str = ""
    explanation: str = ""
    steps: list[str] = Field(default_factory=list)
    source_file: str = ""
    formula: str = ""                                # 公式/LaTeX（S7 新增）
    images: list[str] = Field(default_factory=list)  # 图片路径列表（S7 新增）
    tables: list[dict] = Field(default_factory=list)  # 表格 JSON（S7 新增）
    paper_meta: dict = Field(default_factory=dict)    # 试卷元信息：年份/卷型/省份（S7 新增）
    content_hash: str = ""                            # MD5 内容指纹（去重）
    pending_review: bool = False                      # 残缺标记：需人工复核
    created_at: str | None = None

    def has_answer(self) -> bool:
        return bool(
            self.correct_answer
            and self.correct_answer.strip()
            and ANSWER_PLACEHOLDER not in self.correct_answer
        )
