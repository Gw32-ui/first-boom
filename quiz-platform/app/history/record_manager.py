"""历史记录：保存每次答题结果，支持查询/导出。"""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.record import GradedItem, Record
from app.storage.db_manager import get_conn

ROOT = Path(__file__).resolve().parent.parent.parent
RECORDS_DIR = ROOT / "output" / "records"


def save_record(record: Record) -> Record:
    """保存记录到 records 表，返回带 id 的记录。"""
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO records
                (paper_id, title, subject, answers, score, total_score,
                 correct_count, wrong_count, pending_count, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.paper_id,
                record.title,
                record.subject,
                json.dumps(
                    [item.model_dump() for item in record.answers],
                    ensure_ascii=False,
                ),
                record.score,
                record.total_score,
                record.correct_count,
                record.wrong_count,
                record.pending_count,
                record.status,
            ),
        )
        conn.commit()
        record.id = int(cur.lastrowid)
    finally:
        conn.close()
    return record


def _row_to_record(row: Any) -> Record:
    d = dict(row)
    d["answers"] = [
        GradedItem(**item) for item in json.loads(d.get("answers") or "[]")
    ]
    return Record(**d)


def get_record(record_id: int) -> Record | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM records WHERE id = ?", (record_id,)
        ).fetchone()
        return _row_to_record(row) if row else None
    finally:
        conn.close()


def list_records(
    subject: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[int, list[Record]]:
    conn = get_conn()
    try:
        where: list[str] = ["1=1"]
        params: list[Any] = []
        if subject:
            where.append("subject = ?")
            params.append(subject)
        if status:
            where.append("status = ?")
            params.append(status)
        page = max(1, page)
        page_size = max(1, min(page_size, 200))
        where_sql = " AND ".join(where)
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM records WHERE {where_sql}", params
        ).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM records WHERE {where_sql} "
            "ORDER BY id DESC LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
        return int(total), [_row_to_record(r) for r in rows]
    finally:
        conn.close()


def export_record(record_id: int, fmt: str = "json") -> tuple[str, str]:
    """导出记录到 output/records/，返回 (相对路径, 内容)。"""
    record = get_record(record_id)
    if not record:
        raise FileNotFoundError(f"记录不存在: {record_id}")
    RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    base = f"record_{record_id}_{stamp}"

    if fmt == "csv":
        filename = f"{base}.csv"
        path = RECORDS_DIR / filename
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["题号", "题目", "标准答案", "作答", "状态", "得分", "点评"])
            for i, item in enumerate(record.answers, 1):
                writer.writerow(
                    [
                        i,
                        item.question,
                        item.correct_answer,
                        item.user_answer,
                        item.status,
                        item.score,
                        item.comment,
                    ]
                )
        content = path.read_text(encoding="utf-8-sig")
    else:
        filename = f"{base}.json"
        path = RECORDS_DIR / filename
        content = record.model_dump_json(indent=2, ensure_ascii=False)
        path.write_text(content, encoding="utf-8")
    return filename, content
