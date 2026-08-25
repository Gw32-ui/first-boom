"""图片识别预处理：检测纯黑/废图，深色背景图反相归一化。

扫描件/截图里常见两类问题：
  1. 纯黑图片（如 0 亮度、单色）——内容本身已丢失，无法反相恢复，
     识别流程应跳过，避免把黑图附到题目上或浪费云端视觉调用；
  2. 深色背景但有内容的图片（如暗色模式截图、黑底公式）——
     反相 + 自动对比度后转为白底黑字，视觉模型才能正常识别。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps, ImageStat

# 纯黑/废图判定：亮度均值极低且几乎无变化（单色黑）
SOLID_BLACK_MEAN = 5.0
SOLID_BLACK_STD = 8.0
# 低于该亮度视为深色背景，需要反相归一化
DARK_MEAN = 128.0


def brightness_stats(img_path: str | Path) -> tuple[float, float]:
    """返回 (灰度均值, 标准差)。"""
    with Image.open(Path(img_path)) as im:
        gray = im.convert("L")
        stat = ImageStat.Stat(gray)
        return float(stat.mean[0]), float(stat.stddev[0])


def is_solid_black(
    img_path: str | Path,
    mean_threshold: float = SOLID_BLACK_MEAN,
    std_threshold: float = SOLID_BLACK_STD,
) -> bool:
    """是否为纯黑/近似纯黑的废图（内容不可恢复）。"""
    mean, std = brightness_stats(img_path)
    return mean < mean_threshold and std < std_threshold


def normalize_dark_image(
    src: str | Path,
    dst: str | Path,
    dark_mean: float = DARK_MEAN,
) -> str:
    """把深色背景图归一化为白底黑字，返回状态：
    - 'black'：纯黑废图，无法恢复（不写 dst）
    - 'normalized'：已反相 + 自动对比度，写入 dst
    - 'kept'：本身为浅色/正常图，无需处理
    """
    src_p = Path(src)
    mean, std = brightness_stats(src_p)
    if mean < SOLID_BLACK_MEAN and std < SOLID_BLACK_STD:
        return "black"
    if mean >= dark_mean:
        return "kept"
    with Image.open(src_p) as im:
        gray = im.convert("L")
        inverted = ImageOps.invert(gray)
        normalized = ImageOps.autocontrast(inverted)
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        normalized.save(dst)
    return "normalized"


def prepare_ocr_images(
    image_paths: list[str],
    out_dir: str | Path,
) -> dict:
    """对一批待识别图片做预处理，返回可直接附到题目的可用图片列表。

    返回 dict:
      - usable: 可直接用于识别的图片路径（浅色原图 / 反相后的新图）
      - skipped_black: 被跳过的纯黑废图路径
      - normalized: {原图路径: 反相后新图路径}
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    usable: list[str] = []
    skipped_black: list[str] = []
    normalized: dict[str, str] = {}
    for i, p in enumerate(image_paths):
        src = Path(p)
        if not src.is_file():
            skipped_black.append(p)
            continue
        status = normalize_dark_image(src, out / f"{src.stem}_norm.png")
        if status == "black":
            skipped_black.append(p)
        elif status == "normalized":
            dst = str(out / f"{src.stem}_norm.png")
            usable.append(dst)
            normalized[p] = dst
        else:
            usable.append(p)
    return {
        "usable": usable,
        "skipped_black": skipped_black,
        "normalized": normalized,
    }
