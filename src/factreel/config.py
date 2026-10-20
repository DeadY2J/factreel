"""Channel configuration: a folder with ``channel.toml`` + ``facts.json``.

Every value has a sensible default, so a ``channel.toml`` only needs the keys you want to change.
Secrets are never stored in the config: it only holds the *names* of the environment variables
that contain them (``api_key_env = "NVIDIA_API_KEY"``). A ``.env`` file next to ``channel.toml``
is loaded automatically for convenience.
"""
from __future__ import annotations

import copy
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

CONFIG_NAME = "channel.toml"

DEFAULTS: dict[str, Any] = {
    "channel": {
        "name": "My Channel",
        "language": "en",
        "sign_off": "",
        "facts_file": "facts.json",
        "output_dir": "output",
        "archive_dir": "archive",
        "music_dir": "music",
        "queue_file": "queue.txt",
    },
    "countdown": {"event": "", "date": ""},
    "script": {
        "scenes": 4,
        "min_words": 30,
        "max_words": 56,
        "grace_words": 8,
        "retries": 6,
        "fact_check": True,
        "allowed_numbers": [],
        "extra_rules": "",
        "image_rules": "",
    },
    "llm": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model": "nvidia/nemotron-3-ultra-550b-a55b",
        "api_key_env": "NVIDIA_API_KEY",
        "temperature": 0.8,
        "timeout": 120,
        "extra_body": {},
    },
    "voice": {
        "chain": ["edge", "cloudflare", "system"],
        "edge": {"voice": "", "rate": "+4%", "pitch": "+0Hz"},
        "elevenlabs": {"voice_id": "pNInz6obpgDQGcFmaJgB", "model": "eleven_multilingual_v2", "tempo": 1.0,
                       "api_key_env": "ELEVENLABS_API_KEY", "max_chars": 1500},
        "cloudflare": {"model": "@cf/deepgram/aura-2-en", "speaker": "pluto", "tempo": 0.85},
        "system": {"voice": "", "rate": 0},
        "dummy": {"words_per_second": 2.6},
    },
    "images": {
        "chain": ["cloudflare", "nvidia", "archive", "gradient"],
        "width": 768,
        "height": 1344,
        "style": ", cinematic lighting, highly detailed, vertical composition, no text, no letters, no logo, no watermark",
        "banned_words": ["gore", "gory", "blood", "bloody", "corpse", "dead", "death", "kill", "murder", "gun", "weapon"],
        "text_check_model": "",
        "cloudflare": {"model": "@cf/black-forest-labs/flux-2-klein-4b", "neurons": 110},
        "nvidia": {"models": ["flux.1-dev", "flux.1-schnell"], "api_key_env": "NVIDIA_API_KEY", "timeout": 60},
        "gradient": {"palette": ["#1b0b3a", "#ff3c9a", "#ffb03c"]},
    },
    "video": {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "fade": 0.7,
        "zoom": 0.08,
        "tail": 1.5,
        "voice_lufs": -14,
        "music_lufs": -27,
        "crf": 20,
    },
    "subtitles": {
        "enabled": True,
        "font": "Arial Black",
        "size": 84,
        "color": "#FFFFFF",
        "highlight": "#FF3C9A",
        "outline": 7,
        "margin_v": 640,
        "max_words": 3,
        "max_chars": 18,
        "uppercase": True,
    },
    "metadata": {
        "title_suffix": " #shorts",
        "tags": [],
        "hashtags_fixed": ["#shorts"],
        "hashtags_rotating": [],
        "hashtags_rotating_count": 4,
        "disclaimer": "",
        "description": "{teaser}\n\n{countdown}\n\n{music}\n\n{disclaimer}\n\n{hashtags}",
    },
    "cloudflare": {
        "account_id_env": "CLOUDFLARE_ACCOUNT_ID",
        "api_token_env": "CLOUDFLARE_API_TOKEN",
        "daily_neuron_cap": 10000,
        "whisper_model": "@cf/openai/whisper-large-v3-turbo",
    },
    "youtube": {
        "privacy": "public",
        "category_id": "20",
        "made_for_kids": False,
        "synthetic_media": True,
        "client_secrets": "client_secrets.json",
    },
}


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_dotenv(path: Path) -> None:
    """Minimal ``.env`` loader (KEY=VALUE lines). Existing environment variables win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def read_secret(env_name: str) -> str | None:
    """Value of an environment variable. On Windows it also looks at the user's registry environment,
    so variables created with ``setx`` work in an already-open terminal or a scheduled task."""
    if not env_name:
        return None
    value = os.environ.get(env_name)
    if not value and sys.platform == "win32":  # pragma: no cover - Windows only
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value = winreg.QueryValueEx(key, env_name)[0]
        except OSError:
            value = None
    return value or None


@dataclass
class Channel:
    """A loaded channel: its folder plus the merged configuration."""

    root: Path
    cfg: dict = field(default_factory=dict)

    def __getitem__(self, key: str) -> dict:
        return self.cfg[key]

    @property
    def language(self) -> str:
        return str(self.cfg["channel"]["language"]).lower()[:2]

    def path(self, key: str) -> Path:
        """Absolute path for a ``[channel]`` path setting, relative to the channel folder."""
        p = Path(self.cfg["channel"][key])
        return p if p.is_absolute() else self.root / p

    @property
    def state_dir(self) -> Path:
        d = self.root / ".factreel"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def temp_dir(self) -> Path:
        d = self.state_dir / "tmp"
        d.mkdir(parents=True, exist_ok=True)
        return d


def load_channel(root: str | os.PathLike = ".", overrides: dict | None = None) -> Channel:
    root_path = Path(root).expanduser().resolve()
    cfg_file = root_path / CONFIG_NAME
    if not cfg_file.is_file():
        raise FileNotFoundError(
            f"No {CONFIG_NAME} in {root_path}. Create a channel with: factreel init {root_path.name or 'my-channel'}"
        )
    load_dotenv(root_path / ".env")
    with cfg_file.open("rb") as f:
        user_cfg = tomllib.load(f)
    cfg = deep_merge(DEFAULTS, user_cfg)
    if overrides:
        cfg = deep_merge(cfg, overrides)
    return Channel(root=root_path, cfg=cfg)
