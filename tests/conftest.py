import shutil

import pytest

from factreel.cli import main
from factreel.config import load_channel


def make_channel(tmp_path, lang="en", extra=""):
    root = tmp_path / f"chan_{lang}"
    assert main(["init", str(root), "--lang", lang]) == 0
    if extra:
        with (root / "channel.toml").open("a", encoding="utf-8") as f:
            f.write("\n" + extra)
    return load_channel(root)


@pytest.fixture
def channel_en(tmp_path, monkeypatch):
    for var in ("NVIDIA_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return make_channel(tmp_path, "en")


@pytest.fixture
def channel_es(tmp_path, monkeypatch):
    for var in ("NVIDIA_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return make_channel(tmp_path, "es")


has_ffmpeg = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not has_ffmpeg, reason="ffmpeg not installed")
