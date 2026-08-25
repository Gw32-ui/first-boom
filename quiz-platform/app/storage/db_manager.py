"""SQLite 连接管理与建表（幂等）。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "questions.db"


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    """幂等地给表补充缺失列（SQLite 的 ALTER TABLE ADD COLUMN 不能重复执行）。"""
    existing = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def get_conn() -> sqlite3.Connection:
    """获取数据库连接（每次独立连接，线程安全）。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    # 并发写保护：等待锁而不是立即报 database is locked
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate() -> None:
    """增量迁移：确保所有需要的表/字段存在。"""
    conn = get_conn()
    try:
        # WAL：读写不互相阻塞（-wal/-shm 已被 .gitignore 忽略）
        conn.execute("PRAGMA journal_mode = WAL")
        # 旧库可能没有 records 表 → 新建
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL DEFAULT '',
                answers TEXT NOT NULL DEFAULT '[]',
                score REAL NOT NULL DEFAULT 0,
                total_score REAL NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                wrong_count INTEGER NOT NULL DEFAULT 0,
                pending_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'graded',
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_records_subject ON records(subject)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_records_created ON records(created_at)"
        )
        # S7：题库表补充公式/图片/表格/试卷元信息字段（老库自动加列，不丢数据）
        # pending_review：残缺标记（公式/图片未解析成功，需人工复核）
        _ensure_columns(
            conn,
            "questions",
            {
                "formula": "TEXT DEFAULT ''",
                "images": "TEXT DEFAULT '[]'",
                "tables": "TEXT DEFAULT '[]'",
                "paper_meta": "TEXT DEFAULT '{}'",
                "content_hash": "TEXT DEFAULT ''",
                "pending_review": "INTEGER DEFAULT 0",
            },
        )
        # 内容指纹去重索引（MD5 查重走索引，避免全表扫描）
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_questions_content_hash "
            "ON questions(content_hash)"
        )
        # 判重按题干精确匹配，补索引避免导入时全表扫描
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_questions_question "
            "ON questions(question)"
        )
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """建表（幂等，可重复执行）：题库 + 文档 + 历史记录。"""
    conn = get_conn()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                course TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                page_count INTEGER DEFAULT 0,
                char_count INTEGER DEFAULT 0,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                course TEXT NOT NULL,
                doc_id INTEGER,
                page_no INTEGER DEFAULT 0,
                topic TEXT DEFAULT '',
                qtype TEXT NOT NULL,
                question TEXT NOT NULL,
                options TEXT DEFAULT '',
                answer TEXT NOT NULL,
                explanation TEXT DEFAULT '',
                steps TEXT DEFAULT '[]',
                source_file TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE INDEX IF NOT EXISTS idx_questions_subject
                ON questions(subject);
            CREATE INDEX IF NOT EXISTS idx_questions_course
                ON questions(course);
            CREATE INDEX IF NOT EXISTS idx_questions_topic
                ON questions(topic);
            CREATE INDEX IF NOT EXISTS idx_questions_qtype
                ON questions(qtype);
            """
        )
        conn.commit()
    finally:
        conn.close()
    migrate()