"""Simple logging: one timestamped line per event to a text file in Logs/,
plus a lightweight status.json to watch progress live without needing to
load heavy dependencies just to look at it.
"""

import json
import time
from typing import Optional

import config

LOG_FILE = config.LOGS / "rawtoreel.log"
STATUS_FILE = config.LOGS / "status.json"


def log(message: str) -> None:
    config.LOGS.mkdir(parents=True, exist_ok=True)
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n"
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="")


def update_status(video: Optional[str], stage: str) -> None:
    """Atomic write (writes to a temp file and renames it) so an external
    reader never finds the file mid-write."""
    config.LOGS.mkdir(parents=True, exist_ok=True)
    data = {
        "video": video,
        "stage": stage,
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    temp = STATUS_FILE.with_suffix(".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temp.replace(STATUS_FILE)
