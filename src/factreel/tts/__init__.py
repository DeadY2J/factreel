"""Text-to-speech with an automatic fallback chain.

``[voice] chain = ["edge", "elevenlabs", "cloudflare", "system"]`` is tried in order. A provider that
fails is skipped for the rest of the run (no waiting twice per scene), and every failure/recovery is
recorded in ``.factreel/voice_health.json`` so ``factreel doctor`` can tell you when a service comes back.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from ..config import Channel
from ..log import log, warn
from .providers import PROVIDERS, TTSError

__all__ = ["synthesize", "PROVIDERS", "TTSError", "record_health", "read_health"]

_down: set[str] = set()


def _health_file(channel: Channel) -> Path:
    return channel.state_dir / "voice_health.json"


def read_health(channel: Channel) -> dict:
    try:
        return json.loads(_health_file(channel).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def record_health(channel: Channel, provider: str, ok: bool, detail: str = "") -> bool:
    """Store the provider status. Returns True when the provider just came back after being down."""
    health = read_health(channel)
    prev = health.get(provider, {})
    recovered = ok and prev.get("ok") is False
    now = time.strftime("%Y-%m-%d %H:%M")
    health[provider] = {"ok": ok, "checked": now, "detail": detail[:160],
                        "since": prev.get("since") if prev.get("ok") == ok and prev.get("since") else now}
    _health_file(channel).write_text(json.dumps(health, ensure_ascii=False, indent=2), encoding="utf-8")
    return recovered


def synthesize(channel: Channel, text: str, out_path: Path, chain: list[str] | None = None) -> tuple[list, str]:
    """Generate ``out_path`` (MP3) and return ``(word_timings, provider_name)``."""
    chain = list(chain or channel["voice"]["chain"])
    errors = []
    for name in chain:
        if name in _down:
            continue
        provider = PROVIDERS.get(name)
        if provider is None:
            warn(f"Unknown voice provider '{name}' in [voice] chain (available: {', '.join(PROVIDERS)})")
            continue
        try:
            log(f"Voice: {name}...")
            words = provider(channel, text, Path(out_path))
            if record_health(channel, name, True, "ok"):
                log(f"  {name} is working again.")
            return words, name
        except TTSError as e:
            _down.add(name)
            record_health(channel, name, False, str(e))
            errors.append(f"{name}: {e}")
            log(f"  {name} not available ({str(e)[:140]})")
    raise TTSError("no voice provider worked -> " + " | ".join(errors))
