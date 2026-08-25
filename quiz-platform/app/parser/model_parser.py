"""纯文本题目解析器。

支持的文本格式：
  - 每道题独立段落（用空行或题号分隔）
  - 选项以 A./B./C./D. 开头
  - 题型关键词：选择题/多选题/填空题/判断题/简答题/计算题/思考题
  - 答案行：答案：X 或 【答案】X
  - 文末答案区：答案：1.A 2.B（按题号回填到对应题目）
  - 解析行：解析：……
"""
from __future__ import annotations

import re

from app.models.question import Question, QuestionType

TYPE_KEYWORDS: dict[str, QuestionType] = {
    "单选": QuestionType.single_choice,
    "多选": QuestionType.multiple_choice,
    "多项": QuestionType.multiple_choice,
    "不定项": QuestionType.multiple_choice,
    "选择": QuestionType.single_choice,
    "填空": QuestionType.blank,
    "判断": QuestionType.judge,
    "简答": QuestionType.essay,
    "计算": QuestionType.calc,
    "思考": QuestionType.thinking,
}

SECTION_QTYPE_MAP: dict[str, QuestionType] = {
    "单选": QuestionType.single_choice,
    "多选": QuestionType.multiple_choice,
    "多项": QuestionType.multiple_choice,
    "不定项": QuestionType.multiple_choice,
    "选择": QuestionType.single_choice,
    "填空": QuestionType.blank,
    "判断": QuestionType.judge,
    "简答": QuestionType.essay,
    "计算": QuestionType.calc,
    "解答": QuestionType.calc,
    "思考": QuestionType.thinking,
}
# 试卷大题头：一、单选题（本题共8小题……）→ 作为后续题目的题型上下文
SECTION_HEADER = re.compile(
    r"^[一二三四五六七八九十]+、\s*[（(]?\s*(?P<qtype>单选|选择|多选|填空|判断|简答|计算|解答|思考)题?"
)

QUESTION_START = re.compile(
    r"^\s*(?:第\s*\d+\s*题|问\s*\d{0,3}\s*[:：]|【\s*\d{1,3}\s*[-－—]\s*\d{1,3}\s*】|(?:\d{1,3})\s*[\.．、)）：:])"
)
# 汉字数字章节头：二、分析作图题 / 三、（10分） → 切块边界
SECTION_NUM_HEAD = re.compile(r"^\s*[一二三四五六七八九十]+\s*[、.．]\s*\S")
# 行内答案：题干……答1：答案（问答题 docx 常见格式）
INLINE_ANSWER = re.compile(r"答\s*\d{0,3}\s*[：:]")
# 行内出现的 【x-y】 题号：OCR/PDF 文本层常把多道题挤在同一行，
# 解析前先拆行，避免“多道题合并成一道题”的误判
INLINE_QUESTION_MARKER = re.compile(r"(【\s*\d{1,3}\s*[-－—]\s*\d{1,3}\s*】)")
# 括号编号题号（（1）（2）…），仅在块首时视为新题
SUB_QUESTION = re.compile(r"^\s*[（(]\s*\d{1,3}\s*[）)]")
OPTION_LINE = re.compile(r"^\s*[（(]?\s*([A-Ha-h])\s*(?:[\.．、)）]\s*|\s+)(.*)$")
# 单行多选项里的选项标记：字母 + 点/顿/右括号（如 “A. 质量 B. 体积”）
OPTION_MARKER = re.compile(r"(?<![A-Za-z0-9])([A-Ha-h])\s*[\.．、)）]")
ANSWER_LINE = re.compile(
    r"^\s*(?:\[?【?)?\s*(?:答案|参考答案)\s*[】\]）)】]?\s*[:：]?\s*(.*)$"
)
# 文末答案区：整行由“题号+答案”组成，如 “答案：1.A 2.B” 或 “答案：12.-1 13.18”
# 答案值支持：字母（A/AB）、整数/小数/负数（-1、18、0.5）、分数（1/2）、根式（√2）
_ANSWER_KEY_VALUE = r"[A-Ha-h]{1,8}|\d+/\d+|√\d+|[-+]?\d+(?:\.\d+)?"
ANSWER_KEY_ENTRY = re.compile(
    rf"(\d{{1,3}})\s*[.．、]?\s*({_ANSWER_KEY_VALUE})"
)
ANSWER_KEY_LINE = re.compile(
    r"^\s*(?:答案|参考答案)?\s*[:：]?\s*"
    rf"(?:\d{{1,3}}\s*[.．、]?\s*(?:{_ANSWER_KEY_VALUE})\s*[,，;；、]?\s*)+$"
)
EXPLAIN_LINE = re.compile(r"^\s*解析\s*[:：]\s*(.*)$")
TYPE_LINE = re.compile(r"^\s*(?:题型|类型)\s*[:：]\s*(.+)$")
TYPE_MARKER = re.compile(r"^【\s*([^】]{0,16}?题?)\s*】")
BLANK_MARK = re.compile(r"_+|＿+|（\s*）|\(\s*\)")
LATEX_INLINE = re.compile(r"\$[^$\n]+\$")
LATEX_PAREN = re.compile(r"\\\(.*?\\\)")
SEPARATOR_LINE = re.compile(r"^[-=—]{5,}$")
PAGE_HEADER = re.compile(r"^\s*第\s*\d+\s*页\s*/\s*共\s*\d+\s*页\s*$")
NOTE_ENTRY = re.compile(r"^(\d{1,3})[、.．]\s*(.{1,60})$")
SECTION_HEAD = re.compile(r"^(第[一二三四五六七八九十]+节|导论)[、\s]*(.*)$")
CHAPTER_HEAD = re.compile(r"^第[一二三四五六七八九十]+章")
# 判断题题干模式：仅在“没有 2 个及以上选项”时生效，
# 避免把 “下列说法正确的是（ ）A..B..” 这类单选误判为判断
JUDGE_STEM_PATTERNS = (
    r"^判断.*?(是否|对错|正确|错误)",
    r"^判别.*?(是否|正确|错误)",
    r"(是否|对不对).{0,12}(正确|对)",
    r"下列说法(正确|对)(的)?是",
    r"下列(说法|描述|命题)(正确|对|错误)(的)?是",
)
# 计算题动词：出现即倾向计算（普通词如“要求”不触发）
CALC_VERBS = (
    "计算", "试求", "求解", "求值", "算出", "推导", "判别",
    "画出", "证明", "化简", "展开", "积分", "微分", "解得", "解出",
)
# 简答题开头词
ESSAY_LEADERS = (
    "简述", "论述", "说明", "什么是", "为什么", "名词解释",
    "谈谈", "分析", "比较", "讨论", "评价", "解释", "阐述",
    "总结", "列举", "举例说明", "描述",
)
JUDGE_OPTION_LINE = re.compile(r"^(对|错|正确|错误)([\s、，,]+(对|错|正确|错误))*$")
# 括号编号题号（（1）（2）…），仅在块首时视为新题
SUB_QUESTION = re.compile(r"^\s*[（(]\s*\d{1,3}\s*[）)]")


PENDING_PLACEHOLDER = re.compile(r"<(?:Formula|ImgRef)[^>]*>", re.IGNORECASE)
# 半截 LaTeX 命令后跟空格再接字母（如 \rh o、\Delt a、\inft y）→ 文本层被公式排版拆散
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
KNOWN_LATEX_LOWER = {k.lower() for k in KNOWN_LATEX_COMMANDS}

# 卷头/试卷头噪声关键词：出现在首个真实题目前的前言块视为卷头丢弃
PREAMBLE_NOISE_KEYS = (
    "试卷", "满分", "考试时间", "姓名", "学号", "班级", "考场", "座位",
    "准考证", "监考", "注意事项", "答题卡", "密封线", "得分", "评卷",
    "命题", "审题", "复核", "学年", "学期", "专业", "院系", "年级",
    "科目", "课程", "题号", "座位号", "考生号",
)

# 残缺启发式（公式被 docx OMML 吞掉后的常见形态）
EMPTY_PAREN = re.compile(r"[（(]\s*[）)]")
LONE_MATH_SYMBOL = re.compile(
    r"[\u222b\u2211\u221a\u2202\u221e\u2190-\u21ff"
    r"\u03b1-\u03c9\u2208\u2209\u2260\u2264\u2265\u00d7\u00f7\u00b1]"
)
GAP_AFTER_VERB = re.compile(
    r"(?:为|是|等于|均为|相距|间距|大于|小于|宽度|长度|半径|质量)"
    r"\s*[，。、；]"
)


def mark_pending_review(q: Question) -> None:
    """残缺检测：占位符标签或启发式规则命中 -> pending_review。

    按“非结构化文本槽”策略：不尝试脑补残缺公式，只标记待人工复核后继续处理；
    占位符原样保留在字段中，后续由复核前端人工补全后确认对齐。
    """
    if q is None:
        return
    haystack = " ".join(
        filter(
            None,
            [
                q.question or "",
                q.formula or "",
                q.correct_answer or "",
                q.explanation or "",
                *(q.options or []),
            ],
        )
    )
    if PENDING_PLACEHOLDER.search(haystack):
        q.pending_review = True
        return

    # 半截 LaTeX 命令（\rh o 等）→ 文本层碎片化产物，标记待人工复核
    for m in BROKEN_LATEX_CMD.finditer(haystack):
        if m.group(1).lower() not in KNOWN_LATEX_LOWER:
            q.pending_review = True
            return

    # 启发式评分（≥2 条命中才标记，降低误报）
    stem = q.question or ""
    plain = LATEX_INLINE.sub("", stem)  # 剔除已包裹公式后再看孤立符号
    score = 0
    if stem.count("$") % 2 == 1:
        score += 1  # 公式未闭合
    if EMPTY_PAREN.search(stem) and (
        LONE_MATH_SYMBOL.search(plain) or re.search(r"[A-Za-z0-9]", plain)
    ):
        score += 1  # 空括号且周围有公式/字母（公式被吞）
    if LONE_MATH_SYMBOL.search(plain):
        score += 1  # 孤立数学符号未被 $ 包裹
    gap_hits = len(GAP_AFTER_VERB.findall(stem))
    if gap_hits:
        score += min(gap_hits, 2)  # 中文动词后空白+标点（变量被吞，多处累加）
    if len(stem) < 15 and re.search(r"[=∫∑√（(]", stem):
        score += 1  # 题干极短且含公式特征
    if not (q.correct_answer or "").strip() and LONE_MATH_SYMBOL.search(plain):
        score += 1  # 答案缺失 + 题干含公式特征
    if score >= 2:
        q.pending_review = True


def _has_real_blank_mark(stem: str) -> bool:
    """检测真实填空线：先剔除 $...$ 与 \\(...\\) 包裹的 LaTeX，
    避免下标下划线（如 $x_i$）被误认为填空。"""
    cleaned = LATEX_INLINE.sub("", stem)
    cleaned = LATEX_PAREN.sub("", cleaned)
    return bool(BLANK_MARK.search(cleaned))


def _detect_qtype(
    type_text: str,
    options: list[str],
    stem: str,
    default_qtype: QuestionType | None = None,
) -> QuestionType:
    if type_text:
        for key, qt in TYPE_KEYWORDS.items():
            if key in type_text:
                return qt
    m = TYPE_MARKER.search(stem)
    if m:
        for key, qt in TYPE_KEYWORDS.items():
            if key in m.group(1):
                return qt
    if options and len(options) >= 2:
        # 有选项时按题型词优先，其次视为单选；板块 default 只在无选项时生效
        if default_qtype == QuestionType.multiple_choice:
            return QuestionType.multiple_choice
        return QuestionType.single_choice
    if default_qtype is not None:
        return default_qtype
    for pat in JUDGE_STEM_PATTERNS:
        if re.search(pat, stem):
            return QuestionType.judge
    if _has_real_blank_mark(stem) or stem.rstrip().endswith("="):
        return QuestionType.blank
    if (
        stem.startswith("求")
        or any(v in stem for v in CALC_VERBS)
        or re.search(r"[，。；]求", stem)
    ):
        return QuestionType.calc
    if any(stem.startswith(k) for k in ESSAY_LEADERS):
        return QuestionType.essay
    return QuestionType.blank


def _strip_wrapper(a: str) -> str:
    """整段答案被一对括号包裹时（如 （北京））去掉外壳；数学区间表达式不受影响。"""
    if len(a) >= 2:
        for left, right in (("（", "）"), ("(", ")")):
            if a.startswith(left) and a.endswith(right):
                return a[1:-1]
    return a


def _clean_answer(raw: str, qtype: QuestionType) -> str:
    a = raw.strip()
    if qtype == QuestionType.multiple_choice:
        # 数字型多选（1,2,3）也保留，避免清洗成空
        a = re.sub(r"[^A-Za-z0-9]", "", a).upper()
        return "".join(sorted(set(a)))
    if qtype == QuestionType.single_choice:
        a = a.strip("（）()[]【】")
        m = re.match(r"^[A-Za-z]", a)
        return m.group(0).upper() if m else a
    if qtype == QuestionType.judge:
        a = a.strip("（）()[]【】")
        a = a.split()[0] if " " in a else a
        a = re.sub(
            r"^(对|正确|错|错误).*",
            lambda m: "对" if m.group(1) in ("对", "正确") else "错",
            a,
        )
        if a in ("对", "正确", "T", "TRUE", "√", "是"):
            return "对"
        if a in ("错", "错误", "F", "FALSE", "×", "X", "否"):
            return "错"
        return a
    # 填空/简答/计算/思考：只去掉“整段被一对括号包裹”的外壳
    return _strip_wrapper(a)


def _split_multi_option_line(line: str) -> list[str] | None:
    """把 “A. 甲 B. 乙 C. 丙 D. 丁” 式单行多选项拆成列表；不是多选项行返回 None。"""
    matches = list(OPTION_MARKER.finditer(line))
    if len(matches) < 2:
        return None
    first = matches[0]
    if line[: first.start()].strip("（( \t"):
        return None
    parts: list[str] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(line)
        parts.append(line[start:end].strip().rstrip("（(").strip())
    if not any(parts):
        return None
    return parts


def _looks_like_preamble(lines: list[str]) -> bool:
    """判断一个行块是否像试卷卷头/前言（而不是题目本身）。

    命中卷头噪声关键词（试卷/满分/注意事项/答题卡…）或年份开头的行视为卷头；
    无噪声词的普通文本（如未编号的题干、笔记标题）不丢弃。
    """
    text = " ".join(lines)
    if any(k in text for k in PREAMBLE_NOISE_KEYS):
        return True
    return bool(re.match(r"^\s*\d{4}\s*年", text))


def _split_blocks(
    lines: list[str],
) -> list[tuple[list[str], QuestionType | None, str]]:
    """把文本行切分为题目块，并记录每块所属的板块题型上下文与知识点。

    新块只由「题号开头」「空行」「大题头（一、单选题等）」触发；
    答案/解析/题型行都归入当前块，避免被拆散。
    PDF 文本层内部偶发的空行（选项/答案延续）不会切块。
    """
    blocks: list[tuple[list[str], QuestionType | None, str]] = []
    cur: list[str] = []
    cur_section: QuestionType | None = None
    cur_topic: str = ""
    seen_marker = False  # 是否已遇到第一个真实题目/板块头
    i = 0

    def flush() -> None:
        """把当前块收尾：首个真实标记之前的前言块若像卷头则直接丢弃。"""
        nonlocal cur
        if not cur:
            return
        if not seen_marker and _looks_like_preamble(cur):
            cur = []
            return
        blocks.append((cur, cur_section, cur_topic))
        cur = []

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            j = i
            while j < len(lines) and not lines[j].strip():
                j += 1
            next_line = lines[j].strip() if j < len(lines) else ""
            # 空行后仍是选项/答案 → 同一题的延续，不切块
            option_continue = OPTION_LINE.match(next_line) or (
                ANSWER_LINE.match(next_line)
                and not any(ANSWER_LINE.match(x.strip()) for x in cur)
            )
            if cur and option_continue:
                i = j
                continue
            flush()
            i = j
            continue
        km = re.match(r"^\s*知识点\s*[:：]\s*(.*)$", line)
        if km:
            flush()
            cur_section = None
            cur_topic = km.group(1).strip()
            seen_marker = True
            i += 1
            continue
        sm = SECTION_HEADER.match(line)
        if sm:
            flush()
            cur_section = SECTION_QTYPE_MAP.get(sm.group("qtype"))
            seen_marker = True
            i += 1
            continue
        if SECTION_NUM_HEAD.match(line):
            flush()
            cur_section = None
            seen_marker = True
            i += 1
            continue
        if SEPARATOR_LINE.match(line):
            flush()
            i += 1
            continue
        if not cur and SUB_QUESTION.match(line):
            cur = [line]
            seen_marker = True
            i += 1
            continue
        if QUESTION_START.match(line):
            flush()
            cur = [line]
            seen_marker = True
            i += 1
            continue
        cur.append(line)
        i += 1
    flush()
    return blocks


def _parse_block(
    block: list[str],
    subject: str,
    course: str,
    source_file: str,
    default_qtype: QuestionType | None = None,
    topic: str = "",
) -> Question | None:
    options: list[str] = []
    stem_lines: list[str] = []
    answer = ""
    explanation = ""
    type_text = ""
    judge_flag = False
    in_explanation = False
    in_answer = False
    marker_question = False

    for raw in block:
        line = raw.strip()
        if not line:
            continue
        if _is_answer_key_line(line):
            # 文末答案区行（如 “答案：1.A 2.B”）不当作普通答案行，
            # 交给 parse_text 末尾按题号回填
            continue
        ans_m = re.match(r"^【\s*答案\s*】\s*(.*)$", line)
        if ans_m:
            answer = ans_m.group(1).strip()
            in_explanation = True
            continue
        exp_m = re.match(r"^【\s*(?:解析|详解)\s*】\s*(.*)$", line)
        if exp_m:
            explanation = (
                (explanation + "\n" if explanation else "") + exp_m.group(1).strip()
            )
            in_explanation = True
            continue
        if in_explanation:
            # 【答案】/【解析】之后的解析正文归入 explanation，不进题干
            explanation = (explanation + "\n" if explanation else "") + line
            continue
        ia = INLINE_ANSWER.search(line)
        if ia and not answer:
            # 行内答案：题干……答1：答案 → 拆成题干与答案，后续行归入答案
            stem_part = line[: ia.start()].strip()
            answer = line[ia.end():].strip()
            in_answer = True
            if stem_part:
                stripped = QUESTION_START.sub("", stem_part).strip()
                tm2 = TYPE_MARKER.match(stripped)
                if tm2 and any(k in tm2.group(1) for k in TYPE_KEYWORDS):
                    type_text = type_text or tm2.group(1)
                    stripped = stripped[tm2.end():].strip()
                if stripped:
                    stem_lines.append(stripped)
            continue
        if in_answer:
            answer = (answer + "\n" if answer else "") + line
            continue
        multi = _split_multi_option_line(line)
        if multi is not None:
            for part in multi:
                if len(options) < 8:
                    options.append(part)
            continue
        tm = TYPE_LINE.match(line)
        if tm:
            type_text = tm.group(1)
            continue
        am = ANSWER_LINE.match(line)
        if am:
            answer = am.group(1)
            continue
        em = EXPLAIN_LINE.match(line)
        if em:
            explanation = em.group(1)
            continue
        om = OPTION_LINE.match(line)
        if om and len(options) < 8:
            options.append(line)
            continue
        if JUDGE_OPTION_LINE.match(line):
            judge_flag = True
            continue
        # 【x-y】结构题号视为显式题目（无选项/答案也保留）
        if QUESTION_START.match(line) and re.match(r"^\s*【\s*\d{1,3}\s*[-－—]\s*\d{1,3}\s*】", line):
            marker_question = True
        # 去掉题号前缀
        stripped = QUESTION_START.sub("", line).strip()
        # 识别并去掉行首题型标记，如 【判断题】
        tm2 = TYPE_MARKER.match(stripped)
        if tm2 and any(k in tm2.group(1) for k in TYPE_KEYWORDS):
            type_text = type_text or tm2.group(1)
            stripped = stripped[tm2.end():].strip()
        if stripped:
            stem_lines.append(stripped)

    stem = " ".join(stem_lines).strip()
    if not stem and options:
        stem = " ".join(options)
    if not stem:
        return None
    # 孤立选项碎片（如 PDF 劈题残留的“D 民族主义”）直接丢弃
    if not stem_lines and len(options) <= 1:
        return None
    if not stem_lines and not options and re.search(r"[A-Za-z]", answer):
        return None

    # 板块上下文（如“一、填空题”）参与题型判定；有选项时仍按选项判单选/多选
    qtype = _detect_qtype(type_text, options, stem, default_qtype)
    # 多选识别：选项题且答案含 ≥2 个字母（如 答案：ABCDE）
    if qtype == QuestionType.single_choice and len(re.findall(r"[A-Za-z]", answer)) >= 2:
        qtype = QuestionType.multiple_choice
    options = [
        re.sub(r"^[（(]?[A-Ha-h]\s*(?:[\.．、)）]\s*|\s+)", "", o).strip()
        for o in options
    ]
    answer = _clean_answer(answer, qtype)
    # 判断题识别：答案为 对/错，或出现“对 对/错 错”选项行
    if answer in ("对", "错") or judge_flag:
        qtype = QuestionType.judge
    # 丢弃纯“对/错”选项碎片块（PDF 渲染重复导致）
    if len(stem) < 3 or JUDGE_OPTION_LINE.fullmatch(stem):
        return None

    # 只保留“显式题目”：有选项 / 有答案 / 有填空线 / 题型明确 / 板块上下文明确；
    # 纯笔记条目交给 parse_notes_* 处理，避免生成无意义空题
    # 填空题板块下即使碎片丢了填空线（如下划线），只要题干有题目特征就保留为 blank
    section_blank_stem = (
        default_qtype == QuestionType.blank
        and (
            LONE_MATH_SYMBOL.search(stem)
            or re.search(r"[=＝求设若当已知满足使得则试]", stem)
        )
    )
    explicit = (
        marker_question
        or len(options) >= 2
        or bool(answer)
        or qtype in (
            QuestionType.single_choice,
            QuestionType.multiple_choice,
            QuestionType.judge,
            QuestionType.essay,
            QuestionType.calc,
        )
        or (_has_real_blank_mark(stem) and len(stem) <= 120)
        or section_blank_stem
    )
    if not explicit:
        return None

    return Question(
        subject=subject,
        course=course,
        topic=topic,
        qtype=qtype,
        question=stem,
        options=options,
        correct_answer=answer,
        explanation=explanation,
        source_file=source_file,
    )


def _block_qnum(block: list[str]) -> int | None:
    """取题目块的行首题号（“1.” 或 “第5题”）。"""
    for raw in block:
        m = QUESTION_START.match(raw.strip())
        if m:
            digits = re.search(r"\d+", m.group(0))
            return int(digits.group(0)) if digits else None
    return None


def _extract_answer_key(lines: list[str]) -> dict[int, str]:
    """扫描文末答案区：把“1.A 2.B”这类行解析为 {题号: 答案字母}。"""
    result: dict[int, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or not _is_answer_key_line(line):
            continue
        for m in ANSWER_KEY_ENTRY.finditer(line):
            result[int(m.group(1))] = m.group(2).upper()
    return result


def _is_answer_key_line(line: str) -> bool:
    """判断是否为文末答案区行。

    规则：整行匹配“题号+答案”格式，且：
      - 行首带“答案/参考答案”前缀（可含数字答案，如 “答案：12.-1 13.18”）；或
      - 无前缀时至少 2 个条目且至少一个是字母答案（如 “1.A 2.B”），
    避免把 PDF 公式残片（如 “3 5”“1 1”）误判成答案区。
    """
    if not ANSWER_KEY_LINE.match(line):
        return False
    has_prefix = bool(re.match(r"^\s*(?:答案|参考答案)\s*[:：]?", line))
    entries = list(ANSWER_KEY_ENTRY.finditer(line))
    if has_prefix:
        return len(entries) >= 1
    if len(entries) >= 2:
        return any(re.match(r"[A-Ha-h]{1,8}$", e.group(2)) for e in entries)
    if len(entries) == 1:
        return bool(re.match(r"[A-Ha-h]{1,8}$", entries[0].group(2)))
    return False


def parse_text(
    text: str,
    subject: str = "",
    course: str = "",
    source_file: str = "",
    return_qnums: bool = False,
) -> list[Question]:
    """解析纯文本 → 题目列表。"""
    # 行内 【x-y】 题号拆行（格式为题目编号，拆后每道题独立成块）
    text = INLINE_QUESTION_MARKER.sub(r"\n\1", text)
    lines = text.replace("\r\n", "\n").split("\n")
    # 清理页眉页脚：第X页/共X页
    lines = [ln for ln in lines if not PAGE_HEADER.match(ln)]
    blocks = _split_blocks(lines)
    questions: list[Question] = []
    qnums: list[int | None] = []
    for block, section_qtype, topic in blocks:
        q = _parse_block(
            block, subject, course, source_file, section_qtype, topic=topic
        )
        if q and q.question:
            questions.append(q)
            qnums.append(_block_qnum(block))

    # 文末答案区回填：只补没有答案的题，按题号匹配
    answer_map = _extract_answer_key(lines)
    if answer_map:
        for q, num in zip(questions, qnums):
            if num is None or q.correct_answer or num not in answer_map:
                continue
            q.correct_answer = _clean_answer(answer_map[num], q.qtype)
            # 回填后如果答案是多个字母，修正为多选题
            if (
                q.qtype == QuestionType.single_choice
                and len(re.findall(r"[A-Za-z]", q.correct_answer)) >= 2
            ):
                q.qtype = QuestionType.multiple_choice
    for q in questions:
        mark_pending_review(q)
    if return_qnums:
        return questions, qnums
    return questions


# ---------------------------------------------------------------------------
# 笔记型内容 → 题目（归纳题库）
# ---------------------------------------------------------------------------


def _strip_marker(title: str) -> tuple[str, str]:
    """从条目标题中提取题型标记，返回 (干净标题, 标记文本)。"""
    marker = ""
    m = re.search(r"【([^】]{1,12})】", title)
    if m:
        marker = m.group(1)
        title = re.sub(r"【[^】]{1,12}】", "", title)
    m = re.search(r"[（(]([^）)]{0,12})[）)]", title)
    if m and any(
        k in m.group(1) for k in ("单选", "名词解释", "简答", "论述")
    ):
        marker = marker or m.group(1)
        title = re.sub(r"[（(][^）)]{0,12}[）)]", "", title)
    return title.strip(), marker


def _essay_question(title: str) -> str:
    t = title.strip()
    if re.match(r"^(简述|论述|如何|为什么|什么是|名词解释)", t):
        return t
    return f"简述{t}。"


def parse_notes_points(
    text: str,
    subject: str = "",
    course: str = "",
    source_file: str = "",
) -> list[Question]:
    """编号知识点笔记 → 简答/名词解释/判断。

    适配格式（如 4_毛概(1).docx）：
      X、知识点标题【名词解释/简答/论述/（单选）】
         内容……
      单选
      考点事实行……
    """
    questions: list[Question] = []
    cur: dict | None = None
    facts: list[str] = []
    in_facts = False

    def flush() -> None:
        nonlocal cur
        if cur is None:
            return
        title, marker = _strip_marker(cur["title"])
        body = "\n".join(cur["body"]).strip()
        if not title:
            cur = None
            return
        if marker and "名词解释" in marker:
            q = Question(
                subject=subject, course=course, qtype=QuestionType.thinking,
                question=f"名词解释：{title}", correct_answer=body,
                explanation=source_file, source_file=source_file,
            )
        elif marker and "单选" in marker:
            q = Question(
                subject=subject, course=course, qtype=QuestionType.judge,
                question=title, correct_answer="对",
                explanation=body or source_file, source_file=source_file,
            )
        else:
            q = Question(
                subject=subject, course=course, qtype=QuestionType.essay,
                question=_essay_question(title), correct_answer=body,
                explanation=source_file, source_file=source_file,
            )
        if q.question:
            questions.append(q)
        cur = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line or SEPARATOR_LINE.match(line):
            continue
        if re.fullmatch(r"单选(?:题)?[：:]?", line):
            flush()
            in_facts = True
            continue
        m = NOTE_ENTRY.match(line)
        if m:
            flush()
            in_facts = False
            cur = {"num": m.group(1), "title": m.group(2), "body": []}
            continue
        if cur is not None:
            cur["body"].append(line)
        elif in_facts:
            # 单选区考点事实行
            facts.append(line)
    flush()

    for fact in facts:
        if len(fact) > 120 or not fact:
            continue
        questions.append(
            Question(
                subject=subject, course=course, qtype=QuestionType.judge,
                question=fact, correct_answer="对",
                explanation=source_file, source_file=source_file,
            )
        )
    for q in questions:
        mark_pending_review(q)
    return questions


def parse_notes_sections(
    text: str,
    subject: str = "",
    course: str = "",
    source_file: str = "",
) -> list[Question]:
    """章节式复习笔记 → 每节一道简答题。

    适配格式（如 毛概期末复习笔记.pdf）：
      第X章 ……
      第X节、小节标题
         内容……
    """
    questions: list[Question] = []
    cur: dict | None = None

    def flush() -> None:
        nonlocal cur
        if cur is None:
            return
        title = cur["title"]
        m = SECTION_HEAD.match(title)
        if m:
            title = m.group(2).strip()
        if not title:
            cur = None
            return
        body = "\n".join(cur["body"]).strip()
        if not body:
            cur = None
            return
        questions.append(
            Question(
                subject=subject, course=course, qtype=QuestionType.essay,
                question=_essay_question(title), correct_answer=body,
                explanation=source_file, source_file=source_file,
            )
        )
        cur = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line or SEPARATOR_LINE.match(line):
            continue
        if CHAPTER_HEAD.match(line):
            flush()
            continue
        if SECTION_HEAD.match(line):
            flush()
            cur = {"title": line, "body": []}
            continue
        if cur is not None:
            cur["body"].append(line)
    flush()
    for q in questions:
        mark_pending_review(q)
    return questions
