"""Safe choreography of delivering a finished video to Ready/ and only
then deleting the original from Raw/. The original is never touched until
the final copy has been independently verified.
"""

import shutil
from pathlib import Path

import config
import logger


def _valid_copy(temp_path: Path, destination: Path) -> bool:
    """Cheap check that the copy to Ready/ arrived complete."""
    return destination.exists() and destination.stat().st_size == temp_path.stat().st_size


def finalize(temp_path: Path, original: Path) -> bool:
    """Copies temp_path -> Ready/, verifies the copy, and only then
    deletes the original from Raw/ and the temp file. If anything fails
    along the way, the original stays intact."""
    config.READY.mkdir(parents=True, exist_ok=True)
    destination = config.READY / original.name

    try:
        shutil.copy2(temp_path, destination)
    except OSError as e:
        logger.log(f"ERROR copying to Ready/: {e}")
        return False

    if not _valid_copy(temp_path, destination):
        logger.log("ERROR: the copy in Ready/ doesn't match the temp file, not deleting the original")
        destination.unlink(missing_ok=True)
        return False

    try:
        original.unlink()
    except OSError as e:
        logger.log(f"ERROR deleting original from Raw/ (the copy in Ready/ is already OK): {e}")
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
