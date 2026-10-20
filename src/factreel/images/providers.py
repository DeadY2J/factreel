"""Image providers: ``fn(channel, prompt, index, total) -> PIL.Image | None``.

Return ``None`` to let the next provider in the chain try this scene; raise ``ImageError`` when the
provider is not usable at all (missing key, service down) so it is skipped for the rest of the video.
"""
from __future__ import annotations

import base64
import hashlib
import math
import os
import random
import re
import shlex
import subprocess

import requests
from PIL import Image, ImageDraw, ImageFilter

from ..cloudflare import Cloudflare, CloudflareError
from ..config import Channel, read_secret
from ..log import log
from .common import open_image


class ImageError(RuntimeError):
    pass


def clean_prompt(channel: Channel, prompt: str) -> str:
    """Remove words that trigger safety filters (they return black images) and add the channel style."""
    for word in sorted(channel["images"].get("banned_words", []), key=len, reverse=True):
        prompt = re.sub(rf"\b{re.escape(word)}\b", "", prompt, flags=re.I)
    prompt = re.sub(r"\s*,\s*(,\s*)+", ", ", re.sub(r"\s{2,}", " ", prompt)).strip(" ,")
    return prompt + str(channel["images"].get("style") or "")


# ---------------------------------------------------------------- Cloudflare Workers AI (FLUX)

def cloudflare(channel: Channel, prompt: str, index: int, total: int) -> Image.Image | None:
    c = channel["images"]["cloudflare"]
    cf = Cloudflare(channel)
    fields = {"prompt": clean_prompt(channel, prompt), "width": channel["images"]["width"],
              "height": channel["images"]["height"], "seed": random.randint(1, 999_999)}
    try:
        res = cf.run(c["model"], estimate=float(c.get("neurons", 110)),
                     files={k: (None, str(v)) for k, v in fields.items()}, timeout=90)
        data = res.json()
    except (CloudflareError, ValueError) as e:
        raise ImageError(str(e)) from e
    if not data.get("success"):
        raise ImageError(str(data.get("errors"))[:150])
    return open_image(base64.b64decode(data["result"]["image"]))


# ---------------------------------------------------------------- NVIDIA NIM (FLUX, free credits)

NVIDIA_MODELS = {
    "flux.1-dev": ("https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-dev", {"mode": "base", "steps": 30}),
    "flux.1-schnell": ("https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-schnell", {"steps": 4}),
}


def nvidia(channel: Channel, prompt: str, index: int, total: int) -> Image.Image | None:
    c = channel["images"]["nvidia"]
    key = read_secret(c.get("api_key_env", "NVIDIA_API_KEY"))
    if not key:
        raise ImageError(f"missing {c.get('api_key_env')}")
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    last_error = "no model configured"
    for name in c.get("models", []):
        if name not in NVIDIA_MODELS:
            continue
        url, extra = NVIDIA_MODELS[name]
        payload = {"prompt": clean_prompt(channel, prompt), **extra, "seed": random.randint(1, 999_999),
                   "width": channel["images"]["width"], "height": channel["images"]["height"]}
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=float(c.get("timeout", 60)))
        except requests.RequestException as e:
            last_error = f"{name}: {str(e)[:100]}"
            continue
        if res.status_code != 200:
            last_error = f"{name}: HTTP {res.status_code} {res.text[:100]}"
            continue
        artifacts = (res.json() or {}).get("artifacts") or []
        # the safety filter answers with a black image and a finishReason other than SUCCESS
        if artifacts and artifacts[0].get("finishReason") in (None, "SUCCESS"):
            return open_image(base64.b64decode(artifacts[0]["base64"]))
        last_error = f"{name}: filtered or empty"
    if index == 0:
        raise ImageError(last_error)
    log(f"  NVIDIA: {last_error}")
    return None


# ---------------------------------------------------------------- Your own generator (local GPU, ComfyUI, A1111...)

def _split(template: str) -> list[str]:
    """shlex.split that keeps Windows backslashes (C:\\gen\\run.py)."""
    if os.name != "nt":
        return shlex.split(template, posix=True)
    return [p[1:-1] if len(p) > 1 and p[0] == p[-1] and p[0] in "\"'" else p for p in shlex.split(template, posix=False)]


def command(channel: Channel, prompt: str, index: int, total: int) -> Image.Image | None:
    """Runs ``[images.command] run = "python my_gen.py --prompt {prompt} --out {out}"`` and reads ``{out}``."""
    c = channel["images"].get("command") or {}
    template = c.get("run")
    if not template:
        raise ImageError("set [images.command] run = \"...{prompt}...{out}...\"")
    out = channel.temp_dir / f"command_{index}.png"
    out.unlink(missing_ok=True)
    args = [part.format(prompt=clean_prompt(channel, prompt), out=str(out), width=channel["images"]["width"],
                        height=channel["images"]["height"], seed=random.randint(1, 999_999))
            for part in _split(template)]
    try:
        subprocess.run(args, check=True, capture_output=True, timeout=float(c.get("timeout", 600)))
    except (OSError, subprocess.SubprocessError) as e:
        raise ImageError(f"command failed: {str(e)[:150]}") from e
    if not out.is_file():
        raise ImageError(f"command did not create {out.name}")
    return open_image(out.read_bytes())


# ---------------------------------------------------------------- Archive (previous AI images + your own pictures)

def archive(channel: Channel, prompt: str, index: int, total: int) -> Image.Image | None:
    d = channel.path("archive_dir")
    files = sorted(p for p in d.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")) if d.is_dir() else []
    if not files:
        raise ImageError(f"{d.name}/ is empty")
    rng = random.Random(f"{prompt}-{index}")
    return open_image(rng.choice(files).read_bytes())


# ---------------------------------------------------------------- Procedural background (offline, never fails)

def _hex(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def gradient(channel: Channel, prompt: str, index: int, total: int) -> Image.Image:
    """Retro gradient with a sun, glow and a perspective grid. Deterministic per prompt, different per scene."""
    w, h = int(channel["video"]["width"]), int(channel["video"]["height"])
    palette = [_hex(c) for c in channel["images"]["gradient"].get("palette") or ["#1b0b3a", "#ff3c9a", "#ffb03c"]]
    seed = int(hashlib.sha1(f"{prompt}|{index}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    top, mid, low = (palette * 3)[:3]
    horizon = int(h * rng.uniform(0.56, 0.66))
    img = Image.new("RGB", (w, h))
    px = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(horizon, 1)
        if y <= horizon:
            a, b, k = (top, mid, t / 0.65) if t < 0.65 else (mid, low, (t - 0.65) / 0.35)
        else:
            a, b, k = (tuple(int(c * 0.25) for c in top), top, (y - horizon) / (h - horizon))
        k = min(max(k, 0.0), 1.0)
        px.line([(0, y), (w, y)], fill=tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3)))
    # stars
    for _ in range(rng.randint(60, 140)):
        x, y = rng.randrange(w), rng.randrange(int(horizon * 0.55))
        r = rng.choice((1, 1, 2))
        px.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255))
    # sun with glow and stripes
    glow = Image.new("RGB", (w, h))
    gd = ImageDraw.Draw(glow)
    cx = int(w * rng.uniform(0.35, 0.65))
    radius = int(w * rng.uniform(0.22, 0.3))
    cy = horizon - int(radius * rng.uniform(0.3, 0.8))
    gd.ellipse([cx - radius * 1.6, cy - radius * 1.6, cx + radius * 1.6, cy + radius * 1.6], fill=low)
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(radius * 0.6)), 0.35)
    px = ImageDraw.Draw(img)
    for y in range(cy - radius, min(cy + radius, horizon)):
        half = int(math.sqrt(max(radius ** 2 - (y - cy) ** 2, 0)))
        k = (y - (cy - radius)) / (2 * radius)
        band = y > cy and int((y - cy) / max(radius * 0.12, 1)) % 2 == 1
        if not band:
            color = tuple(int(low[i] + (mid[i] - low[i]) * k) for i in range(3))
            px.line([(cx - half, y), (cx + half, y)], fill=color)
    # grid floor
    line = tuple(min(255, int(c * 1.2)) for c in mid)
    for i in range(-12, 13):
        px.line([(w / 2 + i * w * 0.02, horizon), (w / 2 + i * w * 0.35, h)], fill=line, width=2)
    y, step = horizon, 6.0
    while y < h:
        px.line([(0, int(y)), (w, int(y))], fill=line, width=2)
        step *= 1.32
        y += step
    return img


PROVIDERS = {"cloudflare": cloudflare, "nvidia": nvidia, "command": command, "archive": archive, "gradient": gradient}
