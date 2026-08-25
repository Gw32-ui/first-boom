"""图片理解：两步择优（启发式 + 可选视觉模型）。

第1步 启发式（零依赖）：按尺寸与上下文关键词粗分类。
第2步 视觉模型（可选，默认智谱 GLM-4.6V-Flash，任意 OpenAI 兼容接口均可）：
      分类 + 公式 LaTeX + 一句中文描述。
择优：视觉模型启用且调用成功时以视觉结果为准（准确率更高）；
      未启用或失败时退回启发式结果，保证流程不中断。
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from app.llm.zhipu_client import chat_completion
from app.vision.image_utils import is_solid_black

VALID_KINDS = (
    "diagram",
    "formula",
    "symbol",
    "data_table",
    "decorative",
    "other",
)


def classify_image_heuristic(
    img_path: str | Path,
    context: str = "",
) -> dict:
    """第1步：基于尺寸和上下文关键词的粗分类（零依赖）。"""
    from PIL import Image

    with Image.open(Path(img_path)) as im:
        w, h = im.size
    ratio = w / h if h else 0
    if context and any(k in context for k in ("如图", "图像")):
        # 上下文出现“如图/图像”时优先判定为示意图
        kind = "diagram"
    elif h <= 40 and w <= 80:
        kind = "symbol"
    elif h <= 120 and ratio >= 3:
        kind = "formula"
    else:
        kind = "diagram"
    return {
        "kind": kind,
        "width": w,
        "height": h,
        "ratio": round(ratio, 2),
        "description": "",
        "latex": "",
        "method": "heuristic",
    }


def classify_image_vision(
    img_path: str | Path,
    vision_cfg: dict,
    context: str = "",
) -> dict:
    """第2步：调用视觉模型分类（OpenAI 兼容，默认智谱 GLM-4.6V-Flash）。"""
    base_url = (vision_cfg.get("base_url") or "").rstrip("/")
    api_key = vision_cfg.get("api_key") or ""
    model = vision_cfg.get("model") or ""
    timeout = int(vision_cfg.get("timeout") or 60)
    if not base_url or not model:
        raise RuntimeError("视觉模型配置不完整（base_url/model）")

    p = Path(img_path)
    suffix = p.suffix.lower() or ".png"
    mime = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
    }.get(suffix.lstrip("."), "image/png")
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")

    prompt = (
        "你是一名试卷图片分析器。请判断这张图片属于哪一类："
        "diagram(题干示意图/装置图)、formula(数学公式)、symbol(单个符号/角标)、"
        "data_table(数据表格)、decorative(装饰/水印)。"
        '只输出一行 JSON：{"kind":"...","latex":"若为公式则给 LaTeX，否则空","description":"一句话中文描述"}'
    )
    if context:
        prompt += f"\n图片所在题目上下文：{context[:100]}"
    prompt += (
        "\n只输出一个 JSON 对象，不要输出 Markdown 代码块或其他任何文字。"
    )

    content = chat_completion(
        [
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
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=0,
        timeout=timeout,
        retries=3,
    )
    return _parse_vision_result(content)


def _parse_vision_result(content: str) -> dict:
    """从模型输出里提取 JSON（容忍前后缀文本）。"""
    start = content.find("{")
    end = content.rfind("}") + 1
    if start < 0 or end <= start:
        raise RuntimeError(f"视觉模型未返回 JSON: {content[:100]}")
    try:
        obj = json.loads(content[start:end])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"视觉模型 JSON 解析失败: {content[:100]}") from exc
    kind = str(obj.get("kind") or "other")
    if kind not in VALID_KINDS:
        kind = "other"
    return {
        "kind": kind,
        "latex": str(obj.get("latex") or ""),
        "description": str(obj.get("description") or ""),
        "method": "vision",
    }


def classify_image(
    img_path: str | Path,
    cfg: dict,
    context: str = "",
) -> dict:
    """两步择优：视觉模型优先，失败/未启用退回启发式。"""
    heuristic = classify_image_heuristic(img_path, context)
    vision_cfg = (cfg or {}).get("vision") or {}
    if not vision_cfg.get("enabled"):
        return heuristic
    try:
        result = classify_image_vision(img_path, vision_cfg, context)
        result["width"] = heuristic["width"]
        result["height"] = heuristic["height"]
        return result
    except Exception as exc:  # noqa: BLE001 - 视觉不可用时降级，流程不中断
        heuristic["vision_error"] = str(exc)
        return heuristic


def classify_images_in_dir(
    images_dir: str | Path,
    cfg: dict,
    context_map: dict[str, str] | None = None,
    cache_file: str | Path | None = None,
    only: list[str] | None = None,
) -> dict:
    """对目录中的图片做两步分类并写缓存，返回 {文件名: 分类结果}。

    - context_map: {文件名: 该图所在题干片段}（用于启发式上下文提示）
    - cache_file: 已分类结果缓存（跳过重复分类，避免每次导入都调视觉模型）
    - only: 只分类这些文件名（本次导入新提取的图片）；为 None 时扫描整个目录
    """
    out_dir = Path(images_dir)
    cache: dict = {}
    if cache_file and Path(cache_file).exists():
        try:
            cache = json.loads(Path(cache_file).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - 缓存损坏时重建
            cache = {}
    results: dict = {}
    targets = (
        [Path(out_dir) / name for name in only]
        if only is not None
        else sorted(out_dir.glob("*"))
    )
    for img in targets:
        if not img.is_file():
            continue
        if img.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            continue
        if img.name in cache:
            results[img.name] = cache[img.name]
            continue
        # 纯黑废图跳过：内容不可恢复，不浪费视觉调用，也不产出幻觉描述
        if is_solid_black(img):
            r = {
                "kind": "decorative",
                "method": "heuristic",
                "description": "纯黑图片（内容不可恢复，已跳过）",
                "error": "solid black image",
            }
            cache[img.name] = r
            results[img.name] = r
            continue
        ctx = (context_map or {}).get(img.name, "")
        try:
            r = classify_image(img, cfg, context=ctx)
        except Exception as exc:  # noqa: BLE001 - 单图失败不中断
            r = {"kind": "other", "method": "heuristic", "error": str(exc)}
        cache[img.name] = r
        results[img.name] = r
    if cache_file:
        Path(cache_file).write_text(
            json.dumps(cache, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    return results
