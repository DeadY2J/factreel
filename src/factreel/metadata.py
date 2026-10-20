"""Title, description, tags and hashtags. Written next to the MP4 as ``.json`` (for tools) and ``.txt``
(easy to read and to copy-paste into any platform)."""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

from .config import Channel
from .lang import pack


class _Keep(dict):
    """format_map helper: unknown {placeholders} are left as they are instead of crashing."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def teaser(text: str, max_chars: int = 200) -> str:
    sentences = re.findall(r"[^.!?]+[.!?]+['\"’”»]?", text) or [text]
    out = ""
    for s in sentences:
        if out and len(out) + len(s) > max_chars:
            break
        out += s
    return out.strip().rstrip(".!?") + "..."


def hashtags(channel: Channel, topic: dict, rng: random.Random | None = None) -> list[str]:
    m = channel["metadata"]
    rng = rng or random.Random()
    tags = list(m["hashtags_fixed"]) + [t for t in topic.get("hashtags", [])[:2] if t not in m["hashtags_fixed"]]
    pool = [t for t in m["hashtags_rotating"] if t not in tags]
    tags += rng.sample(pool, min(int(m["hashtags_rotating_count"]), len(pool)))
    return tags


def build(channel: Channel, story: dict, topic: dict, days: int | None, music: str = "") -> dict:
    m = channel["metadata"]
    title = story["title"]
    suffix = str(m.get("title_suffix") or "")
    if suffix and suffix.strip().lower() not in title.lower():
        title = f"{title}{suffix}"
    title = title.replace("<", "").replace(">", "")[:100]
    countdown = ""
    if days is not None and days > 0:
        countdown = pack(channel.language)["countdown_line"].format(days=days, event=channel["countdown"]["event"],
                                                                    date=channel["countdown"]["date"])
    values = {
        "teaser": teaser(story["text"]),
        "countdown": countdown,
        "music": f"🎵 {music}" if music else "",
        "disclaimer": str(m.get("disclaimer") or ""),
        "hashtags": " ".join(hashtags(channel, topic)),
        "sources": "\n".join(f"- {s}" for s in topic.get("sources", [])),
        "channel": channel["channel"]["name"],
        "title": story["title"],
    }
    description = str(m["description"]).format_map(_Keep(values))
    description = re.sub(r"\n{3,}", "\n\n", description).strip()
    tags = list(m.get("tags") or [])
    while len(", ".join(tags)) > 480:  # YouTube: ~500 characters for all tags
        tags.pop()
    return {"title": title, "description": description.replace("<", "").replace(">", "")[:4900], "tags": tags,
            "topic": story["topic"], "script": story["text"], "script_source": story.get("source", "ai")}


def write(meta: dict, video: Path) -> tuple[Path, Path]:
    j, t = video.with_suffix(".json"), video.with_suffix(".txt")
    j.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    t.write_text(f"TITLE: {meta['title']}\nTAGS: {', '.join(meta['tags'])}\nDESCRIPTION:\n{meta['description']}\n",
                 encoding="utf-8")
    return j, t


def read(video: Path) -> dict:
    j = video.with_suffix(".json")
    if j.is_file():
        return json.loads(j.read_text(encoding="utf-8"))
    title, tags, desc, in_desc = "", [], [], False  # legacy .txt format
    for line in video.with_suffix(".txt").read_text(encoding="utf-8").splitlines():
        if in_desc:
            desc.append(line)
        elif line.startswith("TITLE:"):
            title = line[6:].strip()
        elif line.startswith("TAGS:"):
            tags = [x.strip() for x in line[5:].split(",") if x.strip()]
        elif line.startswith("DESCRIPTION:"):
            in_desc = True
    return {"title": title or video.stem, "description": "\n".join(desc).strip(), "tags": tags}
