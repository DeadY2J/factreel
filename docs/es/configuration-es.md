# Referencia de configuración

Un canal es una carpeta con `channel.toml` y `facts.json`. Cada clave a continuación tiene un valor predeterminado, por lo que su `channel.toml` solo necesita lo que desea cambiar. Las rutas son relativas a la carpeta del canal.

Los secretos nunca van en `channel.toml`: este contiene los **nombres** de las variables de entorno (`api_key_env`). Un archivo `.env` en la carpeta del canal se carga automáticamente (las variables existentes tienen prioridad). En Windows, las variables guardadas con `setx` también se leen del registro, por lo que las tareas programadas pueden verlas.

## `[channel]`

| Clave | Predeterminado | |
| --- | --- | --- |
| `name` | `"My Channel"` | utilizado en el prompt de la IA y en la descripción |
| `language` | `"en"` | `en` o `es` (consulte `factreel/lang.py` para agregar uno) |
| `sign_off` | `""` | línea de despedida fija que se agrega después del guion de la IA |
| `facts_file` | `"facts.json"` | |
| `output_dir` | `"output"` | videos terminados + metadatos; los subidos se mueven a `output/uploaded/` |
| `archive_dir` | `"archive"` | cada imagen de IA se guarda aquí y se reutiliza si los servicios de imágenes fallan; también puede colocar sus propias fotos aquí |
| `music_dir` | `"music"` | pistas de fondo opcionales (`.mp3 .m4a .wav .ogg .flac`) + `credits.json` |
| `queue_file` | `"queue.txt"` | ids de los temas a publicar a continuación |

## `[countdown]`

`event = "the launch"` y `date = "2026-11-19"` habilitan ganchos como "Solo faltan N días para el lanzamiento.", la línea de cuenta regresiva en la descripción, y permiten que ese número pase por el filtro de números. Deje `date` vacío para desactivarlo.

## `[script]`

| Clave | Predeterminado | |
| --- | --- | --- |
| `scenes` | `4` | escenas (= imágenes) por video |
| `min_words` / `max_words` | `30` / `56` | ~20-25 s con la despedida; los Shorts de menos de 30 s retienen mejor |
| `grace_words` | `8` | si ningún intento encaja, se acepta el más corto hasta `max_words + grace_words` |
| `retries` | `6` | intentos de reescritura antes de recurrir al guion de solo hechos |
| `fact_check` | `true` | segunda pasada del LLM que enumera las afirmaciones no respaldadas |
| `allowed_numbers` | `[]` | números adicionales que pueden aparecer (por ejemplo, el nombre de un producto como `[6]`) |
| `extra_rules` / `image_rules` | `""` | se añade al prompt del escritor |

## `[llm]`

Cualquier endpoint compatible con OpenAI.

```toml
[llm]                                   # NVIDIA NIM (predeterminado, créditos gratis)
base_url = "https://integrate.api.nvidia.com/v1"
model = "nvidia/nemotron-3-ultra-550b-a55b"
api_key_env = "NVIDIA_API_KEY"
extra_body = { chat_template_kwargs = { enable_thinking = false } }

[llm]                                   # Google Gemini (nivel gratuito desde Google AI Studio)
base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
model = "gemini-3.5-flash-lite"
api_key_env = "GOOGLE_API_KEY"          # consiga una en https://aistudio.google.com/apikey

[llm]                                   # Ollama en su PC (sin clave)
base_url = "http://localhost:11434/v1"
model = "qwen3:14b"

[llm]                                   # OpenRouter
base_url = "https://openrouter.ai/api/v1"
model = "meta-llama/llama-3.3-70b-instruct:free"
api_key_env = "OPENROUTER_API_KEY"
```

`temperature` (0.8) y `timeout` (120 s) también están disponibles. `extra_body` se fusiona en cada solicitud.

## `[voice]`

La `chain` (cadena) se prueba en orden: `edge`, `elevenlabs`, `cloudflare`, `system`, `dummy`.

```toml
[voice.edge]          # voces gratuitas de Microsoft Edge: `edge-tts --list-voices`
voice = "es-ES-AlvaroNeural"
rate = "+4%"
pitch = "+0Hz"

[voice.elevenlabs]
voice_id = "pNInz6obpgDQGcFmaJgB"
model = "eleven_multilingual_v2"
tempo = 1.0           # acelerar manteniendo el tono (ffmpeg atempo)
max_chars = 1500      # protege su cuota mensual
api_key_env = "ELEVENLABS_API_KEY"

[voice.cloudflare]    # Deepgram Aura en Workers AI
model = "@cf/deepgram/aura-2-en"
speaker = "pluto"
tempo = 0.85

[voice.system]        # Windows SAPI / macOS say / Linux espeak-ng, sin conexión
voice = ""            # ej. "Microsoft Helena Desktop", "Mónica", "es"
rate = 0
```

## `[images]`

La `chain` (cadena) se prueba por escena: `cloudflare`, `nvidia`, `command`, `archive`, `gradient`.

| Clave | Predeterminado | |
| --- | --- | --- |
| `width` / `height` | `768` / `1344` | tamaño solicitado a los modelos de IA (luego se ajusta al video) |
| `style` | cinematic… no text | se añade a cada prompt |
| `banned_words` | gore, blood, gun… | se eliminan de los prompts (activan los filtros de seguridad que devuelven imágenes negras) |
| `text_check_model` | `""` | modelo de visión (el mismo endpoint `[llm]`) que rechaza imágenes con letras, ej. `"meta/llama-3.2-11b-vision-instruct"` |

```toml
[images.cloudflare]
model = "@cf/black-forest-labs/flux-2-klein-4b"
neurons = 110                 # estimación utilizada para el presupuesto diario

[images.nvidia]
models = ["flux.1-dev", "flux.1-schnell"]   # se prueban en orden

[images.command]              # su propio generador: debe escribir la imagen en {out}
run = "python C:/ai/flux_gen.py --prompt {prompt} --out {out} --width {width} --height {height} --seed {seed}"
timeout = 600

[images.gradient]
palette = ["#1b0b3a", "#ff3c9a", "#ffb03c"]   # cielo superior, horizonte, sol
```

Los modelos Gemini también ven imágenes, por lo que con el endpoint de Gemini puede configurar
`[images] text_check_model = "gemini-3.5-flash-lite"` para rechazar imágenes de IA con letras de forma gratuita.
El nivel gratuito tiene un límite de solicitudes diarias; cada video utiliza entre 2 y 8 llamadas (intentos de guion + verificación de hechos).

## `[video]`

`width 1080`, `height 1920`, `fps 30`, `fade 0.7` (s), `zoom 0.08` (8 % por escena), `tail 1.5` (s después de la última palabra), `voice_lufs -14`, `music_lufs -27`, `crf 20`.

## `[subtitles]`

`enabled true`, `font "Arial Black"`, `size 84`, `color "#FFFFFF"`, `highlight "#FF3C9A"`, `outline 7`,
`margin_v 640` (píxeles desde la parte inferior), `max_words 3`, `max_chars 18`, `uppercase true`.

Antes de renderizar, las líneas de subtítulos en pantalla se comprueban en busca de errores tipográficos visibles (un número pegado a una S como `6S` en lugar de `6'S`, meses abreviados, símbolos sueltos, palabras repetidas, caracteres rotos). Los problemas se muestran como advertencias y se guardan en el `.json` del video como `subtitle_warnings`; nunca bloquean el video.

## `[review]`

Revisión visual de subtítulos opcional después del renderizado: toma muestras de hasta 12 fotogramas distribuidos uniformemente por el video y pide a un modelo de visión que verifique que los subtítulos en pantalla coinciden con el guion y se renderizan sin defectos (como recortes o fallos).
Los resultados se almacenan en los metadatos `.json` del video como `subtitle_review`. Los problemas se muestran como advertencias y nunca bloquean ni eliminan el video.

La revisión reutiliza el endpoint `[llm]` y las credenciales existentes (`base_url`, `api_key_env`, `timeout`, `extra_body`).

| Clave | Predeterminado | |
| --- | --- | --- |
| `subtitles` | `false` | habilita la revisión visual de los subtítulos posterior al renderizado |
| `model` | `""` | nombre del modelo de visión que se pasa al endpoint `[llm]` |

Por ejemplo, al usar Google Gemini como su proveedor de LLM (`generativelanguage.googleapis.com`), puede configurar su modelo de visión ligero para la revisión de subtítulos:

```toml
[review]
subtitles = true
model = "gemini-3.5-flash-lite"
```

## `[metadata]`

| Clave | |
| --- | --- |
| `title_suffix` | se añade al título (`" #shorts"`) |
| `tags` | etiquetas ocultas de YouTube (recortadas a 480 caracteres) |
| `hashtags_fixed` / `hashtags_rotating` / `hashtags_rotating_count` | hashtags visibles: fijos + el propio del tema + N aleatorios |
| `disclaimer` | ej. "Las imágenes y la voz son generadas por IA. Canal de fans, no afiliado a…" |
| `description` | plantilla con `{teaser} {countdown} {sources} {music} {disclaimer} {hashtags} {channel} {title}` |

## `[cloudflare]`

`account_id_env`, `api_token_env`, `daily_neuron_cap` (10000 = la asignación diaria gratuita; el uso se registra en
`.factreel/cloudflare_neurons.json` por día UTC), `whisper_model`.

## `[youtube]`

`privacy` (`public`/`unlisted`/`private`), `category_id` (`20` Juegos, `27` Educación, `28` Ciencia y Tecnología,
`24` Entretenimiento), `made_for_kids`, `synthetic_media` (mantenga `true` para imágenes/voces de IA),
`client_secrets` (ruta del JSON de OAuth).

## Archivos que escribe FactReel

```
mi-canal/
├── output/                 videos + metadatos .json/.txt (en uploaded/ después de subir)
├── archive/                imágenes de IA conservadas para caídas del servicio
├── logs/                   registro mensual, voice_health.log
└── .factreel/              history.json, voice_health.json, cloudflare_neurons.json, youtube_token.json, tmp/
```
