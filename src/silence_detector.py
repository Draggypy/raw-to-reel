"""Conservative detection of real silences over the already-extracted audio.

Uses an ADAPTIVE threshold (this video's own noise floor + margin), not a
fixed number -- a video recorded in a room with some background noise
shouldn't be treated the same as one recorded in near-total silence. When
in doubt, it's not marked as silence: better to leave a bit of silence in
than risk cutting inside a word.
"""

import wave
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import numpy as np

import config
import logger


@dataclass
class Silence:
    start: float  # seconds, timeline of the analyzed audio
    end: float


def _load_mono16_audio(audio_path: Path) -> Tuple[np.ndarray, int]:
    with wave.open(str(audio_path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError(
                "Expected a mono 16-bit WAV (the kind transcription.extract_audio produces)"
            )
        rate = wav.getframerate()
        raw = wav.readframes(wav.getnframes())

    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
    return samples, rate


def _db_volume_per_window(samples: np.ndarray, rate: int) -> np.ndarray:
    window_size = max(1, round(rate * config.SILENCE_WINDOW_MS / 1000))
    n_windows = len(samples) // window_size
    if n_windows == 0:
        return np.array([])

    trimmed = samples[: n_windows * window_size]
    windows = trimmed.reshape(n_windows, window_size)
    rms = np.sqrt(np.mean(windows ** 2, axis=1))
    rms = np.maximum(rms, 1.0)  # avoids log(0) on pure digital-silence stretches
    return 20 * np.log10(rms / 32768.0)


def _smooth(db_per_window: np.ndarray) -> np.ndarray:
    n = max(1, round(config.SILENCE_SMOOTHING_MS / config.SILENCE_WINDOW_MS))
    if n <= 1 or len(db_per_window) < n:
        return db_per_window
    # Moving average with edge-padded borders, so as not to drag zeros
    # (= 0dB, max volume) inward at the start and end.
    pad = n // 2
    padded = np.pad(db_per_window, (pad, n - 1 - pad), mode="edge")
    return np.convolve(padded, np.ones(n) / n, mode="valid")


def _mark_silence_with_hysteresis(db_per_window: np.ndarray, threshold: float) -> np.ndarray:
    """Returns a boolean per window. Entering silence requires dropping
    HYSTERESIS_DB below the threshold; leaving it only requires touching it
    again. This way a soft voice grazing the threshold doesn't open a
    silence, and any hint of voice closes one."""
    enter_threshold = threshold - config.HYSTERESIS_DB
    is_silence = np.zeros(len(db_per_window), dtype=bool)
    in_silence = False
    for i, db in enumerate(db_per_window):
        if in_silence:
            in_silence = db < threshold
        else:
            in_silence = db < enter_threshold
        is_silence[i] = in_silence
    return is_silence


def detect_silences(audio_path: Path) -> List[Silence]:
    samples, rate = _load_mono16_audio(audio_path)
    db_per_window = _db_volume_per_window(samples, rate)
    if len(db_per_window) == 0:
        return []
    return _silences_from_db(db_per_window)


def _silences_from_db(db_per_window: np.ndarray) -> List[Silence]:
    db_per_window = _smooth(db_per_window)

    raw_noise_floor = float(np.percentile(db_per_window, 10))
    # If the 10th percentile already falls within the voice range (little
    # real pause in this particular video), don't trust it as-is -- clamp
    # it to the documented real ceiling of "silence" before adding the margin.
    noise_floor = min(raw_noise_floor, config.NOISE_FLOOR_MAX_DB)
    threshold = noise_floor + config.DB_MARGIN_OVER_FLOOR
    threshold = max(config.DB_THRESHOLD_MIN, min(config.DB_THRESHOLD_MAX, threshold))
    logger.log(
        f"Silence threshold: raw floor {raw_noise_floor:.1f}dB "
        f"(used {noise_floor:.1f}dB) -> threshold {threshold:.1f}dB"
    )

    window_size_sec = config.SILENCE_WINDOW_MS / 1000
    is_silence = _mark_silence_with_hysteresis(db_per_window, threshold)

    raw_segments = []
    current_start = None
    for i, silent in enumerate(is_silence):
        if silent and current_start is None:
            current_start = i
        elif not silent and current_start is not None:
            raw_segments.append((current_start, i))
            current_start = None
    if current_start is not None:
        raw_segments.append((current_start, len(is_silence)))

    result = []
    for start_window, end_window in raw_segments:
        duration_ms = (end_window - start_window) * window_size_sec * 1000
        if duration_ms >= config.MIN_SILENCE_DURATION_MS:
            result.append(
                Silence(
                    start=start_window * window_size_sec,
                    end=end_window * window_size_sec,
                )
            )

    return result
