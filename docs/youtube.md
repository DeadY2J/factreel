# YouTube upload

```bash
pip install "factreel[youtube]"
```

1. Go to [Google Cloud Console](https://console.cloud.google.com/), create a project and enable
   **YouTube Data API v3**.
2. *APIs & Services → OAuth consent screen*: External, add your Google account as a test user, and add
   the scopes `youtube.upload` and `youtube.readonly`. Publish the app ("In production") or the token
   expires every 7 days.
3. *Credentials → Create credentials → OAuth client ID → Desktop app*. Download the JSON and save it as
   `client_secrets.json` in your channel folder (it is in `.gitignore`).
4. `factreel upload --auth` opens the browser once. If the channel is a brand account, pick it there.
   The token is stored in `.factreel/youtube_token.json`.
5. `factreel upload --privacy unlisted` uploads everything in `output/`. Check a couple of videos, then
   use `privacy = "public"` in `channel.toml`.

Each upload costs ~1,600 of the 10,000 daily API units, so about 6 uploads per day per project.
Videos are marked as containing synthetic media (`containsSyntheticMedia`), as YouTube requires for
realistic AI images and voices.
