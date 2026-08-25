"""判卷模块：三档策略。"""
from app.grader.answer_checker import check_answer, normalize_answer
from app.grader.grader import grade_paper

__all__ = ["check_answer", "normalize_answer", "grade_paper"]
