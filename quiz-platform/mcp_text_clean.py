"""文本/文件清洗 MCP 服务器：本地规则清洗 + 智谱 GLM-4.6V-Flash 云端视觉清洗。

风格参考 weather.py：mcp[cli]>=2.0.0 + httpx，stdio 传输。
GLM-4.6V-Flash 是云端免费模型，无需本地部署（无 GPU 也能用），
只需在 .env 里配置 ZHIPU_API_KEY（智谱开放平台：https://open.bigmodel.cn）。

启动：
    .venv\\Scripts\\python.exe mcp_text_clean.py

工具：
    clean_text(text, convert_math=False)   本地规则清洗（去噪声、修 WPS 乱码）
    ocr_clean(image_path)                  云端视觉清洗（识别文字+公式 → Markdown/LaTeX）
"""
from __future__ import annotations

import base64
import os
import re
from pathlib import Path

import httpx
from mcp.server import MCPServer

from app.parser.formula_fixer import (
    fix_html_entities,
    fix_wps_encoding,
    unicode_to_latex,
)

mcp = MCPServer("text-clean")

PROJECT_ROOT = Path(__file__).resolve().parent
ZHIPU_API_BASE = "https://open.bigmodel.cn/api/paas/v4"
ZHIPU_MODEL = "glm-4.6v-flash"
ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "")


def _load_env() -> None:
    """从项目根目录 .env 读取配置（环境变量优先，.env 兜底）。"""
    global ZHIPU_API_KEY, ZHIPU_API_BASE, ZHIPU_MODEL
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k == "ZHIPU_API_KEY" and not os.environ.get("ZHIPU_API_KEY"):
            ZHIPU_API_KEY = v
        elif k == "ZHIPU_API_BASE" and not os.environ.get("ZHIPU_API_BASE"):
            ZHIPU_API_BASE = v
        elif k == "ZHIPU_MODEL" and not os.environ.get("ZHIPU_MODEL"):
            ZHIPU_MODEL = v


_load_env()

# 常见页眉页脚 / 噪声行
_PAGE_NUMBER = re.compile(r"^\s*第\s*\d+\s*页\s*[\/／]\s*共\s*\d+\s*页\s*$")
_SEPARATOR = re.compile(r"^[-=—*_~]{5,}$")
_ONLY_SPACE = re.compile(r"^\s*$")


def _rule_clean(text: str, convert_math: bool) -> str:
    """规则清洗：换行归一 → 去页眉页脚/分隔线/多余空行 → 修 WPS 乱码 → 可选转 LaTeX。"""
    text = fix_html_entities(text)  # 网页/HTML 化数据源残留的 &gt; &lt; 等
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cleaned: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or _ONLY_SPACE.match(line):
            continue
        if _PAGE_NUMBER.match(line) or _SEPARATOR.match(line):
            continue
        cleaned.append(line)
    # 合并连续空行（保留段落分隔，最多一个空行）
    out: list[str] = []
    for line in cleaned:
        if line:
            out.append(line)
        elif out and out[-1] != "":
            out.append("")
    text = "\n".join(out).strip()
    # WPS 私有区乱码 → Unicode 标准字符
    text = fix_wps_encoding(text)
    # 可选：Unicode 数学符号 → LaTeX 命令（如 ∫ → \\int）
    if convert_math:
        text = unicode_to_latex(text)
    return text


@mcp.tool()
async def clean_text(text: str, convert_math: bool = False) -> str:
    """本地规则清洗 OCR/PDF 文本：去页眉页脚、分隔线、多余空行，修复 WPS 私有区乱码。

    Args:
        text: 待清洗的原始文本。
        convert_math: 是否把 Unicode 数学符号转成 LaTeX 命令（默认 False）。
    """
    return _rule_clean(text, convert_math)


async def _zhipu_vision(prompt: str, image_path: str, timeout: float = 90.0) -> str:
    """调用智谱 GLM-4.6V-Flash（OpenAI 兼容接口）识别单张图片。"""
    if not ZHIPU_API_KEY:
        raise RuntimeError(
            "未配置 ZHIPU_API_KEY：请在 quiz-platform/.env 写入 ZHIPU_API_KEY=xxx"
            "（智谱开放平台 https://open.bigmodel.cn 的 API 密钥页创建，模型免费）"
        )
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"图片不存在: {image_path}")
    suffix = path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "image/png")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = {
        "model": ZHIPU_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            }
        ],
        "temperature": 0.1,
    }
    headers = {
        "Authorization": f"Bearer {ZHIPU_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{ZHIPU_API_BASE}/chat/completions", json=payload, headers=headers
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"智谱 API 调用失败 HTTP {resp.status_code}: {resp.text[:500]}"
            )
        data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"智谱 API 返回格式异常: {str(data)[:500]}") from exc


@mcp.tool()
async def ocr_clean(image_path: str, convert_math: bool = True) -> str:
    """云端视觉清洗：调用智谱 GLM-4.6V-Flash 识别图片中的文字与数学公式。

    输出为干净的 Markdown 文本，公式用 $...$ / $$...$$ LaTeX 表示；
    convert_math=True 时要求公式一律输出 LaTeX（默认开启）。

    Args:
        image_path: 本地图片路径（png/jpg/jpeg/webp/gif）。
        convert_math: 是否要求公式输出为 LaTeX（默认 True）。
    """
    math_rule = (
        "数学公式一律用 $...$（行内）或 $$...$$（独立行）包裹的标准 LaTeX 表示，"
        "例如 \\int_{0}^{\\infty} e^{-x^{2}}dx"
        if convert_math
        else "文字按原文转录，保留符号原样"
    )
    prompt = (
        "你是一名试卷/课件文档清洗助手。请识别图片中的全部文字内容，输出干净的 Markdown 文本：\n"
        "1. 去掉页眉页脚、水印、页码等干扰信息；\n"
        "2. 保留题目编号、选项、答案结构；\n"
        f"3. {math_rule}；\n"
        "4. 不要添加任何解释或评论，只输出清洗后的内容。"
    )
    return await _zhipu_vision(prompt, image_path)


if __name__ == "__main__":
    mcp.run(transport="stdio")
