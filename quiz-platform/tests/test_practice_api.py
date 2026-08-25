# -*- coding: utf-8 -*-
"""组卷/练习 API 回归：题型校验与正常组卷。"""
import pytest
from fastapi import HTTPException

import app.storage.db_manager as dm
from app.storage.db_manager import init_db
from app.web import PracticeStart, api_paper_generate, api_practice_start


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "test_practice.db")
    init_db()


def test_practice_start_valid_qtype(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = api_practice_start(
        PracticeStart(subject="", qtype="single_choice", count=0)
    )
    assert r["paper_id"].startswith("P")
    assert r["question_count"] == 0


def test_practice_start_invalid_qtype(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with pytest.raises(HTTPException) as exc:
        api_practice_start(PracticeStart(subject="", qtype="not_a_type", count=1))
    assert exc.value.status_code == 400


def test_paper_generate_invalid_qtype(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    from app.web import PaperGenerate, SectionIn

    req = PaperGenerate(
        sections=[SectionIn(qtype="bad", count=1, score=5)]
    )
    with pytest.raises(HTTPException) as exc:
        api_paper_generate(req)
    assert exc.value.status_code == 400
