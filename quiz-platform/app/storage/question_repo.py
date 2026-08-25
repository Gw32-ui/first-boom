"""题库仓储：题目的增删查改 + 统计 + 旧版文档兼容函数。"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.models.question import (
    ANSWER_PLACEHOLDER,
    QTYPE_LABELS,
    Question,
    QuestionType,
    normalize_qtype,
)
from app.storage.db_manager import get_conn


def _row_to_question(row: Any) -> Question:
    d = dict(row)
    d["qtype"] = normalize_qtype(d.get("qtype"))
    d["options"] = json.loads(d.get("options") or "[]")
    d["steps"] = json.loads(d.get("steps") or "[]")
    d["formula"] = d.get("formula") or ""
    d["images"] = json.loads(d.get("images") or "[]")
    d["tables"] = json.loads(d.get("tables") or "[]")
    d["paper_meta"] = json.loads(d.get("paper_meta") or "{}")
    d["content_hash"] = d.get("content_hash") or ""
    d["pending_review"] = bool(d.get("pending_review"))
    d["correct_answer"] = d.pop("answer", "") or ""
    return Question(**d)


def content_hash(q: Question) -> str:
    """生成内容指纹：题干 + 选项 + 答案拼接，去掉空白/标点后取 MD5。

    用于跨文件同题去重：同一道题在不同 PDF 里排版有差异（空格/换行/标点），
    只取“文本骨架”生成指纹，避免重复入库。
    """
    # 图片锚点【图:xxx】只表示“该题带图”，不参与文本指纹，
    # 否则同题“带图版/不带图版”指纹不同，跨文件导入会重复入库
    stem = re.sub(r"【图:[^】]+】", "", q.question or "")
    parts = [stem]
    parts.extend(q.options or [])
    parts.append(q.correct_answer or "")
    raw = "".join(parts)
    # 去空白、常见标点与 LaTeX 反斜杠（排版差异归一化）
    skeleton = re.sub(r"[\s\\{}()【】\[\]（）\.,，。、;；:：]+", "", raw)
    return hashlib.md5(skeleton.encode("utf-8")).hexdigest()


def _append_paper_meta(
    conn: Any,
    qid: int,
    source_file: str,
    *,
    pending_review: bool = False,
) -> str:
    """把新来源文件追加到已有题目的 paper_meta.paper_files（JSON 数组）。

    新版内容带残缺标记时，同步把旧记录置为 pending_review，保证人工复核不漏题。
    """
    row = conn.execute(
        "SELECT paper_meta FROM questions WHERE id = ?", (qid,)
    ).fetchone()
    try:
        meta = json.loads(row["paper_meta"] or "{}")
    except json.JSONDecodeError:
        meta = {}
    files = meta.get("paper_files") or []
    changed = bool(source_file) and source_file not in files
    if changed:
        files.append(source_file)
    meta["paper_files"] = files
    if changed or pending_review:
        if pending_review:
            conn.execute(
                "UPDATE questions SET paper_meta = ?, pending_review = 1 "
                "WHERE id = ?",
                (json.dumps(meta, ensure_ascii=False), qid),
            )
        else:
            conn.execute(
                "UPDATE questions SET paper_meta = ? WHERE id = ?",
                (json.dumps(meta, ensure_ascii=False), qid),
            )
        conn.commit()
    return json.dumps(meta, ensure_ascii=False)


def find_question_by_hash(hash_value: str) -> int | None:
    """按内容指纹查题，返回题号（无则 None）。"""
    if not hash_value:
        return None
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM questions WHERE content_hash = ? LIMIT 1",
            (hash_value,),
        ).fetchone()
        return int(row["id"]) if row else None
    finally:
        conn.close()


def add_question(
    subject: str,
    course: str = "",
    doc_id: int | None = None,
    page_no: int = 0,
    topic: str = "",
    qtype: str | QuestionType = QuestionType.blank,
    question: str = "",
    answer: str = "",
    options: list[str] | None = None,
    explanation: str = "",
    steps: list[str] | None = None,
    source_file: str = "",
    formula: str = "",
    images: list[str] | None = None,
    tables: list[dict] | None = None,
    paper_meta: dict | None = None,
    hash_value: str = "",
    pending_review: bool = False,
) -> int:
    """新增一道题，返回 question_id。hash_value 为内容指纹（可空）。"""
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO questions
                (subject, course, doc_id, page_no, topic, qtype, question,
                 options, answer, explanation, steps, source_file,
                 formula, images, tables, paper_meta, content_hash, pending_review)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subject or "", course or "", doc_id, page_no, topic or "",
                normalize_qtype(qtype).value,
                question,
                json.dumps(options or [], ensure_ascii=False),
                answer or "",
                explanation or "",
                json.dumps(steps or [], ensure_ascii=False),
                source_file or "",
                formula or "",
                json.dumps(images or [], ensure_ascii=False),
                json.dumps(tables or [], ensure_ascii=False),
                json.dumps(paper_meta or {}, ensure_ascii=False),
                hash_value or "",
                1 if pending_review else 0,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def add_question_dedup(
    q: Question,
    source_file: str = "",
    hash_value: str = "",
    images: list[str] | None = None,
    formula: str = "",
    paper_meta: dict | None = None,
) -> tuple[int, str]:
    """指纹去重入库：同题返回已存在的 id 并追加来源，不同题插入。

    返回 (question_id, 'inserted' | 'merged')。
    """
    h = hash_value or content_hash(q)
    existing = find_question_by_hash(h)
    if existing is not None:
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT question, answer, options, explanation, images "
                "FROM questions WHERE id = ?",
                (existing,),
            ).fetchone()
            new_images = [
                str(p).split("\\")[-1].split("/")[-1]
                for p in (images if images is not None else q.images)
            ]
            try:
                old_images = json.loads(row["images"] or "[]")
            except json.JSONDecodeError:
                old_images = []
            # 图片升级：新内容带图而旧记录没有 → 合并进 images 字段
            image_union = list(dict.fromkeys([*old_images, *new_images]))
            if image_union != old_images:
                conn.execute(
                    "UPDATE questions SET images = ? WHERE id = ?",
                    (json.dumps(image_union, ensure_ascii=False), existing),
                )
            # 同指纹但文本不同（如旧行残留 HTML 实体/公式残缺）→ 用新内容覆盖
            old_anchors = set(re.findall(r"【图:([^】]+)】", row["question"] or ""))
            new_anchors = set(re.findall(r"【图:([^】]+)】", q.question or ""))
            text_changed = row["question"] != q.question
            # 旧题有图锚点而新内容没有 → 不覆盖，避免丢图
            if old_anchors and not new_anchors:
                text_changed = False
            if (
                row is not None
                and (text_changed or (row["answer"] or "") != (q.correct_answer or ""))
            ):
                conn.execute(
                    "UPDATE questions SET question = ?, answer = ?, options = ?, "
                    "explanation = ?, pending_review = ? WHERE id = ?",
                    (
                        q.question,
                        q.correct_answer or "",
                        json.dumps(q.options or [], ensure_ascii=False),
                        q.explanation or "",
                        1 if q.pending_review else 0,
                        existing,
                    ),
                )
            _append_paper_meta(
                conn,
                existing,
                source_file or "",
                pending_review=q.pending_review,
            )
        finally:
            conn.close()
        return existing, "merged"
    meta = dict(paper_meta or {})
    if source_file:
        files = meta.get("paper_files") or []
        if source_file not in files:
            meta["paper_files"] = [*files, source_file]
    qid = add_question(
        subject=q.subject,
        course=q.course,
        topic=q.topic,
        qtype=q.qtype,
        question=q.question,
        answer=q.correct_answer,
        options=q.options,
        explanation=q.explanation,
        source_file=source_file or q.source_file,
        images=(images if images is not None else q.images),
        formula=formula or q.formula,
        paper_meta=meta,
        hash_value=h,
        pending_review=q.pending_review,
    )
    return qid, "inserted"


def list_pending_questions(
    page: int = 1,
    page_size: int = 50,
) -> tuple[int, list[Question]]:
    """拉取待人工复核的题目（pending_review=1，如公式/图片未解析成功）。"""
    conn = get_conn()
    try:
        page = max(1, page)
        page_size = max(1, min(page_size, 200))
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM questions WHERE pending_review = 1"
        ).fetchone()["c"]
        rows = conn.execute(
            "SELECT * FROM questions WHERE pending_review = 1 "
            "ORDER BY id DESC LIMIT ? OFFSET ?",
            (page_size, (page - 1) * page_size),
        ).fetchall()
        return int(total), [_row_to_question(r) for r in rows]
    finally:
        conn.close()


def clear_pending_review(qid: int) -> bool:
    """把题目标记为已人工复核（取消残缺标记）。"""
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE questions SET pending_review = 0 WHERE id = ?", (qid,)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def resolve_pending_question(
    qid: int,
    question: str | None = None,
    formula: str | None = None,
    answer: str | None = None,
    explanation: str | None = None,
    clear: bool = True,
) -> Question | None:
    """人工复核补全：更新题干/公式/答案/解析（None=不修改），重算指纹并取消残缺标记。

    用于“确认对齐”操作：对照原始 PDF 手动补全后再入正式题库，
    修改后重新生成 MD5 指纹，保证题目仍参与后续去重。
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM questions WHERE id = ?", (qid,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        if question is not None:
            d["question"] = question
        if formula is not None:
            d["formula"] = formula
        if answer is not None:
            d["answer"] = answer
        if explanation is not None:
            d["explanation"] = explanation
        q = _row_to_question(d)
        pending = 0 if clear else (1 if q.pending_review else 0)
        conn.execute(
            "UPDATE questions SET question = ?, formula = ?, answer = ?, "
            "explanation = ?, content_hash = ?, pending_review = ? WHERE id = ?",
            (
                q.question,
                q.formula,
                q.correct_answer,
                q.explanation,
                content_hash(q),
                pending,
                qid,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_question(qid)


def get_question(qid: int) -> Question | None:
    """按 id 查一道题。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM questions WHERE id = ?", (qid,)
        ).fetchone()
        return _row_to_question(row) if row else None
    finally:
        conn.close()


def find_question_by_text(question_text: str) -> int | None:
    """按题干全文精确查找（用于幂等，避免重复导入）。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM questions WHERE question = ? LIMIT 1",
            (question_text,),
        ).fetchone()
        return int(row["id"]) if row else None
    finally:
        conn.close()


def delete_question(qid: int) -> bool:
    """删除一道题，返回是否删除成功。"""
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM questions WHERE id = ?", (qid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_questions(ids: list[int]) -> int:
    """批量删除题目（单事务），返回删除数量。"""
    ids = [i for i in dict.fromkeys(ids) if i > 0]
    if not ids:
        return 0
    conn = get_conn()
    try:
        placeholders = ",".join("?" * len(ids))
        cur = conn.execute(
            f"DELETE FROM questions WHERE id IN ({placeholders})", ids
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def add_questions_batch(
    questions: list[Question],
    source_file: str = "",
    paper_meta: dict | None = None,
) -> dict:
    """批量事务入库（指纹去重）：单连接单事务。

    返回 {inserted, merged, pending_review, total, by_type}，语义与单条
    add_question_dedup 保持一致。
    """
    inserted = 0
    merged = 0
    pending = 0
    by_type: dict[str, int] = {}
    conn = get_conn()
    try:
        for q in questions:
            h = content_hash(q)
            row = conn.execute(
                "SELECT id FROM questions WHERE content_hash = ? LIMIT 1",
                (h,),
            ).fetchone()
            if row is not None:
                existing = int(row["id"])
                prow = conn.execute(
                    "SELECT paper_meta FROM questions WHERE id = ?",
                    (existing,),
                ).fetchone()
                try:
                    meta = json.loads(prow["paper_meta"] or "{}")
                except json.JSONDecodeError:
                    meta = {}
                files = meta.get("paper_files") or []
                changed = bool(source_file) and source_file not in files
                if changed:
                    files.append(source_file)
                meta["paper_files"] = files
                if changed or q.pending_review:
                    conn.execute(
                        "UPDATE questions SET paper_meta = ?, pending_review = ? "
                        "WHERE id = ?",
                        (
                            json.dumps(meta, ensure_ascii=False),
                            1 if (changed or q.pending_review) else 0,
                            existing,
                        ),
                    )
                # 同指纹但文本不同 → 用最新导入内容覆盖旧行
                orow = conn.execute(
                    "SELECT question, answer FROM questions WHERE id = ?",
                    (existing,),
                ).fetchone()
                if orow is not None and (
                    orow["question"] != q.question
                    or (orow["answer"] or "") != (q.correct_answer or "")
                ):
                    conn.execute(
                        "UPDATE questions SET question = ?, answer = ?, "
                        "options = ?, explanation = ? WHERE id = ?",
                        (
                            q.question,
                            q.correct_answer or "",
                            json.dumps(q.options or [], ensure_ascii=False),
                            q.explanation or "",
                            existing,
                        ),
                    )
                merged += 1
            else:
                meta = dict(paper_meta or {})
                if source_file:
                    files = meta.get("paper_files") or []
                    if source_file not in files:
                        meta["paper_files"] = [*files, source_file]
                qt = normalize_qtype(q.qtype)
                conn.execute(
                    """
                    INSERT INTO questions
                        (subject, course, doc_id, page_no, topic, qtype, question,
                         options, answer, explanation, steps, source_file,
                         formula, images, tables, paper_meta, content_hash, pending_review)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        q.subject or "", q.course or "", q.doc_id, q.page_no,
                        q.topic or "", qt.value,
                        q.question,
                        json.dumps(q.options or [], ensure_ascii=False),
                        q.correct_answer or "",
                        q.explanation or "",
                        json.dumps(q.steps or [], ensure_ascii=False),
                        source_file or q.source_file,
                        q.formula or "",
                        json.dumps(q.images or [], ensure_ascii=False),
                        json.dumps(q.tables or [], ensure_ascii=False),
                        json.dumps(meta, ensure_ascii=False),
                        h,
                        1 if q.pending_review else 0,
                    ),
                )
                inserted += 1
                by_type[qt.value] = by_type.get(qt.value, 0) + 1
            if q.pending_review:
                pending += 1
        conn.commit()
    finally:
        conn.close()
    return {
        "inserted": inserted,
        "merged": merged,
        "pending_review": pending,
        "total": count_questions(),
        "by_type": by_type,
    }


def update_answer(qid: int, answer: str, explanation: str | None = None) -> Question | None:
    """档位3：用户补充标准答案（可带解析）。"""
    conn = get_conn()
    try:
        if explanation is None:
            conn.execute(
                "UPDATE questions SET answer = ? WHERE id = ?",
                (answer.strip(), qid),
            )
        else:
            conn.execute(
                "UPDATE questions SET answer = ?, explanation = ? WHERE id = ?",
                (answer.strip(), explanation.strip(), qid),
            )
        conn.commit()
    finally:
        conn.close()


def update_question_images(
    qid: int,
    images: list[str] | None = None,
    question: str | None = None,
) -> Question | None:
    """更新题目图片绑定与题干文本（锚点 + images 字段保持一致）。

    题干变更时同步重算内容指纹；图片只存文件名。返回更新后的题目。
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM questions WHERE id = ?", (qid,)
        ).fetchone()
        if row is None:
            return None
        q = _row_to_question(row)
        sets: list[str] = []
        params: list[Any] = []
        if question is not None:
            q.question = question
            sets.append("question = ?")
            params.append(question)
            sets.append("content_hash = ?")
            params.append(content_hash(q))
        names = [
            str(p).split("\\")[-1].split("/")[-1] for p in (images or [])
        ]
        sets.append("images = ?")
        params.append(json.dumps(names, ensure_ascii=False))
        params.append(qid)
        conn.execute(
            f"UPDATE questions SET {', '.join(sets)} WHERE id = ?", params
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM questions WHERE id = ?", (qid,)
        ).fetchone()
        return _row_to_question(row)
    finally:
        conn.close()


def image_stats(images_dir: str | Path) -> dict:
    """图片绑定诊断：有图题数、锚点数、锚点/字段文件缺失、孤儿图片。"""
    images_dir = Path(images_dir)
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, question, images FROM questions"
        ).fetchall()
    finally:
        conn.close()
    total = len(rows)
    with_images_field = 0
    with_anchors = 0
    missing_anchors: list[tuple[int, str]] = []
    missing_field: list[tuple[int, str]] = []
    referenced: set[str] = set()
    for r in rows:
        qtext = r["question"] or ""
        anchors = re.findall(r"【图:([^】]+)】", qtext)
        if anchors:
            with_anchors += 1
            referenced.update(anchors)
            for name in anchors:
                if not (images_dir / name).is_file():
                    missing_anchors.append((int(r["id"]), name))
        try:
            field = json.loads(r["images"] or "[]")
        except json.JSONDecodeError:
            field = []
        if field:
            with_images_field += 1
            referenced.update(field)
            for name in field:
                if not (images_dir / name).is_file():
                    missing_field.append((int(r["id"]), name))
    orphans: list[str] = []
    if images_dir.is_dir():
        for f in sorted(images_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in (
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
            ):
                if f.name not in referenced:
                    orphans.append(f.name)
    return {
        "total_questions": total,
        "questions_with_images_field": with_images_field,
        "questions_with_anchors": with_anchors,
        "missing_anchor_files": missing_anchors[:50],
        "missing_anchor_count": len(missing_anchors),
        "missing_images_field_files": missing_field[:50],
        "missing_images_field_count": len(missing_field),
        "orphan_images": orphans[:50],
        "orphan_image_count": len(orphans),
    }
    return get_question(qid)


def list_questions(
    subject: str | None = None,
    qtype: str | QuestionType | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[int, list[Question]]:
    """按学科/题型/关键词筛选题目，返回 (总数, 当前页题目)。"""
    conn = get_conn()
    try:
        where: list[str] = ["1=1"]
        params: list[Any] = []
        if subject:
            where.append("subject = ?")
            params.append(subject)
        if qtype:
            qt = normalize_qtype(qtype)
            where.append("qtype IN (?, ?)")
            params.extend([qt.value, qt.value])
            # 兼容旧库值（single/multi 等）
            legacy = {
                QuestionType.single_choice: "single",
                QuestionType.multiple_choice: "multi",
                QuestionType.judge: "judge",
                QuestionType.blank: "blank",
                QuestionType.calc: "calc",
                QuestionType.essay: "essay",
                QuestionType.thinking: "thinking",
            }.get(qt)
            if legacy and legacy != qt.value:
                where[-1] = "qtype IN (?, ?)"
                params[-2:] = [qt.value, legacy]
        if search:
            where.append("(question LIKE ? OR topic LIKE ? OR subject LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

        page = max(1, page)
        page_size = max(1, min(page_size, 200))
        where_sql = " AND ".join(where)
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM questions WHERE {where_sql}", params
        ).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM questions WHERE {where_sql} "
            "ORDER BY id DESC LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
        return int(total), [_row_to_question(r) for r in rows]
    finally:
        conn.close()


def list_question_ids(
    subject: str | None = None,
    qtype: str | QuestionType | None = None,
    limit: int = 20,
) -> list[int]:
    """随机抽题 id（组卷用）。"""
    conn = get_conn()
    try:
        where: list[str] = ["1=1"]
        params: list[Any] = []
        if subject:
            where.append("subject = ?")
            params.append(subject)
        if qtype:
            qt = normalize_qtype(qtype)
            legacy = {
                QuestionType.single_choice: "single",
                QuestionType.multiple_choice: "multi",
                QuestionType.judge: "judge",
                QuestionType.blank: "blank",
                QuestionType.calc: "calc",
                QuestionType.essay: "essay",
                QuestionType.thinking: "thinking",
            }.get(qt)
            if legacy and legacy != qt.value:
                where.append("qtype IN (?, ?)")
                params.extend([qt.value, legacy])
            else:
                where.append("qtype = ?")
                params.append(qt.value)
        rows = conn.execute(
            f"SELECT id FROM questions WHERE {' AND '.join(where)} "
            "ORDER BY RANDOM() LIMIT ?",
            [*params, limit],
        ).fetchall()
        return [int(r["id"]) for r in rows]
    finally:
        conn.close()


def list_subjects() -> list[dict]:
    """学科分布。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT subject, COUNT(*) AS count
            FROM questions
            GROUP BY subject
            ORDER BY count DESC, subject
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_qtypes(subject: str | None = None) -> list[dict]:
    """题型分布（含 label）；传入 subject 时只统计该学科。"""
    conn = get_conn()
    try:
        sql = "SELECT qtype, COUNT(*) AS count FROM questions"
        params: list[str] = []
        if subject:
            sql += " WHERE subject = ?"
            params.append(subject)
        sql += " GROUP BY qtype"
        rows = conn.execute(sql, params).fetchall()
        counter: dict[str, int] = {}
        for r in rows:
            qt = normalize_qtype(r["qtype"])
            counter[qt.value] = counter.get(qt.value, 0) + int(r["count"])
        return [
            {
                "value": qtype.value,
                "label": QTYPE_LABELS[qtype],
                "count": counter.get(qtype.value, 0),
            }
            for qtype in QuestionType
        ]
    finally:
        conn.close()


def stats() -> dict:
    """首页统计。"""
    conn = get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) AS c FROM questions").fetchone()["c"]
        record_n = conn.execute("SELECT COUNT(*) AS c FROM records").fetchone()["c"]
        pending_n = conn.execute(
            "SELECT COUNT(*) AS c FROM questions WHERE pending_review = 1"
        ).fetchone()["c"]
        return {
            "total": int(total),
            "records": int(record_n),
            "pending_review": int(pending_n),
            "subjects": list_subjects(),
            "qtypes": list_qtypes(),
        }
    finally:
        conn.close()


def count_questions() -> int:
    """题库总题数（兼容旧脚本）。"""
    conn = get_conn()
    try:
        return int(conn.execute("SELECT COUNT(*) AS c FROM questions").fetchone()["c"])
    finally:
        conn.close()


def list_all_questions() -> list[Question]:
    """返回全部题目（供向量索引构建等批量场景使用）。"""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM questions").fetchall()
        return [_row_to_question(r) for r in rows]
    finally:
        conn.close()
