"""Voice providers. Each one is ``fn(channel, text, out_path) -> [(start_s, end_s, word), ...]``
and raises ``TTSError`` when it can't produce audio."""
from __future__ import annotations

import asyncio
import base64
import platform
import re
import shutil
import subprocess
from pathlib import Path

import requests

from ..cloudflare import Cloudflare, CloudflareError
from ..config import Channel, read_secret
from ..lang import pack
from ..log import log
from .timing import estimate_word_times, word_times_for


class TTSError(RuntimeError):
    pass


def _ffmpeg(*args: str) -> None:
    try:
        subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True, capture_output=True)
    except FileNotFoundError as e:
        raise TTSError("ffmpeg is not installed or not on PATH") from e
    except subprocess.CalledProcessError as e:
        raise TTSError(f"ffmpeg failed: {e.stderr.decode('utf-8', 'replace')[-200:]}") from e


def _retime(src: Path, dst: Path, tempo: float) -> float:
    """Change speed keeping pitch (ffmpeg atempo). Returns the tempo actually applied."""
    if abs(tempo - 1.0) < 1e-3:
        _ffmpeg("-i", str(src), "-b:a", "192k", str(dst))
        return 1.0
    _ffmpeg("-i", str(src), "-filter:a", f"atempo={tempo}", "-b:a", "192k", str(dst))
    return tempo


# ---------------------------------------------------------------- Microsoft Edge (free, no key)

async def _edge(text: str, out: Path, voice: str, rate: str, pitch: str) -> list:
    import edge_tts

    attempts, waited = 0, 0
    while True:
        attempts += 1
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
            words = []
            with out.open("wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        start = chunk["offset"] / 10_000_000  # 100 ns units -> seconds
                        words.append((start, start + chunk["duration"] / 10_000_000, chunk["text"]))
            if out.stat().st_size < 2000:
                raise TTSError("empty audio")
            return words
        except TTSError:
            raise
        except Exception as e:  # edge-tts raises many exception types
            msg = str(e)
            # 429 = too many requests in a row: wait and retry (20, 40, 60 s) before giving up
            if msg.startswith("429") and waited < 3:
                waited += 1
                log(f"  edge-tts: 429 too many requests, waiting {20 * waited} s")
                await asyncio.sleep(20 * waited)
                continue
            if attempts < 2:
                await asyncio.sleep(3)
                continue
            raise TTSError(msg[:160] or type(e).__name__) from e


def edge(channel: Channel, text: str, out: Path) -> list:
    c = channel["voice"]["edge"]
    voice = c.get("voice") or pack(channel.language)["default_voice"]
    words = asyncio.run(_edge(text, out, voice, c.get("rate", "+0%"), c.get("pitch", "+0Hz")))
    return words or word_times_for(channel, text, out)


# ---------------------------------------------------------------- ElevenLabs (paid / free tier, exact timings)

def elevenlabs_word_times(text: str, alignment: dict) -> list:
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    if len(chars) != len(text) or not (len(starts) == len(ends) == len(chars)):
        raise ValueError("alignment does not match the text")
    return [(starts[m.start()], ends[m.end() - 1], m.group()) for m in re.finditer(r"\S+", text)]


def elevenlabs(channel: Channel, text: str, out: Path) -> list:
    c = channel["voice"]["elevenlabs"]
    key = read_secret(c["api_key_env"])
    if not key:
        raise TTSError(f"missing {c['api_key_env']}")
    if len(text) > int(c.get("max_chars", 1500)):
        raise TTSError("text longer than [voice.elevenlabs] max_chars")
    headers = {"xi-api-key": key}
    try:
        sub = requests.get("https://api.elevenlabs.io/v1/user/subscription", headers=headers, timeout=30)
        if sub.ok:
            info = sub.json()
            left = info.get("character_limit", 0) - info.get("character_count", 0)
            if left < len(text) + 50:
                raise TTSError(f"monthly quota used up ({left} characters left)")
        res = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{c['voice_id']}/with-timestamps",
                            headers=headers, json={"text": text, "model_id": c["model"]}, timeout=180)
    except requests.RequestException as e:
        raise TTSError(str(e)[:150]) from e
    if not res.ok:
        raise TTSError(f"HTTP {res.status_code}: {res.text[:150]}")
    data = res.json()
    raw = out.with_suffix(".raw.mp3")
    raw.write_bytes(base64.b64decode(data["audio_base64"]))
    tempo = _retime(raw, out, float(c.get("tempo", 1.0)))
    raw.unlink(missing_ok=True)
    try:
        return [(s / tempo, e / tempo, w) for s, e, w in elevenlabs_word_times(text, data.get("alignment") or {})]
    except ValueError:
        return word_times_for(channel, text, out)


# ---------------------------------------------------------------- Cloudflare Workers AI (Deepgram Aura)

def cloudflare(channel: Channel, text: str, out: Path) -> list:
    c = channel["voice"]["cloudflare"]
    cf = Cloudflare(channel)
    try:
        res = cf.run(c["model"], estimate=len(text) * 2.73 + 60, json_body={"text": text, "speaker": c["speaker"]})
    except CloudflareError as e:
        raise TTSError(str(e)) from e
    if res.status_code != 200 or "audio" not in res.headers.get("content-type", "") or len(res.content) < 2000:
        raise TTSError(f"HTTP {res.status_code}: {res.text[:150]}")
    raw = out.with_suffix(".raw.mp3")
    raw.write_bytes(res.content)
    _retime(raw, out, float(c.get("tempo", 1.0)))
    raw.unlink(missing_ok=True)
    return word_times_for(channel, text, out)


# ---------------------------------------------------------------- Offline voice of the operating system

def system(channel: Channel, text: str, out: Path) -> list:
    """Windows SAPI (PowerShell), macOS ``say`` or Linux ``espeak-ng``/``espeak``. Works without internet."""
    c = channel["voice"]["system"]
    voice = str(c.get("voice") or "")
    tmp = channel.temp_dir
    txt = tmp / "system_voice.txt"
    txt.write_text(text, encoding="utf-8")
    os_name = platform.system()
    try:
        if os_name == "Windows":
            wav = tmp / "system_voice.wav"
            q = lambda p: str(p).replace("'", "''")  # noqa: E731 - PowerShell single-quote escaping
            select = f"$s.SelectVoice('{q(voice)}'); " if voice else ""
            script = (f"Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                      f"{select}$s.Rate = {int(c.get('rate', 0))}; $s.SetOutputToWaveFile('{q(wav)}'); "
                      f"$s.Speak([IO.File]::ReadAllText('{q(txt)}', [Text.Encoding]::UTF8)); $s.Dispose()")
            subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, capture_output=True, timeout=180)
        elif os_name == "Darwin":
            wav = tmp / "system_voice.aiff"
            subprocess.run(["say", *(["-v", voice] if voice else []), "-o", str(wav), "-f", str(txt)], check=True,
                           capture_output=True, timeout=180)
        else:
            exe = shutil.which("espeak-ng") or shutil.which("espeak")
            if not exe:
                raise TTSError("no offline voice found (install espeak-ng)")
            wav = tmp / "system_voice.wav"
            subprocess.run([exe, "-v", voice or channel.language, "-w", str(wav), "-f", str(txt)], check=True,
                           capture_output=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as e:
        raise TTSError(f"system voice failed: {str(e)[:150]}") from e
    _ffmpeg("-i", str(wav), "-ar", "44100", "-b:a", "192k", str(out))
    return word_times_for(channel, text, out)


# ---------------------------------------------------------------- Silent placeholder (tests, previews, CI)

def dummy(channel: Channel, text: str, out: Path) -> list:
    """Silent track with estimated word timings: lets you preview images and subtitles without any voice service."""
    wps = float(channel["voice"]["dummy"].get("words_per_second", 2.6))
    total = max(2.0, len(text.split()) / wps)
    _ffmpeg("-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", f"{total:.2f}", "-b:a", "128k", str(out))
    return estimate_word_times(text, total)


PROVIDERS = {"edge": edge, "elevenlabs": elevenlabs, "cloudflare": cloudflare, "system": system, "dummy": dummy}
