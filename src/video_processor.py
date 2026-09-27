"""Applies the cuts to the video with ffmpeg.

Cuts with trim/atrim, resetting PTS per segment (PTS-STARTPTS), NEVER with
select+setpts assuming a constant frame rate -- that approach already
caused up to 4.9s of audio/video desync in the previous system, because
phones record at a variable frame rate.

IMPORTANT (found and measured on 2026-08-24, after a real machine freeze):
a single giant filter that references [0:v]/[0:a] once per segment (with
an N-way concat) makes ffmpeg use MUCH more memory than expected --
measured: 161MB for a simple transcode, but over 1GB with just 3 segments
in a single filter, and 1.4GB with 30. Cutting each segment to its own
file with a simple filter (a single trim, sharing the input with nothing
else) costs ~165MB per segment no matter how many segments there are in
total -- and joining them afterward with the concat demuxer (stream copy,
no re-encoding) is practically free. That's why cutting here NEVER builds
a filter_complex with more than one trim inside.
"""

import subprocess
from pathlib import Path
from typing import List, Tuple

import config
from cut_manager import Segment


def _cut_one_segment(video: Path, segment: Segment, destination: Path) -> None:
    """Cuts ONE segment to its own file.

    The `-ss` goes BEFORE `-i`: this way ffmpeg jumps straight to the cut
    point instead of decoding the video from second 0 every time. This
    used to use a `trim` filter, which forces decoding everything before
    it: with 18 segments the video was being decoded 18 times over in
    full. Measured on a real 1080p HEVC video, cutting the same 2s segment
    starting at second 30: 31.6s with the trim filter versus 6.6s with
    `-ss` up front, and the difference grows the further into the video
    the segment is. It's still exact because it re-encodes: with `-ss`
    before `-i` ffmpeg seeks to the previous keyframe and discards the
    extra frames up to the requested timestamp.

    The audio carries a short fade-in and fade-out so the join with the
    neighboring segment doesn't produce a "click" (see AUDIO_FADE_SEC).

    The output is always 8-bit 4:2:0 with even dimensions (see
    OUTPUT_PIXEL_FORMAT). Without this, a 10-bit HDR phone video or a
    4:4:4 screen recording produced a High 10 / High 4:4:4 H.264 file
    that passed validation but doesn't play on most phones, browsers, or
    social apps. yuv420p requires even width and height, so odd-sized
    sources (common in screen recordings) are trimmed by at most one
    pixel. ffmpeg's autorotation still applies before this filter, so a
    phone video with rotation metadata comes out upright."""
    fade = min(config.AUDIO_FADE_SEC, segment.duration / 2)
    fade_out_start = max(0.0, segment.duration - fade)
    audio_filter = (
        f"afade=t=in:st=0:d={fade:.3f},"
        f"afade=t=out:st={fade_out_start:.3f}:d={fade:.3f}"
    )
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{segment.start:.3f}",
        "-i", str(video),
        "-t", f"{segment.duration:.3f}",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v", "libx264", "-preset", config.SEGMENT_PRESET, "-crf", str(config.SEGMENT_CRF),
        "-pix_fmt", config.OUTPUT_PIXEL_FORMAT,
        "-af", audio_filter,
        "-c:a", "aac", "-b:a", "128k",
        str(destination),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed cutting a segment: {result.stderr.strip()}")


def _escape_path_for_concat_list(path: Path) -> str:
    """Escapes a path for the concat demuxer's own quoted-string syntax
    (single quotes around the path). A literal single quote in the path
    has to be closed, escaped, and reopened (`'\\''`) -- otherwise it ends
    the quoted path early and corrupts every line after it.

    Found 2026-09-26: a video named with an apostrophe (e.g.
    "gianni's_video.mp4", a completely ordinary filename) broke the
    concat step. ffmpeg tried to open a mangled path with the apostrophe
    silently missing, and the video went to failed/ with a cryptic error."""
    return str(path).replace("'", "'\\''")


def _concatenate(segment_files: List[Path], destination: Path) -> None:
    """Joins the already-cut files with the concat demuxer -- stream copy,
    no re-encoding, practically free in time and memory."""
    list_path = destination.with_suffix(".txt")
    content = "\n".join(f"file '{_escape_path_for_concat_list(s.resolve())}'" for s in segment_files)
    list_path.write_text(content, encoding="utf-8")

    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(list_path),
        "-c", "copy",
        str(destination),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    list_path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed concatenating: {result.stderr.strip()}")


def _escape_path_for_filter(path: Path) -> str:
    """ffmpeg's ass= filter uses ':' and ''' as special characters in its
    own mini-language -- they need escaping before wrapping the path in
    single quotes.

    On Windows, using '/' slashes (posix format) is the standard supported
    by ffmpeg to avoid escaping collisions with backslashes."""
    if hasattr(path, "as_posix"):
        text = path.as_posix()
    else:
        text = str(path).replace("\\", "/")
    text = text.replace(":", "\\:").replace("'", "\\'")
    return f"'{text}'"


def _burn_subtitles(video: Path, ass_path: Path, destination: Path) -> None:
    """The only step that re-encodes the final video -- the audio is
    copied as-is, subtitles don't touch it."""
    escaped_ass_path = _escape_path_for_filter(ass_path)
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(video),
        "-vf", f"ass={escaped_ass_path}",
        "-c:v", "libx264", "-preset", config.FINAL_PRESET, "-crf", str(config.FINAL_CRF),
        "-pix_fmt", config.OUTPUT_PIXEL_FORMAT,
        "-c:a", "copy",
        str(destination),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed burning subtitles: {result.stderr.strip()}")


def cut_segments(video: Path, segments: List[Segment], destination: Path) -> List[Tuple[Path, float]]:
    """Cuts every kept segment to its own file next to `destination` and
    returns each file with its REAL duration, measured with ffprobe.

    The real duration is what everything downstream has to use, not the
    requested one. Every cut lands on a frame boundary and AAC pads the
    audio to whole frames, so each file comes out slightly longer than
    requested -- ~23ms on average at 25fps, ~21ms at 24fps, ~20ms at
    30fps, ~8ms at 60fps (measured 2026-09-27). That small excess adds up
    over dozens of cuts: on a 5-minute 25fps horizontal video with 79
    cuts, the output was 1.87s longer than the sum of the requested
    segments. Validating against the requested durations rejected those
    perfectly good videos into failed/, and remapping subtitles against
    them made the captions drift further out of sync the longer the video
    ran. The concat demuxer offsets each file by exactly this measured
    duration, so it's the one number that matches the final timeline.

    On failure every partially written file is removed before raising."""
    if not segments:
        raise ValueError("No segments to keep -- can't generate an empty video")

    destination.parent.mkdir(parents=True, exist_ok=True)
    files: List[Path] = []
    try:
        for i, segment in enumerate(segments):
            seg_path = destination.parent / f"{destination.stem}_seg{i}.mp4"
            files.append(seg_path)
            _cut_one_segment(video, segment, seg_path)
        return [(f, get_total_duration(f)) for f in files]
    except Exception:
        remove_files(files)
        raise


def join_and_burn_subtitles(segment_files: List[Path], ass_path: Path, destination: Path) -> None:
    """Concatenates the already-cut segment files without re-encoding and
    burns the subtitles in a single final pass -- simple steps instead of
    one giant filter (see the module docstring)."""
    concatenated = destination.parent / f"{destination.stem}_concat.mp4"
    try:
        _concatenate(segment_files, concatenated)
        _burn_subtitles(concatenated, ass_path, destination)
    finally:
        concatenated.unlink(missing_ok=True)


def remove_files(paths) -> None:
    for path in paths:
        Path(path).unlink(missing_ok=True)


def get_total_duration(video: Path) -> float:
    command = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(video),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"ffprobe failed getting duration: {result.stderr.strip()}")
    return float(result.stdout.strip())


def stream_durations(video: Path) -> Tuple[float, float]:
    """Duration of the video and audio streams separately -- reporting
    differently is exactly the signal of the desync bug that already
    happened before."""
    def _duration(select_stream: str) -> float:
        command = [
            "ffprobe", "-v", "error", "-select_streams", select_stream,
            "-show_entries", "stream=duration", "-of", "csv=p=0",
            str(video),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError(f"ffprobe failed getting duration ({select_stream}): {result.stderr.strip()}")
        # the video stream can carry an extra trailing comma if it has
        # SIDE_DATA (rotation metadata, very common in phone HEVC)
        return float(result.stdout.strip().rstrip(","))

    return _duration("v:0"), _duration("a:0")
