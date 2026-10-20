# Providers

FactReel never depends on a single service. Voices and images are **chains**: the first provider that
works wins, a provider that fails is skipped for the rest of the video, and the last links of each
chain work offline.

## Voices

| Name | Needs | Word timings | Notes |
| --- | --- | --- | --- |
| `edge` | internet | exact (WordBoundary) | Microsoft Edge neural voices, free, 400+ voices. Unofficial: it can go down for a few days; keep a fallback. |
| `elevenlabs` | `ELEVENLABS_API_KEY` | exact (character alignment) | checks your remaining quota before spending |
| `cloudflare` | Cloudflare keys | Whisper or estimated | Deepgram Aura on Workers AI, counted in the daily neuron budget |
| `system` | nothing | Whisper or estimated | Windows SAPI, macOS `say`, Linux `espeak-ng` |
| `dummy` | nothing | estimated | silent track, for previews and tests |

`factreel doctor --voices --log` tests each voice and writes `logs/voice_health.log`. When a provider
that was down works again it creates `logs/VOICE_BACK_<name>.txt`. Run it every few hours as a
scheduled task and you will know when, for example, Edge voices are back after an outage.

## Images

| Name | Needs | Notes |
| --- | --- | --- |
| `cloudflare` | Cloudflare keys | FLUX.2 klein on Workers AI, ~110 neurons per image |
| `nvidia` | `NVIDIA_API_KEY` | FLUX.1 dev, then schnell; black (filtered) images are discarded |
| `command` | your script | any local generator: ComfyUI, Automatic1111, diffusers on your GPU… |
| `archive` | images in `archive/` | every AI image is archived; you can also drop your own pictures |
| `gradient` | nothing | procedural retro background, deterministic per prompt |

Every image is centre-cropped to 9:16, cinema bars painted by the model are trimmed, and black images are
rejected. With `text_check_model` a vision model also rejects images with letters (diffusion models love
to write gibberish on signs).

## Writing a provider

A voice provider is a function `fn(channel, text, out_path) -> [(start_s, end_s, word), ...]` that writes
an MP3 to `out_path` and raises `TTSError` when it can't. Register it in `PROVIDERS` in
`src/factreel/tts/providers.py`. If your engine doesn't return word timings, return
`word_times_for(channel, text, out_path)`.

An image provider is `fn(channel, prompt, index, total) -> PIL.Image | None` in
`src/factreel/images/providers.py`: return `None` to let the next provider try this scene, raise
`ImageError` if the provider is unusable (missing key, service down).

Add a test, a line in this file and open a pull request. Ideas in the [roadmap](../ROADMAP.md).
