# -*- coding: utf-8 -*-
"""解析层（model_parser）测试：题型检测、分块、答案清洗。"""
import pytest

from app.parser.model_parser import (
    _clean_answer,
    _detect_qtype,
    mark_pending_review,
    parse_text,
)
from app.models.question import Question, QuestionType


def test_essay_without_options_or_answer_is_kept():
    qs = parse_text("简述什么是采样定理", subject="x", source_file="t")
    assert len(qs) == 1
    assert qs[0].qtype == QuestionType.essay


def test_blank_mark_ignores_latex_underscore():
    # $...$ 里的下划线（下标）不应触发填空线检测
    qs = parse_text(
        "求 $\\int_0^{1} x^2 \\, dx$ 的值",
        subject="x", source_file="t",
    )
    assert len(qs) == 1
    assert qs[0].qtype == QuestionType.calc


def test_real_blank_mark_still_detected():
    qs = parse_text("求极限 lim_{x→0} = ____", subject="x", source_file="t")
    assert len(qs) == 1
    assert qs[0].qtype == QuestionType.blank


def test_judge_stem_without_options():
    qs = parse_text("判断下列说法是否正确：信号 f(t)=t 是能量信号", subject="x", source_file="t")
    assert len(qs) == 1
    assert qs[0].qtype == QuestionType.judge


def test_judge_style_stem_with_options_is_single_choice():
    text = (
        "下列说法正确的是（ ）\n"
        "A. 甲\nB. 乙\nC. 丙\nD. 丁"
    )
    qs = parse_text(text, subject="x", source_file="t")
    assert len(qs) == 1
    assert qs[0].qtype == QuestionType.single_choice


def test_type_keywords_priority():
    assert _detect_qtype("多项选择题", [], "") is QuestionType.multiple_choice
    assert _detect_qtype("不定项选择题", [], "") is QuestionType.multiple_choice
    assert _detect_qtype("选择题", [], "") is QuestionType.single_choice
    assert _detect_qtype("单选题", [], "") is QuestionType.single_choice
    assert _detect_qtype("判断题", [], "") is QuestionType.judge


def test_type_marker_priority():
    assert _detect_qtype("", [], "【多项选择题】下列哪些正确") is QuestionType.multiple_choice


def test_calc_mid_stem_verbs():
    assert _detect_qtype("", [], "设 f(t)=t^2，画出波形") is QuestionType.calc
    assert _detect_qtype("", [], "化简下列表达式") is QuestionType.calc
    # 仅含“要求”等普通词不应误判计算
    assert _detect_qtype("", [], "请按要求完成填空") is not QuestionType.calc


def test_essay_keywords():
    assert _detect_qtype("", [], "谈谈你对采样定理的理解") is QuestionType.essay
    assert _detect_qtype("", [], "比较零输入响应与零状态响应") is QuestionType.essay


def test_multi_choice_numeric_answer_kept():
    assert _clean_answer("1,2,3", QuestionType.multiple_choice) == "123"


def test_judge_answer_no_letter_coercion():
    # A/B 不再强映射为 对/错（选项顺序可能相反）
    assert _clean_answer("A", QuestionType.judge) == "A"
    assert _clean_answer("对", QuestionType.judge) == "对"
    assert _clean_answer("√", QuestionType.judge) == "对"


def test_topic_captured_from_knowledge_point():
    text = (
        "知识点：采样定理\n"
        "【1-1】要保证采样后信号无失真，采样频率应满足____。"
    )
    qs = parse_text(text, subject="x", source_file="t")
    assert len(qs) == 1
    assert qs[0].topic == "采样定理"


def test_inline_numbered_qa_lines_split():
    # 问答题 docx 常见格式：1：/问N：/问： + 行内 答N：
    text = (
        "1：题干一？答1：答案一\n"
        "问2：计算某个值。答2：① 1；② 2。\n"
        "二、分析作图题\n"
        "问1：画波形。答1：见附图。\n"
        "三、（10分）\n"
        "问：求系统函数。答：$H(z)=1$。\n"
        "后续答案行\n"
    )
    qs = parse_text(text, subject="x", source_file="t")
    assert len(qs) == 4
    assert qs[0].question == "题干一？"
    assert qs[0].correct_answer == "答案一"
    assert qs[1].qtype == QuestionType.calc
    assert qs[1].correct_answer == "① 1；② 2。"
    assert qs[2].correct_answer == "见附图。"
    assert qs[3].question == "求系统函数。"
    assert "后续答案行" in qs[3].correct_answer


def test_paper_preamble_is_dropped():
    # 卷头（试卷/注意事项/考试时间）不应被识别成题目
    text = (
        "2024年秋季学期《电磁场》课程考试试卷（A卷）\n"
        "考试时间：120分钟 满分：100分\n"
        "注意事项：1．答案写在答题卡上；2．考试结束后试卷一并上交。\n"
        "一、单项选择题\n"
        "1．下列关于电磁波的说法正确的是（ ）\n"
        "A. 横波\nB. 纵波\nC. 标量波\nD. 机械波\n"
        "答案：A\n"
    )
    qs = parse_text(text, subject="x", source_file="t")
    assert len(qs) == 1
    assert qs[0].qtype == QuestionType.single_choice
    assert "试卷" not in qs[0].question


def test_unnumbered_first_choice_question_kept():
    # 第一题没有编号（无 QUESTION_START 标记）时不能当卷头丢掉
    text = (
        "下列说法正确的是（ ）\n"
        "A. 甲\nB. 乙\nC. 丙\nD. 丁\n"
        "答案：A\n"
    )
    qs = parse_text(text, subject="x", source_file="t")
    assert len(qs) == 1
    assert qs[0].qtype == QuestionType.single_choice


def test_blank_section_default_without_underscore():
    # 填空题板块下，即使碎片丢了填空线（无下划线），有题目特征仍判为 blank
    text = (
        "二、填空题\n"
        "1．设函数 f(x)=x^2，则 f(0) 的值\n"
    )
    qs = parse_text(text, subject="x", source_file="t")
    assert len(qs) == 1
    assert qs[0].qtype == QuestionType.blank


def test_broken_latex_command_marks_pending():
    # \rh o 这类半截命令是公式拆散产物，应标为待人工复核而不是直接入库
    q = Question(
        subject="x",
        question="电磁能流密度矢量 $s \\rh o$",
    )
    mark_pending_review(q)
    assert q.pending_review is True


def test_valid_latex_not_marked_pending():
    q = Question(
        subject="x",
        question="求 $\\sin x + \\cos x$ 的值",
    )
    mark_pending_review(q)
    assert q.pending_review is False
