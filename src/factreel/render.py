"""FFmpeg render: smooth Ken Burns zoom (no jitter), cross-fades on scene changes, burned subtitles,
voice normalised to YouTube loudness and optional background music."""
from __future__ import annotations

import io
import json
import os
import random
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageOps

from .config import Channel
from .images.common import is_black
from .log import log
from .tts.timing import media_duration

AUDIO_EXT = (".mp3", ".m4a", ".wav", ".ogg", ".flac")


class RenderError(RuntimeError):
    pass


def zoom_clip(img_path: Path, out_path: Path, w: int, h: int, length: float, zoom_in: bool, amount: float,
              fps: int) -> None:
    """Slow zoom WITHOUT jitter: each frame is an affine transform with sub-pixel bicubic sampling (Pillow)
    piped to FFmpeg. FFmpeg's zoompan rounds to whole pixels, which is what makes zooms 'shake'."""
    n = max(2, int(round(length * fps)))
    img = Image.open(img_path).convert("RGB")
    base = ImageOps.fit(img, (w * 2, h * 2), method=Image.Resampling.LANCZOS)  # 2x canvas: resolution to spare
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps),
           "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    cx, cy = base.width / 2, base.height / 2

    def frame(k: int) -> bytes:
        p = k / (n - 1)
        z = (1.0 + amount * p) if zoom_in else (1.0 + amount * (1 - p))
        sc = 2.0 / z
        return base.transform((w, h), Image.Transform.AFFINE, (sc, 0, cx - sc * w / 2, 0, sc, cy - sc * h / 2),
                              resample=Image.Resampling.BICUBIC).tobytes()

    try:
        # Pillow releases the GIL while transforming, so frames are computed in parallel (kept in order by map)
        workers = min(8, os.cpu_count() or 2)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for chunk in range(0, n, workers * 2):  # bounded batches: a 1080x1920 frame is ~6 MB
                for data in pool.map(frame, range(chunk, min(chunk + workers * 2, n))):
                    proc.stdin.write(data)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode("utf-8", "replace")
    if proc.wait() != 0:
        raise RenderError("zoom clip failed: " + err[-500:])


def pick_music(channel: Channel, duration: float) -> tuple[Path | None, float]:
    d = channel.path("music_dir")
    tracks = sorted(p for p in d.glob("*") if p.suffix.lower() in AUDIO_EXT) if d.is_dir() else []
    if not tracks:
        return None, 0.0
    lengths = {t: media_duration(t) for t in tracks}
    long_enough = [t for t in tracks if lengths[t] >= duration + 2]  # short tracks would loop audibly
    track = random.choice(long_enough or tracks)
    start = max(0.0, random.uniform(0, lengths[track] - duration - 1))
    log(f"Music: {track.name} (from second {int(start)})")
    return track, start


def music_credit(channel: Channel, track: Path | None) -> str:
    """Credit line from ``music/credits.json`` ({"file.mp3": "Song by Artist (License)"}), else the file name."""
    if track is None:
        return ""
    try:
        credits = json.loads((track.parent / "credits.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        credits = {}
    return credits.get(track.name) or track.stem


def render(channel: Channel, images: list[Path], starts: list[float], audio: Path, out: Path,
           ass: Path | None = None, music: bool = True) -> Path | None:
    """Render the MP4. Returns the music track used (or None)."""
    v = channel["video"]
    w, h, fps, fade = int(v["width"]), int(v["height"]), int(v["fps"]), float(v["fade"])
    tmp = channel.temp_dir
    total = media_duration(audio) + float(v["tail"])
    n = len(images)
    ends = starts[1:] + [total]
    lengths = [ends[i] - starts[i] + (fade if i < n - 1 else 0) for i in range(n)]

    cmd = ["ffmpeg", "-y", "-hide_banner", "-v", "error"]
    for i, (path, length) in enumerate(zip(images, lengths)):
        clip = tmp / f"zoom_{i}.mp4"
        zoom_clip(path, clip, w, h, length, i % 2 == 0, float(v["zoom"]), fps)
        cmd += ["-i", str(clip)]
    cmd += ["-i", str(audio)]
    track, track_start = pick_music(channel, total) if music else (None, 0.0)
    if track:
        cmd += ["-stream_loop", "-1", "-ss", f"{track_start:.2f}", "-i", str(track)]

    filters = [f"[{i}:v]fps={fps},setsar=1,format=yuv420p[v{i}]" for i in range(n)]
    last = "v0"
    for i in range(1, n):
        filters.append(f"[{last}][v{i}]xfade=transition=fade:duration={fade}:offset={starts[i]:.3f}[x{i}]")
        last = f"x{i}"
    # relative path (cwd = temp dir) avoids escaping "C:" inside the filter graph
    filters.append(f"[{last}]ass={ass.name}[vout]" if ass else f"[{last}]null[vout]")
    filters.append(f"[{n}:a]apad=pad_dur={v['tail']},loudnorm=I={v['voice_lufs']}:TP=-2:LRA=11,aresample=48000[voice]")
    if track:
        filters.append(f"[{n + 1}:a]loudnorm=I={v['music_lufs']}:TP=-9:LRA=11,aresample=48000,"
                       f"afade=t=in:d=2,afade=t=out:st={max(total - 2, 0):.2f}:d=2[amb]")
        filters.append("[voice][amb]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.9[aout]")
    else:
        filters.append("[voice]anull[aout]")
    cmd += ["-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(v["crf"]), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out.resolve())]
    if ass and ass.parent.resolve() != tmp.resolve():
        raise RenderError("subtitles must live in the temp dir")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=tmp)
    if res.returncode != 0:
        raise RenderError(f"FFmpeg failed:\n{res.stderr[-1500:]}")
    return track


def verify(channel: Channel, video: Path) -> float:
    """Resolution, audio track and a non-black middle frame. Returns the duration."""
    w, h = int(channel["video"]["width"]), int(channel["video"]["height"])
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                            "-of", "json", str(video)], capture_output=True, text=True, check=True)
    info = json.loads(probe.stdout)
    vs = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if not vs or (vs["width"], vs["height"]) != (w, h):
        raise RenderError(f"wrong resolution: {vs}")
    if not any(s["codec_type"] == "audio" for s in info["streams"]):
        raise RenderError("the video has no audio track")
    duration = float(info["format"]["duration"])
    frame = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{duration / 2:.2f}", "-i", str(video), "-frames:v", "1",
                            "-f", "image2pipe", "-c:v", "png", "-"], capture_output=True, check=True).stdout
    with Image.open(io.BytesIO(frame)) as img:
        if is_black(img):
            raise RenderError("the middle frame is black")
    log(f"Video verified: {w}x{h}, {duration:.1f}s, audio OK, no black screen.")
    return duration
