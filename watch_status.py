#!/usr/bin/env python3
"""Watch Status -- shows live what RawToReel is doing.

Independent, lightweight script: it doesn't import anything from the
pipeline (not even src/config.py), so it runs with the system's python3,
without the project's venv, and it's safe to leave open in a terminal
while editing the code -- it never loads numpy/whisper/ffmpeg.

Usage: python3 watch_status.py   (Ctrl+C to quit)
"""

import json
import time
from pathlib import Path

STATUS_FILE = Path(__file__).resolve().parent / "Logs" / "status.json"


def read_status():
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def main():
    print("Watching RawToReel's progress (Ctrl+C to quit)...")
    previous = None
    waiting_notified = False

    while True:
        status = read_status()

        if status is None:
            if not waiting_notified:
                print("Waiting for RawToReel to start...")
                waiting_notified = True
        elif status != previous:
            video = status.get("video") or "(none)"
            stage = status.get("stage", "?")
            time_str = status.get("updated", "")
            print(f"[{time_str}] {video} -> {stage}")
            previous = status
            waiting_notified = False

        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBye.")
