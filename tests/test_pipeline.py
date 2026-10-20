from factreel import tts
from factreel.cli import main
from factreel.pipeline import make_video

from .conftest import needs_ffmpeg


@needs_ffmpeg
def test_full_offline_video(channel_es):
    channel_es.cfg["video"].update({"width": 360, "height": 640, "fps": 12})
    channel_es.cfg["subtitles"].update({"size": 28, "margin_v": 200, "outline": 2})
    result = make_video(channel_es, "dia_venus", offline=True, voice_chain=["dummy"])
    assert result.video.is_file() and result.video.with_suffix(".json").is_file()
    assert result.voice == "dummy" and result.duration > 5
    assert "Venus" in result.meta["script"]
    assert (channel_es.state_dir / "history.json").is_file()


def test_voice_chain_falls_back_and_records_health(channel_en, monkeypatch, tmp_path):
    def broken(*a):
        raise tts.TTSError("service down")

    def ok(channel, text, out):
        out.write_bytes(b"x")
        return [(0, 1, "hi")]

    monkeypatch.setitem(tts.PROVIDERS, "broken", broken)
    monkeypatch.setitem(tts.PROVIDERS, "ok", ok)
    tts._down.clear()
    words, name = tts.synthesize(channel_en, "hi", tmp_path / "a.mp3", chain=["broken", "ok"])
    assert name == "ok" and words == [(0, 1, "hi")]
    health = tts.read_health(channel_en)
    assert health["broken"]["ok"] is False and health["ok"]["ok"] is True
    assert tts.record_health(channel_en, "broken", True) is True  # recovery detected


def test_cli_topics(channel_en, capsys):
    assert main(["topics", "-c", str(channel_en.root)]) == 0
    assert "venus_day" in capsys.readouterr().out
