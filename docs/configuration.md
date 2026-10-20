# Configuration reference

A channel is a folder with `channel.toml` and `facts.json`. Every key below has a default, so your
`channel.toml` only needs what you want to change. Paths are relative to the channel folder.

Secrets never go in `channel.toml`: it holds the **names** of environment variables (`api_key_env`).
A `.env` file in the channel folder is loaded automatically (existing variables win). On Windows,
variables saved with `setx` are also read from the registry, so scheduled tasks see them.

## `[channel]`

| Key | Default | |
| --- | --- | --- |
| `name` | `"My Channel"` | used in the AI prompt and description |
| `language` | `"en"` | `en` or `es` (see `factreel/lang.py` to add one) |
| `sign_off` | `""` | fixed closing line appended after the AI script |
| `facts_file` | `"facts.json"` | |
| `output_dir` | `"output"` | finished videos + metadata; uploaded ones move to `output/uploaded/` |
| `archive_dir` | `"archive"` | every AI image is saved here and reused if image services fail; drop your own pictures here too |
| `music_dir` | `"music"` | optional background tracks (`.mp3 .m4a .wav .ogg .flac`) + `credits.json` |
| `queue_file` | `"queue.txt"` | topic ids to publish next |

## `[countdown]`

`event = "the launch"` and `date = "2026-11-19"` enable "Only N days until the launch." hooks, the countdown
line in the description and allow that number through the number guard. Leave `date` empty to disable.

## `[script]`

| Key | Default | |
| --- | --- | --- |
| `scenes` | `4` | scenes (= images) per video |
| `min_words` / `max_words` | `30` / `56` | ~20-25 s with the sign-off; Shorts under 30 s retain better |
| `grace_words` | `8` | if no attempt fits, the shortest one up to `max_words + grace_words` is accepted |
| `retries` | `6` | rewrite attempts before falling back to the facts-only script |
| `fact_check` | `true` | second LLM pass that lists unsupported claims |
| `allowed_numbers` | `[]` | extra numbers that may appear (e.g. a product name such as `[6]`) |
| `extra_rules` / `image_rules` | `""` | appended to the writer prompt |

## `[llm]`

Any OpenAI-compatible endpoint.

```toml
[llm]                                   # NVIDIA NIM (default, free credits)
base_url = "https://integrate.api.nvidia.com/v1"
model = "nvidia/nemotron-3-super-120b-a12b"
api_key_env = "NVIDIA_API_KEY"
extra_body = { chat_template_kwargs = { enable_thinking = false } }

[llm]                                   # Ollama on your PC (no key)
base_url = "http://localhost:11434/v1"
model = "qwen3:14b"

[llm]                                   # OpenRouter
base_url = "https://openrouter.ai/api/v1"
model = "meta-llama/llama-3.3-70b-instruct:free"
api_key_env = "OPENROUTER_API_KEY"
```

`temperature` (0.8) and `timeout` (120 s) are also available. `extra_body` is merged into every request.

## `[voice]`

`chain` is tried in order: `edge`, `elevenlabs`, `cloudflare`, `system`, `dummy`.

```toml
[voice.edge]          # free Microsoft Edge voices: `edge-tts --list-voices`
voice = "es-ES-AlvaroNeural"
rate = "+4%"
pitch = "+0Hz"

[voice.elevenlabs]
voice_id = "pNInz6obpgDQGcFmaJgB"
model = "eleven_multilingual_v2"
tempo = 1.0           # speed-up keeping the pitch (ffmpeg atempo)
max_chars = 1500      # protects your monthly quota
api_key_env = "ELEVENLABS_API_KEY"

[voice.cloudflare]    # Deepgram Aura on Workers AI
model = "@cf/deepgram/aura-2-en"
speaker = "pluto"
tempo = 0.85

[voice.system]        # Windows SAPI / macOS say / Linux espeak-ng, offline
voice = ""            # e.g. "Microsoft Helena Desktop", "Mónica", "es"
rate = 0
```

## `[images]`

`chain` is tried per scene: `cloudflare`, `nvidia`, `command`, `archive`, `gradient`.

| Key | Default | |
| --- | --- | --- |
| `width` / `height` | `768` / `1344` | size requested to AI models (then fitted to the video) |
| `style` | cinematic… no text | appended to every prompt |
| `banned_words` | gore, blood, gun… | removed from prompts (they trigger safety filters that return black images) |
| `text_check_model` | `""` | vision model (same `[llm]` endpoint) that rejects images with letters, e.g. `"meta/llama-3.2-11b-vision-instruct"` |

```toml
[images.cloudflare]
model = "@cf/black-forest-labs/flux-2-klein-4b"
neurons = 110                 # estimate used for the daily budget

[images.nvidia]
models = ["flux.1-dev", "flux.1-schnell"]   # tried in order

[images.command]              # your own generator: must write the image to {out}
run = "python C:/ai/flux_gen.py --prompt {prompt} --out {out} --width {width} --height {height} --seed {seed}"
timeout = 600

[images.gradient]
palette = ["#1b0b3a", "#ff3c9a", "#ffb03c"]   # sky top, horizon, sun
```

## `[video]`

`width 1080`, `height 1920`, `fps 30`, `fade 0.7` (s), `zoom 0.08` (8 % per scene), `tail 1.5` (s after the
last word), `voice_lufs -14`, `music_lufs -27`, `crf 20`.

## `[subtitles]`

`enabled true`, `font "Arial Black"`, `size 84`, `color "#FFFFFF"`, `highlight "#FF3C9A"`, `outline 7`,
`margin_v 640` (pixels from the bottom), `max_words 3`, `max_chars 18`, `uppercase true`.

## `[metadata]`

| Key | |
| --- | --- |
| `title_suffix` | appended to the title (`" #shorts"`) |
| `tags` | hidden YouTube tags (trimmed to 480 characters) |
| `hashtags_fixed` / `hashtags_rotating` / `hashtags_rotating_count` | visible hashtags: fixed + the topic's own + N random |
| `disclaimer` | e.g. "Images and voice are AI-generated. Fan channel, not affiliated with…" |
| `description` | template with `{teaser} {countdown} {sources} {music} {disclaimer} {hashtags} {channel} {title}` |

## `[cloudflare]`

`account_id_env`, `api_token_env`, `daily_neuron_cap` (10000 = the free daily allowance; usage is tracked in
`.factreel/cloudflare_neurons.json` by UTC day), `whisper_model`.

## `[youtube]`

`privacy` (`public`/`unlisted`/`private`), `category_id` (`20` Gaming, `27` Education, `28` Science & Tech,
`24` Entertainment), `made_for_kids`, `synthetic_media` (keep `true` for AI images/voices),
`client_secrets` (path of the OAuth JSON).

## Files FactReel writes

```
my-channel/
├── output/                 videos + .json/.txt metadata (uploaded/ after upload)
├── archive/                AI images kept for outages
├── logs/                   monthly log, voice_health.log
└── .factreel/              history.json, voice_health.json, cloudflare_neurons.json, youtube_token.json, tmp/
```
