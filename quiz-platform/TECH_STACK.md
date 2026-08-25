# 技术栈

## 后端
| 技术 | 版本 | 用途 |
|---|---|---|
| Python | ≥ 3.12 | 主语言 |
| FastAPI | ≥ 0.141 | Web 框架 / API 服务 |
| Uvicorn | ≥ 0.52 | ASGI 服务器 |
| Pydantic | ≥ 2.7 | 数据模型校验 |
| SQLite | 内置 | 数据持久化（questions.db） |
| python-docx | ≥ 1.2 | .docx 解析（文本 / 内嵌图片 / 公式） |
| pdfplumber | ≥ 0.11 | PDF 文本层解析 |
| PyMuPDF | ≥ 1.24 | PDF 图片提取 / OCR 兜底渲染 |
| Pillow | ≥ 12.3 | 图片处理（格式转换 / 缩放） |
| lxml | ≥ 5.0 | XML / HTML 解析 |
| httpx | ≥ 0.28 | 异步 HTTP 客户端（调用 LLM API） |
| PyYAML | ≥ 6.0 | 配置文件解析 |

## AI / 机器学习
| 技术 | 版本 | 用途 |
|---|---|---|
| sentence-transformers | ≥ 3.0 | 文本向量化（语义检索） |
| faiss-cpu | ≥ 1.8 | 向量相似度检索 |
| torch | ≥ 2.2 | 深度学习后端（sentence-transformers 依赖） |
| 智谱 GLM-4.7-Flash | — | LLM 辅助判卷（可选，免费） |
| 智谱 GLM-4.6V-Flash | — | 图片理解 / 分类（可选，免费） |

## 前端
| 技术 | 用途 |
|---|---|
| 原生 HTML/CSS/JS | 单页应用（无框架） |
| KaTeX | LaTeX 数学公式渲染 |

## 工具链
| 工具 | 用途 |
|---|---|
| uv | 依赖管理 / 虚拟环境 |
| pytest | 单元测试 |
| Git + GitHub | 版本控制 / 远程备份 |

## 部署方式
- 纯本地运行，绑定 127.0.0.1:8000
- 无 Docker / 云端依赖
- 数据不出本机