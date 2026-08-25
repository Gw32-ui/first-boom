"""组卷引擎：专项训练抽题 + 自由组卷 + 模板组卷。

生成的试卷以 JSON 保存到 output/papers/，并返回 Paper 对象。
"""
from __future__ import annotations

import json
import random
import string
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from app.models.paper import Paper, PaperQuestion, SectionConfig
from app.models.question import Question, QuestionType, normalize_qtype
from app.storage import get_question, list_question_ids

ROOT = Path(__file__).resolve().parent.parent.parent
PAPERS_DIR = ROOT / "output" / "papers"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _new_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"P{stamp}{suffix}"


def _pick(subject: str | None, qtype: QuestionType, count: int) -> list[Question]:
    ids = list_question_ids(subject, qtype, limit=count)
    questions: list[Question] = []
    for qid in ids:
        q = get_question(qid)
        if q:
            questions.append(q)
    return questions


def practice(subject: str, qtype: str | QuestionType, count: int = 5) -> Paper:
    """专项训练：选定学科 + 单题型随机抽题。"""
    qt = normalize_qtype(qtype)
    count = max(0, int(count))
    questions = _pick(subject, qt, count)
    per_score = 10.0
    paper = Paper(
        id=_new_id(),
        title=f"专项训练-{qt.value}",
        subject=subject or "",
        sections=[SectionConfig(qtype=qt, count=len(questions), score=per_score)],
        questions=[PaperQuestion(question=q, score=per_score) for q in questions],
        total_score=round(len(questions) * per_score, 2),
        created_at=_now(),
    )
    save_paper(paper)
    return paper


def generate_paper(
    title: str,
    subject: str,
    sections: list[SectionConfig | dict],
) -> Paper:
    """自由组卷：按 sections 配置抽题并保存。"""
    normalized: list[SectionConfig] = []
    for sec in sections:
        if isinstance(sec, SectionConfig):
            normalized.append(sec)
        else:
            d = dict(sec)
            d["count"] = max(0, int(d.get("count", 1)))
            d["score"] = max(0.0, float(d.get("score", 5)))
            normalized.append(SectionConfig(**d))
    # 非负保护：负数一律按 0 处理，数量为 0 的板块跳过
    normalized = [
        SectionConfig(
            qtype=normalize_qtype(sec.qtype),
            count=max(0, int(sec.count)),
            score=max(0.0, float(sec.score)),
        )
        for sec in normalized
        if max(0, int(sec.count)) > 0
    ]

    questions: list[PaperQuestion] = []
    total_score = 0.0
    used_sections: list[SectionConfig] = []
    for sec in normalized:
        picked = _pick(subject, normalize_qtype(sec.qtype), max(0, sec.count))
        for q in picked:
            questions.append(PaperQuestion(question=q, score=sec.score))
            total_score += sec.score
        used_sections.append(
            SectionConfig(
                qtype=normalize_qtype(sec.qtype),
                count=len(picked),
                score=sec.score,
            )
        )

    paper = Paper(
        id=_new_id(),
        title=title or "自由组卷",
        subject=subject or "",
        sections=used_sections,
        questions=questions,
        total_score=round(total_score, 2),
        created_at=_now(),
    )
    save_paper(paper)
    return paper


def save_paper(paper: Paper) -> Paper:
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    path = PAPERS_DIR / f"{paper.id}.json"
    path.write_text(
        paper.model_dump_json(indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return paper


def load_paper(paper_id: str) -> Paper | None:
    path = PAPERS_DIR / f"{paper_id}.json"
    if not path.exists():
        return None
    try:
        return Paper.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, OSError, json.JSONDecodeError):
        return None


def list_papers() -> list[dict]:
    """列出已保存试卷（基本信息）。"""
    if not PAPERS_DIR.exists():
        return []
    papers: list[dict] = []
    for f in sorted(PAPERS_DIR.glob("P*.json"), reverse=True):
        try:
            p = Paper.model_validate_json(f.read_text(encoding="utf-8"))
        except (ValidationError, OSError, json.JSONDecodeError):
            continue
        papers.append(
            {
                "id": p.id,
                "title": p.title,
                "subject": p.subject,
                "total_score": p.total_score,
                "question_count": p.question_count,
                "created_at": p.created_at,
            }
        )
    return papers
