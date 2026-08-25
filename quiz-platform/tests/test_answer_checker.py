# -*- coding: utf-8 -*-
"""判卷层测试：判断题语义映射、计算题数值等价、填空/简答行为。"""
from app.grader.answer_checker import check_answer, normalize_answer
from app.grader.grader import grade_paper
from app.grader.llm_client import parse_llm_verdict
from app.models.paper import Paper, PaperQuestion, SectionConfig
from app.models.question import Question, QuestionType
from app.models.record import AnswerSubmit


def _q(qtype: QuestionType, **kw) -> Question:
    base = dict(
        subject="x", course="", question="题干", options=[], correct_answer="",
    )
    base.update(kw)
    return Question(qtype=qtype, **base)


def test_judge_letter_mapped_by_option_text():
    # 选项顺序 A.对 B.错
    q = _q(QuestionType.judge, options=["对", "错"], correct_answer="A")
    assert check_answer(q, "对")[0] is True
    assert check_answer(q, "错")[0] is False
    # 选项顺序反转 A.错 B.对
    q2 = _q(QuestionType.judge, options=["错", "对"], correct_answer="A")
    assert check_answer(q2, "错")[0] is True
    assert check_answer(q2, "对")[0] is False


def test_judge_letter_without_options_not_coerced():
    q = _q(QuestionType.judge, correct_answer="对")
    assert check_answer(q, "A")[0] is False
    assert check_answer(q, "对")[0] is True


def test_judge_y_n():
    assert normalize_answer("Y", QuestionType.judge) == "对"
    assert normalize_answer("N", QuestionType.judge) == "错"


def test_calc_fraction_equivalence():
    q = _q(QuestionType.calc, correct_answer="1/2")
    assert check_answer(q, "0.5")[0] is True
    q2 = _q(QuestionType.calc, correct_answer="3/2")
    assert check_answer(q2, "1.5")[0] is True


def test_calc_sqrt_and_pi():
    q = _q(QuestionType.calc, correct_answer="√2")
    assert check_answer(q, "1.414")[0] is True
    q2 = _q(QuestionType.calc, correct_answer="π/2")
    assert check_answer(q2, "1.5708")[0] is True


def test_calc_tolerance_not_too_loose():
    q = _q(QuestionType.calc, correct_answer="1000")
    assert check_answer(q, "1001")[0] is False


def test_calc_wrong_value():
    q = _q(QuestionType.calc, correct_answer="1/2")
    assert check_answer(q, "2")[0] is False


def test_blank_order_insensitive():
    q = _q(QuestionType.blank, correct_answer="上海，北京")
    assert check_answer(q, "北京、上海")[0] is True


def test_essay_with_answer_goes_pending():
    q = _q(QuestionType.essay, correct_answer="参考答案文本", question="简述原理", id=1)
    paper = Paper(
        id="P-test",
        title="t",
        subject="x",
        sections=[SectionConfig(qtype=QuestionType.essay, count=1, score=10)],
        questions=[PaperQuestion(question=q, score=10)],
        total_score=10,
    )
    rec = grade_paper(paper, [AnswerSubmit(question_id=q.id, user_answer="任意作答")])
    assert rec.answers[0].status == "pending"
    assert rec.pending_count == 1


def test_llm_verdict_negation():
    assert parse_llm_verdict("不正确") is False
    assert parse_llm_verdict("正确") is True
    assert parse_llm_verdict("不完全对") is False
    assert parse_llm_verdict("回答错误") is False
    assert parse_llm_verdict("对，但过程需注意") is True
