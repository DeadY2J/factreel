# Roadmap

Ideas are tracked as GitHub issues. Want one? Comment on the issue and it's yours.

## Good first issues
- [ ] Portuguese, French, Italian and German language packs (`lang.py` + templates)
- [ ] `factreel voices --lang es`: list Edge voices for a language
- [ ] `factreel validate`: lint `facts.json` (missing sources, facts without numbers or dates, very long facts)
- [ ] More subtitle styles (box background, bottom-only, different pop animations)
- [ ] Gradient provider: more scene presets (ocean, city skyline, forest)

## Providers
- [ ] Piper TTS (offline neural voices)
- [ ] Kokoro TTS (offline, high quality)
- [ ] Local word timings with `faster-whisper`
- [ ] Pollinations / Together / fal.ai image providers
- [ ] ComfyUI workflow provider (API mode)

## Bigger features
- [ ] Long-form mode: chapters from several topics, 16:9, thumbnails, chapters in the description
- [ ] TikTok and Instagram Reels uploaders
- [ ] Scheduled publishing (`publishAt`) and a weekly calendar
- [ ] Docker image with FFmpeg included
- [ ] Simple web UI to edit facts and preview videos
- [ ] News helper: suggest new facts from RSS feeds for human approval (never auto-publish)
