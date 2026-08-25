from pathlib import Path
import os

# 数据库位置
db_path = Path('quiz-platform/data/questions.db')
print(f"数据库路径: {db_path.resolve()}")
if db_path.exists():
    size = db_path.stat().st_size
    print(f"数据库大小: {size:,} bytes ({size/1024/1024:.2f} MB)")

# 图片存储位置
img_dir = Path('quiz-platform/output/images')
print(f"\n图片目录: {img_dir.resolve()}")
if img_dir.exists():
    files = list(img_dir.glob('*'))
    total_size = sum(f.stat().st_size for f in files if f.is_file())
    print(f"图片文件数: {len(files)} 个")
    print(f"图片总大小: {total_size:,} bytes ({total_size/1024:.2f} KB)")
else:
    print("图片目录不存在")

# 总体存储
total = (db_path.stat().st_size if db_path.exists() else 0) + \
        (sum(f.stat().st_size for f in img_dir.glob('*') if f.is_file()) if img_dir.exists() else 0)
print(f"\n总存储占用: {total:,} bytes ({total/1024/1024:.2f} MB)")
