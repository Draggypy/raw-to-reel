"""Audio extraction + transcription with faster-whisper.

Returns words with timestamps -- that's the only output the rest of the
program cares about (subtitles, silence/repetition detection all work on
this list of words, not on the video).
"""

import gc
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

import config
import logger


@dataclass
class Word:
    text: str
    start: float  # seconds, ORIGINAL timeline of the video
    end: float


@dataclass
class TranscriptionResult:
    audio_path: Path
    words: List[Word]


def verify_audio_usable(video: Path) -> None:
    """Fails with a clear message if the video doesn't have an audio track
    that can be worked with. Without this, ffmpeg used to fail with
    "Output file does not contain any stream" -- cryptic, and the user had
    no way to know why the video ended up in failed/.

    Real case (2026-09-26, VID_20260926_033221.mp4 from a Xiaomi phone):
    the file had an audio track created but EMPTY -- 0 samples, no codec
    (codec_tag 0x0000), an 8-byte stbl box. The phone recorded 30s of video
    and no audio at all; this happens when another app has the microphone
    locked when recording starts, or the microphone is muted."""
    command = [
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=codec_name,sample_rate,channels",
        "-of", "csv=p=0", str(video),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe could not read the video: {result.stderr.strip()}")

    tracks = [l for l in result.stdout.strip().splitlines() if l.strip()]
    if not tracks:
        raise RuntimeError(
            "The video has no audio track. With no audio there's nothing "
            "to transcribe and no silences to cut."
        )

    for track in tracks:
        fields = [c.strip() for c in track.rstrip(",").split(",")]
        codec = fields[0] if fields else ""
        try:
            sample_rate = int(fields[1]) if len(fields) > 1 and fields[1] else 0
        except ValueError:
            sample_rate = 0
        if codec and codec not in ("unknown", "none") and sample_rate > 0:
            return

    raise RuntimeError(
        "The video's audio track is empty (no codec, no samples): the "
        "phone recorded video but no audio. This usually happens when "
        "another app had the microphone locked when recording started, or "
        "the microphone was muted. Check that the video has sound when "
        "you play it back."
    )


def extract_audio(video: Path) -> Path:
    """Extracts the video's audio to a mono 16kHz WAV in Temp/ -- the
    format whisper expects natively, and enough for the silence analysis
    from Phase 5 further down the pipeline."""
    verify_audio_usable(video)
    config.TEMP.mkdir(parents=True, exist_ok=True)
    destination = config.TEMP / f"{video.stem}.wav"

    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(video),
        "-vn", "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le",
        str(destination),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed extracting audio: {result.stderr.strip()}")

    return destination


def transcribe(audio_path: Path) -> List[Word]:
    """Loads the model, transcribes, releases the model. Never keeps the
    model loaded between calls -- every video pays the loading cost again,
    in exchange for never accumulating memory from one video to the next."""
    from faster_whisper import WhisperModel

    model = WhisperModel(
        config.WHISPER_MODEL,
        device=config.WHISPER_DEVICE,
        compute_type=config.WHISPER_COMPUTE_TYPE,
    )
    try:
        segments, _info = model.transcribe(
            str(audio_path),
            language=config.WHISPER_LANGUAGE,
            word_timestamps=True,
        )
        words = [
            Word(text=w.word.strip(), start=w.start, end=w.end)
            for segment in segments
            for w in segment.words
        ]
    finally:
        del model
        gc.collect()

    return words


def transcribe_video(video: Path) -> TranscriptionResult:
    logger.update_status(video.name, "extracting audio")
    audio_path = extract_audio(video)

    logger.update_status(video.name, "transcribing")
    words = transcribe(audio_path)
    logger.log(f"Transcription: {len(words)} word(s)")

    return TranscriptionResult(audio_path=audio_path, words=words)
