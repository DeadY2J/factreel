"""OpenAI-compatible chat client.

Works with any provider that speaks ``/v1/chat/completions``: NVIDIA NIM (free tier), OpenRouter, Groq,
Cerebras, OpenAI, a local Ollama / LM Studio, or a self-hosted gateway such as OmniRoute.
"""
from __future__ import annotations

import base64
import io
import json

import requests

from .config import Channel, read_secret


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, channel: Channel):
        c = channel["llm"]
        self.base_url = str(c["base_url"]).rstrip("/")
        self.model = c["model"]
        self.temperature = float(c.get("temperature", 0.8))
        self.timeout = float(c.get("timeout", 120))
        self.extra_body = dict(c.get("extra_body") or {})
        self.api_key = read_secret(c.get("api_key_env", ""))
        # Local servers (Ollama, LM Studio) don't need a key
        self.needs_key = not any(h in self.base_url for h in ("localhost", "127.0.0.1", "0.0.0.0"))

    @property
    def available(self) -> bool:
        return bool(self.api_key) or not self.needs_key

    def chat(self, messages: list[dict], *, temperature: float | None = None, max_tokens: int = 2000,
             model: str | None = None) -> str:
        if not self.available:
            raise LLMError("no API key for the LLM (set the variable named in [llm] api_key_env)")
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {"model": model or self.model, "messages": messages, "max_tokens": max_tokens,
                "temperature": self.temperature if temperature is None else temperature, **self.extra_body}
        try:
            res = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=body, timeout=self.timeout)
        except requests.RequestException as e:
            raise LLMError(f"request failed: {e}") from e
        if res.status_code != 200:
            raise LLMError(f"HTTP {res.status_code}: {res.text[:200]}")
        try:
            content = res.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise LLMError(f"unexpected response: {res.text[:200]}") from e
        if not content:
            raise LLMError("empty response")
        return content

    def ask_image_yes_no(self, image, question: str, model: str) -> bool | None:
        """Ask a vision model a YES/NO question about a PIL image. ``None`` if it could not be checked."""
        try:
            small = image.convert("RGB")
            small.thumbnail((512, 512))
            buf = io.BytesIO()
            small.save(buf, "JPEG", quality=85)
            url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
            answer = self.chat([{"role": "user", "content": [{"type": "text", "text": question},
                                                            {"type": "image_url", "image_url": {"url": url}}]}],
                               temperature=0, max_tokens=5, model=model)
            return answer.strip().upper().startswith(("YES", "SÍ", "SI"))
        except (LLMError, OSError):
            return None


def extract_json(content: str) -> dict:
    """First ``{...}`` block of a model answer (models like to wrap JSON in markdown)."""
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("the answer contains no JSON object")
    return json.loads(content[start:end + 1])
