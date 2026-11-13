# Proveedores

FactReel nunca depende de un solo servicio. Las voces y las imágenes son **cadenas** (`chains`): el primer proveedor que funcione gana, un proveedor que falle se omite durante el resto del video, y los últimos eslabones de cada cadena funcionan sin conexión.

## Voces

| Nombre | Necesita | Tiempos de palabras | Notas |
| --- | --- | --- | --- |
| `edge` | internet | exacto (WordBoundary) | Voces neuronales de Microsoft Edge, gratis, más de 400 voces. No oficial: puede caerse durante unos días; mantenga un respaldo. |
| `elevenlabs` | `ELEVENLABS_API_KEY` | exacto (alineación de caracteres) | comprueba su cuota restante antes de gastar |
| `cloudflare` | Claves de Cloudflare | Whisper o estimado | Deepgram Aura en Workers AI, descontado del presupuesto diario de neuronas |
| `system` | nada | Whisper o estimado | Windows SAPI, `say` de macOS, `espeak-ng` de Linux |
| `dummy` | nada | estimado | pista silenciosa, para vistas previas y pruebas |

`factreel doctor --voices --log` prueba cada voz y escribe `logs/voice_health.log`. Cuando un proveedor que estaba caído vuelve a funcionar, crea `logs/VOICE_BACK_<name>.txt`. Ejecútelo cada pocas horas como una tarea programada y sabrá cuándo, por ejemplo, las voces de Edge vuelven después de una interrupción.

## Imágenes

| Nombre | Necesita | Notas |
| --- | --- | --- |
| `cloudflare` | Claves de Cloudflare | FLUX.2 klein en Workers AI, ~110 neuronas por imagen |
| `nvidia` | `NVIDIA_API_KEY` | FLUX.1 dev, luego schnell; las imágenes negras (filtradas) se descartan |
| `command` | su script | cualquier generador local: ComfyUI, Automatic1111, diffusers en su GPU… |
| `archive` | imágenes en `archive/` | cada imagen de IA se archiva; también puede colocar sus propias fotos |
| `gradient` | nada | fondo retro procedural, determinista por prompt |

Cada imagen se recorta al centro a 9:16, las barras de cine pintadas por el modelo se recortan y las imágenes negras se rechazan. Con `text_check_model`, un modelo de visión también rechaza las imágenes con letras (a los modelos de difusión les encanta escribir galimatías en los carteles/letreros).

## Escribir un proveedor

Un proveedor de voz es una función `fn(channel, text, out_path) -> [(start_s, end_s, word), ...]` que escribe un MP3 en `out_path` y lanza `TTSError` cuando no puede. Regístrelo en `PROVIDERS` en `src/factreel/tts/providers.py`. Si su motor no devuelve los tiempos de las palabras, devuelva `word_times_for(channel, text, out_path)`.

Un proveedor de imágenes es `fn(channel, prompt, index, total) -> PIL.Image | None` en `src/factreel/images/providers.py`: devuelva `None` para dejar que el siguiente proveedor intente esta escena, lance `ImageError` si el proveedor es inutilizable (falta clave, servicio caído).

Añada una prueba, una línea en este archivo y abra un *pull request*. Hay ideas en la [hoja de ruta](../../ROADMAP.md)
