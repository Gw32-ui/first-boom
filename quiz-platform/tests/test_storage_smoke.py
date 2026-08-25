# -*- coding: utf-8 -*-
"""存储层冒烟测试（只读，不污染题库）。"""
import app.storage.db_manager as dm
from app.storage import list_all_questions
from app.storage.db_manager import get_conn, init_db


def _ensure_migrated(tmp_path, monkeypatch):
    # 全部指向临时库，绝不触碰正式 data/questions.db
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "smoke.db")
    init_db()


def test_list_all_questions_available(tmp_path, monkeypatch):
    _ensure_migrated(tmp_path, monkeypatch)
    rows = list_all_questions()
    assert isinstance(rows, list)
    assert rows == []


def test_question_text_index_exists(tmp_path, monkeypatch):
    _ensure_migrated(tmp_path, monkeypatch)
    conn = get_conn()
    try:
        idx = conn.execute(
            "PRAGMA index_list('questions')"
        ).fetchall()
        names = {r["name"] for r in idx}
        assert "idx_questions_question" in names
    finally:
        conn.close()
