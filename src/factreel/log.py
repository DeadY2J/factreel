"""Tiny logging helper: one ``log()`` that prints to the console and, once configured, to a monthly file."""
from __future__ import annotations

import sys
import time
from pathlib import Path

_log_file: Path | None = None
_quiet = False

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass


def configure(log_dir: Path | None = None, quiet: bool = False) -> None:
    global _log_file, _quiet
    _quiet = quiet
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        _log_file = log_dir / f"factreel_{time.strftime('%Y-%m')}.log"


def log(msg: str, *, level: str = "INFO") -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {level:<5} | {msg}"
    if not _quiet or level != "INFO":
        print(msg if level == "INFO" else f"[{level}] {msg}", flush=True)
    if _log_file is not None:
        try:
            with _log_file.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:  # pragma: no cover
            pass


def warn(msg: str) -> None:
    log(msg, level="WARN")


def error(msg: str) -> None:
    log(msg, level="ERROR")
