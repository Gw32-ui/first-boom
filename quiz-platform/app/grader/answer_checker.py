"""档位1：题库自带答案的精确比对（按题型规则）。"""
from __future__ import annotations

import ast
import math
import operator
import re

from app.models.question import Question, QuestionType
from app.parser.formula_fixer import fix_html_entities


def normalize_answer(user_ans: str, qtype: QuestionType) -> str:
    u = fix_html_entities(user_ans or "").strip()
    if qtype == QuestionType.judge:
        if u in ("对", "正确", "T", "TRUE", "√", "yes", "是", "Y"):
            return "对"
        if u in ("错", "错误", "F", "FALSE", "×", "X", "no", "否", "N"):
            return "错"
        return u
    if qtype == QuestionType.multiple_choice:
        return "".join(sorted(set(re.sub(r"[^A-Za-z]", "", u.upper()))))
    if qtype == QuestionType.single_choice:
        m = re.match(r"[A-Za-z]", u.upper())
        return m.group(0) if m else u
    return u


def _extract_numbers(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"-?\d+\.?\d*(?:[eE][+-]?\d+)?", text)]


_MATH_SAFE = {
    "pi": math.pi,
    "e": math.e,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "exp": math.exp,
    "log": math.log,
    "abs": abs,
}


def _eval_node(node) -> float | None:
    """只允许常量 + 四则/幂/取模 + 白名单函数的安全求值。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp):
        a = _eval_node(node.left)
        b = _eval_node(node.right)
        if a is None or b is None:
            return None
        op = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Pow: operator.pow,
            ast.Mod: operator.mod,
        }.get(type(node.op))
        return op(a, b) if op else None
    if isinstance(node, ast.UnaryOp):
        a = _eval_node(node.operand)
        if a is None:
            return None
        if isinstance(node.op, ast.UAdd):
            return a
        if isinstance(node.op, ast.USub):
            return -a
        return None
    if isinstance(node, ast.Name):
        return _MATH_SAFE.get(node.id)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fn = _MATH_SAFE.get(node.func.id)
        if fn is None:
            return None
        args = [_eval_node(a) for a in node.args]
        if any(a is None for a in args):
            return None
        try:
            return float(fn(*args))
        except (ValueError, ZeroDivisionError, OverflowError):
            return None
    return None


def _eval_math(expr: str) -> float | None:
    """把常见数学表达式（分数、√、π、乘方）安全求值为数值。"""
    t = expr.strip()
    if not t:
        return None
    t = (
        t.replace("×", "*")
        .replace("÷", "/")
        .replace("−", "-")
        .replace("π", "pi")
        .replace("^", "**")
    )
    # √2 / √π → sqrt(2) / sqrt(pi)
    t = re.sub(r"√\s*([0-9]+(?:\.[0-9]+)?|pi)", r"sqrt(\1)", t)
    t = t.replace("√", "sqrt")
    t = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1)/(\2)", t)
    try:
        node = ast.parse(t, mode="eval")
    except SyntaxError:
        return None
    val = _eval_node(node.body)
    if val is None or not math.isfinite(val):
        return None
    return val


def _parse_numeric_answers(text: str) -> list[float]:
    """把参考答案/作答拆成数值列表：优先整体求值（1/2→0.5、√2→1.414…），
    失败则退回提取数字。"""
    values: list[float] = []
    for seg in re.split(r"[,，、;；\s]+", text.strip()):
        if not seg:
            continue
        v = _eval_math(seg)
        if v is not None:
            values.append(v)
    if values:
        return values
    return _extract_numbers(text)


def _calc_close(user: str, ref: str) -> bool:
    un = _parse_numeric_answers(user)
    rn = _parse_numeric_answers(ref)
    if not un or not rn or len(un) != len(rn):
        return False
    for a, b in zip(un, rn):
        if math.isclose(a, b, rel_tol=5e-4, abs_tol=1e-6):
            continue
        return False
    return True


def _judge_option_value(question: Question, letter: str) -> str | None:
    """按选项文本判断字母对应的对/错语义，避免 A=对 的硬编码。"""
    opts = [
        re.sub(r"^[（(]?[A-Ha-h]\s*(?:[\.．、)）]\s*|\s+)", "", o).strip()
        for o in question.options
    ]
    idx = ord(letter.upper()) - ord("A")
    if 0 <= idx < len(opts):
        val = opts[idx]
        if val in ("对", "正确", "√", "是", "T"):
            return "对"
        if val in ("错", "错误", "×", "否", "F"):
            return "错"
    return None


def _judge_value(question: Question, raw: str) -> str:
    """判断题答案语义化：字母先按选项文本映射，映射不了保留原值。"""
    v = normalize_answer(raw, QuestionType.judge)
    if re.fullmatch(r"[A-Ha-h]", v or ""):
        mapped = _judge_option_value(question, v)
        if mapped:
            return mapped
    return v


def check_answer(question: Question, user_answer: str) -> tuple[bool, str]:
    """返回 (是否正确, 说明)。只处理有标准答案的题目。"""
    ref = (question.correct_answer or "").strip()
    u = normalize_answer(user_answer, question.qtype)
    if not ref or not u:
        return False, "答案不完整"

    if question.qtype == QuestionType.multiple_choice:
        ref_n = "".join(sorted(set(re.sub(r"[^A-Za-z]", "", ref.upper()))))
        return u == ref_n, ("正确" if u == ref_n else "答案不匹配")

    if question.qtype == QuestionType.single_choice:
        m = re.match(r"[A-Za-z]", ref.upper())
        ref_n = m.group(0) if m else ref
        return u == ref_n, ("正确" if u == ref_n else "答案不匹配")

    if question.qtype == QuestionType.judge:
        u_n = _judge_value(question, u)
        r_n = _judge_value(question, ref)
        return u_n == r_n, ("正确" if u_n == r_n else "答案不匹配")

    if question.qtype == QuestionType.calc:
        ok = _calc_close(u, ref)
        return ok, ("数值正确" if ok else "数值不匹配")

    if question.qtype in (QuestionType.essay, QuestionType.thinking):
        # 简答/思考题：文本精确比对无意义，交由人工/LLM 核对
        return False, "简答/思考题请人工核对"

    # 填空/简答/思考：支持多答案容错（逗号/顿号/分号分隔）
    parts_ref = [p.strip() for p in re.split(r"[,，、;；]", ref) if p.strip()]
    parts_user = [p.strip() for p in re.split(r"[,，、;；]", u) if p.strip()]
    if len(parts_ref) != len(parts_user):
        return False, "答案不匹配"
    # 多空答案容错：顺序无关（如 “上海，北京” 与 “北京、上海” 等价）
    ok = sorted(a.strip().lower() for a in parts_user) == sorted(
        b.strip().lower() for b in parts_ref
    )
    return ok, ("正确" if ok else "答案不匹配")
