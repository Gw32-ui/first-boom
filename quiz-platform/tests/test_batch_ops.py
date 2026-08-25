# -*- coding: utf-8 -*-
"""批量删除与批量事务导入。"""
import app.storage.db_manager as dm
from app.models.question import Question, QuestionType
from app.storage import (
    add_questions_batch,
    count_questions,
    delete_questions,
    list_questions,
)
from app.storage.db_manager import init_db


def _mk(subject="测试", q="题干", qt=QuestionType.blank, ans="1"):
    return Question(subject=subject, qtype=qt, question=q, correct_answer=ans)


def test_delete_questions_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "batch.db")
    init_db()
    add_questions_batch([_mk(q="题干A"), _mk(q="题干B"), _mk(q="题干C")])
    assert count_questions() == 3

    _, items = list_questions(page=1, page_size=10)
    ids = [q.id for q in items]
    deleted = delete_questions(ids[:2])
    assert deleted == 2
    assert count_questions() == 1


def test_add_questions_batch_dedup(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "batch2.db")
    init_db()
    r1 = add_questions_batch([_mk(q="同题")], source_file="a.pdf")
    assert r1["inserted"] == 1

    r2 = add_questions_batch([_mk(q="同题")], source_file="b.pdf")
    assert r2["merged"] == 1
    assert r2["inserted"] == 0
    assert count_questions() == 1

    _, items = list_questions(page=1, page_size=5)
    assert "b.pdf" in items[0].paper_meta.get("paper_files", [])


def test_add_questions_batch_by_type(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "batch3.db")
    init_db()
    r = add_questions_batch(
        [
            _mk(q="选择1", qt=QuestionType.single_choice),
            _mk(q="选择2", qt=QuestionType.single_choice),
            _mk(q="填空1"),
        ]
    )
    assert r["by_type"]["single_choice"] == 2
    assert r["by_type"]["blank"] == 1
    assert r["pending_review"] == 0
