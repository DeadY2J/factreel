import datetime as dt
import json
import random

import pytest

from factreel.cli import main
from factreel.facts import FactsError, History, choose_topic, days_until, load_topics, validate_topics


def test_load_and_validate(tmp_path):
    p = tmp_path / "facts.json"
    p.write_text(json.dumps({"topics": [{"id": "a", "angle": "x", "facts": ["f"]}, {"id": "a", "angle": "y", "facts": ["g"]}]}))
    with pytest.raises(FactsError, match="Duplicated"):
        load_topics(p)
    p.write_text(json.dumps({"topics": [{"id": "a", "facts": ["f"]}]}))
    with pytest.raises(FactsError, match="angle"):
        load_topics(p)


def test_least_used_and_weight(tmp_path):
    topics = [{"id": "a", "angle": "", "facts": []}, {"id": "b", "angle": "", "facts": [], "weight": 3}]
    h = History(tmp_path / "h.json")
    for t in ("a", "b", "b"):
        h.add({"title": t, "topic": t})
    # a: 1 use / 1, b: 2 uses / 3 -> b wins
    assert choose_topic(topics, h, rng=random.Random(1))["id"] == "b"
    assert History(tmp_path / "h.json").uses("b") == 2


def test_queue_goes_first_and_is_consumed(tmp_path):
    topics = [{"id": "a", "angle": "", "facts": []}, {"id": "b", "angle": "", "facts": []}]
    q = tmp_path / "queue.txt"
    q.write_text("# comment\nunknown\nb\na\n")
    h = History(tmp_path / "h.json")
    assert choose_topic(topics, h, q)["id"] == "b"
    assert q.read_text() == "# comment\na\n"


def test_forced_unknown_topic(tmp_path):
    with pytest.raises(FactsError, match="Unknown topic"):
        choose_topic([{"id": "a", "angle": "", "facts": []}], History(tmp_path / "h.json"), forced="zzz")


def test_days_until(channel_en):
    assert days_until(channel_en) is None
    channel_en.cfg["countdown"] = {"event": "launch", "date": "2026-11-19"}
    assert days_until(channel_en, dt.date(2026, 11, 9)) == 10


def _clean_topic(**overrides):
    topic = {
        "id": "moon_distance",
        "angle": "how far away the Moon is",
        "facts": ["Earth to Moon is about 384,400 km.", "Moonlight takes about 1.3 seconds to reach Earth."],
        "sources": ["https://science.nasa.gov/moon/facts/"],
    }
    topic.update(overrides)
    return topic


def test_validate_topics_clean():
    assert validate_topics([_clean_topic()]) == []
    assert validate_topics([_clean_topic(facts=["x" * 200, "short fact"])]) == []
    assert validate_topics([_clean_topic(facts=["RUMOR: first.", "RUMOR: second."])]) == []


def test_validate_topics_missing_sources():
    no_key = _clean_topic()
    no_key.pop("sources")
    assert any("sources" in w for w in validate_topics([no_key]))
    assert any("sources" in w for w in validate_topics([_clean_topic(sources=[])]))


def test_validate_topics_long_fact():
    warnings = validate_topics([_clean_topic(facts=["a" * 201, "short fact"])])
    assert len(warnings) == 1
    assert "fact #1" in warnings[0]
    assert "201 chars" in warnings[0]


def test_validate_topics_too_few_facts():
    warnings = validate_topics([_clean_topic(facts=["Only one fact."])])
    assert len(warnings) == 1
    assert "fewer than 2 facts" in warnings[0]


def test_validate_topics_mixed_rumors():
    warnings = validate_topics([_clean_topic(facts=["Confirmed fact.", "RUMOR: unconfirmed claim."])])
    assert len(warnings) == 1
    assert "RUMOR:" in warnings[0]


@pytest.mark.parametrize("bad_id", ["Moon_distance", "moon distance", "BAD ID"])
def test_validate_topics_bad_id(bad_id):
    warnings = validate_topics([_clean_topic(id=bad_id)])
    assert len(warnings) == 1
    assert "spaces or uppercase" in warnings[0]


def test_cli_validate_clean(channel_en, capsys):
    assert main(["validate", "-c", str(channel_en.root)]) == 0
    out = capsys.readouterr().out
    assert "no warnings" in out


def test_cli_validate_warnings_and_strict(channel_en, capsys):
    facts_file = channel_en.path("facts_file")
    topic = _clean_topic()
    topic.pop("sources")
    facts_file.write_text(json.dumps({"topics": [topic]}), encoding="utf-8")

    assert main(["validate", "-c", str(channel_en.root)]) == 0
    out = capsys.readouterr().out
    assert "[WARN]" in out
    assert "sources" in out

    assert main(["validate", "-c", str(channel_en.root), "--strict"]) == 1
    out = capsys.readouterr().out
    assert "[WARN]" in out


def test_cli_validate_error(channel_en, capsys):
    facts_file = channel_en.path("facts_file")
    facts_file.write_text("{not json", encoding="utf-8")

    assert main(["validate", "-c", str(channel_en.root)]) == 1
    out = capsys.readouterr().out
    assert "[ERROR]" in out
    assert "not valid JSON" in out
