"""系统配置：读取 config/config.yaml（无 PyYAML 时降级为简易解析）。"""
from __future__ import annotations

import os
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

# 智谱默认值：llm / vision 配置留空时自动回退
ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
ZHIPU_MODEL = "glm-4.6v-flash"

DEFAULTS: dict = {
    "enable_llm_grading": False,
    "llm": {
        "api_key": "",
        "base_url": "",
        "model": "",
        "timeout": 20,
    },
    "vision": {
        "enabled": False,
        "base_url": ZHIPU_BASE_URL,
        "api_key": "",
        "model": ZHIPU_MODEL,
        "timeout": 60,
    },
    "parser": {
        "pdf_text_quality_threshold": 0.30,
        "pdf_ocr_enabled": True,
        "pdf_ocr_max_pages": 10,
        "pdf_ocr_dpi": 200,
    },
}


def _load_dotenv() -> dict:
    """解析项目根 .env（环境变量优先，.env 兜底），只取系统用到的键。"""
    env: dict = {}
    if not ENV_PATH.exists():
        return env
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _apply_zhipu_fallback(cfg: dict, env: dict) -> None:
    """智谱默认回退：llm/vision 的 base_url、model、api_key 留空时自动补齐。"""
    zhipu_key = os.environ.get("ZHIPU_API_KEY") or env.get("ZHIPU_API_KEY") or ""
    base = (
        os.environ.get("ZHIPU_API_BASE")
        or env.get("ZHIPU_API_BASE")
        or ZHIPU_BASE_URL
    )
    model = (
        os.environ.get("ZHIPU_MODEL") or env.get("ZHIPU_MODEL") or ZHIPU_MODEL
    )
    for section in ("llm", "vision"):
        if not cfg[section].get("base_url"):
            cfg[section]["base_url"] = base
        if not cfg[section].get("model"):
            cfg[section]["model"] = model
        if not cfg[section].get("api_key"):
            cfg[section]["api_key"] = zhipu_key


def _simple_parse(text: str) -> dict:
    """极简 yaml 子集解析：支持 key: value 与两级缩进。"""
    data: dict = {}
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith((" ", "\t")) and ":" in line and current is not None:
            k, v = line.split(":", 1)
            current[k.strip()] = v.strip().strip('"\'')
        elif ":" in line:
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip()
            if v == "":
                current = {}
                data[k] = current
            else:
                data[k] = v.strip('"\'')
    return data


def load_config() -> dict:
    cfg: dict = {
        "enable_llm_grading": DEFAULTS["enable_llm_grading"],
        "llm": dict(DEFAULTS["llm"]),
        "vision": dict(DEFAULTS["vision"]),
        "parser": dict(DEFAULTS["parser"]),
    }
    if CONFIG_PATH.exists():
        try:
            text = CONFIG_PATH.read_text(encoding="utf-8")
            try:
                import yaml

                raw = yaml.safe_load(text) or {}
            except ImportError:
                raw = _simple_parse(text)
        except OSError:
            raw = None

        if isinstance(raw, dict):
            if "enable_llm_grading" in raw:
                cfg["enable_llm_grading"] = bool(raw["enable_llm_grading"])
            llm = raw.get("llm") or {}
            if isinstance(llm, dict):
                for key in ("api_key", "base_url", "model", "timeout"):
                    if key in llm and llm[key] not in (None, ""):
                        cfg["llm"][key] = llm[key]
            vision = raw.get("vision") or {}
            if isinstance(vision, dict):
                for key in ("enabled", "base_url", "api_key", "model", "timeout"):
                    if key in vision and vision[key] not in (None, ""):
                        cfg["vision"][key] = vision[key]
            if isinstance(cfg["vision"].get("enabled"), str):
                cfg["vision"]["enabled"] = cfg["vision"]["enabled"].lower() in (
                    "true",
                    "1",
                    "yes",
                )
            parser_raw = raw.get("parser") or {}
            if isinstance(parser_raw, dict):
                for key in (
                    "pdf_text_quality_threshold",
                    "pdf_ocr_enabled",
                    "pdf_ocr_max_pages",
                    "pdf_ocr_dpi",
                ):
                    if key in parser_raw and parser_raw[key] not in (None, ""):
                        cfg["parser"][key] = parser_raw[key]
            if isinstance(cfg["parser"].get("pdf_ocr_enabled"), str):
                cfg["parser"]["pdf_ocr_enabled"] = (
                    cfg["parser"]["pdf_ocr_enabled"].lower()
                    in ("true", "1", "yes")
                )
    _apply_zhipu_fallback(cfg, _load_dotenv())
    return cfg
