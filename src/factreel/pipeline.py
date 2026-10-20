"""End-to-end: topic -> script -> voice -> subtitles -> images -> render -> verify -> metadata."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from . import images as image_mod
from . import metadata, render, subtitles, tts
from .config import Channel
from .facts import History, choose_topic, days_until, load_topics
from .llm import LLM
from .log import log
from .script import fallback_script, write_ai_script


@dataclass
class Result:
    video: Path
    meta: dict
    voice: str
    duration: float


def write_script(channel: Channel, topic: dict, history: History, offline: bool = False) -> dict:
    days = days_until(channel)
    story = None
    if not offline:
        llm = LLM(channel)
        if llm.available:
            story = write_ai_script(channel, llm, topic, days, history.titles, history.recent_titles())
        else:
            log(f"No LLM key ({channel['llm']['api_key_env']} is not set): the facts will be read as they are.")
    if not story:
        log("Using the facts-only script.")
        story = fallback_script(channel, topic, days)
    return story


def make_video(channel: Channel, topic_id: str | None = None, *, offline: bool = False,
               voice_chain: list[str] | None = None, image_chain: list[str] | None = None,
               record_history: bool = True) -> Result:
    started = time.time()
    topics = load_topics(channel.path("facts_file"))
    history = History(channel.state_dir / "history.json")
    topic = choose_topic(topics, history, channel.path("queue_file"), forced=topic_id)
    log(f"Topic: {topic['id']} - {topic['angle']}")

    story = write_script(channel, topic, history, offline=offline)
    log(f"Title: {story['title']}")
    log(f"Script ({len(story['text'].split())} words): {story['text']}")

    tmp = channel.temp_dir
    audio = tmp / "voice.mp3"
    words, voice = tts.synthesize(channel, story["text"], audio, chain=voice_chain)

    scenes = story["scenes"]
    starts = subtitles.scene_start_times(scenes, words) if words else [
        i * render.media_duration(audio) / len(scenes) for i in range(len(scenes))]
    fade = float(channel["video"]["fade"])
    keep = [0] + [i for i in range(1, len(starts)) if starts[i] - starts[i - 1] > fade + 1]
    scenes, starts = [scenes[i] for i in keep], [starts[i] for i in keep]

    ass = None
    if channel["subtitles"]["enabled"] and words:
        ass = tmp / "subs.ass"
        subtitles.write_ass(channel, story["text"], words, ass)

    if offline and image_chain is None:
        image_chain = ["archive", "gradient"]
    log(f"Images for {len(scenes)} scenes...")
    pictures = image_mod.scene_images(channel, scenes, tmp, chain=image_chain)

    out_dir = channel.path("output_dir")
    out_dir.mkdir(parents=True, exist_ok=True)
    video = out_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_{topic['id']}.mp4"
    log("Rendering with FFmpeg...")
    try:
        try:
            track = render.render(channel, pictures, starts, audio, video, ass)
        except render.RenderError as e:
            log(f"Render with music failed, retrying with voice only ({str(e)[-200:]})")
            track = render.render(channel, pictures, starts, audio, video, ass, music=False)
        duration = render.verify(channel, video)
    except Exception:
        video.unlink(missing_ok=True)  # never leave a broken file in the upload queue
        raise

    meta = metadata.build(channel, story, topic, days_until(channel), render.music_credit(channel, track))
    meta["voice"] = voice
    metadata.write(meta, video)
    if record_history:
        history.add(story, video.name)
    log(f"Done in {time.time() - started:.0f}s: {video}")
    return Result(video=video, meta=meta, voice=voice, duration=duration)
