"""Picks the next video to process from Raw/ and confirms it's stable
(not mid-copy, e.g. from a USB drive) before handing it off.
"""

import time
from pathlib import Path
from typing import Optional

import config


def list_pending_videos() -> list[Path]:
    """Videos in Raw/ (not in subfolders like failed/), oldest to newest
    by modification date."""
    config.RAW.mkdir(parents=True, exist_ok=True)
    videos = [
        p for p in config.RAW.iterdir()
        if p.is_file() and p.suffix.lower() in config.VIDEO_EXTENSIONS
    ]
    videos.sort(key=lambda p: p.stat().st_mtime)
    return videos


def is_stable(video: Path) -> bool:
    """Confirms the file's size doesn't change between successive checks,
    so as not to grab a file that's mid-copy."""
    try:
        previous_size = video.stat().st_size
    except FileNotFoundError:
        return False

    for _ in range(config.STABILITY_CHECKS):
        time.sleep(config.STABILITY_WAIT_SEC)
        try:
            current_size = video.stat().st_size
        except FileNotFoundError:
            return False
        if current_size != previous_size:
            return False
        previous_size = current_size

    return True


def next_video() -> Optional[Path]:
    """Next video ready to process, or None if none are stable yet."""
    for video in list_pending_videos():
        if is_stable(video):
            return video
    return None
