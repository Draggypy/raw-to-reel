"""Generates .ass subtitles from Whisper's words.

Can work on the original timeline or on one already remapped to a cut
video (see remap_words) -- it doesn't need to know which is which, it just
receives a list of Word with whatever timestamps they have.
"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import config
import cut_manager
from transcription import Word


def remap_words(
    words: List[Word],
    segments: List["cut_manager.Segment"],
    real_durations: Optional[Sequence[float]] = None,
) -> List[Word]:
    """Translates each word onto the output timeline against the
    already-cut segments (see cut_manager.remap_interval). A word that
    doesn't overlap ANY kept segment is dropped -- there's no point
    showing a subtitle for something that's no longer in the final video.
    If it overlaps partially (an imprecise Whisper edge), it's trimmed to
    the segment instead of being dropped entirely."""
    remapped = []
    for w in words:
        interval = cut_manager.remap_interval(w.start, w.end, segments, real_durations)
        if interval is None:
            continue
        new_start, new_end = interval
        remapped.append(Word(text=w.text, start=new_start, end=new_end))
    return remapped


@dataclass
class Caption:
    text: str
    start: float
    end: float


def group_into_captions(words: List[Word]) -> List[Caption]:
    """Groups consecutive words into short captions (CapCut/Reels style):
    at most N words, and always starts a new caption if there's a real
    pause between one word and the next."""
    if not words:
        return []

    captions = []
    group = [words[0]]

    for word in words[1:]:
        pause = word.start - group[-1].end
        long_pause = pause >= config.CAPTION_PAUSE_CUT_SEC
        group_full = len(group) >= config.MAX_WORDS_PER_CAPTION
        if long_pause or group_full:
            captions.append(_close_group(group))
            group = [word]
        else:
            group.append(word)

    captions.append(_close_group(group))
    return captions


def _close_group(group: List[Word]) -> Caption:
    text = " ".join(w.text for w in group)
    return Caption(text=text, start=group[0].start, end=group[-1].end)


def get_dimensions(video: Path) -> Tuple[int, int]:
    """Width and height of the video AS IT WILL BE RENDERED: rotation
    metadata applied and trimmed to even numbers, exactly like
    video_processor._cut_one_segment produces it.

    Phones often store a vertical video as a 1920x1080 frame plus a
    "rotate 90" tag. ffmpeg auto-rotates it when cutting (the output is
    1080x1920), but ffprobe reports the stored 1920x1080. Using those raw
    numbers gave the subtitles the wrong canvas: libass stretched them to
    fit a frame of the opposite orientation.

    Parsed as JSON instead of CSV: CSV output mixes in side-data fields
    whose layout changes between ffmpeg versions."""
    command = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height:stream_side_data=rotation",
        "-of", "json",
        str(video),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed getting dimensions: {result.stderr.strip()}")

    streams = json.loads(result.stdout or "{}").get("streams") or []
    if not streams:
        raise RuntimeError("ffprobe found no video stream to get dimensions from")
    stream = streams[0]
    width, height = int(stream["width"]), int(stream["height"])
    rotation = 0
    for side_data in stream.get("side_data_list") or []:
        if "rotation" in side_data:
            rotation = int(float(side_data["rotation"]))
    if abs(rotation) % 180 == 90:
        width, height = height, width
    return width - width % 2, height - height % 2


def _format_ass_time(seconds: float) -> str:
    """Converts to hundredths as an integer first, so as not to carry
    floating-point rounding errors into the H:MM:SS.CC formatting."""
    total_hundredths = round(seconds * 100)
    hundredths = total_hundredths % 100
    total_seconds = total_hundredths // 100
    secs = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60
    return f"{hours}:{minutes:02d}:{secs:02d}.{hundredths:02d}"


def generate_ass(captions: List[Caption], width: int, height: int, destination: Path) -> None:
    font_size = round(height * config.FONT_SIZE_FRACTION)
    outline = round(height * config.OUTLINE_FRACTION)
    margin_fraction = (
        config.HORIZONTAL_BOTTOM_MARGIN_FRACTION if width > height else config.BOTTOM_MARGIN_FRACTION
    )
    bottom_margin = round(height * margin_fraction)

    header = (
        "[Script Info]\n"
        "Title: RawToReel\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{config.SUBTITLE_FONT},{font_size},&H00FFFFFF,&H000000FF,"
        f"&H00000000,&H00000000,0,0,0,0,100,{config.SUBTITLE_VERTICAL_SCALE},0,0,1,{outline},0,2,20,20,{bottom_margin},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    # The negative tracking is applied here, not in the Style's Spacing
    # field: tested, and libass ignores it when negative (behaves the same
    # as 0), but it does honor the \fsp override placed on each dialogue line.
    tracking_prefix = f"{{\\fsp{config.SUBTITLE_TRACKING}}}" if config.SUBTITLE_TRACKING else ""

    lines = []
    for cap in captions:
        start = _format_ass_time(cap.start)
        end = _format_ass_time(cap.end)
        text = cap.text.replace("\n", " ").strip()
        if text:
            lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{tracking_prefix}{text}")

    destination.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
