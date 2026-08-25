"""智谱/OpenAI 兼容聊天客户端：统一 /chat/completions 调用（含 429 自动重试）。

判卷、docx 图片分类、扫描 PDF OCR、变式出题、AI 文本整理共用此模块。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


def chat_completion(
    messages: list[dict],
    *,
    base_url: str,
    api_key: str,
    model: str,
    temperature: float = 0,
    timeout: float = 60,
    retries: int = 3,
) -> str:
    """调用 OpenAI 兼容 /chat/completions，返回 message.content 文本。

    429 / 5xx 自动重试（递增退避）；其他错误或重试用尽时抛 RuntimeError。
    """
    if not base_url or not api_key or not model:
        raise RuntimeError("模型配置不完整（base_url/api_key/model）")
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            return (content or "").strip()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            last_err = RuntimeError(f"API {exc.code}: {detail}")
            if exc.code != 429 and exc.code < 500:
                break
            if attempt == retries:
                break
        except Exception as exc:  # noqa: BLE001 - 网络/超时/解析异常统一兜底
            last_err = exc
            if attempt == retries:
                break
        time.sleep(min(3 * attempt, 15))
    raise RuntimeError(f"模型调用失败: {last_err}")
