"""Word timings for providers that don't return them (estimate, or Whisper aligned to the script)."""
from __future__ import annotations

import base64
import difflib
import re
import subprocess

from ..cloudflare import Cloudflare, CloudflareError
from ..config import Channel
from ..lang import pack
from ..log import log

Word = tuple[float, float, str]


def media_duration(path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def estimate_word_times(text: str, total: float) -> list[Word]:
    """Spread the words over ``total`` seconds, weighted by length and punctuation pauses."""
    tokens = text.split()
    if not tokens:
        return []
    weights = [len(t) + 2 + (6 if t[-1:] in ".!?" else 3 if t[-1:] in ",;:—" else 0) for t in tokens]
    scale = max(total - 0.2, 0.1) / sum(weights)
    words, t = [], 0.0
    for tok, w in zip(tokens, weights):
        words.append((t, t + w * scale * 0.85, tok))
        t += w * scale
    return words


def _norm(w: str) -> str:
    return re.sub(r"[^\w]", "", w.lower())


def align_to_script(text: str, heard: list[Word]) -> list[Word]:
    """Put the timings Whisper heard on the script's words (the ones shown on screen).
    Words Whisper wrote differently (numbers, names) are interpolated between their neighbours."""
    tokens = text.split()
    matcher = difflib.SequenceMatcher(None, [_norm(t) for t in tokens], [_norm(w[2]) for w in heard], autojunk=False)
    times: list[tuple[float, float] | None] = [None] * len(tokens)
    for tag, i1, i2, j1, _j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                times[i1 + k] = (heard[j1 + k][0], heard[j1 + k][1])
    end_all = heard[-1][1] if heard else 0.0
    i = 0
    while i < len(tokens):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(tokens) and times[j] is None:
            j += 1
        t0 = times[i - 1][1] if i > 0 else 0.0
        t1 = max(times[j][0] if j < len(tokens) else end_all, t0)
        weights = [max(1, len(_norm(tokens[k]))) for k in range(i, j)]
        acc = t0
        for k, w in zip(range(i, j), weights):
            d = (t1 - t0) * w / sum(weights)
            times[k] = (acc, acc + d * 0.9)
            acc += d
        i = j
    return [(st, en, tok) for (st, en), tok in zip(times, tokens)]


def word_times_for(channel: Channel, text: str, audio_path) -> list[Word]:
    """Whisper (Cloudflare) aligned to the script; if not available, estimated from the audio length."""
    cf = Cloudflare(channel)
    try:
        with open(audio_path, "rb") as f:
            audio = base64.b64encode(f.read()).decode()
        res = cf.run(channel["cloudflare"]["whisper_model"], estimate=60,
                     json_body={"audio": audio, "language": pack(channel.language)["whisper_lang"]}, timeout=180)
        data = res.json()
        if not data.get("success"):
            raise CloudflareError(str(data.get("errors"))[:150])
        heard = [(w["start"], w["end"], w["word"].strip())
                 for seg in data["result"].get("segments") or [] for w in seg.get("words") or []]
        if len(heard) < 0.6 * len(text.split()):
            raise CloudflareError(f"Whisper only returned {len(heard)} words")
        log(f"  Word timings from Whisper ({len(heard)} heard).")
        return align_to_script(text, heard)
    except (CloudflareError, ValueError, KeyError, OSError) as e:
        log(f"  Whisper not available ({str(e)[:100]}); word timings are estimated.")
        return estimate_word_times(text, media_duration(audio_path))
