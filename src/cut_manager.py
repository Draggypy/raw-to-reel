"""Consolidates the candidate cuts (silences, filler words, and
repetitions) into the final list of segments to KEEP from the video.

Two cuts that are too close together get merged, so as not to leave a
kept segment between them so short it looks like a scene flash -- but
never if a word starts in between, because merging would delete whatever
is left in there.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import config
from silence_detector import Silence
from transcription import Word


@dataclass
class Cut:
    start: float
    end: float


@dataclass
class Segment:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def _ends_sentence(sorted_words: List[Word], instant: float) -> bool:
    """True if the last word starting before `instant` closes a sentence
    according to Whisper's punctuation (or if there's no word before it:
    the start of the video is treated as dead air)."""
    last = None
    for w in sorted_words:
        if w.start >= instant:
            break
        last = w
    if last is None:
        return True
    text = last.text.rstrip("\"'»)]")
    return bool(text) and text[-1] in config.SENTENCE_END_PUNCTUATION


def cuts_from_silences(
    silences: List[Silence], words: Sequence[Word] = ()
) -> List[Cut]:
    """The real cut is narrower than the detected silence: it leaves a
    buffer margin on each edge so as not to eat into the end or start of a
    word.

    Rules:
    - Pause BETWEEN sentences (the previous word ends in . ? ! ...): cut
      with SILENCE_MARGIN_MS. Pause WITHIN a sentence: it's speech rhythm,
      not dead air; it's only cut if it lasts at least
      MIN_MIDSENTENCE_PAUSE_MS, leaving MIDSENTENCE_MARGIN_MS on each side
      so the pause keeps existing.
    - If Whisper transcribed a word that STARTS inside the silence,
      there's soft voice there that volume didn't register: the cut is
      trimmed to end a margin before that start. Only word starts are
      looked at, never endings: Whisper stretches a word's `end` up to
      where the next one starts, so it swallows the pause in between. An
      earlier version protected whole words (start and end) and discarded
      almost every real cut -- measured on a real video: out of 20
      detected silences almost none got cut, leaving 9.4s of silence in a
      35s video.
    - A cut that saves less than MIN_CUT_MS is discarded: it's a visual
      jump (the head moves, the audio makes a "click") for nothing. With a
      150 margin and a 300 minimum silence, a 320ms pause used to produce
      a 20ms cut -- those micro-cuts were a big part of "it cuts out of
      nowhere" mid-sentence."""
    between_sentences_margin = config.SILENCE_MARGIN_MS / 1000
    midsentence_margin = config.MIDSENTENCE_MARGIN_MS / 1000
    min_midsentence_pause = config.MIN_MIDSENTENCE_PAUSE_MS / 1000
    min_cut = config.MIN_CUT_MS / 1000
    sorted_words = sorted(words, key=lambda w: w.start)

    cuts = []
    for s in silences:
        if _ends_sentence(sorted_words, s.start):
            margin = between_sentences_margin
        else:
            if s.end - s.start < min_midsentence_pause:
                continue
            margin = midsentence_margin

        start = s.start + margin
        end = s.end - margin
        for w in sorted_words:
            if w.start >= s.end:
                break
            if w.start >= s.start:
                end = min(end, w.start - margin)
                break
        if end - start >= min_cut:
            cuts.append(Cut(start=start, end=end))
    return cuts


def _merge_close_cuts(cuts: List[Cut], words: List[Word]) -> List[Cut]:
    """Merges two cuts that are very close together, so as not to leave a
    kept segment between them so short it looks like a scene flash.

    WATCH OUT: merging DELETES whatever was left in between. That's why it
    only merges if no word starts in that gap -- if there's a real word
    there (even a short one, "yes", "no", "and"), the short segment is
    kept instead of deleting something the user actually said. It checks
    the word's start rather than its end because Whisper stretches word
    endings (see cuts_from_silences)."""
    if not cuts:
        return []

    sorted_cuts = sorted(cuts, key=lambda c: c.start)
    merged = [Cut(sorted_cuts[0].start, sorted_cuts[0].end)]

    for current in sorted_cuts[1:]:
        previous = merged[-1]
        gap = current.start - previous.end
        word_starts_in_gap = any(
            previous.end <= w.start < current.start for w in words
        )
        if gap < config.MIN_SEGMENT_SEC and not word_starts_in_gap:
            previous.end = max(previous.end, current.end)
        else:
            merged.append(Cut(current.start, current.end))

    return merged


def _kept_segments(cuts: List[Cut], total_duration: float) -> List[Segment]:
    segments = []
    cursor = 0.0

    for cut in cuts:
        if cut.start > cursor:
            segments.append(Segment(start=cursor, end=cut.start))
        cursor = max(cursor, cut.end)

    if cursor < total_duration:
        segments.append(Segment(start=cursor, end=total_duration))

    return [s for s in segments if s.duration > 0]


def _enforce_min_segment(
    segments: List[Segment], words: List[Word], total_duration: float
) -> List[Segment]:
    """Removes "instant scenes": kept segments so short they look like a
    flash (one measured at 50ms = a frame and a half).

    Two different cases:
    - The segment has no word in it at all: it was pure margin filler (the
      typical case is the start of the video, where the first silence's
      margin leaves 50ms loose before the cut). It's discarded.
    - The segment does have a word: it can't be thrown away without
      losing what was said, so it gets WIDENED sideways, borrowing time
      from the silence next to it until it reaches the minimum. In other
      words: a bit of silence is given back to the video right there,
      which is exactly what's needed for the cut to not feel like a weird
      jump."""
    minimum = config.MIN_SEGMENT_SEC
    result: List[Segment] = []

    for i, s in enumerate(segments):
        if s.duration >= minimum:
            result.append(s)
            continue

        if not any(s.start <= w.start < s.end for w in words):
            continue

        missing = minimum - s.duration
        # the left edge can't step on the previous segment, already widened
        left_limit = result[-1].end if result else 0.0
        right_limit = segments[i + 1].start if i + 1 < len(segments) else total_duration
        left_space = max(0.0, s.start - left_limit)
        right_space = max(0.0, right_limit - s.end)

        take_right = min(missing / 2, right_space)
        take_left = min(missing - take_right, left_space)
        take_right = min(missing - take_left, right_space)  # rebalance if one side fell short

        result.append(Segment(start=s.start - take_left, end=s.end + take_right))

    return result


def consolidate(cuts: List[Cut], total_duration: float, words: List[Word]) -> List[Segment]:
    """Source-agnostic: takes already-computed cuts (from silences, filler
    words, and repetitions), merges the ones that would end up too close
    together -- without deleting words while doing so -- and returns the
    final segments to keep."""
    cuts = _merge_close_cuts(cuts, words)
    segments = _kept_segments(cuts, total_duration)
    return _enforce_min_segment(segments, words, total_duration)


def remap_interval(
    start: float,
    end: float,
    segments: List[Segment],
    real_durations: Optional[Sequence[float]] = None,
) -> Optional[Tuple[float, float]]:
    """Translates an [start, end) interval from the ORIGINAL timeline
    (e.g. a Whisper word) onto the already-cut timeline.

    On purpose it does NOT require both edges to land exactly inside the
    same kept segment: Whisper's word timestamps aren't perfect, and
    remapping each edge separately (like an earlier version of this did)
    used to discard whole words -- audible in the final video -- just
    because one edge, according to Whisper, grazed a cut boundary by a few
    milliseconds. Here it finds the segment with the most overlap with the
    interval and trims to that segment. It only returns None if the
    interval doesn't overlap ANY kept segment -- only then is there really
    nothing to show.

    `real_durations` are the measured durations of the cut segment files
    (see video_processor.cut_segments). When given, each segment's offset
    in the output accumulates those instead of the requested durations:
    every cut comes out a few ms longer than requested, and over dozens
    of cuts that drift pushed subtitles out of sync with the audio."""
    accumulated = 0.0
    best: Optional[Tuple[float, Segment, float, float]] = None
    for i, s in enumerate(segments):
        output_duration = real_durations[i] if real_durations is not None else s.duration
        overlap_start = max(start, s.start)
        overlap_end = min(end, s.end)
        overlap = overlap_end - overlap_start
        if overlap > 0 and (best is None or overlap > best[0]):
            best = (overlap, s, accumulated, output_duration)
        accumulated += output_duration

    if best is None:
        return None

    _, segment, offset, output_duration = best
    trimmed_start = max(start, segment.start)
    trimmed_end = min(end, segment.end)
    return (
        offset + min(trimmed_start - segment.start, output_duration),
        offset + min(trimmed_end - segment.start, output_duration),
    )
