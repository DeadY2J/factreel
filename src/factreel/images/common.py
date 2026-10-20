from __future__ import annotations

import io
import random
import time

from PIL import Image, ImageOps, ImageStat

from ..config import Channel

MIN_BRIGHTNESS = 8  # mean luminance (0-255) below which a frame counts as "black screen"


def open_image(data: bytes) -> Image.Image:
    """Decode bytes and flatten transparency on white."""
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            rgba = img.convert("RGBA")
            canvas = Image.new("RGB", rgba.size, (255, 255, 255))
            canvas.paste(rgba, mask=rgba.split()[-1])
            return canvas
        return img.convert("RGB")


def trim_black_bars(img: Image.Image, threshold: int = 8, min_bar: int = 40) -> Image.Image:
    """Diffusion models sometimes paint 'cinema' bars; crop them before fitting to 9:16."""
    gray = img.convert("L")
    w, h = gray.size
    xs = range(0, w, max(1, w // 64))

    def dark(y: int) -> bool:
        return max(gray.getpixel((x, y)) for x in xs) < threshold

    top = 0
    while top < h // 4 and dark(top):
        top += 1
    bottom = h
    while bottom > h * 3 // 4 and dark(bottom - 1):
        bottom -= 1
    if top >= min_bar or h - bottom >= min_bar:
        return img.crop((0, top, w, bottom))
    return img


def to_frame(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Center-crop to the target aspect ratio and resize with LANCZOS (no distortion)."""
    img = trim_black_bars(img.convert("RGB"))
    return ImageOps.fit(img, size, method=Image.Resampling.LANCZOS)


def is_black(img: Image.Image) -> bool:
    return ImageStat.Stat(img.convert("L")).mean[0] < MIN_BRIGHTNESS


def archive_image(channel: Channel, img: Image.Image) -> None:
    d = channel.path("archive_dir")
    d.mkdir(parents=True, exist_ok=True)
    img.save(d / f"img_{time.strftime('%Y%m%d_%H%M%S')}_{random.randint(100, 999)}.jpg", quality=92)
