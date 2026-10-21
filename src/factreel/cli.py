"""Command line: ``factreel init | make | topics | doctor | voices | upload | run``."""
from __future__ import annotations

import argparse
import shutil
import sys
from importlib import resources
from pathlib import Path

from . import __version__
from .config import load_channel
from .log import configure, error, log

RENAMES = {"env.example": ".env.example", "gitignore": ".gitignore"}


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.directory)
    if (target / "channel.toml").exists() and not args.force:
        error(f"{target / 'channel.toml'} already exists (use --force to overwrite)")
        return 1
    src = resources.files("factreel") / "templates" / args.lang

    def copy(node, dest: Path) -> None:
        for item in node.iterdir():
            name = RENAMES.get(item.name, item.name)
            if item.is_dir():
                (dest / name).mkdir(parents=True, exist_ok=True)
                copy(item, dest / name)
            else:
                (dest / name).write_bytes(item.read_bytes())

    target.mkdir(parents=True, exist_ok=True)
    copy(src, target)
    for sub in ("output", "archive", "music"):
        (target / sub).mkdir(exist_ok=True)
    es = args.lang == "es"
    print(("Canal creado en" if es else "Channel created in") + f" {target.resolve()}\n")
    steps = [
        ("Edita channel.toml y facts.json (tus temas y hechos verificados).", "Edit channel.toml and facts.json (your topics and verified facts)."),
        ("Opcional: copia .env.example como .env y añade tus claves.", "Optional: copy .env.example to .env and add your API keys."),
        (f"Comprueba todo:   factreel doctor -c {target}", f"Check everything: factreel doctor -c {target}"),
        (f"Primer vídeo:     factreel make -c {target}", f"First video:      factreel make -c {target}"),
    ]
    for i, (s_es, s_en) in enumerate(steps, 1):
        print(f"  {i}. {s_es if es else s_en}")
    return 0


def _channel(args: argparse.Namespace):
    channel = load_channel(args.channel)
    configure(channel.root / "logs", quiet=getattr(args, "quiet", False))
    return channel


def _split(value: str | None) -> list[str] | None:
    return [v.strip() for v in value.split(",") if v.strip()] if value else None


def cmd_make(args: argparse.Namespace) -> int:
    from .pipeline import make_video

    channel = _channel(args)
    failures = 0
    for i in range(args.count):
        if args.count > 1:
            log(f"=== Video {i + 1}/{args.count} ===")
        try:
            result = make_video(channel, args.topic, offline=args.offline, voice_chain=_split(args.voice),
                                image_chain=_split(args.images), record_history=not args.no_history)
            print(f"\n✔ {result.video}\n  {result.meta['title']}  ({result.duration:.1f}s, voice: {result.voice})")
        except Exception as e:  # noqa: BLE001 - one failed video must not stop the batch
            failures += 1
            error(f"{type(e).__name__}: {e}")
            if args.debug:
                raise
    return 1 if failures else 0


def cmd_topics(args: argparse.Namespace) -> int:
    from .facts import History, load_topics

    channel = _channel(args)
    topics = load_topics(channel.path("facts_file"))
    history = History(channel.state_dir / "history.json")
    width = max(len(t["id"]) for t in topics)
    print(f"{'id':<{width}}  uses  weight  facts  angle")
    for t in sorted(topics, key=lambda t: history.uses(t["id"])):
        print(f"{t['id']:<{width}}  {history.uses(t['id']):>4}  {t.get('weight', 1):>6}  {len(t['facts']):>5}  {t['angle']}")
    return 0


def cmd_voices(args: argparse.Namespace) -> int:
    import asyncio

    import edge_tts

    try:
        voices = asyncio.run(edge_tts.list_voices())
    except Exception as e:  # noqa: BLE001 - network errors, etc.
        error(f"Could not list voices: {type(e).__name__}: {e}")
        return 1

    prefix = (args.lang or "").lower()

    def matches(locale: str) -> bool:
        locale = locale.lower()
        return not prefix or locale == prefix or locale.startswith(prefix + "-")

    found = sorted((v for v in voices if matches(v["Locale"])), key=lambda v: v["ShortName"])
    if not found:
        error(f"No voices found for language '{args.lang}'")
        return 1
    width = max(len(v["ShortName"]) for v in found)
    print(f"{'name':<{width}}  gender   locale")
    for v in found:
        print(f"{v['ShortName']:<{width}}  {v['Gender']:<7}  {v['Locale']}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import run

    return run(_channel(args), voices_only=args.voices, write_log=args.log)


def cmd_upload(args: argparse.Namespace) -> int:
    from .youtube import UploadError, service, upload_pending

    channel = _channel(args)
    try:
        if args.auth:
            service(channel)
            log("YouTube authorised.")
            return 0
        return 1 if upload_pending(channel, args.privacy) else 0
    except UploadError as e:
        error(str(e))
        return 1


def cmd_run(args: argparse.Namespace) -> int:
    made = cmd_make(args)
    args.auth = False
    uploaded = cmd_upload(args)  # uploads anything pending even if today's video failed
    return made or uploaded


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="factreel", description="Fact-checked faceless short videos.")
    p.add_argument("--version", action="version", version=f"factreel {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def with_channel(sp: argparse.ArgumentParser) -> argparse.ArgumentParser:
        sp.add_argument("-c", "--channel", default=".", help="channel folder (default: current folder)")
        sp.add_argument("-q", "--quiet", action="store_true", help="only warnings and errors")
        return sp

    s = sub.add_parser("init", help="create a channel folder from a template")
    s.add_argument("directory")
    s.add_argument("--lang", choices=["es", "en"], default="en")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_init)

    def make_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("-t", "--topic", help="topic id (default: queue.txt, then least used)")
        sp.add_argument("-n", "--count", type=int, default=1, help="number of videos")
        sp.add_argument("--offline", action="store_true", help="no script AI, offline images (archive/gradient)")
        sp.add_argument("--voice", help="override the voice chain, e.g. 'edge,system' or 'dummy'")
        sp.add_argument("--images", help="override the image chain, e.g. 'gradient'")
        sp.add_argument("--no-history", action="store_true", help="don't record it (for tests)")
        sp.add_argument("--debug", action="store_true", help="show the full traceback on errors")

    s = with_channel(sub.add_parser("make", help="generate video(s) into output/"))
    make_args(s)
    s.set_defaults(func=cmd_make)

    s = with_channel(sub.add_parser("topics", help="list topics and how often each was used"))
    s.set_defaults(func=cmd_topics)

    s = sub.add_parser("voices", help="list available Edge voices")
    s.add_argument("--lang", help="language prefix, e.g. 'es' matches es-ES, es-MX...")
    s.set_defaults(func=cmd_voices)

    s = with_channel(sub.add_parser("doctor", help="check FFmpeg, keys and every voice provider"))
    s.add_argument("--voices", action="store_true", help="only test the voices (fast, good for a scheduled task)")
    s.add_argument("--log", action="store_true", help="append results to logs/voice_health.log")
    s.set_defaults(func=cmd_doctor)

    s = with_channel(sub.add_parser("upload", help="upload pending videos to YouTube"))
    s.add_argument("--privacy", choices=["public", "unlisted", "private"])
    s.add_argument("--auth", action="store_true", help="only authorise the channel")
    s.set_defaults(func=cmd_upload)

    s = with_channel(sub.add_parser("run", help="make + upload (for scheduled tasks)"))
    make_args(s)
    s.add_argument("--privacy", choices=["public", "unlisted", "private"])
    s.set_defaults(func=cmd_run)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "init" and not shutil.which("ffmpeg") and args.command in ("make", "run"):
        error("FFmpeg is not installed or not on PATH: https://ffmpeg.org/download.html")
        return 1
    try:
        return args.func(args)
    except FileNotFoundError as e:
        error(str(e))
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
