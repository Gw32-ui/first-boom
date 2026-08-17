# 依赖安装与启动指南

## 1. 安装依赖
```bash
cd C:\Users\17739\workflu\quiz-platform
pip install fastapi uvicorn python-docx pdfplumber pillow lxml pyyaml sentence-transformers faiss-cpu
```

## 2. 启动服务
```bash
python -m app.web
```

## 3. 验证API
打开浏览器访问 http://127.0.0.1:8000/docs 查看API文档
