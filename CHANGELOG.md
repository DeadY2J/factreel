# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Optional visual subtitle review after render: samples up to 12 frames evenly across the video and checks them with a vision model, storing warnings in `subtitle_review` metadata.

## [0.1.1] - 2026-10-21

### Added
- `factreel voices [--lang es]` lists the Edge voices for a language (thanks @Nurana100!).
- Free subtitle check before rendering: warns about visible typos (e.g. `6S` instead of `6'S`, abbreviated
  months, stray symbols, repeated words) and stores them as `subtitle_warnings` in the video metadata.
- Docs: Google Gemini (free tier) as script AI through its OpenAI-compatible endpoint.

### Changed
- Default LLM is now `nvidia/nemotron-3-ultra-550b-a55b` (the previous default was retired by NVIDIA).
- Fatal LLM errors (rejected key, unknown model) stop the retries at once and fall back to the facts-only script.
- The facts-only script uses the channel's image rules for its image prompts.
- Python 3.10-3.14 declared in the package metadata.

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
