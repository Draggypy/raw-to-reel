"""Safe choreography of delivering a finished video to Ready/ and only
then moving the original out of Raw/'s scan path. The original is never
touched until the final copy has been independently verified, and it's
never deleted -- only moved to Raw/processed/, so a result you don't like
can always be recovered and reprocessed (see config.PROCESSED).
"""

import shutil
from pathlib import Path

import config
import logger


def _valid_copy(temp_path: Path, destination: Path) -> bool:
    """Cheap check that the copy to Ready/ arrived complete."""
    return destination.exists() and destination.stat().st_size == temp_path.stat().st_size


def finalize(temp_path: Path, original: Path) -> bool:
    """Copies temp_path -> Ready/, verifies the copy, and only then moves
    the original into Raw/processed/ (never deletes it) along with the
    temp file. If anything fails along the way, the original stays right
    where it was, untouched, in Raw/."""
    config.READY.mkdir(parents=True, exist_ok=True)
    destination = config.READY / original.name

    try:
        shutil.copy2(temp_path, destination)
    except OSError as e:
        logger.log(f"ERROR copying to Ready/: {e}")
        return False

    if not _valid_copy(temp_path, destination):
        logger.log("ERROR: the copy in Ready/ doesn't match the temp file, leaving the original in place")
        destination.unlink(missing_ok=True)
        return False

    config.PROCESSED.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(original), str(config.PROCESSED / original.name))
    except OSError as e:
        logger.log(f"ERROR moving original to Raw/processed/ (the copy in Ready/ is already OK): {e}")
        return False

    try:
        temp_path.unlink()
    except OSError:
        pass  # not critical: the temp file can be cleaned up on the next run

    return True


def mark_failed(original: Path, reason: str) -> None:
    """Moves an original that failed processing to Raw/failed/, so it
    isn't retried on just the next scan, and writes the reason right next
    to it as <video name>.error.txt -- the user sees why it failed by
    opening the folder, without digging through the log."""
    config.FAILED.mkdir(parents=True, exist_ok=True)
    destination = config.FAILED / original.name
    try:
        shutil.move(str(original), str(destination))
        logger.log(f"Moved to failed/: {original.name}")
    except OSError as e:
        logger.log(f"ERROR moving to failed/: {e}")
        return

    try:
        (config.FAILED / f"{original.name}.error.txt").write_text(
            f"{original.name} could not be processed.\n\nReason:\n{reason}\n\n"
            "To retry, move the video back into Raw/. The full history is in "
            "Logs/rawtoreel.log.\n",
            encoding="utf-8",
        )
    except OSError as e:
        logger.log(f"ERROR writing the failure reason next to {original.name}: {e}")
