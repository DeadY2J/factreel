"""Facts file, topic rotation and publishing history.

``facts.json`` format::

    {
      "topics": [
        {
          "id": "release_date",                   # unique, used in history and queue.txt
          "angle": "when the game comes out",     # what the video is about (given to the AI)
          "facts": ["Fact one.", "RUMOR: fact two."],
          "sources": ["https://..."],             # for you and your viewers; never sent to the AI
          "hashtags": ["#releasedate"],           # optional, added to this topic's videos
          "weight": 2                             # optional, >1 = chosen more often
        }
      ]
    }
"""
from __future__ import annotations

import datetime as dt
import json
import random
import time
from pathlib import Path

from .config import Channel
from .log import log


class FactsError(ValueError):
    pass


def load_topics(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise FactsError(f"Facts file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise FactsError(f"{path} is not valid JSON: {e}") from e
    topics = data.get("topics") if isinstance(data, dict) else None
    if not topics:
        raise FactsError(f"{path} has no 'topics' list")
    seen = set()
    for i, t in enumerate(topics):
        for key in ("id", "angle", "facts"):
            if not t.get(key):
                raise FactsError(f"Topic #{i + 1} in {path.name} is missing '{key}'")
        if t["id"] in seen:
            raise FactsError(f"Duplicated topic id '{t['id']}' in {path.name}")
        if not isinstance(t["facts"], list) or not all(isinstance(f, str) and f.strip() for f in t["facts"]):
            raise FactsError(f"Topic '{t['id']}': 'facts' must be a list of non-empty strings")
        seen.add(t["id"])
    return topics


class History:
    """Published titles/topics, stored in ``.factreel/history.json``."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self.items: list[dict] = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            self.items = []

    def uses(self, topic_id: str) -> int:
        return sum(1 for h in self.items if h.get("topic") == topic_id)

    @property
    def titles(self) -> set[str]:
        return {str(h.get("title", "")).lower() for h in self.items}

    def recent_titles(self, n: int = 30) -> list[str]:
        return [h["title"] for h in self.items[-n:] if h.get("title")]

    def add(self, story: dict, video: str | None = None) -> None:
        self.items.append({"date": time.strftime("%Y-%m-%d %H:%M"), "title": story["title"],
                           "topic": story["topic"], "video": video})
        self.path.write_text(json.dumps(self.items, ensure_ascii=False, indent=2), encoding="utf-8")


def pop_queue(queue_file: Path, valid_ids: set[str]) -> str | None:
    """First valid topic id from ``queue.txt`` (one id per line, ``#`` = comment). It is removed from the file."""
    try:
        lines = [ln.strip() for ln in queue_file.read_text(encoding="utf-8").splitlines()]
    except FileNotFoundError:
        return None
    queue = [ln for ln in lines if ln and not ln.startswith("#")]
    chosen = None
    while queue and chosen is None:
        candidate = queue.pop(0)
        if candidate in valid_ids:
            chosen = candidate
        else:
            log(f"queue.txt: unknown topic id '{candidate}', skipped")
    comments = [ln for ln in lines if ln.startswith("#")]
    queue_file.write_text("".join(f"{ln}\n" for ln in comments + queue), encoding="utf-8")
    return chosen


def choose_topic(topics: list[dict], history: History, queue_file: Path | None = None,
                 forced: str | None = None, rng: random.Random | None = None) -> dict:
    """Forced id > queue.txt > least used topic (``uses / weight``, ties broken at random)."""
    rng = rng or random.Random()
    by_id = {t["id"]: t for t in topics}
    if forced:
        if forced not in by_id:
            raise FactsError(f"Unknown topic '{forced}'. Available: {', '.join(by_id)}")
        return by_id[forced]
    if queue_file is not None:
        queued = pop_queue(queue_file, set(by_id))
        if queued:
            log(f"Topic from queue.txt: {queued}")
            return by_id[queued]
    return min(topics, key=lambda t: (history.uses(t["id"]) / max(float(t.get("weight", 1)), 0.01), rng.random()))


def days_until(channel: Channel, today: dt.date | None = None) -> int | None:
    """Days left until ``[countdown].date`` or ``None`` if there is no countdown."""
    date = str(channel["countdown"].get("date") or "").strip()
    if not date or not channel["countdown"].get("event"):
        return None
    try:
        target = dt.date.fromisoformat(date)
    except ValueError as e:
        raise FactsError(f"[countdown] date must be YYYY-MM-DD, got '{date}'") from e
    return (target - (today or dt.date.today())).days
