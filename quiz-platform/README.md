# 出题交互系统（quiz-platform）

本地化出题交互系统：题库管理、专项训练、自由组卷、智能判卷与历史追溯。完全本地运行（仅绑定 127.0.0.1），数据不出本机，不做内网穿透、不做云端部署。

自带题库：`data/questions.db` 内置「毛概」1068 题（单选 / 多选 / 判断 / 简答 / 思考），开箱即用。

## 项目结构

```
quiz-platform/
├─ app/
│  ├─ models/           # 数据模型（question.py / paper.py / record.py）
│  ├─ parser/           # 文本/docx/pdf 解析（model_parser.py / file_loader.py / formula_fixer.py / text_quality.py）
│  ├─ storage/          # 数据库操作（db_manager.py / question_repo.py）
│  ├─ generator/        # 组卷引擎（paper_generator.py / variant_gen.py）
│  ├─ grader/           # 判卷三档策略（grader.py / answer_checker.py / llm_client.py）
│  ├─ history/          # 历史记录（record_manager.py）
│  ├─ vector/           # 向量检索（embedding_service.py）
│  ├─ vision/           # 图片理解（可选，默认关闭）
│  ├─ llm/              # 智谱 GLM 客户端（zhipu_client.py）
│  ├─ config.py         # 配置加载
│  ├─ web.py            # FastAPI 服务入口
│  └─ static/           # 前端（index.html / css / js / KaTeX）
├─ data/                # questions.db（题库 + 历史记录）
├─ input/               # 待导入的文件（可选）
├─ materials/           # 学习材料（可选）
├─ output/images/       # 从 docx/pdf 抽取的题目图片
├─ output/papers/       # 生成的试卷 JSON
├─ output/records/      # 历史记录导出（CSV/JSON）
├─ scripts/             # 诊断脚本（diagnose_images.py）
├─ templates/           # 预置组卷模板（可选）
├─ tests/               # pytest 测试
├─ config/              # config.yaml（LLM 判卷 / vision 开关）
├─ .env                 # API Key（不入库）
└─ pyproject.toml       # 依赖声明
```

## 快速启动

### 1. 安装依赖

```bash
cd quiz-platform
uv sync
# 或手动安装
pip install fastapi uvicorn python-docx pdfplumber pymupdf pillow lxml pyyaml sentence-transformers faiss-cpu httpx
```

### 2. 配置 API Key（可选）

AI 判卷和图片理解需要智谱 API Key（免费）：

```bash
# 编辑 quiz-platform/.env
ZHIPU_API_KEY=你的key
```

不配置也能正常使用（判卷走题库自带答案比对）。

### 3. 启动服务

```bash
cd quiz-platform
uv run python -m app.web
# 或直接使用项目虚拟环境
.venv\Scripts\python.exe -m app.web
```

打开 http://127.0.0.1:8000（仅本机可访问）。

## 主要功能

- **题库管理**：文本粘贴或上传 txt / docx / pdf 导入，docx 内嵌图片/公式自动抽取，浏览、筛选、删除、补充答案
- **专项训练**：选定学科 + 单题型随机抽题练习
- **自由组卷**：自选各题型数量与分值，或使用预置模板一键组卷，生成试卷并保存
- **公式与图片展示**：docx 公式转 LaTeX，页面用 KaTeX 渲染；题目图片自动展示
- **智能判卷（三档）**：
  1. 题库自带答案 → 直接比对（选择/填空/判断/计算按题型规则）
  2. 简答/思考题 + 已配置 LLM → 本地大模型辅助判卷（config.yaml 开关，默认关闭）
  3. 无答案 → 提示待补，支持用户填写标准答案入库
- **历史记录**：保存每次答题结果，支持筛选查询与 CSV/JSON 导出

## 测试

```bash
.venv\Scripts\python.exe -m pytest tests -q
```

## 说明

- AI 判卷与图片理解为可选功能：`config/config.yaml` 默认关闭，关闭时系统照常工作
- 删除题库：可在网页「题库管理」中按学科删除，或直接清空 `data/questions.db`
- 诊断图片归属：`python scripts/diagnose_images.py`

## API 速览

`GET /api/stats`、`GET /api/questions`、`POST /api/question/import`、`POST /api/practice/start`、`POST /api/paper/generate`、`POST /api/submit`、`GET /api/records`、`GET /api/record/{id}/export?format=csv|json`