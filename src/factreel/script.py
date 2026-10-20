"""Script writing with anti-hallucination guards.

The AI only sees the verified facts of one topic. Every answer goes through:

1. structure checks (valid JSON, number of scenes, word count),
2. **number guard**: any number in the script must appear in the facts (or be the countdown),
3. **repetition guard**: no 4-word sequence may appear twice,
4. **rumor guard**: if every fact is a rumor, the script must say so,
5. **fact-check pass**: a second, temperature-0 call lists unsupported claims (title included).

Rejected answers are sent back to the model with the reason, up to ``retries`` times. If everything
fails, the facts are read as they are (``fallback_script``): less flashy, but always correct.
"""
from __future__ import annotations

import re

from .config import Channel
from .lang import expand_months, pack
from .llm import LLM, LLMError, extract_json
from .log import log, warn


class ScriptRejected(ValueError):
    pass


def norm_words(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower())


def allowed_numbers(channel: Channel, topic: dict, days: int | None) -> set[str]:
    sources = " ".join(topic["facts"]) + " " + topic.get("angle", "") + " " + channel["channel"]["name"]
    sources += " " + str(channel["countdown"].get("event") or "")
    nums = set(re.findall(r"\d+", sources))
    nums.update(str(n) for n in channel["script"].get("allowed_numbers", []))
    if days is not None:
        nums.update({str(days), str(max(days, 0) // 7)})
    return nums


def repeated_ngrams(text: str, n: int = 4) -> list[str]:
    toks = norm_words(text)
    grams = [" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1)]
    return sorted({g for g in grams if grams.count(g) > 1})


def parse_script(channel: Channel, content: str, topic: dict, days: int | None, used_titles: set[str],
                 max_words: int | None = None) -> dict:
    """Validate a model answer. Returns the story dict or raises ``ScriptRejected`` with a reason the model can act on."""
    sc = channel["script"]
    lang = channel.language
    p = pack(lang)
    max_words = max_words or int(sc["max_words"])
    try:
        data = extract_json(content)
    except ValueError as e:
        raise ScriptRejected(f"invalid JSON ({e})") from e
    title = " ".join(str(data.get("title", "")).split())
    scenes = []
    for scene in data.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        text = expand_months(" ".join(str(scene.get("text", "")).split()), lang)
        text = p["cta_regex"].sub("", text).strip()  # the sign-off is fixed: remove the model's own CTA
        prompt = " ".join(str(scene.get("prompt", "")).split())
        if text and prompt:
            scenes.append({"text": text, "prompt": prompt})
    expected = int(sc["scenes"])
    if not title:
        raise ScriptRejected("missing title")
    if not expected - 1 <= len(scenes) <= expected + 1:
        raise ScriptRejected(f"wrong number of scenes ({len(scenes)}, expected {expected})")
    text = " ".join(s["text"] for s in scenes)
    words = len(text.split())
    if words > max_words:
        raise ScriptRejected(f"too long: {words} words. Cut at least {words - int(sc['max_words']) + 6} words")
    if words < int(sc["min_words"]):
        raise ScriptRejected(f"too short: {words} words")
    if title.lower() in used_titles:
        raise ScriptRejected(f"title already used: {title}")
    rep = repeated_ngrams(text)
    if rep:
        raise ScriptRejected(f"the same words are repeated ({rep[:3]}): say each thing only once")
    if re.search(r"(^|[.!?]\s+)\d+\s+(days?|días?)\s*(left|to go|más)?[.!?]", text, re.I):
        raise ScriptRejected("the day count is a bare fragment (like '36 days.'): put it inside a full sentence")
    extra = set(re.findall(r"\d+", text + " " + title)) - allowed_numbers(channel, topic, days)
    if extra:
        raise ScriptRejected(f"numbers that are not in the facts: {sorted(extra)}")
    facts = topic["facts"]
    if facts and all(f.strip().upper().startswith("RUMOR") for f in facts):
        if not any(w in text.lower() for w in p["rumor_words"]):
            raise ScriptRejected("every fact is a rumor but the script presents it as confirmed")
    sign_off = str(channel["channel"].get("sign_off") or "").strip()
    if sign_off:
        scenes[-1]["text"] = f"{scenes[-1]['text']} {sign_off}"
        text = f"{text} {sign_off}"
    return {"title": title[:70], "text": text, "scenes": scenes, "topic": topic["id"], "source": "ai"}


def countdown_text(channel: Channel, days: int | None) -> str:
    p = pack(channel.language)
    event = channel["countdown"].get("event")
    if days is None:
        return ""
    if days <= 0:
        return p["countdown_past"].format(event=event)
    return p["countdown_hint"].format(event=event, days=days)


def verify_script(llm: LLM, channel: Channel, topic: dict, days: int | None, text: str) -> list[str]:
    """Second pass: the model checks each claim against the facts. Returns unsupported claims ([] = fine/unknown)."""
    p = pack(channel.language)
    note = p["countdown_note"] if days is not None else ""
    facts = "\n".join(f"- {f}" for f in topic["facts"])
    user = f"Facts:\n{facts}\n" + (f"Days until {channel['countdown']['event']}: {days}\n" if days is not None else "")
    user += f"\nScript:\n{text}"
    try:
        answer = llm.chat([{"role": "system", "content": p["verify_prompt"].format(countdown_note=note)},
                           {"role": "user", "content": user}], temperature=0, max_tokens=600)
        data = extract_json(answer)
    except (LLMError, ValueError):
        return []  # the checker failing must not block publishing: the other guards still apply
    if data.get("ok", True) and not data.get("unsupported"):
        return []
    bad = [str(x) for x in data.get("unsupported") or []]
    if days is not None:  # checkers sometimes flag a correct countdown; the number guard already covers it
        bad = [b for b in bad if not re.search(rf"\b{days}\s+(days?|días?)\b", b, re.I)]
    sign_off = str(channel["channel"].get("sign_off") or "").strip().lower()
    return [b for b in bad if not (sign_off and b.strip().lower() in sign_off)]


def write_ai_script(channel: Channel, llm: LLM, topic: dict, days: int | None, used_titles: set[str],
                    recent_titles: list[str]) -> dict | None:
    sc = channel["script"]
    p = pack(channel.language)
    min_w, max_w, n_scenes = int(sc["min_words"]), int(sc["max_words"]), int(sc["scenes"])
    min_target, max_target = min_w + (max_w - min_w) // 4, max_w - (max_w - min_w) // 6
    extra = f"\n- {sc['extra_rules'].strip()}" if str(sc.get("extra_rules") or "").strip() else ""
    img_extra = f"\n- {sc['image_rules'].strip()}" if str(sc.get("image_rules") or "").strip() else ""
    system = p["script_prompt"].format(
        channel=channel["channel"]["name"], min_target=min_target, max_target=max_target, max_words=max_w,
        scenes=n_scenes, countdown_rule=p["countdown_rule"] if days is not None else "",
        extra_rules=extra, image_rules=img_extra)
    user = p["user_msg"].format(angle=topic["angle"], facts="\n".join(f"- {f}" for f in topic["facts"]),
                                countdown=countdown_text(channel, days),
                                recent="\n".join(f"- {t}" for t in recent_titles) or "- (none)")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    near_miss: tuple[int, str] | None = None
    retries = int(sc["retries"])
    for attempt in range(1, retries + 1):
        log(f"Writing script with {llm.model} (topic {topic['id']}, attempt {attempt}/{retries})...")
        try:
            content = llm.chat(messages)
        except LLMError as e:
            warn(f"LLM error: {e}")
            if e.fatal:
                return None
            continue
        try:
            story = parse_script(channel, content, topic, days, used_titles)
            if sc.get("fact_check", True):
                bad = verify_script(llm, channel, topic, days, f"Title: {story['title']}\n{story['text']}")
                if bad:
                    raise ScriptRejected("claims not supported by the facts: " + " | ".join(bad)[:300])
            return story
        except ScriptRejected as e:
            log(f"  Script rejected: {e}")
            m = re.match(r"too long: (\d+) words", str(e))
            if m and int(m.group(1)) <= max_w + int(sc["grace_words"]) and (not near_miss or int(m.group(1)) < near_miss[0]):
                near_miss = (int(m.group(1)), content)
            messages += [{"role": "assistant", "content": content},
                         {"role": "user", "content": p["rewrite"].format(error=e, min_target=min_target,
                                                                         max_target=max_target, scenes=n_scenes)}]
    if near_miss:  # a slightly longer video beats reading the raw facts
        try:
            story = parse_script(channel, near_miss[1], topic, days, used_titles, max_words=max_w + int(sc["grace_words"]))
            if not sc.get("fact_check", True) or not verify_script(llm, channel, topic, days,
                                                                   f"Title: {story['title']}\n{story['text']}"):
                log(f"Using the shortest attempt ({near_miss[0]} words, slightly over the limit).")
                return story
        except ScriptRejected as e:
            log(f"  Shortest attempt rejected too: {e}")
    return None


def fallback_script(channel: Channel, topic: dict, days: int | None) -> dict:
    """No AI: read the facts as they are, split into scenes."""
    p = pack(channel.language)
    sentences = []
    if days is not None and days > 0 and channel["countdown"].get("event"):
        sentences.append(p["countdown_sentence"].format(days=days, event=channel["countdown"]["event"]))
    for fact in topic["facts"][:3]:
        fact = re.sub(r"^RUMOR:\s*", "Rumor: ", fact.strip(), flags=re.I)
        sentences.append(fact if fact[-1:] in ".!?" else fact + ".")
    sign_off = str(channel["channel"].get("sign_off") or "").strip()
    if sign_off:
        sentences.append(sign_off)
    n = max(1, min(int(channel["script"]["scenes"]), len(sentences)))
    per = -(-len(sentences) // n)
    chunks = [" ".join(sentences[i:i + per]) for i in range(0, len(sentences), per)]
    angle = topic["angle"][:1].upper() + topic["angle"][1:]
    return {"title": angle[:55], "topic": topic["id"], "text": " ".join(chunks), "source": "facts",
            "scenes": [{"text": c, "prompt": fallback_image_prompt(channel, topic)} for c in chunks]}


def fallback_image_prompt(channel: Channel, topic: dict) -> str:
    """Image prompt without AI: the topic's own ``image_prompt``, else the channel's image rules.
    The angle alone is a poor prompt (often not in English, and image models only understand English well)."""
    if topic.get("image_prompt"):
        return topic["image_prompt"]
    rules = str(channel["script"].get("image_rules") or "").strip()
    return f"{rules} Theme: {topic['angle']}" if rules else topic["angle"]
