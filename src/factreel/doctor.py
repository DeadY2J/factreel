"""``factreel doctor``: checks the whole toolchain and every provider, and tells you what to fix.

With ``--log`` it appends one line per voice provider to ``logs/voice_health.log`` (handy as a scheduled
task) and creates ``logs/VOICE_BACK_<provider>.txt`` the first time a provider that was down works again.
"""
from __future__ import annotations

import shutil
import subprocess
import time

from . import tts
from .config import Channel, read_secret
from .facts import FactsError, load_topics
from .llm import LLM, LLMError

OK, BAD, SKIP = "✔", "✘", "–"


def _line(mark: str, name: str, detail: str) -> str:
    return f"  {mark} {name:<18} {detail}"


def check_tools() -> list[str]:
    out = []
    for exe in ("ffmpeg", "ffprobe"):
        path = shutil.which(exe)
        if not path:
            out.append(_line(BAD, exe, "not found: install FFmpeg and add it to PATH (https://ffmpeg.org/download.html)"))
            continue
        ver = subprocess.run([exe, "-version"], capture_output=True, text=True).stdout.split("\n")[0]
        out.append(_line(OK, exe, ver[:70]))
    if shutil.which("ffmpeg"):
        filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        for f in ("ass", "xfade", "loudnorm"):
            present = f" {f} " in filters
            out.append(_line(OK if present else SKIP if f == "ass" else BAD, f"ffmpeg:{f}", "available" if present else
                             "missing: macOS 'brew install ffmpeg-full', Windows a 'full' build from gyan.dev"
                             + (" (videos will have no subtitles)" if f == "ass" else "")))
    return out


def check_config(channel: Channel) -> list[str]:
    try:
        topics = load_topics(channel.path("facts_file"))
        facts = sum(len(t["facts"]) for t in topics)
        return [_line(OK, "facts", f"{len(topics)} topics, {facts} facts")]
    except FactsError as e:
        return [_line(BAD, "facts", str(e))]


def check_llm(channel: Channel) -> list[str]:
    llm = LLM(channel)
    if not llm.available:
        return [_line(SKIP, "llm", f"{channel['llm']['api_key_env']} not set: scripts will read the facts as they are")]
    try:
        llm.chat([{"role": "user", "content": "Reply with: ok"}], max_tokens=5, temperature=0)
        return [_line(OK, "llm", f"{llm.model} responds")]
    except LLMError as e:
        return [_line(BAD, "llm", str(e)[:100])]


def check_voices(channel: Channel, providers: list[str] | None = None, write_log: bool = False) -> list[str]:
    out = []
    sample = "Voice check." if channel.language == "en" else "Prueba de voz."
    logs_dir = channel.root / "logs"
    for name in providers or channel["voice"]["chain"]:
        fn = tts.PROVIDERS.get(name)
        if fn is None:
            out.append(_line(BAD, f"voice:{name}", "unknown provider"))
            continue
        target = channel.temp_dir / f"doctor_{name}.mp3"
        t0 = time.time()
        try:
            fn(channel, sample, target)
            ok, detail = True, f"OK ({time.time() - t0:.1f}s)"
        except tts.TTSError as e:
            ok, detail = False, str(e)[:110]
        except Exception as e:  # noqa: BLE001 - doctor must report, never crash
            ok, detail = False, f"{type(e).__name__}: {str(e)[:100]}"
        recovered = tts.record_health(channel, name, ok, detail)
        mark = OK if ok else SKIP if detail.startswith("missing") else BAD
        out.append(_line(mark, f"voice:{name}", detail + ("  (back after being down!)" if recovered else "")))
        if write_log:
            logs_dir.mkdir(exist_ok=True)
            with (logs_dir / "voice_health.log").open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M')} | {name} | {'OK' if ok else 'DOWN'} | {detail}\n")
            if recovered:
                (logs_dir / f"VOICE_BACK_{name}.txt").write_text(
                    f"{name} works again since {time.strftime('%Y-%m-%d %H:%M')}.\n", encoding="utf-8")
    return out


def check_keys(channel: Channel) -> list[str]:
    out = []
    pairs = [("cloudflare", channel["cloudflare"]["account_id_env"]), ("cloudflare", channel["cloudflare"]["api_token_env"]),
             ("nvidia images", channel["images"]["nvidia"]["api_key_env"]),
             ("elevenlabs", channel["voice"]["elevenlabs"]["api_key_env"])]
    for name, env in pairs:
        out.append(_line(OK if read_secret(env) else SKIP, name, f"{env} {'set' if read_secret(env) else 'not set'}"))
    secrets = channel.root / channel["youtube"]["client_secrets"]
    out.append(_line(OK if secrets.is_file() else SKIP, "youtube", f"{secrets.name} {'found' if secrets.is_file() else 'not found (only needed to upload)'}"))
    return out


def run(channel: Channel, voices_only: bool = False, write_log: bool = False) -> int:
    sections = [] if voices_only else [("Tools", check_tools()), ("Channel", check_config(channel)),
                                       ("API keys", check_keys(channel)), ("Script AI", check_llm(channel))]
    sections.append(("Voices", check_voices(channel, write_log=write_log)))
    bad, fatal = 0, False
    for title, lines in sections:
        print(f"\n{title}")
        for line in lines:
            print(line)
            is_bad = line.lstrip().startswith(BAD)
            bad += is_bad
            fatal |= is_bad and title in ("Tools", "Channel")
    if not any(line.lstrip().startswith(OK) for line in sections[-1][1]):
        fatal = True
        print("\nNo voice provider works: add 'system' or check your connection.")
    print("\nAll good." if not bad else f"\n{bad} problem(s) found" + (" (video generation will fail)." if fatal else
                                                                      " (fallbacks will cover them)."))
    return 1 if fatal else 0
