# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-20

### Added
- First public release, extracted from a channel that publishes a Short every day.
- Fact-grounded script writer for any OpenAI-compatible LLM, with number, repetition and rumour guards,
  a fact-check pass and a facts-only fallback.
- Voice chain: Edge, ElevenLabs, Cloudflare Aura, system voice, dummy; health tracking.
- Image chain: Cloudflare FLUX, NVIDIA FLUX, custom command, archive, procedural gradient.
- Word-by-word ASS subtitles, jitter-free zoom, cross-fades, loudness normalisation, music with credits.
- Spanish and English templates; `init`, `make`, `topics`, `doctor`, `upload`, `run` commands.
- Optional YouTube upload with synthetic-media declaration.
- Works with FFmpeg builds without libass (e.g. Homebrew's `ffmpeg`): the video is rendered without burned
  subtitles and a warning explains how to get a full build.
