# -*- coding: utf-8 -*-
"""HTML 实体反转义：单测 + 导入链路清洗。"""
import app.storage.db_manager as dm
from app.parser.formula_fixer import fix_html_entities
from app.storage import list_questions
from app.storage.db_manager import init_db


def test_fix_html_entities_basic():
    assert fix_html_entities("|z|&gt;3 &lt; x") == "|z|>3 < x"


def test_fix_html_entities_amp():
    assert fix_html_entities("A &amp; B") == "A & B"


def test_fix_html_entities_double_escape():
    assert fix_html_entities("&amp;lt;") == "<"


def test_fix_html_entities_numeric():
    assert fix_html_entities("&#x5728; &#50;") == "在 2"


def test_fix_html_entities_keeps_latex():
    assert fix_html_entities(r"\int x &lt; 1") == r"\int x < 1"


def test_run_import_cleans_html_entities(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "html.db")
    init_db()

    from app.web import _run_import

    text = (
        "1. 已知 |z|&gt;3，且 A &amp; B 表示与运算。\n"
        "A. 1\nB. 2\n答案：A\n"
    )
    res = _run_import(text, subject="测试", course="")
    assert res["inserted"] == 1

    _, items = list_questions(page=1, page_size=5)
    assert "&gt;" not in items[0].question
    assert "|z|>3" in items[0].question
    assert "A & B" in items[0].question
