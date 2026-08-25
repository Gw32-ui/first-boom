# 技术上下文（Tech Context）

## 架构分层
输入层（web.py 上传 / mcp_text_clean.py）
→ 解析层（app/parser：file_loader.py 文件抽取、model_parser.py 题型检测、formula_fixer.py 公式修复）
→ 存储层（app/storage：db_manager.py 建表迁移、question_repo.py 题库操作）
→ 判卷层（app/grader：answer_checker.py 规则判卷、llm_client.py 可选 LLM 判卷）
→ 检索层（app/vector：embedding_service.py FAISS 语义检索，可选）
→ 展示层（app/static：原生 JS + KaTeX）

## 外部依赖
- GLM-4.6V-Flash（智谱云 API：vision 图片分类 / OCR / 变式 / AI 整理；key 在 .env 的 ZHIPU_API_KEY）
- FAISS（app/vector/embedding_service.py，模块级硬依赖）
- sentence-transformers + BGE 模型（首次需下载 ~1GB+）
- pdfplumber / python-docx / Pillow / lxml（文件解析）

## 数据清洗顺序（导入统一入口 _run_import）
HTML 实体反转义（fix_html_entities，2 轮）→ WPS 私有区乱码（fix_wps_encoding）→
Unicode 数学符号转 LaTeX（unicode_to_latex）；判卷归一化与 MCP clean_text 同步覆盖。

## 接口契约（Question 模型，字段已冻结）
- id / subject / course / doc_id / page_no / topic：归属与来源
- qtype：题型枚举（见 product_context）
- question：题干文本（可含 $LaTeX$ 与 【图:文件名】 标记）
- options / correct_answer / explanation / steps
- formula / images / tables / paper_meta：S7 扩展字段

## 存储约定
- 无 ORM：db_manager.migrate() 用 `ALTER TABLE ADD COLUMN` 幂等补列
- 新增列必须走 migrate()/ _ensure_columns，不删旧列
