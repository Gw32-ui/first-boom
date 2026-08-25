# -*- coding: utf-8 -*-
"""文本层质量检测测试：公式型 PDF 碎片文本应被判定为 fragmented。"""
from app.parser.text_quality import assess_text_quality


def test_clean_text_is_not_fragmented():
    text = (
        "一、单项选择题\n"
        "1．下列关于电磁波的说法正确的是（ ）\n"
        "A. 横波\nB. 纵波\nC. 标量波\nD. 机械波\n"
        "答案：A\n"
    )
    r = assess_text_quality(text)
    assert r["fragmented"] is False
    assert r["score"] < 0.30


def test_fragmented_single_char_tokens():
    # 公式型 PDF 文本层：空白分隔单字符占比极高
    text = "2 2 ( ) ( ) ( ) x y z A a x z x e b y e z z c x z e = + + + − + \\rho 2"
    r = assess_text_quality(text)
    assert r["fragmented"] is True
    assert any("单字符token" in s for s in r["reasons"])


def test_broken_latex_command_detected():
    # \rh o、\Delt a 是命令被拆散的产物；合法写法 \sin x 不误报
    text = "电磁能流密度矢量 $s \\rh o$ 且 $\\Delt a 2$ 已知"
    r = assess_text_quality(text)
    assert r["fragmented"] is True
    assert any("半截LaTeX" in s for s in r["reasons"])

    clean = assess_text_quality("$\\sin x + \\cos x$ 与 $\\frac 12$")
    assert clean["fragmented"] is False


def test_empty_text_is_fragmented():
    r = assess_text_quality("   \n  ")
    assert r["fragmented"] is True
    assert r["reasons"] == ["文本层为空"]


def test_threshold_override():
    r = assess_text_quality("", threshold=0.99)
    # 空文本永远视为碎片化（OCR 必需）
    assert r["fragmented"] is True
    r2 = assess_text_quality("$\\rh o$ 唯一一处", threshold=0.99)
    assert r2["fragmented"] is False
