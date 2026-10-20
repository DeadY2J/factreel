import json

import pytest

from factreel.facts import load_topics
from factreel.script import ScriptRejected, fallback_script, parse_script, repeated_ngrams, write_ai_script

TOPIC = {"id": "venus_day", "angle": "a day on Venus is longer than its year",
         "facts": ["Venus takes about 243 Earth days to spin once on its axis.",
                   "Venus takes about 225 Earth days to orbit the Sun."]}


def answer(scenes, title="Venus breaks the rules 🌕"):
    return "Sure! ```json\n" + json.dumps({"title": title, "scenes": [{"text": t, "prompt": "venus"} for t in scenes]}) + "\n```"


GOOD = ["A day on Venus lasts longer than its whole year.", "It needs about 243 Earth days to spin once.",
        "But it circles the Sun in only about 225 Earth days.", "Would you survive a day that long on Venus?"]


def test_good_script_gets_sign_off(channel_en):
    story = parse_script(channel_en, answer(GOOD), TOPIC, None, set())
    assert story["text"].endswith("Follow for one space fact a day.")
    assert len(story["scenes"]) == 4
    assert story["topic"] == "venus_day"


def test_invented_number_is_rejected(channel_en):
    bad = GOOD[:2] + ["It is 470 degrees hot and circles the Sun in about 225 days.", GOOD[3]]
    with pytest.raises(ScriptRejected, match="470"):
        parse_script(channel_en, answer(bad), TOPIC, None, set())


def test_countdown_number_is_allowed(channel_en):
    s = ["Only 12 days until launch, and Venus still beats us.", *GOOD[1:]]
    parse_script(channel_en, answer(s), TOPIC, 12, set())


def test_too_long_and_too_short(channel_en):
    with pytest.raises(ScriptRejected, match="too long"):
        parse_script(channel_en, answer([g + " " + g.lower() for g in GOOD] * 1), TOPIC, None, set())
    with pytest.raises(ScriptRejected, match="too short"):
        parse_script(channel_en, answer(["Venus.", "Slow.", "Very slow.", "Wow?"]), TOPIC, None, set())


def test_repeated_idea_is_rejected(channel_en):
    s = GOOD[:3] + ["It needs about 243 Earth days, can you believe it?"]
    with pytest.raises(ScriptRejected, match="repeated"):
        parse_script(channel_en, answer(s), TOPIC, None, set())


def test_used_title_is_rejected(channel_en):
    with pytest.raises(ScriptRejected, match="title already used"):
        parse_script(channel_en, answer(GOOD), TOPIC, None, {"venus breaks the rules 🌕"})


def test_ai_call_to_action_is_removed(channel_en):
    s = GOOD[:3] + ["Would you survive a day that long on Venus? Subscribe to my channel for more."]
    story = parse_script(channel_en, answer(s), TOPIC, None, set())
    assert "Subscribe" not in story["text"]


def test_rumor_must_be_labelled(channel_en):
    topic = {**TOPIC, "facts": ["RUMOR: " + f for f in TOPIC["facts"]]}
    with pytest.raises(ScriptRejected, match="rumor"):
        parse_script(channel_en, answer(GOOD), topic, None, set())
    labelled = ["Reportedly, a day on Venus lasts longer than its year."] + GOOD[1:]
    parse_script(channel_en, answer(labelled), topic, None, set())


def test_spanish_months_and_cta(channel_es):
    topic = {"id": "x", "angle": "fecha", "facts": ["El lanzamiento es el 19 de noviembre de 2026."]}
    s = ["El gran día llega el 19 de nov. de 2026 y queda poquísimo.", "Todo el mundo habla de esa fecha marcada.",
         "Nadie quiere perderse ese momento tan esperado.", "¿Tú ya lo tienes apuntado? Suscríbete al canal."]
    story = parse_script(channel_es, answer(s, "La fecha clave 🚀"), topic, None, set())
    assert "noviembre" in story["text"] and "Suscríbete" not in story["text"]


def test_repeated_ngrams():
    assert repeated_ngrams("one two three four and one two three four") == ["one two three four"]
    assert repeated_ngrams("all different words here today") == []


def test_fallback_script_uses_only_facts(channel_es):
    topic = load_topics(channel_es.path("facts_file"))[0]
    story = fallback_script(channel_es, topic, None)
    assert not story["text"].startswith("Solo faltan")
    channel_es.cfg["countdown"] = {"event": "el lanzamiento", "date": "2030-01-01"}
    assert fallback_script(channel_es, topic, 30)["text"].startswith("Solo faltan 30 días para el lanzamiento.")
    assert topic["facts"][0] in story["text"]
    assert story["source"] == "facts"


class FakeLLM:
    model = "fake"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, **kw):
        self.calls.append(messages)
        return self.replies.pop(0)


def test_ai_retries_until_valid_and_fact_checks(channel_en):
    bad = answer(GOOD[:2] + ["It is 470 degrees hot there.", GOOD[3]])
    llm = FakeLLM([bad, answer(GOOD), '{"ok": true, "unsupported": []}'])
    story = write_ai_script(channel_en, llm, TOPIC, None, set(), [])
    assert story and story["source"] == "ai"
    assert "Rejected" in llm.calls[1][-1]["content"]  # the reason was sent back to the model


def test_fact_check_rejection(channel_en):
    flagged = '{"ok": false, "unsupported": ["A day on Venus lasts longer than its whole year."]}'
    replies = []
    for _ in range(int(channel_en["script"]["retries"])):
        replies += [answer(GOOD), flagged]
    story = write_ai_script(channel_en, FakeLLM(replies), TOPIC, None, set(), [])
    assert story is None
