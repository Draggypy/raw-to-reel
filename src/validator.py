"""Full validation of the generated file, before approving it for Ready/.
Checks go from cheapest to most expensive and stop at the first failure.
If any of them fails, the video is NOT approved and the original in Raw/
is left untouched -- see file_manager.py.

Note: that ffmpeg finished with exit code 0 is already guaranteed by
video_processor.cut_segments() and join_and_burn_subtitles() (they raise
an exception if not) -- if that fails, validate() is never even called
with a file to check.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import config


@dataclass
class ValidationResult:
    ok: bool
    reason: Optional[str] = None


def _exists_and_has_size(video: Path) -> ValidationResult:
    if not video.exists():
        return ValidationResult(False, "the file doesn't exist")
    if video.stat().st_size < config.MIN_SIZE_BYTES:
        return ValidationResult(False, f"only weighs {video.stat().st_size} bytes, suspiciously little")
    return ValidationResult(True)


def _ffprobe_opens_with_streams(video: Path) -> ValidationResult:
    command = [
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
        "-of", "csv=p=0", str(video),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        return ValidationResult(False, f"ffprobe couldn't open the file: {result.stderr.strip()}")

    # ffprobe adds an extra trailing comma on the line of a stream with
    # SIDE_DATA (e.g. rotation metadata, very common in phone HEVC) -- it's
    # stripped before comparing, otherwise any real video with that
    # metadata would fail here on a technicality, not because it's
    # actually missing the video stream.
    types = [line.rstrip(",") for line in result.stdout.strip().splitlines()]
    if "video" not in types:
        return ValidationResult(False, "has no video stream")
    if "audio" not in types:
        return ValidationResult(False, "has no audio stream")
    return ValidationResult(True)


def _expected_duration(video: Path, expected_duration: float, segment_count: int) -> ValidationResult:
    command = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(video),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return ValidationResult(False, "could not read the output duration")

    real_duration = float(result.stdout.strip())
    difference = abs(real_duration - expected_duration)
    tolerance = (
        config.DURATION_TOLERANCE_BASE_SEC
        + segment_count * config.DURATION_TOLERANCE_PER_SEGMENT_SEC
    )
    if difference > tolerance:
        return ValidationResult(
            False,
            f"expected duration {expected_duration:.2f}s, real is {real_duration:.2f}s "
            f"(difference {difference:.2f}s, tolerance {tolerance:.2f}s for {segment_count} segments)",
        )
    return ValidationResult(True)


def _decodes_without_errors(video: Path) -> ValidationResult:
    command = ["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or result.stderr.strip():
        return ValidationResult(False, f"errors decoding: {result.stderr.strip()[:500]}")
    return ValidationResult(True)


def validate(video: Path, expected_duration: float, segment_count: int) -> ValidationResult:
    """Runs every check, from cheapest to most expensive, and stops at the
    first one that fails. Only if all of them pass can it be moved to
    Ready/.

    `expected_duration` is the sum of the REAL durations of the cut
    segment files (see video_processor.cut_segments), not of the requested
    segments -- see DURATION_TOLERANCE_BASE_SEC for why."""
    checks = [
        lambda: _exists_and_has_size(video),
        lambda: _ffprobe_opens_with_streams(video),
        lambda: _expected_duration(video, expected_duration, segment_count),
        lambda: _decodes_without_errors(video),
    ]
    for check in checks:
        result = check()
        if not result.ok:
            return result
    return ValidationResult(True)
