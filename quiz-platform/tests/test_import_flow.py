# -*- coding: utf-8 -*-
"""导入链路回归：_run_import 的 topic 透传、图片文件名化、image_stats。"""
import io

import pytest
import app.storage.db_manager as dm
from app.storage import list_questions, question_repo
from app.storage.db_manager import init_db
from app.models.question import Question, QuestionType


def test_run_import_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "test_import.db")
    init_db()

    from app.web import _run_import  # 验证 web 模块可在无 faiss 环境导入

    text = (
        "知识点：傅里叶变换的性质\n"
        "【4-4】已知傅里叶变换对 f(t)↔ F(jω)，则 f(t−2)↔ ；"
    )
    res = _run_import(
        text,
        subject="测试",
        course="",
        images=[r"C:\work\img_a.png"],
        image_stats={"usable": 1, "black_skipped": 0},
    )
    assert res["inserted"] == 1
    assert res["image_stats"]["usable"] == 1

    _, items = list_questions(page=1, page_size=5)
    assert items[0].topic == "傅里叶变换的性质"
    # 只存文件名，不存绝对路径
    assert items[0].images == ["img_a.png"]


def test_qtypes_subject_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "test_qtypes.db")
    init_db()

    question_repo.add_question(subject="毛概", qtype=QuestionType.blank, question="q1")
    question_repo.add_question(subject="毛概", qtype=QuestionType.calc, question="q2")
    question_repo.add_question(subject="其他", qtype=QuestionType.blank, question="q3")

    scoped = {r["value"]: r["count"] for r in question_repo.list_qtypes("毛概")}
    assert scoped["blank"] == 1
    assert scoped["calc"] == 1

    global_counts = {r["value"]: r["count"] for r in question_repo.list_qtypes()}
    assert global_counts["blank"] == 2


def test_content_hash_normalizes_layout():
    a = Question(
        subject="x",
        question="  题干一、求值；",
        options=["A. 甲", "B. 乙"],
        correct_answer="A",
    )
    b = Question(
        subject="x",
        question="题干一、求值；",
        options=["A 甲", "B 乙"],
        correct_answer="A",
    )
    assert question_repo.content_hash(a) == question_repo.content_hash(b)


def test_dedup_merge_appends_source(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "dedup.db")
    init_db()

    q = Question(
        subject="测试",
        qtype=QuestionType.blank,
        question="题干一",
        correct_answer="1",
    )
    id1, s1 = question_repo.add_question_dedup(q, source_file="a.pdf")
    id2, s2 = question_repo.add_question_dedup(q, source_file="b.pdf")
    assert (s1, s2) == ("inserted", "merged")
    assert id1 == id2

    _, items = list_questions(page=1, page_size=5)
    assert len(items) == 1
    assert items[0].paper_meta.get("paper_files") == ["a.pdf", "b.pdf"]


def test_pending_marker_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "pending.db")
    init_db()

    from app.web import (
        PendingResolve,
        _run_import,
        api_admin_pending_resolve,
    )

    text = (
        "1. 计算 ∫x dx <Formula>Unparsed</Formula>\n"
        "A. 1\n"
        "B. 2\n"
        "答案：A\n"
    )
    res = _run_import(text, subject="测试", course="")
    assert res["inserted"] == 1
    assert res["pending_review"] == 1

    total, items = question_repo.list_pending_questions()
    assert total == 1
    assert items[0].pending_review is True

    qid = items[0].id
    out = api_admin_pending_resolve(
        qid,
        PendingResolve(
            question="计算 ∫x dx = 1/2 x^2 + C",
            answer="A",
            explanation="凑微分",
        ),
    )
    assert out["ok"] is True
    assert out["question"]["pending_review"] is False
    assert question_repo.list_pending_questions()[0] == 0

    q = question_repo.get_question(qid)
    assert q is not None
    assert q.question == "计算 ∫x dx = 1/2 x^2 + C"
    assert q.content_hash == question_repo.content_hash(q)


def test_exam_paper_does_not_spawn_notes_essays(tmp_path, monkeypatch):
    """试卷（含板块头/选项）不应再被 parse_notes_points 套上“简述”前缀。"""
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "exam_paper.db")
    init_db()

    from app.web import _run_import

    text = (
        "2024年秋季学期《电磁场》课程考试试卷（A卷）\n"
        "考试时间：120分钟 满分：100分\n"
        "注意事项：1．答案写在答题卡上；\n"
        "一、填空题（共5小题，每小题4分）\n"
        "1．电位移矢量在法线方向上的边界条件为＿。\n"
        "2．散度定理的数学表达式为＿。\n"
        "二、单项选择题\n"
        "3．下列说法正确的是（ ）\n"
        "A. 甲\nB. 乙\nC. 丙\nD. 丁\n"
        "答案：B\n"
    )
    res = _run_import(text, subject="电磁场", course="")
    assert res["inserted"] == 3
    assert res["by_type"].get("essay", 0) == 0
    assert res["by_type"].get("blank", 0) == 2
    assert res["by_type"].get("single_choice", 0) == 1


def test_numbered_notes_still_imported(tmp_path, monkeypatch):
    """无试卷特征的编号知识点笔记仍走 parse_notes_points。"""
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "notes.db")
    init_db()

    from app.web import _run_import

    text = (
        "知识点：电磁辐射防护\n"
        "1、名词解释：比吸收率\n"
        "单位质量组织吸收的电磁辐射功率。\n"
        "2、名词解释：电磁环境\n"
        "存在于给定场所的所有电磁现象的总和。\n"
    )
    res = _run_import(text, subject="电磁场", course="")
    assert res["inserted"] == 2


def _fake_upload(data: bytes, filename: str):
    from fastapi import UploadFile

    return UploadFile(file=io.BytesIO(data), filename=filename)


def test_pdf_fragmented_text_routes_to_ocr(tmp_path, monkeypatch):
    """公式型 PDF 碎片文本层 → 整页渲染 → OCR，OCR 文本入库且标记 ocr_used。"""
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "pdf_ocr.db")
    init_db()

    import app.web as web

    monkeypatch.setattr(web, "LOG_DIR", tmp_path / "logs")
    garbage = "2 2 ( ) ( ) ( ) x y z A a x z x e = + + + − + \\rho 2"
    clean = (
        "1．设矢量场 A=(xz+x^2)e_x，试确定 a、b、c，使得 ∇⋅A=0。\n"
        "答案：a=1"
    )
    monkeypatch.setattr(
        web,
        "extract_pdf_rich_meta",
        lambda data, out: (garbage, [], [], []),
    )
    monkeypatch.setattr(
        web,
        "extract_pdf_pages",
        lambda data, out, dpi=200, max_pages=10: ["C:/fake/page1.png"],
    )
    monkeypatch.setattr(web, "_ocr_images_fallback", lambda paths: clean)

    res = web.api_question_import_file(
        file=_fake_upload(b"%PDF-1.4 fake", "周周测5.pdf"),
        subject="电磁场",
        course="",
    )
    assert res["image_stats"]["ocr_used"] is True
    assert res["inserted"] == 1
    _, items = list_questions(page=1, page_size=5)
    assert "试确定" in items[0].question


def test_pdf_fragmented_rejected_when_ocr_fails(tmp_path, monkeypatch):
    """碎片文本层且 OCR 未改善 → 400，垃圾不入库。"""
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "pdf_reject.db")
    init_db()

    import app.web as web

    monkeypatch.setattr(web, "LOG_DIR", tmp_path / "logs")
    garbage = "2 2 ( ) ( ) ( ) x y z A = + + + − + \\rho 2"
    monkeypatch.setattr(
        web,
        "extract_pdf_rich_meta",
        lambda data, out: (garbage, [], [], []),
    )
    monkeypatch.setattr(
        web,
        "extract_pdf_pages",
        lambda data, out, dpi=200, max_pages=10: ["C:/fake/page1.png"],
    )
    monkeypatch.setattr(web, "_ocr_images_fallback", lambda paths: "")

    with pytest.raises(Exception) as ei:
        web.api_question_import_file(
            file=_fake_upload(b"%PDF-1.4 fake", "bad.pdf"),
            subject="x",
            course="",
        )
    from fastapi import HTTPException

    assert isinstance(ei.value, HTTPException)
    assert ei.value.status_code == 400
    # 日志已落盘
    assert list((tmp_path / "logs").glob("*.txt"))
    # 库中没有垃圾题
    assert question_repo.count_questions() == 0


def test_pdf_clean_text_skips_ocr(tmp_path, monkeypatch):
    """正常文本层不触发 OCR。"""
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "pdf_clean.db")
    init_db()

    import app.web as web

    calls = []
    clean = (
        "一、单项选择题\n"
        "1．下列关于电磁波的说法正确的是（ ）\n"
        "A. 横波\nB. 纵波\nC. 标量波\nD. 机械波\n"
        "答案：A\n"
    )
    monkeypatch.setattr(
        web,
        "extract_pdf_rich_meta",
        lambda data, out: (clean, [], [], []),
    )
    monkeypatch.setattr(
        web,
        "extract_pdf_pages",
        lambda data, out, dpi=200, max_pages=10: calls.append(1) or [],
    )

    res = web.api_question_import_file(
        file=_fake_upload(b"%PDF-1.4 fake", "clean.pdf"),
        subject="x",
        course="",
    )
    assert res["image_stats"]["ocr_used"] is False
    assert calls == []
    assert res["inserted"] == 1


def test_map_pdf_images_to_questions():
    """坐标映射：图片归属到它之前最近的题号；首题前的图归 None。"""
    from app.parser.file_loader import map_pdf_images_to_questions

    images = [
        {"fname": "a.png", "page": 0, "y": 5},
        {"fname": "b.png", "page": 0, "y": 30},
        {"fname": "c.png", "page": 0, "y": 70},
    ]
    markers = [
        {"key": "1", "page": 0, "y": 10},
        {"key": "2", "page": 0, "y": 40},
    ]
    m = map_pdf_images_to_questions(images, markers)
    assert m == {"a.png": None, "b.png": "1", "c.png": "2"}


def test_run_import_image_anchor_map(tmp_path, monkeypatch):
    """按题号回填图片锚点：图进题干、images 字段同步、不标复核。"""
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "anchor.db")
    init_db()

    from app.web import _run_import

    text = "1．已知 f(t) 的频谱，求…\n答案：1\n\n2．求极限…\n答案：2\n"
    res = _run_import(
        text,
        subject="测试",
        course="",
        image_anchor_map={"1": ["fig1.png"], "2": ["fig2.png"]},
    )
    assert res["inserted"] == 2
    assert res["image_stats"]["bound_certain"] == 2

    _, items = list_questions(page=1, page_size=10)
    q1 = next(q for q in items if "已知 f(t)" in q.question)
    q2 = next(q for q in items if "求极限" in q.question)
    assert "【图:fig1.png】" in q1.question
    assert "【图:fig2.png】" in q2.question
    assert q1.images == ["fig1.png"]
    assert q2.images == ["fig2.png"]
    assert q1.pending_review is False


def test_run_import_image_unbound_marks_pending(tmp_path, monkeypatch):
    """题号对不上时顺序兜底绑定，并标待人工复核（不丢图、不猜）。"""
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "unbound.db")
    init_db()

    from app.web import _run_import

    text = "1．题干一\n答案：A\n"
    res = _run_import(
        text,
        subject="测试",
        course="",
        image_anchor_map={"9": ["x.png"]},
    )
    assert res["inserted"] == 1
    assert res["image_stats"]["bound_uncertain"] == 1

    _, items = list_questions(page=1, page_size=5)
    assert items[0].pending_review is True
    assert "【图:x.png】" in items[0].question
    assert items[0].images == ["x.png"]


def test_content_hash_ignores_image_anchors():
    """图锚点不参与指纹：同题带图/不带图跨文件导入仍能去重。"""
    a = Question(subject="x", question="题干一【图:a.png】", correct_answer="A")
    b = Question(subject="x", question="题干一", correct_answer="A")
    assert question_repo.content_hash(a) == question_repo.content_hash(b)


def test_run_import_image_class_applied(tmp_path, monkeypatch):
    """视觉分类应用：公式图→$latex$ 嵌入题干，装饰图→移除，坏 LaTeX 保留原图。"""
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "imgclass.db")
    init_db()

    from app.web import _run_import

    text = "1．计算极限值并说明理由\n答案：A\n"
    res = _run_import(
        text,
        subject="测试",
        course="",
        image_anchor_map={"1": ["formula.png", "deco.png", "bad.png"]},
        image_class={
            "formula.png": {
                "kind": "formula",
                "latex": r"\int_0^1 x\,dx",
            },
            "deco.png": {"kind": "decorative"},
            "bad.png": {"kind": "formula", "latex": r"\frac{1}{"},
        },
    )
    assert res["inserted"] == 1
    _, items = list_questions(page=1, page_size=5)
    q = items[0]
    assert r"$\int_0^1 x\,dx$" in q.question
    assert "【图:formula.png】" not in q.question
    assert "【图:deco.png】" not in q.question
    assert "【图:bad.png】" in q.question  # 坏 LaTeX 不嵌入，保留原图
    assert q.images == ["bad.png"]


def test_pdf_ocr_path_keeps_images_by_qnum(tmp_path, monkeypatch):
    """OCR 兜底路径：坐标映射的图片按题号回填进 OCR 文本对应题目。"""
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "pdf_img.db")
    init_db()

    import app.web as web

    monkeypatch.setattr(web, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(web, "ROOT", tmp_path)
    # 生成一张真实图片，prepare_ocr_images 才会把它算作可用
    from PIL import Image

    images_dir = tmp_path / "output" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (200, 120), "white").save(images_dir / "diagram_a.png")

    garbage = "2 2 ( ) ( ) ( ) x y z A a x z x e = + + + − + \\rho 2"
    clean = (
        "1．设矢量场 A=(xz+x^2)e_x，试确定 a、b、c。\n"
        "答案：a=1\n"
        "2．求极限。\n"
        "答案：2"
    )
    monkeypatch.setattr(
        web,
        "extract_pdf_rich_meta",
        lambda data, out: (
            garbage,
            [str(images_dir / "diagram_a.png")],
            [
                {
                    "fname": "diagram_a.png",
                    "page": 0,
                    "y": 30,
                    "rect": (0, 30, 200, 150),
                }
            ],
            [
                {"key": "1", "page": 0, "y": 10},
                {"key": "2", "page": 0, "y": 60},
            ],
        ),
    )
    monkeypatch.setattr(
        web,
        "extract_pdf_pages",
        lambda data, out, dpi=200, max_pages=10: [],
    )
    monkeypatch.setattr(web, "_ocr_images_fallback", lambda paths: clean)
    # 分类调用走纯启发式（避免测试里真实调视觉 API）
    monkeypatch.setattr(
        "app.vision.image_classify.classify_images_in_dir",
        lambda *a, **k: {},
    )

    res = web.api_question_import_file(
        file=_fake_upload(b"%PDF-1.4 fake", "带图.pdf"),
        subject="电磁场",
        course="",
    )
    assert res["image_stats"]["ocr_used"] is True
    assert res["image_stats"]["image_map_size"] == 1
    _, items = list_questions(page=1, page_size=10)
    q1 = next(q for q in items if "设矢量场" in q.question)
    assert "【图:diagram_a.png】" in q1.question
    assert q1.images == ["diagram_a.png"]
    q2 = next(q for q in items if "求极限" in q.question)
    assert "【图:" not in q2.question


def test_question_images_update_api(tmp_path, monkeypatch):
    """PUT /api/question/{id}/images：替换图片列表 + 题干锚点，拒绝非法文件名。"""
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "img_upd.db")
    init_db()

    import app.web as web
    from app.web import QuestionImagesUpdate, api_question_images_update

    q = Question(subject="x", question="题干一", correct_answer="A")
    qid, _ = question_repo.add_question_dedup(q, source_file="a.docx")
    img_dir = tmp_path / "out" / "images"
    img_dir.mkdir(parents=True)
    (img_dir / "a.png").write_bytes(b"fake-png")
    monkeypatch.setattr(web, "IMAGES_DIR", img_dir)

    out = api_question_images_update(
        qid,
        QuestionImagesUpdate(
            images=["a.png"], question="题干一【图:a.png】"
        ),
    )
    assert out["ok"] is True
    got = question_repo.get_question(qid)
    assert got.images == ["a.png"]
    assert "【图:a.png】" in got.question

    with pytest.raises(Exception):
        api_question_images_update(
            qid, QuestionImagesUpdate(images=["../evil.png"])
        )


def test_image_stats(tmp_path, monkeypatch):
    """诊断统计：锚点/字段缺失文件能被发现。"""
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "imgstats.db")
    init_db()

    q = Question(
        subject="x",
        question="题干一【图:ghost.png】",
        correct_answer="A",
        images=["ghost.png"],
    )
    question_repo.add_question_dedup(q, source_file="a.pdf")
    q2 = Question(subject="x", question="题干二", correct_answer="B")
    question_repo.add_question_dedup(q2, source_file="b.pdf")

    stats = question_repo.image_stats(tmp_path / "no_images_dir")
    assert stats["total_questions"] == 2
    assert stats["questions_with_anchors"] == 1
    assert stats["questions_with_images_field"] == 1
    assert stats["missing_anchor_count"] == 1
    assert stats["missing_images_field_count"] == 1


def test_docx_media_conversion_fallback(tmp_path):
    """docx 媒体转换：可渲染格式直接落盘，无法渲染格式保留原文件并记录。"""
    from app.parser.file_loader import _convert_docx_media

    out = tmp_path / "imgs"
    out.mkdir()
    assert _convert_docx_media(b"\x89PNG\r\n", ".png", out, "a.png") == "a.png"
    assert (out / "a.png").read_bytes() == b"\x89PNG\r\n"
    assert _convert_docx_media(b"\x00\x01\x02", ".emf", out, "b.emf") is None
    assert (out / "b.emf").read_bytes() == b"\x00\x01\x02"


def test_pdf_anchored_import_end_to_end(tmp_path, monkeypatch):
    """真实 PDF 端到端：文本层可用 + 内嵌图片 → 锚点落在对应题、images 字段同步。"""
    import pymupdf
    from PIL import Image

    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "pdf_e2e.db")
    init_db()

    import app.web as web

    monkeypatch.setattr(web, "LOG_DIR", tmp_path / "logs")
    images_dir = tmp_path / "output" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    img_path = images_dir / "embed.png"
    Image.new("RGB", (120, 80), "white").save(img_path)
    monkeypatch.setattr(web, "ROOT", tmp_path)

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 80), "1．如图所示，求值。", fontname="china-s")
    page.insert_text((72, 100), "A. 1", fontname="china-s")
    page.insert_text((72, 115), "B. 2", fontname="china-s")
    page.insert_text((72, 130), "答案：A", fontname="china-s")
    page.insert_image(pymupdf.Rect(72, 150, 192, 230), filename=str(img_path))
    page.insert_text((72, 260), "2．计算极限。", fontname="china-s")
    page.insert_text((72, 280), "答案：1", fontname="china-s")
    pdf_bytes = doc.tobytes()
    doc.close()
    # 分类调用走纯启发式（避免测试里真实调视觉 API）
    monkeypatch.setattr(
        "app.vision.image_classify.classify_images_in_dir",
        lambda *a, **k: {},
    )

    res = web.api_question_import_file(
        file=_fake_upload(pdf_bytes, "e2e.pdf"),
        subject="x",
        course="",
    )
    assert res["image_stats"]["ocr_used"] is False
    assert res["image_stats"]["anchored_in_text"] is True
    _, items = list_questions(page=1, page_size=10)
    q1 = next(q for q in items if "如图所示" in q.question)
    assert "【图:" in q1.question
    assert len(q1.images) == 1
    q2 = next(q for q in items if "计算极限" in q.question)
    assert "【图:" not in q2.question
    assert q2.images == []
