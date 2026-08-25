# -*- coding: utf-8 -*-
"""公式片段转换、残缺启发式检测、指纹去重覆盖。"""
import app.storage.db_manager as dm
from app.models.question import Question, QuestionType
from app.parser.formula_fixer import latexize_math_segments
from app.parser.model_parser import mark_pending_review
from app.storage import get_question
from app.storage.db_manager import init_db
from app.storage.question_repo import add_question_dedup, content_hash


def test_latexize_basic_inequality():
    out = latexize_math_segments("已知 |z|>3 且 A & B")
    assert out == "已知 $|z|>3$ 且 A & B"


def test_latexize_unicode_symbol():
    out = latexize_math_segments("计算 ∫x dx 的值")
    assert "\\int x dx" in out
    assert out.startswith("计算 $")


def test_latexize_keeps_existing_formula():
    out = latexize_math_segments("已知 $F(z)=\\frac{z}{z-3}$，求 |z|>3")
    assert "$F(z)=\\frac{z}{z-3}$" in out
    assert "$|z|>3$" in out


def test_latexize_keeps_image_anchor():
    out = latexize_math_segments("【图:img.png】如图，v=√2")
    assert "【图:img.png】" in out
    assert "$v=\\sqrt 2$" in out


def test_mark_pending_heuristic_broken():
    q = Question(
        subject="1",
        qtype=QuestionType.blank,
        question="已知 ( ) ω j F t f ↔ ，求频谱",
        correct_answer="",
    )
    mark_pending_review(q)
    assert q.pending_review is True


def test_mark_pending_heuristic_gap():
    q = Question(
        subject="2",
        qtype=QuestionType.single_choice,
        question="动摩擦因数为 、夹角为 ，重力加速度为 g",
        correct_answer="",
    )
    mark_pending_review(q)
    assert q.pending_review is True


def test_mark_pending_clean_not_flagged():
    q = Question(
        subject="测试",
        qtype=QuestionType.single_choice,
        question="已知 $f(t)=sin(t)$，求 $f(2t)$ 的频谱",
        correct_answer="A",
        options=["A. $\\frac{1}{2}F(j\\omega)$", "B. $F(j\\omega)$"],
    )
    mark_pending_review(q)
    assert q.pending_review is False


def test_dedup_overwrites_stale_text(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "overwrite.db")
    init_db()

    q1 = Question(
        subject="测试",
        qtype=QuestionType.blank,
        question="题干一；",
        correct_answer="1",
    )
    q2 = Question(
        subject="测试",
        qtype=QuestionType.blank,
        question="题干一",
        correct_answer="1",
    )
    assert content_hash(q1) == content_hash(q2)  # 分号被骨架剔除，指纹相同

    id1, s1 = add_question_dedup(q1, source_file="old.pdf")
    id2, s2 = add_question_dedup(q2, source_file="new.pdf")
    assert (s1, s2) == ("inserted", "merged")
    assert id1 == id2

    q = get_question(id1)
    assert q is not None
    assert q.question == "题干一"  # 被最新导入内容覆盖
