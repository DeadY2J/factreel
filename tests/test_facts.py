import datetime as dt
import json
import random

import pytest

from factreel.facts import FactsError, History, choose_topic, days_until, load_topics


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
