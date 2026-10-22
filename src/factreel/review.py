"""Post-render visual subtitle review using a vision LLM.

Samples video frames at the timestamps of on-screen subtitles, sends them to a vision model,
and checks whether the observed subtitles match the expected captions without rendering defects.
"""

from __future__ import annotations

import base64
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Channel
from .llm import LLM, extract_json
from .log import log, warn


@dataclass
class CaptionEntry:
    text: str
    start: float
    end: float


def parse_ass_time(timestr: str) -> float:
    """Parse ASS timestamp (e.g. '0:00:01.25' or '01:23.45') to seconds as float."""
    try:
        parts = timestr.strip().split(":")
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except (ValueError, IndexError):
        return 0.0


def clean_ass_text(raw_text: str) -> str:
    """Strip ASS override tags {...}, handle escaped newlines, and collapse whitespace."""
    # Strip override tags like {\c&H...} or {\fscx...}
    text = re.sub(r"\{.*?\}", "", raw_text)
    # Handle ASS newline markers (\N, \n) and non-breaking space (\h)
    text = re.sub(r"\\[Nnh]", " ", text)
    # Collapse whitespace
    return re.sub(r"\s+", " ", text).strip()


def parse_ass_dialogues(ass_path: Path) -> list[CaptionEntry]:
    """Parse ASS Dialogue entries into captions with their start and end times.

    Accounts for commas in dialogue text (ASS dialogue format: Layer, Start, End, Style,
    Name, MarginL, MarginR, MarginV, Effect, Text).
    Merges repeated identical cleaned captions only when their time ranges are consecutive
    or overlapping (as generated during word-by-word karaoke), preserving separate occurrences
    in distant scenes as distinct caption entries.
    """
    if not ass_path.is_file():
        return []
    try:
        lines = ass_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        warn(f"Visual subtitle review: could not read ASS file '{ass_path}': {e}")
        return []

    dialogues: list[tuple[float, float, str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("Dialogue:"):
            continue
        body = stripped[len("Dialogue:") :].strip()
        # Maxsplit=9 separates the first 9 header fields from the dialogue text
        parts = body.split(",", 9)
        if len(parts) < 10:
            continue
        start = parse_ass_time(parts[1])
        end = parse_ass_time(parts[2])
        cleaned = clean_ass_text(parts[9])
        if not cleaned:
            continue
        dialogues.append((start, end, cleaned))

    # Keep chronological order
    dialogues.sort(key=lambda d: (d[0], d[1]))

    entries: list[CaptionEntry] = []
    for start, end, cleaned in dialogues:
        if entries and entries[-1].text == cleaned and start <= entries[-1].end + 0.1:
            entries[-1].end = max(entries[-1].end, end)
            entries[-1].start = min(entries[-1].start, start)
        else:
            entries.append(CaptionEntry(text=cleaned, start=start, end=end))

    return entries


def normalize_caption(text: str) -> str:
    """Retain only letters and digits, converted to uppercase."""
    return "".join(ch.upper() for ch in text if ch.isalnum())


def sample_captions(captions: list[CaptionEntry], max_samples: int = 12) -> list[CaptionEntry]:
    """Sample at most max_samples captions distributed evenly across the video.

    If len(captions) <= max_samples, returns all captions.
    If len(captions) > max_samples, selects max_samples indices from beginning to end
    without duplicates, preserving chronological order.
    """
    if max_samples <= 0:
        return []
    n = len(captions)
    if n <= max_samples:
        return list(captions)
    if max_samples == 1:
        return [captions[0]]
    indices = [round(i * (n - 1) / (max_samples - 1)) for i in range(max_samples)]
    return [captions[i] for i in indices]


def build_extract_frame_cmd(video_path: Path | str, timestamp: float, out_path: Path | str) -> list[str]:
    """Build the FFmpeg command to extract and scale a single frame to 540px wide."""
    return [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-v",
        "error",
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        str(video_path),
        "-vf",
        "scale=540:-1",
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(out_path),
    ]


def extract_frame(video_path: Path, timestamp: float, out_path: Path) -> bool:
    """Extract a single frame from video at timestamp using FFmpeg."""
    cmd = build_extract_frame_cmd(video_path, timestamp, out_path)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode != 0 or not out_path.is_file() or out_path.stat().st_size == 0:
            warn(f"Visual subtitle review: FFmpeg extraction failed at {timestamp:.2f}s: {res.stderr[:200]}")
            return False
        return True
    except (subprocess.SubprocessError, OSError) as e:
        warn(f"Visual subtitle review: FFmpeg error at {timestamp:.2f}s: {e}")
        return False


def review_subtitles(channel: Channel, video: Path | str, ass_path: Path | str) -> list[str]:
    """Sample video frames at subtitle timestamps and review them with a vision LLM.

    Returns a list of actionable warnings (empty if all subtitles match and look good).
    Never propagates exceptions; logs a warning and returns an empty or partial list.
    """
    try:
        return _review_subtitles(channel, Path(video), Path(ass_path))
    except Exception as e:
        warn(f"Visual subtitle review failed: {e}")
        return []


def _review_subtitles(channel: Channel, video: Path, ass_path: Path) -> list[str]:
    review_cfg = channel.cfg.get("review") or {}
    model = str(review_cfg.get("model") or "").strip()
    if not model:
        log("Visual subtitle review: no model configured in [review] model, skipping.")
        return []

    try:
        llm = LLM(channel)
    except Exception as e:
        warn(f"Visual subtitle review: could not initialize LLM ({e})")
        return []

    if not llm.available:
        warn(f"Visual subtitle review: credentials unavailable for LLM ({channel['llm'].get('api_key_env')})")
        return []

    if not video.is_file():
        warn(f"Visual subtitle review: video file '{video}' does not exist")
        return []

    captions = parse_ass_dialogues(ass_path)
    if not captions:
        return []

    # Sample up to 12 captions distributed evenly across the video
    selected = sample_captions(captions, max_samples=12)

    with tempfile.TemporaryDirectory(prefix="factreel_review_") as tmp_dir:
        extracted: list[dict[str, Any]] = []
        for idx, entry in enumerate(selected, start=1):
            mid_ts = max(0.0, (entry.start + entry.end) / 2.0)
            frame_path = Path(tmp_dir) / f"frame_{idx:02d}.jpg"
            if extract_frame(video, mid_ts, frame_path):
                try:
                    data = frame_path.read_bytes()
                    b64 = base64.b64encode(data).decode("ascii")
                    data_url = f"data:image/jpeg;base64,{b64}"
                    extracted.append(
                        {
                            "n": idx,
                            "entry": entry,
                            "timestamp": mid_ts,
                            "data_url": data_url,
                        }
                    )
                except OSError as e:
                    warn(f"Visual subtitle review: could not read extracted frame {idx}: {e}")

        if not extracted:
            warn("Visual subtitle review: no frames could be extracted")
            return []

        prompt_text = (
            "You are reviewing the visual quality and accuracy of subtitles rendered on video frames.\n"
            "For each numbered frame, transcribe the visible subtitle caption text and check for visual rendering issues "
            "(such as clipped or truncated text, bad wrapping, visual glitches, or overlapping words).\n\n"
            "Return a JSON object with this exact shape:\n"
            '{"frames": [{"n": 1, "caption": "...", "ok": true, "problem": ""}]}\n\n'
            "For each frame:\n"
            '- "n": integer matching the frame number\n'
            '- "caption": the subtitle text visible on screen\n'
            '- "ok": true if rendered cleanly without problems, false if there are visual defects\n'
            '- "problem": description of any visual problem, or empty string if ok is true.'
        )

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt_text}]
        for item in extracted:
            content.append(
                {
                    "type": "text",
                    "text": f"Frame {item['n']}:",
                }
            )
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": item["data_url"]},
                }
            )

        messages = [{"role": "user", "content": content}]

        try:
            response_text = llm.chat(messages, model=model, temperature=0.0)
        except Exception as e:
            warn(f"Visual subtitle review: LLM request failed: {e}")
            return []

        try:
            data = extract_json(response_text)
        except Exception as e:
            warn(f"Visual subtitle review: failed to parse JSON from model response: {e}")
            return []

        if not isinstance(data, dict):
            warn("Visual subtitle review: model response is not a JSON object")
            return []

        raw_frames = data.get("frames")
        if not isinstance(raw_frames, list):
            warn("Visual subtitle review: model response missing 'frames' list")
            return []

        frames_by_n: dict[int, dict] = {}
        for f in raw_frames:
            if isinstance(f, dict):
                n_val = f.get("n")
                try:
                    frames_by_n[int(n_val)] = f
                except (TypeError, ValueError):
                    pass

        warnings: list[str] = []
        for item in extracted:
            idx = item["n"]
            entry = item["entry"]
            ts = item["timestamp"]
            expected_text = entry.text
            expected_norm = normalize_caption(expected_text)

            m_entry = frames_by_n.get(idx)
            if m_entry is None and idx - 1 < len(raw_frames) and isinstance(raw_frames[idx - 1], dict):
                m_entry = raw_frames[idx - 1]

            if not isinstance(m_entry, dict):
                warn(f"Visual subtitle review: missing or malformed review entry for frame {idx}")
                continue

            observed_caption = str(m_entry.get("caption") or "").strip()
            observed_norm = normalize_caption(observed_caption)
            ok = m_entry.get("ok", True)
            problem = str(m_entry.get("problem") or "").strip()

            if expected_norm != observed_norm:
                warnings.append(
                    f"Frame {idx} ('{expected_text}' @ {ts:.2f}s): text mismatch - "
                    f"expected '{expected_text}', observed '{observed_caption}'"
                )

            if ok is False or (problem and problem.lower() not in ("none", "null", "no", "ok", "n/a", "")):
                prob_desc = problem or "rendering defect reported"
                warnings.append(f"Frame {idx} ('{expected_text}' @ {ts:.2f}s): rendering problem - {prob_desc}")

        return warnings
