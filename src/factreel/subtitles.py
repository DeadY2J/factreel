"""Word-by-word "karaoke" subtitles (.ass): short groups of words, the spoken word highlighted, a small pop-in."""
from __future__ import annotations

import re
from pathlib import Path

from .config import Channel

Word = tuple[float, float, str]


def ass_color(hex_color: str) -> str:
    """'#FF3C9A' -> '&H9A3CFF&' (ASS uses BBGGRR)."""
    c = hex_color.lstrip("#").upper()
    if len(c) != 6:
        raise ValueError(f"colour must be #RRGGBB, got {hex_color}")
    return f"&H{c[4:6]}{c[2:4]}{c[0:2]}&"


def ass_time(seconds: float) -> str:
    cs = int(round(max(seconds, 0) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def attach_punctuation(text: str, words: list[Word]) -> list[Word]:
    """Some engines return words without punctuation; take it back from the original text."""
    result, cursor = [], 0
    for start, end, word in words:
        pos = text.find(word, cursor)
        if pos == -1:
            result.append((start, end, word))
            continue
        stop = pos + len(word)
        while stop < len(text) and not text[stop].isspace() and not text[stop].isalnum():
            stop += 1
        result.append((start, end, text[cursor:stop].strip()))
        cursor = stop
    return result


def group_words(words: list[Word], max_words: int = 3, max_chars: int = 18) -> list[list[Word]]:
    """Short blocks that break at punctuation and pauses."""
    groups, current = [], []
    for i, w in enumerate(words):
        current.append(w)
        chars = sum(len(x[2]) + 1 for x in current)
        ends_phrase = w[2].rstrip("'\"‘’“”»")[-1:] in tuple(".,:;!?")
        pause = i + 1 < len(words) and words[i + 1][0] - w[1] > 0.35
        if len(current) >= max_words or chars >= max_chars or ends_phrase or pause:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def scene_start_times(scenes: list[dict], words: list[Word]) -> list[float]:
    """Second at which the voice starts each scene."""
    text = " ".join(s["text"] for s in scenes)
    positions, cursor = [], 0
    for _, _, word in words:
        pos = text.find(word, cursor)
        positions.append(pos if pos != -1 else cursor)
        if pos != -1:
            cursor = pos + len(word)
    starts, offset = [0.0], 0
    for scene in scenes[:-1]:
        offset += len(scene["text"]) + 1
        idx = next((i for i, p in enumerate(positions) if p >= offset), None)
        starts.append(words[idx][0] if idx is not None else starts[-1])
    return starts


def _clean(word: str, upper: bool) -> str:
    word = word.upper() if upper else word
    word = word.replace("{", "(").replace("}", ")")
    # drop quotes, keep apostrophes between letters/digits (GTA 6'S, it's)
    return re.sub(r"[\"“”«»]", "", re.sub(r"(?<![\w])['‘’]|['‘’](?![\w])", "", word))


def write_ass(channel: Channel, text: str, words: list[Word], path: Path) -> None:
    s = channel["subtitles"]
    w, h = int(channel["video"]["width"]), int(channel["video"]["height"])
    primary = "&H00" + ass_color(s["color"])[2:-1]  # style colours are &HAABBGGRR
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {w}\nPlayResY: {h}\nWrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n"
        f"Style: Default,{s['font']},{int(s['size'])},{primary},{primary},&H00000000,&H96000000,-1,0,0,0,100,100,2,0,1,"
        f"{int(s['outline'])},4,2,80,80,{int(s['margin_v'])},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    hl, base = ass_color(s["highlight"]), ass_color(s["color"])
    groups = group_words(attach_punctuation(text, words), int(s["max_words"]), int(s["max_chars"]))
    lines = [header]
    for g, group in enumerate(groups):
        next_start = groups[g + 1][0][0] if g + 1 < len(groups) else None
        group_end = group[-1][1] + 0.4 if next_start is None else min(group[-1][1] + 0.4, next_start)
        for k, (start, _, _) in enumerate(group):
            end = group[k + 1][0] if k + 1 < len(group) else group_end
            parts = [f"{{\\c{hl}}}{_clean(word, s['uppercase'])}{{\\c{base}}}" if j == k else _clean(word, s["uppercase"])
                     for j, (_, _, word) in enumerate(group)]
            pop = "{\\fscx80\\fscy80\\t(0,90,\\fscx100\\fscy100)}" if k == 0 else ""
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(max(end, start + 0.05))},Default,,0,0,0,,{pop}{' '.join(parts)}\n")
    path.write_text("".join(lines), encoding="utf-8")
