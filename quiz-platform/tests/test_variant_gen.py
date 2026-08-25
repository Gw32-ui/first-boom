# -*- coding: utf-8 -*-
"""变式出题：JSON 解析 + 生成流程（mock LLM）。"""
import pytest

from app.generator.variant_gen import _parse_variant_json
from app.models.question import Question, QuestionType


def test_parse_variant_json_plain():
    content = (
        '[{"question":"q1","options":["A. x","B. y"],'
        '"correct_answer":"A","explanation":"e"}]'
    )
    items = _parse_variant_json(content)
    assert len(items) == 1
    assert items[0]["question"] == "q1"
    assert items[0]["options"] == ["A. x", "B. y"]


def test_parse_variant_json_with_code_fence():
    content = '```json\n[{"question":"q2","options":[],"correct_answer":"B"}]\n```'
    items = _parse_variant_json(content)
    assert items[0]["question"] == "q2"


def test_parse_variant_json_invalid():
    with pytest.raises(RuntimeError):
        _parse_variant_json("抱歉，我无法生成。")


def test_generate_variants_mocked(monkeypatch):
    def fake_chat(messages, **kwargs):
        assert kwargs["temperature"] == 0.8
        return (
            '[{"question":"变式一","options":["A. 1","B. 2"],'
            '"correct_answer":"A"}]'
        )

    import app.generator.variant_gen as vg

    monkeypatch.setattr(vg, "chat_completion", fake_chat)
    q = Question(
        subject="测试",
        qtype=QuestionType.blank,
        question="原题",
        correct_answer="1",
    )
    items = vg.generate_variants(
        q, count=1, llm_cfg={"base_url": "x", "api_key": "k", "model": "m"}
    )
    assert items[0]["question"] == "变式一"
