# Subida a YouTube

```bash
pip install "factreel[youtube]"
```

1. Vaya a [Google Cloud Console](https://console.cloud.google.com/), cree un proyecto y habilite **YouTube Data API v3**.
2. *API y servicios → Pantalla de consentimiento de OAuth*: Externo (External), añada su cuenta de Google como usuario de prueba, y añada los ámbitos (scopes) `youtube.upload` y `youtube.readonly`. Publique la aplicación ("En producción") o el token caducará cada 7 días.
3. *Credenciales → Crear credenciales → ID de cliente de OAuth → Aplicación de escritorio*. Descargue el JSON y guárdelo como `client_secrets.json` en la carpeta de su canal (está en `.gitignore`).
4. `factreel upload --auth` abre el navegador una vez. Si el canal es una cuenta de marca, elíjala ahí. El token se almacena en `.factreel/youtube_token.json`.
5. `factreel upload --privacy unlisted` sube todo lo que hay en `output/`. Compruebe un par de videos, y luego use `privacy = "public"` en `channel.toml`.

Cada subida cuesta ~1.600 de las 10.000 unidades diarias de la API, lo que equivale a unas 6 subidas por día y por proyecto.
Los videos se marcan como que contienen medios sintéticos (`containsSyntheticMedia`), tal como lo exige YouTube para las imágenes y voces realistas generadas por IA.
