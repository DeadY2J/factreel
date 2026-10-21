import json

from factreel.config import Channel
from factreel.llm import LLM
from factreel.pipeline import make_video
from factreel.review import (
    clean_ass_text,
    normalize_caption,
    parse_ass_dialogues,
    parse_ass_time,
    review_subtitles,
)

from .conftest import needs_ffmpeg

SAMPLE_ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,2,0,1,7,4,2,80,80,640,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:00.50,Default,,0,0,0,,{\\fscx80\\fscy80\\t(0,90,\\fscx100\\fscy100)}{\\c&H9A3CFF&}HELLO{\\c&HFFFFFF&} WORLD
Dialogue: 0,0:00:00.50,0:00:01.20,Default,,0,0,0,,HELLO {\\c&H9A3CFF&}WORLD{\\c&HFFFFFF&}
Dialogue: 0,0:00:01.30,0:00:02.50,Default,,0,0,0,,{\\fscx80\\fscy80\\t(0,90,\\fscx100\\fscy100)}{\\c&H9A3CFF&}NEXT{\\c&HFFFFFF&} SCENE
"""

COMMAS_ASS = """[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:01.00,Default,Actor1,0,0,0,,Hello, world, how, are, you?
Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\c&H9A3CFF&}Yes, indeed, it's 2026.
"""

NEWLINES_ASS = """[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,First line\\NSecond line\\nThird\\hword
"""

DISTANT_DUPLICATES_ASS = """[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:00.50,Default,,0,0,0,,{\\c&H9A3CFF&}HELLO{\\c&HFFFFFF&} WORLD
Dialogue: 0,0:00:00.50,0:00:01.20,Default,,0,0,0,,HELLO {\\c&H9A3CFF&}WORLD{\\c&HFFFFFF&}
Dialogue: 0,0:00:01.30,0:00:02.50,Default,,0,0,0,,NEXT SCENE
Dialogue: 0,0:00:30.00,0:00:30.60,Default,,0,0,0,,{\\c&H9A3CFF&}HELLO{\\c&HFFFFFF&} WORLD
Dialogue: 0,0:00:30.60,0:00:31.50,Default,,0,0,0,,HELLO {\\c&H9A3CFF&}WORLD{\\c&HFFFFFF&}
"""

DISTANT_NO_INTERVENING_ASS = """[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:02.00,0:00:03.00,Default,,0,0,0,,REPEATED PHRASE
Dialogue: 0,0:00:25.00,0:00:26.50,Default,,0,0,0,,REPEATED PHRASE
"""


def test_parse_ass_time():
    assert parse_ass_time("0:00:01.25") == 1.25
    assert parse_ass_time("1:02:03.50") == 3723.5
    assert parse_ass_time("05.50") == 5.5
    assert parse_ass_time("invalid") == 0.0


def test_clean_ass_text():
    raw = r"{\fscx80\fscy80\t(0,90,\fscx100\fscy100)}{\c&H9A3CFF&}HELLO{\c&HFFFFFF&} WORLD\NNEW LINE\hHERE"
    assert clean_ass_text(raw) == "HELLO WORLD NEW LINE HERE"


def test_parse_ass_dialogues_groups_and_cleans(tmp_path):
    p = tmp_path / "subs.ass"
    p.write_text(SAMPLE_ASS, encoding="utf-8")
    entries = parse_ass_dialogues(p)
    assert len(entries) == 2
    assert entries[0].text == "HELLO WORLD"
    assert entries[0].start == 0.0
    assert entries[0].end == 1.20
    assert entries[1].text == "NEXT SCENE"
    assert entries[1].start == 1.30
    assert entries[1].end == 2.50


def test_parse_ass_dialogues_commas_in_text(tmp_path):
    p = tmp_path / "commas.ass"
    p.write_text(COMMAS_ASS, encoding="utf-8")
    entries = parse_ass_dialogues(p)
    assert len(entries) == 2
    assert entries[0].text == "Hello, world, how, are, you?"
    assert entries[0].start == 0.0
    assert entries[0].end == 1.00
    assert entries[1].text == "Yes, indeed, it's 2026."


def test_parse_ass_dialogues_escaped_newlines(tmp_path):
    p = tmp_path / "newlines.ass"
    p.write_text(NEWLINES_ASS, encoding="utf-8")
    entries = parse_ass_dialogues(p)
    assert len(entries) == 1
    assert entries[0].text == "First line Second line Third word"


def test_parse_ass_dialogues_distant_duplicates_preserved(tmp_path):
    p = tmp_path / "distant_dups.ass"
    p.write_text(DISTANT_DUPLICATES_ASS, encoding="utf-8")
    entries = parse_ass_dialogues(p)
    assert len(entries) == 3
    # First karaoke group: merged
    assert entries[0].text == "HELLO WORLD"
    assert entries[0].start == 0.0
    assert entries[0].end == 1.20
    # Intervening scene
    assert entries[1].text == "NEXT SCENE"
    assert entries[1].start == 1.30
    assert entries[1].end == 2.50
    # Distant repetition: preserved as distinct entry with its own timestamps
    assert entries[2].text == "HELLO WORLD"
    assert entries[2].start == 30.00
    assert entries[2].end == 31.50


def test_parse_ass_dialogues_distant_duplicates_without_intervening(tmp_path):
    p = tmp_path / "distant_no_intervening.ass"
    p.write_text(DISTANT_NO_INTERVENING_ASS, encoding="utf-8")
    entries = parse_ass_dialogues(p)
    assert len(entries) == 2
    assert entries[0].text == "REPEATED PHRASE"
    assert entries[0].start == 2.00
    assert entries[0].end == 3.00
    assert entries[1].text == "REPEATED PHRASE"
    assert entries[1].start == 25.00
    assert entries[1].end == 26.50


def test_normalize_caption():
    assert normalize_caption("Hello, World!") == "HELLOWORLD"
    assert normalize_caption("  gta 6's \n ") == "GTA6S"
    assert normalize_caption("¡Hola! ¿Todo bien en 2026?") == "HOLATODOBIENEN2026"
    assert normalize_caption("¡Hola! ¿Todo bien?") == "HOLATODOBIEN"
    assert normalize_caption("") == ""


def make_dummy_channel(tmp_path, review_enabled=True, model="vision-v1") -> Channel:
    root = tmp_path / "chan"
    root.mkdir(parents=True, exist_ok=True)
    cfg = {
        "channel": {"name": "Test", "language": "en"},
        "llm": {"base_url": "https://api.nvidia.com/v1", "model": "text-model", "api_key_env": "TEST_KEY"},
        "review": {"subtitles": review_enabled, "model": model},
    }
    return Channel(root=root, cfg=cfg)


def test_review_matching_captions_produce_no_warnings(tmp_path, monkeypatch):
    channel = make_dummy_channel(tmp_path)
    monkeypatch.setenv("TEST_KEY", "dummy-key")

    video = tmp_path / "test.mp4"
    video.write_bytes(b"dummy video")
    ass = tmp_path / "test.ass"
    ass.write_text(SAMPLE_ASS, encoding="utf-8")

    # Mock extract_frame to avoid needing ffmpeg
    def mock_extract(video_path, ts, out_path):
        out_path.write_bytes(b"fake jpeg data")
        return True

    monkeypatch.setattr("factreel.review.extract_frame", mock_extract)

    # Mock LLM.chat returning matching captions
    def mock_chat(self, messages, *, temperature=None, max_tokens=2000, model=None):
        assert model == "vision-v1"
        return json.dumps(
            {
                "frames": [
                    {"n": 1, "caption": "Hello, World!", "ok": True, "problem": ""},
                    {"n": 2, "caption": "NEXT SCENE", "ok": True, "problem": ""},
                ]
            }
        )

    monkeypatch.setattr(LLM, "chat", mock_chat)

    warnings = review_subtitles(channel, video, ass)
    assert warnings == []


def test_review_caption_mismatches_produce_useful_warnings(tmp_path, monkeypatch):
    channel = make_dummy_channel(tmp_path)
    monkeypatch.setenv("TEST_KEY", "dummy-key")

    video = tmp_path / "test.mp4"
    video.write_bytes(b"dummy video")
    ass = tmp_path / "test.ass"
    ass.write_text(SAMPLE_ASS, encoding="utf-8")

    monkeypatch.setattr("factreel.review.extract_frame", lambda v, ts, o: o.write_bytes(b"x") and True)

    def mock_chat(self, messages, *, temperature=None, max_tokens=2000, model=None):
        return json.dumps(
            {
                "frames": [
                    {"n": 1, "caption": "WRONG CAPTION", "ok": True, "problem": ""},
                    {"n": 2, "caption": "NEXT SCENE", "ok": True, "problem": ""},
                ]
            }
        )

    monkeypatch.setattr(LLM, "chat", mock_chat)

    warnings = review_subtitles(channel, video, ass)
    assert len(warnings) == 1
    assert "Frame 1" in warnings[0]
    assert "text mismatch" in warnings[0]
    assert "HELLO WORLD" in warnings[0]
    assert "WRONG CAPTION" in warnings[0]


def test_review_model_reported_visual_issues(tmp_path, monkeypatch):
    channel = make_dummy_channel(tmp_path)
    monkeypatch.setenv("TEST_KEY", "dummy-key")

    video = tmp_path / "test.mp4"
    video.write_bytes(b"dummy video")
    ass = tmp_path / "test.ass"
    ass.write_text(SAMPLE_ASS, encoding="utf-8")

    monkeypatch.setattr("factreel.review.extract_frame", lambda v, ts, o: o.write_bytes(b"x") and True)

    def mock_chat(self, messages, *, temperature=None, max_tokens=2000, model=None):
        return json.dumps(
            {
                "frames": [
                    {"n": 1, "caption": "HELLO WORLD", "ok": False, "problem": "text clipped on right border"},
                    {"n": 2, "caption": "NEXT SCENE", "ok": True, "problem": ""},
                ]
            }
        )

    monkeypatch.setattr(LLM, "chat", mock_chat)

    warnings = review_subtitles(channel, video, ass)
    assert len(warnings) == 1
    assert "Frame 1" in warnings[0]
    assert "rendering problem" in warnings[0]
    assert "text clipped on right border" in warnings[0]


def test_review_markdown_fenced_json(tmp_path, monkeypatch):
    channel = make_dummy_channel(tmp_path)
    monkeypatch.setenv("TEST_KEY", "dummy-key")

    video = tmp_path / "test.mp4"
    video.write_bytes(b"dummy video")
    ass = tmp_path / "test.ass"
    ass.write_text(SAMPLE_ASS, encoding="utf-8")

    monkeypatch.setattr("factreel.review.extract_frame", lambda v, ts, o: o.write_bytes(b"x") and True)

    def mock_chat(self, messages, *, temperature=None, max_tokens=2000, model=None):
        raw = json.dumps({"frames": [{"n": 1, "caption": "HELLO WORLD", "ok": True, "problem": ""}]})
        return f"```json\n{raw}\n```"

    monkeypatch.setattr(LLM, "chat", mock_chat)

    warnings = review_subtitles(channel, video, ass)
    assert warnings == []


def test_review_error_handling_does_not_escape(tmp_path, monkeypatch):
    channel = make_dummy_channel(tmp_path)
    video = tmp_path / "test.mp4"
    video.write_bytes(b"dummy video")
    ass = tmp_path / "test.ass"
    ass.write_text(SAMPLE_ASS, encoding="utf-8")

    # 1. Missing model configuration
    channel.cfg["review"]["model"] = ""
    assert review_subtitles(channel, video, ass) == []

    # 2. Missing credentials
    channel.cfg["review"]["model"] = "vision-v1"
    monkeypatch.delenv("TEST_KEY", raising=False)
    assert review_subtitles(channel, video, ass) == []

    # 3. FFmpeg extraction failure
    monkeypatch.setenv("TEST_KEY", "dummy-key")
    monkeypatch.setattr("factreel.review.extract_frame", lambda v, ts, o: False)
    assert review_subtitles(channel, video, ass) == []

    # 4. Model returns malformed JSON
    monkeypatch.setattr("factreel.review.extract_frame", lambda v, ts, o: o.write_bytes(b"x") and True)
    monkeypatch.setattr(LLM, "chat", lambda *a, **k: "Sorry, cannot process image")
    assert review_subtitles(channel, video, ass) == []

    # 5. Unexpected exception inside chat
    def raise_err(*a, **k):
        raise RuntimeError("network crash")

    monkeypatch.setattr(LLM, "chat", raise_err)
    assert review_subtitles(channel, video, ass) == []


def test_review_caps_at_12_frames(tmp_path, monkeypatch):
    channel = make_dummy_channel(tmp_path)
    monkeypatch.setenv("TEST_KEY", "dummy-key")

    video = tmp_path / "test.mp4"
    video.write_bytes(b"dummy video")

    # Create ASS with 20 distinct captions
    lines = ["[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"]
    for i in range(20):
        lines.append(f"Dialogue: 0,0:00:{i:02d}.00,0:00:{i:02d}.80,Default,,0,0,0,,Caption {i}\n")
    ass = tmp_path / "many.ass"
    ass.write_text("".join(lines), encoding="utf-8")

    extracted_ts = []

    def mock_extract(video_path, ts, out_path):
        extracted_ts.append(ts)
        out_path.write_bytes(b"jpeg")
        return True

    monkeypatch.setattr("factreel.review.extract_frame", mock_extract)

    sent_content = []

    def mock_chat(self, messages, *, temperature=None, max_tokens=2000, model=None):
        sent_content.extend(messages[0]["content"])
        image_count = sum(1 for c in messages[0]["content"] if c.get("type") == "image_url")
        return json.dumps(
            {
                "frames": [
                    {"n": i, "caption": f"Caption {i - 1}", "ok": True, "problem": ""}
                    for i in range(1, image_count + 1)
                ]
            }
        )

    monkeypatch.setattr(LLM, "chat", mock_chat)

    warnings = review_subtitles(channel, video, ass)
    assert warnings == []
    assert len(extracted_ts) == 12
    image_parts = [c for c in sent_content if c.get("type") == "image_url"]
    assert len(image_parts) == 12


def test_pipeline_review_disabled_by_default(channel_en, monkeypatch, tmp_path):
    # Verify default config has subtitles = False
    assert channel_en.cfg["review"]["subtitles"] is False

    chat_called = False

    def mock_chat(*a, **k):
        nonlocal chat_called
        chat_called = True
        return "{}"

    monkeypatch.setattr(LLM, "chat", mock_chat)

    # When make_video runs with review disabled, review_subtitles is not called
    monkeypatch.setattr("factreel.pipeline.render.render", lambda *a, **k: None)
    monkeypatch.setattr("factreel.pipeline.render.verify", lambda *a, **k: 10.0)
    monkeypatch.setattr("factreel.pipeline.tts.synthesize", lambda *a, **k: ([(0, 1, "hi")], "dummy"))
    monkeypatch.setattr("factreel.pipeline.image_mod.scene_images", lambda *a, **k: [tmp_path / "img.png"])

    # Touch mock image
    (tmp_path / "img.png").write_bytes(b"x")

    result = make_video(channel_en, "venus_day", offline=True, record_history=False)
    assert chat_called is False
    assert result.meta.get("subtitle_review") == []


def test_pipeline_review_stores_warnings_in_metadata(channel_en, monkeypatch, tmp_path):
    channel_en.cfg["review"]["subtitles"] = True
    channel_en.cfg["review"]["model"] = "vision-test"
    monkeypatch.setenv("NVIDIA_API_KEY", "dummy-key")

    monkeypatch.setattr("factreel.pipeline.render.render", lambda *a, **k: None)
    monkeypatch.setattr("factreel.pipeline.render.verify", lambda *a, **k: 10.0)
    monkeypatch.setattr("factreel.pipeline.tts.synthesize", lambda *a, **k: ([(0, 1, "hello")], "dummy"))
    monkeypatch.setattr("factreel.pipeline.image_mod.scene_images", lambda *a, **k: [tmp_path / "img.png"])
    (tmp_path / "img.png").write_bytes(b"x")

    # Mock review_subtitles to return a warning
    monkeypatch.setattr(
        "factreel.pipeline.review_subtitles",
        lambda chan, vid, ass: ["Frame 1 ('HELLO'): text mismatch - expected 'HELLO', observed 'HALO'"],
    )

    result = make_video(channel_en, "venus_day", offline=True, record_history=False)
    assert result.meta["subtitle_review"] == ["Frame 1 ('HELLO'): text mismatch - expected 'HELLO', observed 'HALO'"]
    # Verify file on disk also contains subtitle_review
    meta_json = json.loads(result.video.with_suffix(".json").read_text(encoding="utf-8"))
    assert meta_json["subtitle_review"] == ["Frame 1 ('HELLO'): text mismatch - expected 'HELLO', observed 'HALO'"]


@needs_ffmpeg
def test_full_offline_pipeline_with_visual_review(channel_en, monkeypatch):
    """End-to-end offline pipeline test: real video generation with FFmpeg, visual review enabled, mocked LLM."""
    channel_en.cfg["video"].update({"width": 360, "height": 640, "fps": 12})
    channel_en.cfg["subtitles"].update({"size": 28, "margin_v": 200, "outline": 2})
    channel_en.cfg["review"].update({"subtitles": True, "model": "test-vision-model"})

    # Ensure LLM is available without a real key
    monkeypatch.setattr(LLM, "available", True)

    chat_called = []

    def mock_chat(self, messages, *, temperature=None, max_tokens=2000, model=None):
        chat_called.append({"model": model, "messages": messages})
        user_content = messages[0]["content"]
        image_parts = [c for c in user_content if c.get("type") == "image_url"]
        # Return valid matching JSON for each frame
        return json.dumps(
            {
                "frames": [
                    {"n": i, "caption": f"frame {i}", "ok": True, "problem": ""} for i in range(1, len(image_parts) + 1)
                ]
            }
        )

    monkeypatch.setattr(LLM, "chat", mock_chat)

    result = make_video(
        channel_en,
        "venus_day",
        offline=True,
        voice_chain=["dummy"],
        image_chain=["gradient"],
        record_history=False,
    )
    assert result.video.is_file() and result.video.with_suffix(".json").is_file()
    assert len(chat_called) == 1
    assert chat_called[0]["model"] == "test-vision-model"
    # User content contains both text instructions and image_url parts
    images = [c for c in chat_called[0]["messages"][0]["content"] if c.get("type") == "image_url"]
    assert 1 <= len(images) <= 12
    # Verify data URL format
    assert images[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "subtitle_review" in result.meta
    assert isinstance(result.meta["subtitle_review"], list)
