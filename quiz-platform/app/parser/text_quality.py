"""PDF 文本层质量检测：识别公式排版引擎拆散的碎片文本。

公式型 PDF（LaTeX / Word 公式导出）会把公式拆成最小字符单元排入文本层：
复制出来是一堆单字符和半截命令（如 ``\\rh o``、``\\Delt a``），但
``text.strip()`` 非空，导致此前“文本层为空才走 OCR”的兜底被跳过。
本模块给出碎片化评分，供导入链路决定是否强制走视觉 OCR。
"""
from __future__ import annotations

import re

# WPS 私有区/PDF 内部字符（\uf0xx 等）→ 不可信文本层
PUA_RE = re.compile(r"[\uf000-\uf8ff]")
# 半截 LaTeX 命令后跟空格再接字母：\rh o、\Delt a、\inft y
# 合法写法如 \sin x、\frac 12 不会误报（命令在已知集合内）
BROKEN_LATEX_CMD = re.compile(r"\\([a-zA-Z]{2,})\s+[a-zA-Z]")
KNOWN_LATEX_COMMANDS = {
    "sin", "cos", "tan", "cot", "sec", "csc", "log", "ln", "exp", "lim", "gcd",
    "arg", "frac", "sqrt", "sum", "int", "iint", "iiint", "oint", "prod", "infty",
    "partial", "nabla", "to", "rightarrow", "leftarrow", "leftrightarrow",
    "Rightarrow", "Leftarrow", "cdot", "cdots", "ldots", "times", "div", "pm", "mp",
    "neq", "leq", "geq", "approx", "equiv", "in", "notin", "subset", "supset",
    "subseteq", "supseteq", "cup", "cap", "forall", "exists", "text", "quad",
    "qquad", "begin", "end", "left", "right", "big", "bigg", "bigl", "bigr",
    "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta", "eta",
    "theta", "vartheta", "iota", "kappa", "lambda", "mu", "nu", "xi", "pi", "rho",
    "sigma", "tau", "upsilon", "phi", "varphi", "chi", "psi", "omega",
    "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon",
    "Phi", "Psi", "Omega",
}
_KNOWN_LOWER = {k.lower() for k in KNOWN_LATEX_COMMANDS}


def _has_broken_latex(text: str) -> int:
    """统计未知命令的半截 LaTeX（命令拆散后跟空格再接字母）数量。"""
    n = 0
    for m in BROKEN_LATEX_CMD.finditer(text):
        if m.group(1).lower() not in _KNOWN_LOWER:
            n += 1
    return n


def _single_char_token_ratio(text: str) -> float:
    """空白分隔 token 中长度为 1 的 ASCII 字母/数字/运算符占比。

    公式拆散层表现为“2 2 ( ) ( ) x y z = + − …”这类短碎片；
    单个汉字（与/的/值）和 $ 定界符不计，避免误伤正常中文与合法 LaTeX。
    """
    tokens = [t for t in re.split(r"\s+", text.strip()) if t]
    if not tokens:
        return 0.0
    single = sum(
        1
        for t in tokens
        if len(t) <= 1 and not re.match(r"[\u4e00-\u9fff$]", t)
    )
    return single / len(tokens)


def assess_text_quality(text: str, threshold: float = 0.30) -> dict:
    """评估文本层可信度，返回 {score, fragmented, reasons, stats}。

    score ∈ [0, 1]，越高越不可信；fragmented=True 表示应强制走视觉 OCR。
    指标：
      - 单字符 token 占比 >30%；
      - 未知半截 LaTeX 命令（\\rh o 等）；
      - WPS/PDF 私有区字符（\\uf0xx）；
      - 中文连续句行占比过低。
    """
    stripped = text.strip()
    if not stripped:
        return {
            "score": 1.0,
            "fragmented": True,
            "reasons": ["文本层为空"],
            "stats": {
                "single_char_ratio": 1.0,
                "broken_latex": 0,
                "pua": 0,
                "cjk_line_ratio": 0.0,
            },
        }

    lines = [ln for ln in stripped.splitlines() if ln.strip()]
    single_ratio = _single_char_token_ratio(stripped)
    broken = _has_broken_latex(stripped)
    pua = len(PUA_RE.findall(stripped))
    cjk_lines = sum(1 for ln in lines if re.search(r"[\u4e00-\u9fff]{4,}", ln))
    cjk_ratio = cjk_lines / len(lines) if lines else 0.0

    score = 0.0
    reasons: list[str] = []
    if single_ratio > 0.30:
        score += 0.45
        reasons.append(f"单字符token占比{round(single_ratio * 100)}%")
    if broken >= 2:
        score += 0.35
        reasons.append(f"疑似半截LaTeX命令{broken}处（如 \\rh o）")
    if pua >= 1:
        score += 0.30
        reasons.append(f"私有区字符{pua}个（\\uf0xx）")
    if len(lines) > 5 and cjk_ratio < 0.25:
        score += 0.25
        reasons.append(f"中文连续句行占比仅{round(cjk_ratio * 100)}%")

    score = round(min(score, 1.0), 3)
    return {
        "score": score,
        "fragmented": score >= threshold,
        "reasons": reasons,
        "stats": {
            "single_char_ratio": round(single_ratio, 3),
            "broken_latex": broken,
            "pua": pua,
            "cjk_line_ratio": round(cjk_ratio, 3),
        },
    }
