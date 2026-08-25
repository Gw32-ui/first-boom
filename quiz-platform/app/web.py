"""Web 服务入口（FastAPI，仅绑定 127.0.0.1 本机）。"""
from __future__ import annotations

import re
import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import generator, history, storage
from app.storage.question_repo import add_question_dedup, content_hash
from app.grader import grade_paper
from app.models.question import (
    QTYPE_LABELS,
    Question,
    QuestionType,
    normalize_qtype,
)
from app.models.record import AnswerSubmit
from app.parser import (
    extract_bytes_text,
    parse_notes_points,
    parse_notes_sections,
    parse_text,
)
from app.parser.model_parser import KNOWN_LATEX_COMMANDS, mark_pending_review
from app.parser.file_loader import (
    extract_docx_rich,
    extract_images,
    extract_pdf_pages,
    extract_pdf_rich,
    extract_pdf_rich_meta,
    map_pdf_images_to_questions,
)
from app.parser.text_quality import assess_text_quality
from app.vision.image_utils import prepare_ocr_images
from app.config import load_config

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
LOG_DIR = ROOT / "output" / "logs"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _get_embedding_service():
    """懒加载向量服务：faiss DLL 异常不应拖垮整个服务启动。"""
    from app.vector.embedding_service import get_embedding_service

    return get_embedding_service()


def _ocr_images_fallback(image_paths: list[str]) -> str:
    """扫描版 PDF 兜底：调用 GLM-4.6V-Flash 逐张识别可用图片。"""
    import asyncio

    from mcp_text_clean import ocr_clean

    async def _run() -> list[str]:
        parts: list[str] = []
        for p in image_paths:
            try:
                parts.append(await ocr_clean(p))
            except Exception as exc:  # noqa: BLE001 - 单张失败不中断
                print(f"图片 OCR 失败（忽略）: {exc}")
        return parts

    return "\n\n".join(p for p in asyncio.run(_run()) if p.strip())


def _write_import_log(
    source_file: str,
    raw: str,
    quality: dict,
    ocr: str = "",
) -> Path:
    """把 PDF 文本层与 OCR 结果落盘为 UTF-8 文件，便于调试碎片文本/乱码。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = re.sub(r"[^\w.\-]", "_", source_file or "pdf")
    path = LOG_DIR / f"import_{stamp}_{name}.txt"
    parts = [
        f"来源: {source_file}",
        f"文本层质量: {json.dumps(quality, ensure_ascii=False)}",
        "===== 原始文本层 =====",
        raw,
    ]
    if ocr.strip():
        parts += ["===== OCR 结果 =====", ocr]
    path.write_text("\n".join(parts), encoding="utf-8")
    return path

app = FastAPI(title="出题交互系统", version="1.0.0")


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------


class ImportRequest(BaseModel):
    text: str
    subject: str = ""
    course: str = ""


class BatchDeleteRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)


class VariantRequest(BaseModel):
    count: int = Field(3, ge=1, le=10)


class VariantImportItem(BaseModel):
    question: str
    qtype: str = ""
    options: list[str] = Field(default_factory=list)
    correct_answer: str = ""
    explanation: str = ""
    subject: str = ""
    course: str = ""
    topic: str = ""


class VariantImportRequest(BaseModel):
    items: list[VariantImportItem] = Field(default_factory=list)
    source_file: str = ""


class AiOrganizeRequest(BaseModel):
    text: str
    subject: str = ""
    course: str = ""


class PracticeStart(BaseModel):
    subject: str = ""
    qtype: str = "single_choice"
    count: int = Field(5, ge=0, le=200)


class SectionIn(BaseModel):
    qtype: str = "single_choice"
    count: int = Field(1, ge=0, le=200)
    score: float = Field(5, ge=0)


class PaperGenerate(BaseModel):
    title: str = "自由组卷"
    subject: str = ""
    sections: list[SectionIn] = Field(default_factory=list)


class SubmitRequest(BaseModel):
    paper_id: str
    answers: list[AnswerSubmit] = Field(default_factory=list)


class AnswerFill(BaseModel):
    answer: str
    explanation: str = ""


class PendingResolve(BaseModel):
    """人工复核补全请求：字段为 None 表示不修改，传空字符串表示清空。"""

    question: str | None = None
    formula: str | None = None
    answer: str | None = None
    explanation: str | None = None


class QuestionImagesUpdate(BaseModel):
    """更新题目图片绑定：images 为完整替换列表；question 可选整体替换题干（含锚点）。"""

    images: list[str] = Field(default_factory=list)
    question: str | None = None


def _qdict(q: Question) -> dict:
    d = q.model_dump()
    d["qtype_label"] = QTYPE_LABELS.get(q.qtype, q.qtype.value)
    return d


def _run_import(
    text: str,
    subject: str,
    course: str,
    images: list[str] | None = None,
    formulas: list[str] | None = None,
    image_stats: dict | None = None,
    paper_meta: dict | None = None,
    source_file: str = "",
    image_anchor_map: dict[str, list[str]] | None = None,
    image_unbound: list[str] | None = None,
    image_class: dict[str, dict] | None = None,
) -> dict:
    from app.parser.formula_fixer import (
        fix_html_entities,
        fix_wps_encoding,
        latexize_math_segments,
    )
    # 导入前统一清洗：HTML 实体反转义 → WPS 私有区乱码 → 数学片段转 LaTeX
    text = latexize_math_segments(fix_wps_encoding(fix_html_entities(text)))
    subject = subject.strip() or "默认"
    course = course.strip()
    images = images or []
    formulas = formulas or []
    answer_lines = len(re.findall(r"(?m)^\s*答案\s*[:：]", text))
    has_sections = bool(re.search(r"(?m)^\s*(第[一二三四五六七八九十]+节|导论)", text))
    has_points = bool(re.search(r"(?m)^\s*\d{1,3}[、．]", text))
    # 试卷特征：板块头（一、单选题…）或选项行 → 只走 parse_text，
    # 杜绝“编号行被 parse_notes_points 变成 简述+… 简答题”的污染
    has_exam_headers = bool(
        re.search(
            r"(?m)^\s*[一二三四五六七八九十]+、\s*[（(]?\s*"
            r"(单选|多选|填空|判断|简答|计算|解答|思考)题?",
            text,
        )
    )
    has_options = bool(re.search(r"(?m)^\s*[A-Ha-h]\s*[.．、)]\s*\S", text))
    exam_like = has_exam_headers or has_options
    # 有章节结构、几乎没有答案行、且无试卷特征 → 纯笔记模式
    notes_like = has_sections and answer_lines < 20 and not exam_like

    # 解析时保留每题题号（qnums 与 questions 一一对应），供图片按题号回填
    qnums: list[int | None] = []
    if notes_like:
        questions = parse_notes_sections(text, subject=subject, course=course)
        qnums = [None] * len(questions)
        if has_points:
            extra = parse_notes_points(text, subject=subject, course=course)
            questions += extra
            qnums += [None] * len(extra)
    elif exam_like:
        questions, qnums = parse_text(
            text, subject=subject, course=course, return_qnums=True
        )
    else:
        # 无试卷特征但带编号条目与笔记特征词 → 编号知识点笔记（不再叠加 parse_text，
        # 避免同一行被解析成两道不同形状的题）
        if has_points and re.search(r"知识点|考点|名词解释|复习笔记|笔记", text):
            questions = parse_notes_points(text, subject=subject, course=course)
            qnums = [None] * len(questions)
            if has_sections:
                extra = parse_notes_sections(text, subject=subject, course=course)
                questions += extra
                qnums += [None] * len(extra)
        else:
            questions, qnums = parse_text(
                text, subject=subject, course=course, return_qnums=True
            )
            if has_sections:
                extra = parse_notes_sections(text, subject=subject, course=course)
                questions += extra
                qnums += [None] * len(extra)
    # 图片归属（OCR/兜底路径：按题号坐标回填锚点；锚点路径已在文本内）
    bound_certain = 0
    bound_uncertain = 0
    leftover = 0
    if image_anchor_map:
        keyed: list[tuple[str, Question]] = []
        for num, q in zip(qnums, questions):
            if num is not None:
                keyed.append((str(int(num)), q))
        used_keys: set[str] = set()
        for key, q in keyed:
            names = image_anchor_map.get(key) or []
            if names:
                used_keys.add(key)
                q.question = (
                    q.question + " " + " ".join(f"【图:{n}】" for n in names)
                ).strip()
                bound_certain += len(names)
        remaining = list(image_unbound or [])
        for key, names in image_anchor_map.items():
            if key not in used_keys:
                remaining.extend(names or [])
        if remaining:
            # 题号对不上/缺失 → 按顺序兜底绑定，并标待人工复核（不丢图、不猜）
            for q in questions:
                if not remaining:
                    break
                if re.search(r"【图:", q.question):
                    continue
                q.question = (
                    q.question + " " + f"【图:{remaining.pop(0)}】"
                ).strip()
                q.pending_review = True
                bound_uncertain += 1
            leftover = len(remaining)
    elif images:
        # 无锚点、无坐标映射时，按解析顺序索引绑定（兼容旧路径）
        for i, q in enumerate(questions):
            if i < len(images):
                q.images = [Path(images[i]).name]
    # 视觉分类应用：公式图 → $latex$ 嵌入题干；装饰图 → 移除
    if image_class:
        for q in questions:
            replaced: dict[str, str] = {}
            for m in re.finditer(r"【图:([^】]+)】", q.question):
                name = m.group(1)
                info = image_class.get(name) or {}
                kind = info.get("kind")
                latex = (info.get("latex") or "").strip()
                if kind == "formula" and latex and _latex_ok(latex):
                    replaced[m.group(0)] = f"${latex}$"
                elif kind == "decorative":
                    replaced[m.group(0)] = ""
            for old, new in replaced.items():
                q.question = q.question.replace(old, new)
    # images 字段与题干锚点保持一致（锚点是唯一事实源）
    for q in questions:
        anchors = set(re.findall(r"【图:([^】]+)】", q.question))
        q.images = sorted(set(q.images) | anchors)

    # 按题干去重
    seen: set[str] = set()
    unique: list[Question] = []
    for q in questions:
        if q.question in seen:
            continue
        seen.add(q.question)
        unique.append(q)
    questions = unique

    # 残缺检测：题干/公式/答案含 <Formula> 或 <ImgRef> 占位符
    # → 标记 pending_review（待人工复核），不要把残缺占位符当真实内容入库
    for q in questions:
        mark_pending_review(q)

    # MD5 内容指纹去重：入库前为每道题生成指纹（题干+选项+答案的文本骨架）
    # 同题跨文件导入时命中指纹 → 追加 paper_meta.paper_files，不重复建行
    inserted = 0
    merged = 0
    pending = 0
    by_type: dict[str, int] = {}
    for i, q in enumerate(questions):
        fm = formulas[i] if i < len(formulas) else ""
        _, status = add_question_dedup(
            q,
            source_file=source_file or q.source_file,
            hash_value=content_hash(q),
            images=q.images,
            formula=fm,
            paper_meta=paper_meta,
        )
        if status == "inserted":
            inserted += 1
            by_type[q.qtype.value] = by_type.get(q.qtype.value, 0) + 1
        else:
            merged += 1
        if q.pending_review:
            pending += 1
    stats_out = dict(image_stats) if image_stats else {}
    stats_out["bound_certain"] = bound_certain
    stats_out["bound_uncertain"] = bound_uncertain
    stats_out["unbound"] = leftover
    return {
        "inserted": inserted,
        "merged": merged,
        "pending_review": pending,
        "total": storage.count_questions(),
        "by_type": by_type,
        "preview": [_qdict(q) for q in questions[:10]],
        "image_stats": stats_out,
    }


def _latex_ok(latex: str) -> bool:
    """嵌入题干前的 LaTeX 轻量校验：花括号配对、无嵌套 $、非残缺命令。"""
    if not latex.strip():
        return False
    if latex.count("{") != latex.count("}"):
        return False
    if "$" in latex or "\\begin{" in latex:
        return False
    # 未知命令后紧跟普通字母（如 \fracx、\rhox）说明拼接残缺；
    # 已知命令（\int、\frac…）后跟数字/下划线/空格属正常写法
    for m in re.finditer(r"\\([a-zA-Z]+)", latex):
        cmd = m.group(1)
        nxt = latex[m.end():m.end() + 1]
        if cmd not in KNOWN_LATEX_COMMANDS and nxt.isalpha():
            return False
    return True


def _image_context_map(text: str) -> dict[str, str]:
    """从富文本里收集 {图片名: 所在行片段}，作为图片分类的上下文提示。"""
    ctx: dict[str, str] = {}
    for line in text.splitlines():
        for m in re.finditer(r"【图:([^】]+)】", line):
            ctx.setdefault(m.group(1), line[:80])
    return ctx


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 统计 / 筛选
# ---------------------------------------------------------------------------


@app.get("/api/stats")
def api_stats() -> dict:
    return storage.stats()


@app.get("/api/subjects")
def api_subjects() -> list[dict]:
    return storage.list_subjects()


@app.get("/api/qtypes")
def api_qtypes(subject: str | None = None) -> list[dict]:
    """题型分布；subject 为空时统计全库，否则只统计该学科。"""
    return storage.list_qtypes(subject)


@app.get("/api/questions")
def api_questions(
    subject: str | None = None,
    qtype: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    total, items = storage.list_questions(subject, qtype, search, page, page_size)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_qdict(q) for q in items],
    }


@app.get("/api/question/{qid}")
def api_question(qid: int) -> dict:
    q = storage.get_question(qid)
    if not q:
        raise HTTPException(404, "题目不存在")
    return _qdict(q)


# ---------------------------------------------------------------------------
# 题库管理
# ---------------------------------------------------------------------------


@app.post("/api/question/import")
def api_question_import(req: ImportRequest) -> dict:
    if not req.text.strip():
        raise HTTPException(400, "文本内容为空")
    return _run_import(req.text, req.subject, req.course)


@app.post("/api/question/import-file")
def api_question_import_file(
    file: UploadFile = File(...),
    subject: str = Form(""),
    course: str = Form(""),
) -> dict:
    suffix = Path(file.filename or "").suffix or ".txt"
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "文件过大，最大支持 50MB")
    suffix_l = suffix.lower()
    image_stats: dict | None = None
    image_class: dict[str, dict] = {}
    image_anchor_map: dict[str, list[str]] | None = None
    image_unbound: list[str] | None = None
    try:
        if suffix_l == ".docx":
            # docx：结构化富文本（图片/公式按位置内嵌），不再扁平化
            text, docx_unrendered = extract_docx_rich(
                data, ROOT / "output" / "images"
            )
            images: list[str] = []
            formulas: list[str] = []
            image_stats = {"docx_unrendered": docx_unrendered}
            # S17：图片理解两步择优（启发式→视觉），结果缓存到 image_meta.json；
            # 只分类本次文档引用的图片，避免重复扫描历史图片
            try:
                from app.vision.image_classify import classify_images_in_dir

                cfg = load_config()
                only = [m.group(1) for m in re.finditer(r"【图:([^】]+)】", text)]
                if only:
                    image_class = classify_images_in_dir(
                        ROOT / "output" / "images",
                        cfg,
                        context_map=_image_context_map(text),
                        cache_file=ROOT / "output" / "images" / "image_meta.json",
                        only=only,
                    )
            except Exception as exc:  # noqa: BLE001 - 分类失败不影响导入
                print(f"图片分类失败（忽略）: {exc}")
        else:
            if suffix_l == ".pdf":
                # 坐标级图题匹配：PyMuPDF 提取文本块 + 图片区域（位图/矢量图），
                # 按 y 坐标把【图:文件名】锚点插入正文 → 图自然归属到所在题目
                raw_text, pdf_images, pdf_image_events, pdf_qmarkers = (
                    extract_pdf_rich_meta(data, ROOT / "output" / "images")
                )
                text = raw_text
                # 黑图/深色图预处理：纯黑废图跳过，深色有内容图反相为白底
                prepared = prepare_ocr_images(
                    pdf_images, ROOT / "output" / "images"
                )
                # 正文含【图:】锚点时图片已随文定位，不再按序硬绑
                has_anchors = bool(re.search(r"【图:", text))
                parser_cfg = load_config().get("parser") or {}
                quality = assess_text_quality(
                    text,
                    threshold=float(
                        parser_cfg.get("pdf_text_quality_threshold") or 0.30
                    ),
                )
                ocr_used = False
                # 公式型 PDF：文本层碎片化（单字符/半截命令占比高）→ 整页渲染 + 视觉 OCR
                if (
                    quality["fragmented"] or not text.strip()
                ) and parser_cfg.get("pdf_ocr_enabled", True):
                    try:
                        page_images = extract_pdf_pages(
                            data,
                            ROOT / "output" / "images",
                            dpi=int(parser_cfg.get("pdf_ocr_dpi") or 200),
                            max_pages=int(
                                parser_cfg.get("pdf_ocr_max_pages") or 10
                            ),
                        )
                        usable = page_images or prepared["usable"]
                        if usable:
                            max_pages = int(
                                parser_cfg.get("pdf_ocr_max_pages") or 10
                            )
                            ocr_text = _ocr_images_fallback(usable[:max_pages])
                            ocr_quality = assess_text_quality(
                                ocr_text,
                                threshold=float(
                                    parser_cfg.get(
                                        "pdf_text_quality_threshold"
                                    )
                                    or 0.30
                                ),
                            )
                            if (
                                ocr_text.strip()
                                and ocr_quality["score"] < quality["score"]
                            ):
                                text = ocr_text
                                ocr_used = True
                                # OCR 替换文本后，用坐标映射按题号把图片回填（不丢图）
                                if pdf_image_events:
                                    raw_map = map_pdf_images_to_questions(
                                        pdf_image_events, pdf_qmarkers
                                    )
                                    usable_names = {
                                        Path(p).name for p in prepared["usable"]
                                    }
                                    keyed: dict[str, list[str]] = {}
                                    unkeyed: list[str] = []
                                    for fname, key in raw_map.items():
                                        bound = fname
                                        if fname not in usable_names:
                                            norm = prepared["normalized"].get(
                                                str(
                                                    ROOT
                                                    / "output"
                                                    / "images"
                                                    / fname
                                                )
                                            )
                                            if not norm:
                                                continue
                                            bound = Path(norm).name
                                        if key is None:
                                            unkeyed.append(bound)
                                        else:
                                            keyed.setdefault(key, []).append(
                                                bound
                                            )
                                    image_anchor_map = keyed or None
                                    image_unbound = unkeyed or None
                    except Exception as exc:  # noqa: BLE001 - OCR 失败走拒绝/回退
                        print(f"PDF OCR 失败（忽略）: {exc}")
                if quality["fragmented"] and not ocr_used:
                    # 文本层碎片化且 OCR 未改善 → 不把垃圾入库，落盘供人工复核
                    log_path = _write_import_log(
                        file.filename or "", raw_text, quality
                    )
                    raise HTTPException(
                        400,
                        "PDF 文本层碎片化且视觉 OCR 未成功，未入库。"
                        f"原始文本已写入日志：{log_path}",
                    )
                if ocr_used:
                    _write_import_log(
                        file.filename or "",
                        raw_text,
                        quality,
                        ocr=text,
                    )
                # 图锚定（已有【图:】）→ 不重复绑图；OCR 兜底 → 按序绑图
                images = (
                    []
                    if has_anchors
                    or ocr_used
                    or not text.strip()
                    or not prepared["usable"]
                    else prepared["usable"]
                )
                # 视觉分类：只分类本次提取的图片（公式图→LaTeX、装饰图→剔除）
                try:
                    from app.vision.image_classify import classify_images_in_dir

                    cfg = load_config()
                    only = [
                        m.group(1)
                        for m in re.finditer(r"【图:([^】]+)】", text)
                    ]
                    if image_anchor_map:
                        for names in image_anchor_map.values():
                            only.extend(names)
                        only.extend(image_unbound or [])
                    only = list(dict.fromkeys(only))
                    if only:
                        ctx_source = raw_text if ocr_used else text
                        image_class = classify_images_in_dir(
                            ROOT / "output" / "images",
                            cfg,
                            context_map=_image_context_map(ctx_source),
                            cache_file=ROOT
                            / "output"
                            / "images"
                            / "image_meta.json",
                            only=only,
                        )
                except Exception as exc:  # noqa: BLE001 - 分类失败不影响导入
                    print(f"PDF 图片分类失败（忽略）: {exc}")
                image_stats = {
                    "extracted": len(pdf_images),
                    "usable": len(prepared["usable"]),
                    "black_skipped": len(prepared["skipped_black"]),
                    "anchored_in_text": has_anchors,
                    "normalized": list(prepared["normalized"].values()),
                    "black_paths": prepared["skipped_black"],
                    "text_quality": quality,
                    "ocr_used": ocr_used,
                    "image_map_size": len(image_anchor_map or {}),
                    "unbound_images": len(image_unbound or []),
                }
            else:
                text = extract_bytes_text(data, suffix)
                raw_images = (
                    extract_images(data, suffix, ROOT / "output" / "images")
                    if suffix_l == ".pdf"
                    else []
                )
                prepared = prepare_ocr_images(
                    raw_images, ROOT / "output" / "images"
                )
                images = prepared["usable"]
                image_stats = {
                    "extracted": len(raw_images),
                    "usable": len(prepared["usable"]),
                    "black_skipped": len(prepared["skipped_black"]),
                    "normalized": list(prepared["normalized"].values()),
                    "black_paths": prepared["skipped_black"],
                }
            formulas = []
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not text.strip():
        raise HTTPException(400, "未能从文件中识别到文本")
    return _run_import(
        text,
        subject,
        course,
        images=images,
        formulas=formulas,
        image_stats=image_stats,
        source_file=file.filename or "",
        image_anchor_map=image_anchor_map,
        image_unbound=image_unbound,
        image_class=image_class,
    )


@app.delete("/api/question/{qid}")
def api_question_delete(qid: int) -> dict:
    ok = storage.delete_question(qid)
    if not ok:
        raise HTTPException(404, "题目不存在")
    return {"ok": True}


def _safe_image_name(name: str) -> str:
    """只允许纯文件名（丢弃目录部分），拒绝路径穿越。"""
    name = str(name or "").replace("\\", "/").split("/")[-1].strip()
    if not name or name in (".", "..") or ".." in name:
        raise HTTPException(400, "非法图片文件名")
    return name


@app.put("/api/question/{qid}/images")
def api_question_images_update(qid: int, req: QuestionImagesUpdate) -> dict:
    """整体替换某题的图片绑定（images 字段），可选同步替换题干文本（含锚点）。"""
    names = [_safe_image_name(n) for n in req.images]
    for n in names:
        if not (IMAGES_DIR / n).is_file():
            raise HTTPException(400, f"图片不存在: {n}")
    q = storage.update_question_images(qid, names, question=req.question)
    if q is None:
        raise HTTPException(404, "题目不存在")
    return {"ok": True, "question": _qdict(q)}


@app.post("/api/images/upload")
def api_images_upload(file: UploadFile = File(...)) -> dict:
    """手动上传图片到题库图片目录，返回文件名（供锚点/图片绑定使用）。"""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
        raise HTTPException(400, "仅支持 png/jpg/jpeg/gif/bmp/webp 图片")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "文件过大，最大支持 50MB")
    name = f"up_{uuid.uuid4().hex[:10]}{suffix}"
    (IMAGES_DIR / name).write_bytes(data)
    return {"ok": True, "name": name}


@app.get("/api/admin/image-stats")
def api_admin_image_stats() -> dict:
    """图片绑定诊断：有图题数、锚点数、锚点文件缺失、未绑定图片等。"""
    return storage.image_stats(IMAGES_DIR)


@app.post("/api/question/batch-delete")
def api_question_batch_delete(req: BatchDeleteRequest) -> dict:
    """批量删除题目（单事务）。"""
    ids = [i for i in dict.fromkeys(req.ids) if i > 0]
    if not ids:
        raise HTTPException(400, "未提供要删除的题目 id")
    deleted = storage.delete_questions(ids)
    return {"ok": True, "deleted": deleted, "total": storage.count_questions()}


@app.post("/api/question/{qid}/variants")
def api_question_variants(qid: int, req: VariantRequest) -> dict:
    """基于已有题生成变式题（调智谱 LLM，仅返回预览，不直接入库）。"""
    q = storage.get_question(qid)
    if q is None:
        raise HTTPException(404, "题目不存在")
    from app.generator.variant_gen import generate_variants

    cfg = load_config()
    try:
        items = generate_variants(q, count=req.count, llm_cfg=cfg["llm"])
    except RuntimeError as exc:
        raise HTTPException(502, f"变式生成失败: {exc}") from exc
    return {"items": items}


@app.post("/api/variants/import")
def api_variants_import(req: VariantImportRequest) -> dict:
    """把预览确认的变式题批量入库（指纹去重）。"""
    if not req.items:
        raise HTTPException(400, "没有要导入的题目")
    questions = [
        Question(
            subject=it.subject or "默认",
            course=it.course,
            topic=it.topic,
            qtype=normalize_qtype(it.qtype),
            question=it.question,
            options=it.options,
            correct_answer=it.correct_answer,
            explanation=it.explanation,
        )
        for it in req.items
    ]
    return storage.add_questions_batch(
        questions, source_file=req.source_file or "变式生成"
    )


@app.post("/api/question/ai-organize")
def api_question_ai_organize(req: AiOrganizeRequest) -> dict:
    """AI 整理杂乱文本为规范题目文本（供用户确认后重新解析入库）。"""
    if not req.text.strip():
        raise HTTPException(400, "文本内容为空")
    from app.generator.variant_gen import organize_text

    cfg = load_config()
    try:
        organized = organize_text(
            req.text,
            subject=req.subject,
            course=req.course,
            llm_cfg=cfg["llm"],
        )
    except RuntimeError as exc:
        raise HTTPException(502, f"AI 整理失败: {exc}") from exc
    return {"organized_text": organized}


@app.post("/api/question/{qid}/answer")
def api_question_fill_answer(qid: int, req: AnswerFill) -> dict:
    q = storage.update_answer(qid, req.answer, req.explanation or None)
    if not q:
        raise HTTPException(404, "题目不存在")
    return {"ok": True, "question": _qdict(q)}


# ---------------------------------------------------------------------------
# 人工复核 / 残缺标记
# ---------------------------------------------------------------------------


@app.get("/api/admin/pending-questions")
def api_admin_pending_questions(
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """拉取待人工复核的题目（公式/图片未解析成功，含 <Formula> 等占位符）。"""
    total, items = storage.list_pending_questions(page, page_size)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_qdict(q) for q in items],
    }


@app.post("/api/admin/pending/{qid}/clear")
def api_admin_pending_clear(qid: int) -> dict:
    """人工复核通过：取消题目的残缺标记。"""
    ok = storage.clear_pending_review(qid)
    if not ok:
        raise HTTPException(404, "题目不存在")
    return {"ok": True}


@app.post("/api/admin/pending/{qid}/resolve")
def api_admin_pending_resolve(qid: int, req: PendingResolve) -> dict:
    """人工复核补全：按需更新题干/公式/答案/解析，重算指纹并取消残缺标记。"""
    q = storage.resolve_pending_question(
        qid,
        question=req.question,
        formula=req.formula,
        answer=req.answer,
        explanation=req.explanation,
        clear=True,
    )
    if not q:
        raise HTTPException(404, "题目不存在")
    return {"ok": True, "question": _qdict(q)}


# ---------------------------------------------------------------------------
# 专项训练 / 自由组卷
# ---------------------------------------------------------------------------


@app.post("/api/practice/start")
def api_practice_start(req: PracticeStart) -> dict:
    if req.qtype not in {t.value for t in QuestionType}:
        raise HTTPException(400, "题型不合法")
    qt = normalize_qtype(req.qtype)
    paper = generator.practice(req.subject, qt, req.count)
    return {
        "paper_id": paper.id,
        "title": paper.title,
        "subject": paper.subject,
        "sections": [s.model_dump() for s in paper.sections],
        "total_score": paper.total_score,
        "question_count": paper.question_count,
        "questions": [
            {"question": _qdict(pq.question), "score": pq.score}
            for pq in paper.questions
        ],
    }


@app.post("/api/paper/generate")
def api_paper_generate(req: PaperGenerate) -> dict:
    if not req.sections:
        raise HTTPException(400, "请至少配置一个板块")
    valid_qtypes = {t.value for t in QuestionType}
    for s in req.sections:
        if s.qtype not in valid_qtypes:
            raise HTTPException(400, "题型不合法")
    sections = [
        {"qtype": normalize_qtype(s.qtype).value, "count": s.count, "score": s.score}
        for s in req.sections
    ]
    paper = generator.generate_paper(req.title, req.subject, sections)
    return {
        "paper_id": paper.id,
        "title": paper.title,
        "subject": paper.subject,
        "sections": [s.model_dump() for s in paper.sections],
        "total_score": paper.total_score,
        "question_count": paper.question_count,
        "questions": [
            {"question": _qdict(pq.question), "score": pq.score}
            for pq in paper.questions
        ],
    }


@app.get("/api/papers")
def api_papers() -> list[dict]:
    return generator.list_papers()


@app.get("/api/paper/{paper_id}")
def api_paper(paper_id: str) -> dict:
    paper = generator.load_paper(paper_id)
    if not paper:
        raise HTTPException(404, "试卷不存在")
    return {
        "paper_id": paper.id,
        "title": paper.title,
        "subject": paper.subject,
        "sections": [s.model_dump() for s in paper.sections],
        "total_score": paper.total_score,
        "question_count": paper.question_count,
        "created_at": paper.created_at,
        "questions": [
            {"question": _qdict(pq.question), "score": pq.score}
            for pq in paper.questions
        ],
    }


# ---------------------------------------------------------------------------
# 提交判卷 / 历史记录
# ---------------------------------------------------------------------------


@app.post("/api/submit")
def api_submit(req: SubmitRequest) -> dict:
    paper = generator.load_paper(req.paper_id)
    if not paper:
        raise HTTPException(404, "试卷不存在")
    record = grade_paper(paper, req.answers)
    record = history.save_record(record)
    return {
        "record_id": record.id,
        "score": record.score,
        "total_score": record.total_score,
        "correct_count": record.correct_count,
        "wrong_count": record.wrong_count,
        "pending_count": record.pending_count,
        "status": record.status,
        "details": [item.model_dump() for item in record.answers],
    }


@app.get("/api/records")
def api_records(
    subject: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    total, items = history.list_records(subject, status, page, page_size)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": r.id,
                "paper_id": r.paper_id,
                "title": r.title,
                "subject": r.subject,
                "score": r.score,
                "total_score": r.total_score,
                "correct_count": r.correct_count,
                "wrong_count": r.wrong_count,
                "pending_count": r.pending_count,
                "status": r.status,
                "created_at": r.created_at,
            }
            for r in items
        ],
    }


@app.get("/api/record/{rid}")
def api_record(rid: int) -> dict:
    record = history.get_record(rid)
    if not record:
        raise HTTPException(404, "记录不存在")
    return record.model_dump()


@app.get("/api/record/{rid}/export")
def api_record_export(rid: int, format: str = "json") -> PlainTextResponse:
    try:
        filename, content = history.export_record(rid, format)
    except FileNotFoundError:
        raise HTTPException(404, "记录不存在")
    media = "text/csv; charset=utf-8" if format == "csv" else "application/json"
    return PlainTextResponse(
        content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# 相似题目检索 API
# ---------------------------------------------------------------------------


@app.get("/api/similar")
def api_similar_search(
    query: str,
    subject: str = "",
    top_k: int = 5,
):
    """语义搜索相似题目"""
    try:
        service = _get_embedding_service()
        if service.index is None:
            # 尝试加载已有索引
            service._load_index()
        if service.index is None:
            return {"error": "向量索引未构建，请先调用 /api/build-index"}
        results = service.search(query, top_k=top_k)
        return {"query": query, "results": results}
    except Exception as exc:  # noqa: BLE001 - 检索不可用时给出可读错误
        return {"error": f"相似检索不可用: {exc}"}


@app.post("/api/build-index")
def api_build_index():
    """重建向量索引（首次导入或定期重建）"""
    try:
        service = _get_embedding_service()
        questions = storage.list_all_questions()
        if not questions:
            return {"ok": False, "message": "题库为空，无法构建索引"}
        service.build_index(questions)
        return {
            "ok": True,
            "count": len(questions),
            "message": f"已成功构建 {len(questions)} 道题的向量索引",
        }
    except Exception as exc:  # noqa: BLE001 - 构建失败返回可读错误
        return {"ok": False, "message": f"索引构建失败: {exc}"}


@app.get("/api/index-status")
def api_index_status():
    """查询索引状态"""
    try:
        service = _get_embedding_service()
        return {
            "built": service.index is not None,
            "total_questions": service.index.ntotal if service.index else 0,
            "model": service.model_name if service.model else "未初始化",
        }
    except Exception as exc:  # noqa: BLE001
        return {"built": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# 静态资源与启动
# ---------------------------------------------------------------------------


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
IMAGES_DIR = ROOT / "output" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")


def main() -> None:
    import sys
    import uvicorn

    # 重定向/GBK 控制台也能打印 emoji 与 Unicode 测试用例
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    storage.init_db()

    print("\n出题交互系统启动中...")
    print("网址: http://127.0.0.1:8000")
    print("API文档: http://127.0.0.1:8000/docs")
    print("提示: 仅本机可访问（符合安全约束，不暴露网络）")
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
