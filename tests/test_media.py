import json

from PIL import Image

from factreel import metadata, subtitles
from factreel.images.common import is_black, to_frame, trim_black_bars
from factreel.images.providers import clean_prompt, gradient
from factreel.lang import expand_months
from factreel.tts.providers import elevenlabs_word_times
from factreel.tts.timing import align_to_script, estimate_word_times


def test_ass_helpers():
    assert subtitles.ass_color("#FF3C9A") == "&H9A3CFF&"
    assert subtitles.ass_time(3725.456) == "1:02:05.46"


def test_group_words_breaks_on_punctuation_and_pauses():
    words = [(0, .2, "Hello,"), (.3, .5, "big"), (.6, .8, "world"), (1.5, 1.7, "again")]
    groups = subtitles.group_words(words, max_words=3, max_chars=40)
    assert [[w[2] for w in g] for g in groups] == [["Hello,"], ["big", "world"], ["again"]]


def test_scene_start_times():
    scenes = [{"text": "One two."}, {"text": "Three four."}]
    words = [(0, .1, "One"), (.2, .3, "two"), (.5, .6, "Three"), (.7, .8, "four")]
    assert subtitles.scene_start_times(scenes, words) == [0.0, 0.5]


def test_write_ass(channel_en, tmp_path):
    p = tmp_path / "s.ass"
    subtitles.write_ass(channel_en, "Hi there, world.", [(0, .2, "Hi"), (.3, .5, "there"), (.6, .9, "world")], p)
    body = p.read_text(encoding="utf-8")
    assert "PlayResX: 1080" in body and "THERE," in body and body.count("Dialogue:") == 3


def test_estimate_and_align():
    est = estimate_word_times("one two three.", 3.0)
    assert len(est) == 3 and est[-1][1] <= 3.0
    heard = [(0.0, 0.4, "GTA"), (0.5, 0.9, "six"), (1.0, 1.4, "launches")]
    aligned = align_to_script("GTA 6 launches", heard)
    assert [w[2] for w in aligned] == ["GTA", "6", "launches"]
    assert aligned[0][:2] == (0.0, 0.4) and aligned[2][:2] == (1.0, 1.4)


def test_elevenlabs_alignment():
    text = "Hi you"
    al = {"characters": list(text), "character_start_times_seconds": [0, .1, .2, .3, .4, .5],
          "character_end_times_seconds": [.1, .2, .3, .4, .5, .6]}
    assert elevenlabs_word_times(text, al) == [(0, .2, "Hi"), (.3, .6, "you")]


def test_months():
    assert expand_months("Out on Nov 19, 2026", "en") == "Out on November 19, 2026"
    assert expand_months("sale el 19 de nov. de 2026", "es") == "sale el 19 de noviembre de 2026"


def test_images(channel_en):
    img = gradient(channel_en, "a prompt", 0, 4)
    assert img.size == (1080, 1920) and not is_black(img)
    assert gradient(channel_en, "a prompt", 0, 4).tobytes() == img.tobytes()  # deterministic
    barred = Image.new("RGB", (800, 1000), (200, 100, 50))
    barred.paste((0, 0, 0), (0, 0, 800, 120))
    assert trim_black_bars(barred).size == (800, 880)
    assert to_frame(barred, (108, 192)).size == (108, 192)
    assert "blood" not in clean_prompt(channel_en, "a blood moon over the sea").lower()


def test_metadata(channel_en, tmp_path):
    story = {"title": "Venus is weird 🌕", "text": "One. Two. Three.", "topic": "venus_day"}
    topic = {"id": "venus_day", "hashtags": ["#venus"], "sources": ["https://nasa.gov"]}
    meta = metadata.build(channel_en, story, topic, None, "Song by X")
    assert meta["title"].endswith("#shorts")
    assert "#venus" in meta["description"] and "https://nasa.gov" in meta["description"] and "🎵 Song by X" in meta["description"]
    video = tmp_path / "v.mp4"
    metadata.write(meta, video)
    assert metadata.read(video)["title"] == meta["title"]
    video.with_suffix(".json").unlink()
    assert metadata.read(video)["tags"] == meta["tags"]  # legacy .txt reader
    assert json.loads(json.dumps(meta))


def test_description_with_unknown_placeholder(channel_en):
    channel_en.cfg["metadata"]["description"] = "{teaser} {unknown} {hashtags}"
    meta = metadata.build(channel_en, {"title": "T", "text": "A. B.", "topic": "x"}, {"id": "x"}, None)
    assert "{unknown}" in meta["description"]


def test_subtitle_lint():
    issues = subtitles.lint(["GTA 6S IS", "OUT NOV 19", "THE THE END", "ALL GOOD HERE", "STRAY {X}"])
    joined = " ".join(issues)
    assert "6S" in joined and "NOV 19" in joined and "THE THE" in joined and "stray" in joined
    assert not any("ALL GOOD" in i for i in issues)
    assert subtitles.lint(["GTA 6'S BEST", "EL 19 DE NOVIEMBRE"]) == []


def test_write_ass_returns_lint(channel_en, tmp_path):
    words = [(0, .2, "the"), (.3, .5, "the"), (.6, .9, "end.")]
    issues = subtitles.write_ass(channel_en, "the the end.", words, tmp_path / "s.ass")
    assert any("repeated word" in i for i in issues)
