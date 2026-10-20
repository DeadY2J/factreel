"""Optional YouTube upload (``pip install "factreel[youtube]"``).

Uploads every ``output/*.mp4`` that has its metadata next to it, declares AI-generated (synthetic) media
as YouTube requires, and moves the files to ``output/uploaded/``. Credentials stay in your channel folder:
``client_secrets.json`` (from Google Cloud, OAuth "Desktop app") and ``.factreel/youtube_token.json``.
"""
from __future__ import annotations

import random
import shutil
import time
from pathlib import Path

from . import metadata
from .config import Channel
from .log import log

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
RETRIABLE = {500, 502, 503, 504}


class UploadError(RuntimeError):
    pass


def _imports():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
    except ImportError as e:
        raise UploadError('YouTube support is not installed: pip install "factreel[youtube]"') from e
    return Request, Credentials, InstalledAppFlow, build, HttpError, MediaFileUpload


def service(channel: Channel):
    Request, Credentials, InstalledAppFlow, build, _, _ = _imports()
    token = channel.state_dir / "youtube_token.json"
    secrets = channel.root / channel["youtube"]["client_secrets"]
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.is_file() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not secrets.is_file():
                raise UploadError(f"missing {secrets.name}: create an OAuth 'Desktop app' client in Google Cloud "
                                  "and save its JSON there (see docs/youtube.md)")
            log("Opening the browser to authorise the channel (only the first time)...")
            creds = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES).run_local_server(port=0)
        token.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def pending(channel: Channel) -> list[Path]:
    out = channel.path("output_dir")
    return sorted(p for p in out.glob("*.mp4") if p.with_suffix(".json").is_file() or p.with_suffix(".txt").is_file())


def upload_one(yt, channel: Channel, video: Path, privacy: str, publish_at: str | None = None) -> str:
    _, _, _, _, HttpError, MediaFileUpload = _imports()
    meta = metadata.read(video)
    y = channel["youtube"]
    body = {
        "snippet": {"title": meta["title"], "description": meta["description"], "tags": meta.get("tags", []),
                    "categoryId": str(y["category_id"]), "defaultLanguage": channel.language},
        "status": {"privacyStatus": "private" if publish_at else privacy,
                   "selfDeclaredMadeForKids": bool(y["made_for_kids"]),
                   "containsSyntheticMedia": bool(y["synthetic_media"])},
    }
    if publish_at:
        body["status"]["publishAt"] = publish_at
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response, retry = None, 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                log(f"  {int(status.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status not in RETRIABLE or retry >= 5:
                raise
            retry += 1
            wait = random.uniform(1, 2 ** retry)
            log(f"  HTTP {e.resp.status}, retrying in {wait:.0f}s ({retry}/5)")
            time.sleep(wait)
    return response["id"]


def upload_pending(channel: Channel, privacy: str | None = None) -> int:
    """Upload every pending video. Returns the number of failures."""
    _, _, _, _, HttpError, _ = _imports()
    videos = pending(channel)
    if not videos:
        log("Nothing to upload.")
        return 0
    privacy = privacy or channel["youtube"]["privacy"]
    yt = service(channel)
    done_dir = channel.path("output_dir") / "uploaded"
    done_dir.mkdir(exist_ok=True)
    failures = 0
    for video in videos:
        log(f"Uploading {video.name} ({privacy})...")
        try:
            vid = upload_one(yt, channel, video, privacy)
        except HttpError as e:
            failures += 1
            log(f"  ERROR: {e}")
            if e.resp.status == 403 and b"quotaExceeded" in (e.content or b""):
                log("  Daily API quota used up; stopping.")
                break
            continue
        log(f"  Uploaded: https://youtube.com/shorts/{vid}")
        for f in (video, video.with_suffix(".json"), video.with_suffix(".txt")):
            if f.exists():
                shutil.move(str(f), str(done_dir / f.name))
    return failures
