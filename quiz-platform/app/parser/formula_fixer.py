"""公式修复器：解决WPS私有字体乱码 + Unicode数学符号转LaTeX"""
import html
import re

# WPS私有区字符 → Unicode标准字符映射表
PUA_TO_UNICODE = {
    # 数学运算符
    '': '\u2212', '': '=', '': '+', '': '*',
    '': ',', '': ';', '': ':',
    '': '<', '': '>', '': '≤', '': '≥', '': '≠',
    # 希腊字母（小写）
    '': 'α', '': 'β', '': 'γ', '': 'δ',
    '': 'ε', '': 'θ', '': 'λ', '': 'μ',
    '': 'ν', '': 'ξ', '': 'π', '': 'ρ',
    '': 'σ', '': 'τ', '': 'φ', '': 'χ',
    '': 'ψ', '': 'ω',
    # 希腊字母（大写）
    '': 'Α', '': 'Β', '': 'Γ', '': 'Δ',
    '': 'Ε', '': 'Ζ', '': 'Η', '': 'Θ',
    '': 'Ι', '': 'Κ', '': 'Λ', '': 'Μ',
    '': 'Ν', '': 'Ξ', '': 'Ο', '': 'Π',
    '': 'Ρ', '': 'Σ', '': 'Τ', '': 'Υ',
    '': 'Φ', '': 'Χ', '': 'Ψ', '': 'Ω',
    # 数学符号
    'ò': '∫', 'õ': '∐', 'ö': '∑',
    '¥': '∞', '¹': '√', 'º': '∝',
    # 箭头
    'ù': '←', 'ú': '→', 'û': '↑', 'ü': '↓',
    'ý': '↔', 'þ': '⇐', 'ÿ': '⇒',
    # WPS 私有区补充（信号与系统试卷实测码位）
    '\uf028': '(', '\uf029': ')',
    '\uf077': 'ω', '\uf0a2': '′', '\uf0a5': '∞', '\uf0ab': '↔',
    '\uf0d7': '·', '\uf0f2': '∫',
    # 大括号/括号/方括号分段残片
    '\uf0e6': '(', '\uf0f6': ')',
    '\uf0e7': '(', '\uf0f7': ')',
    '\uf0e8': '(', '\uf0f8': ')',
    '\uf0e9': '[', '\uf0f9': ']',
    '\uf0ea': '(', '\uf0fa': ')',
    '\uf0eb': '[', '\uf0fb': ']',
    '\uf0ec': '{', '\uf0ed': '{',
    '\uf0ee': '0', '\uf0ef': ' ',
}

# Unicode → LaTeX 映射表
UNICODE_TO_LATEX = {
    # 积分符号
    '∫': r'\int', '∮': r'\oint', '∯': r'\iiint',
    '∬': r'\iint', '∭': r'\idotsint',
    # 求和符号
    '∑': r'\sum', '∏': r'\prod',
    # 极限符号
    'lim': r'\lim',
    # 无穷大
    '∞': r'\infty',
    # 偏导数
    '∂': r'\partial',
    # 梯度
    '∇': r'\nabla',
    # 分数
    '½': r'\frac{1}{2}', '⅓': r'\frac{1}{3}', '¼': r'\frac{1}{4}',
    '¾': r'\frac{3}{4}',
    # 根号
    '√': r'\sqrt',
    # 上下标（Unicode数字）
    '⁰': r'^{0}', '¹': r'^{1}', '²': r'^{2}', '³': r'^{3}',
    '⁴': r'^{4}', '⁵': r'^{5}', '⁶': r'^{6}', '⁷': r'^{7}',
    '⁸': r'^{8}', '⁹': r'^{9}',
    '₀': r'_{0}', '₁': r'_{1}', '₂': r'_{2}', '₃': r'_{3}',
    '₄': r'_{4}', '₅': r'_{5}', '₆': r'_{6}', '₇': r'_{7}',
    '₈': r'_{8}', '₉': r'_{9}',
    # 希腊字母（小写）
    'α': r'\alpha ', 'β': r'\beta ', 'γ': r'\gamma ', 'δ': r'\delta ',
    'ε': r'\epsilon ', 'ζ': r'\zeta ', 'η': r'\eta ', 'θ': r'\theta ',
    'ι': r'\iota ', 'κ': r'\kappa ', 'λ': r'\lambda ', 'μ': r'\mu ',
    'ν': r'\nu ', 'ξ': r'\xi ', 'π': r'\pi ', 'ρ': r'\rho ',
    'σ': r'\sigma ', 'τ': r'\tau ', 'υ': r'\upsilon ', 'φ': r'\phi ',
    'χ': r'\chi ', 'ψ': r'\psi ', 'ω': r'\omega ',
    # 希腊字母（大写）
    'Γ': r'\Gamma ', 'Δ': r'\Delta ', 'Θ': r'\Theta ', 'Λ': r'\Lambda ',
    'Ξ': r'\Xi ', 'Π': r'\Pi ', 'Σ': r'\Sigma ', 'Φ': r'\Phi ',
    'Ψ': r'\Psi ', 'Ω': r'\Omega ',
    # 关系运算符
    '≠': r'\neq', '≈': r'\approx', '≡': r'\equiv',
    '≤': r'\leq', '≥': r'\geq',
    '∈': r'\in', '∉': r'\notin',
    '⊂': r'\subset', '⊃': r'\supset',
    '∪': r'\cup', '∩': r'\cap',
    '∀': r'\forall', '∃': r'\exists',
    # 箭头
    '→': r'\rightarrow', '←': r'\leftarrow',
    '⇒': r'\Rightarrow', '⇐': r'\Leftarrow',
    '↔': r'\leftrightarrow',
    # 其他运算符
    '·': r'\cdot', '×': r'\times', '÷': r'\div',
    '±': r'\pm', '∓': r'\mp',
    '⊕': r'\oplus', '⊗': r'\otimes',
}


def fix_wps_encoding(text: str) -> str:
    """Step 1: 修复WPS私有字体乱码"""
    for pua, uni in PUA_TO_UNICODE.items():
        text = text.replace(pua, uni)
    return text


def fix_html_entities(text: str) -> str:
    """Step 0: 还原 HTML/XML 实体（&gt; &lt; &amp; &#x...; 等）。

    最多做两轮以兼容 &amp;lt; 这类双重转义；只影响形如 &name; / &#num; 的实体，
    其余文本原样保留。
    """
    result = text
    for _ in range(2):
        unescaped = html.unescape(result)
        if unescaped == result:
            break
        result = unescaped
    return result


def unicode_to_latex(text: str) -> str:
    """Step 2: Unicode数学符号转LaTeX命令"""
    result = text
    
    # 先替换单字符映射
    for uni, latex in UNICODE_TO_LATEX.items():
        result = result.replace(uni, latex)
    
    # 智能模式匹配
    # 1. 分数: a/b → \frac{a}{b}
    result = re.sub(r'\(([^)]+)\)/\(([^)]+)\)', r'\\frac{\1}{\2}', result)
    result = re.sub(r'(\d+)/(\d+)', r'\\frac{\1}{\2}', result)
    
    # 2. 上下标: x^2 → x^{2}, x_n → x_{n}
    result = re.sub(r'([a-zA-Z])\^(\d+)', r'\1^{\2}', result)
    result = re.sub(r'([a-zA-Z])_(\d+)', r'\1_{\2}', result)
    
    # 3. 极限: lim(x→0) → \lim_{x\to 0}
    result = re.sub(r'lim\s*\(?([^)]*)\)?', r'\\lim_{\1}', result)
    result = re.sub(r'lim\s+([^\s]+)\s*→', r'\\lim_{\1\\to}', result)
    
    # 4. 求和/积分范围: sum(i=1,n) → \sum_{i=1}^{n}
    result = re.sub(r'sum\((\w)=([^,]+),\s*([^)]+)\)', 
                    r'\\sum_{\1=\2}^{\3}', result)
    result = re.sub(r'int\(([^)]+)\)', r'\\int_{\1}', result)
    
    # 5. 矩阵提示（简化版）
    if '[' in result and ']' in result and '\\begin' not in result:
        result = result.replace('[', r'\begin{pmatrix}').replace(']', r'\end{pmatrix}')
    
    return result


def smart_formula_convert(text: str) -> str:
    """完整公式转换流程"""
    # Step 0: 还原 HTML 实体（网页/HTML 化数据源可能残留 &gt; &lt; 等）
    text = fix_html_entities(text)
    # Step 1: 修复WPS乱码
    text = fix_wps_encoding(text)
    # Step 2: Unicode转LaTeX
    text = unicode_to_latex(text)
    # Step 3: 包裹公式标记
    has_formula = any(c in text for c in ['\\', '∫', '∑', '∞', 'α', 'β', 'π'])
    if has_formula:
        text = f"${text}$"
    return text


# 数学片段：连续的非中文、非标点字符（允许内部空格，如 "∫x dx"）
MATH_SEGMENT = re.compile(
    r"[^\u4e00-\u9fff，。、；：？！（）()【】《》“”\"'\u2014\u2026\u00b7]+"
)


def latexize_math_segments(text: str) -> str:
    """把文本中独立的数学片段转 LaTeX 并包 $...$（片段级，避免整句包裹中文）。

    已有 $...$ 公式与【图:xxx】标记原样保护；只有发生实际转换
    （Unicode 符号→LaTeX，或含 + - * / ^ = < > 运算）的片段才包裹。
    """
    if not text:
        return text

    placeholders: list[str] = []

    def hold(m: re.Match) -> str:
        placeholders.append(m.group(0))
        return f"\u0001{len(placeholders) - 1}\u0001"

    text = re.sub(r"\$[^$\n]+\$", hold, text)
    text = re.sub(r"【图:[^】]+】", hold, text)

    def convert(m: re.Match) -> str:
        raw = m.group(0)
        seg = raw.strip()
        if not seg:
            return raw
        lead = raw[: len(raw) - len(raw.lstrip())]
        trail = raw[len(raw.rstrip()):]
        latex = unicode_to_latex(seg)
        if latex != seg:
            # 命令后紧跟字母/数字时补空格（\intx → \int x，\sqrt2 → \sqrt 2）
            latex = re.sub(r"(\\[a-zA-Z]+)(?=[A-Za-z0-9])", r"\1 ", latex)
            return lead + f"${latex}$" + trail
        # 普通英文/数字片段仅在含运算关系时包裹（如 |z|>3）
        if re.search(r"[\dA-Za-z\u03b1-\u03c9][+\-*/^=<>]", seg) or re.search(
            r"[+\-*/^=<>][\dA-Za-z\u03b1-\u03c9]", seg
        ):
            return lead + f"${seg}$" + trail
        return raw

    text = re.sub(MATH_SEGMENT, convert, text)

    def restore(m: re.Match) -> str:
        return placeholders[int(m.group(1))]

    return re.sub(r"\u0001(\d+)\u0001", restore, text)


# 测试用例
if __name__ == '__main__':
    test_cases = [
        "求ò₀^¥ e^(-x²)dx的值",           # WPS乱码
        "lim(x→0) sin(x)/x = ?",            # Unicode箭头
        "f(x) = αx² + βx + γ",              # 希腊字母
        "向量v = (₁, ₂, ₃)",                # 下标
        "计算∑(i=1,n) i²",                  # 求和
    ]
    print("公式转换测试:")
    print("=" * 50)
    for t in test_cases:
        print(f"原始: {t}")
        print(f"转换: {smart_formula_convert(t)}")
        print()
