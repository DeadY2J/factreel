import edge_tts
import pytest

from factreel.cli import main

FAKE_VOICES = [
    {"ShortName": "es-ES-AlvaroNeural", "Gender": "Male", "Locale": "es-ES"},
    {"ShortName": "es-MX-DaliaNeural", "Gender": "Female", "Locale": "es-MX"},
    {"ShortName": "en-US-JennyNeural", "Gender": "Female", "Locale": "en-US"},
]


@pytest.fixture
def fake_voices(monkeypatch):
    async def fake_list_voices():
        return FAKE_VOICES

    monkeypatch.setattr(edge_tts, "list_voices", fake_list_voices)


def test_voices_filters_by_language(fake_voices, capsys):
    assert main(["voices", "--lang", "es"]) == 0
    out = capsys.readouterr().out
    assert "es-ES-AlvaroNeural" in out
    assert "es-MX-DaliaNeural" in out
    assert "en-US-JennyNeural" not in out


def test_voices_unknown_language_fails(fake_voices):
    assert main(["voices", "--lang", "xx"]) == 1
