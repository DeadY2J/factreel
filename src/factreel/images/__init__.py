"""One image per scene through a fallback chain.

``[images] chain = ["cloudflare", "nvidia", "archive", "gradient"]``: each scene takes the first provider
that returns a usable picture. A provider that fails on its first scene is skipped for the rest of the
video. Every AI image is saved in ``archive/`` so a later outage can reuse them, and ``gradient`` always
works (procedural background), so a video is never blocked by images.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from ..config import Channel
from ..llm import LLM
from ..log import log
from .common import archive_image, is_black, to_frame
from .providers import PROVIDERS, ImageError

__all__ = ["scene_images", "PROVIDERS", "ImageError"]

TEXT_QUESTION = ("Look carefully at this image, including small details at the edges. Is there ANY visible text, "
                 "letters, words, numbers or sign lettering anywhere? Answer with only YES or NO.")


def _has_text(channel: Channel, img: Image.Image) -> bool | None:
    model = channel["images"].get("text_check_model")
    if not model:
        return None
    return LLM(channel).ask_image_yes_no(img, TEXT_QUESTION, model)


def scene_images(channel: Channel, scenes: list[dict], out_dir: Path, chain: list[str] | None = None) -> list[Path]:
    chain = list(chain or channel["images"]["chain"])
    size = (int(channel["video"]["width"]), int(channel["video"]["height"]))
    images: list[Image.Image | None] = [None] * len(scenes)
    sources = [""] * len(scenes)
    skipped: set[str] = set()
    for i, scene in enumerate(scenes):
        for name in chain:
            if name in skipped:
                continue
            provider = PROVIDERS.get(name)
            if provider is None:
                log(f"Unknown image provider '{name}' (available: {', '.join(PROVIDERS)})")
                skipped.add(name)
                continue
            try:
                img = provider(channel, scene["prompt"], i, len(scenes))
            except ImageError as e:
                log(f"  Image {i + 1}: {name} failed ({str(e)[:120]}); skipping it for this video")
                skipped.add(name)
                continue
            if img is None:
                continue
            img = to_frame(img, size)
            if is_black(img):
                log(f"  Image {i + 1}: {name} returned a black image")
                continue
            if name not in ("archive", "gradient") and _has_text(channel, img):
                log(f"  Image {i + 1}: {name} drew letters; trying again")
                try:
                    retry = provider(channel, scene["prompt"], i, len(scenes))
                except ImageError:
                    retry = None
                retry = to_frame(retry, size) if retry is not None else None
                if retry is None or _has_text(channel, retry) is not False:
                    continue
                img = retry
            if name not in ("archive", "gradient"):
                archive_image(channel, img)
            images[i], sources[i] = img, name
            break
    if not any(images):
        raise ImageError("no image provider worked (add 'gradient' at the end of [images] chain to never fail)")
    for i, img in enumerate(images):  # a scene without image reuses its neighbour's
        if img is None:
            nearby = [x for x in images[i - 1::-1] if x is not None] + [x for x in images[i + 1:] if x is not None]
            images[i], sources[i] = nearby[0], "neighbour"
    paths = []
    for i, img in enumerate(images, 1):
        path = out_dir / f"scene_{i}.png"
        img.save(path, "PNG")
        paths.append(path)
    log("Images: " + ", ".join(f"{i + 1}={s}" for i, s in enumerate(sources)))
    return paths
