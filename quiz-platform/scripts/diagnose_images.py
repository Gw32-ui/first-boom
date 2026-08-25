"""图片绑定诊断脚本（只读）：统计题库图片绑定与 output/images 目录一致性。

用法：
    .venv\\Scripts\\python.exe scripts\\diagnose_images.py [--db data/questions.db]

输出：
    - 有图题数（images 字段 / 题干锚点两条路径）
    - 锚点指向的文件是否存在（缺失列表）
    - images 字段指向的文件是否存在（缺失列表）
    - 目录中未被任何题引用的孤儿图片
    - image_meta.json 中视觉分类失败统计（超时/500/连接拒绝）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage.db_manager import get_conn, init_db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "questions.db"))
    parser.add_argument("--images", default=str(ROOT / "output" / "images"))
    args = parser.parse_args()

    import app.storage.db_manager as dm

    dm.DB_PATH = Path(args.db)
    init_db()
    images_dir = Path(args.images)

    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, question, images FROM questions"
        ).fetchall()
    finally:
        conn.close()

    print(f"题库总数: {len(rows)}")
    with_images_field = 0
    with_anchors = 0
    missing_anchors: list[tuple[int, str]] = []
    missing_field: list[tuple[int, str]] = []
    referenced: set[str] = set()
    for r in rows:
        qtext = r["question"] or ""
        anchors = [m for m in re.findall(r"【图:([^】]+)】", qtext)]
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

    print(f"images 字段非空的题: {with_images_field}")
    print(f"题干含【图:】锚点的题: {with_anchors}")
    print(f"锚点文件缺失: {len(missing_anchors)}")
    for qid, name in missing_anchors[:30]:
        print(f"  - 题 {qid}: {name}")
    print(f"images 字段文件缺失: {len(missing_field)}")
    for qid, name in missing_field[:30]:
        print(f"  - 题 {qid}: {name}")

    orphans = [
        f.name
        for f in sorted(images_dir.glob("*"))
        if f.is_file()
        and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif")
        and f.name not in referenced
    ]
    print(f"孤儿图片（未被任何题引用）: {len(orphans)}")
    for name in orphans[:30]:
        print(f"  - {name}")

    meta_file = images_dir / "image_meta.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}
        errs: dict[str, int] = {}
        kinds: dict[str, int] = {}
        for _, v in meta.items():
            e = v.get("vision_error") or v.get("error") or ""
            if e:
                errs[e] = errs.get(e, 0) + 1
            kinds[v.get("kind")] = kinds.get(v.get("kind"), 0) + 1
        print(f"image_meta.json 条目: {len(meta)}")
        print(f"分类失败统计: {errs or '无'}")
        print(f"分类结果分布: {kinds or '无'}")


if __name__ == "__main__":
    main()
