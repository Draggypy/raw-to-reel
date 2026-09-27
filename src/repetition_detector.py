"""Filler words and repetitions, detected conservatively via rules -- with
no dependency on any external service (point 17 of the spec: no
unnecessary AI systems for this). The architecture allows swapping in a
smarter analyzer later on (for example, something like what the previous
system did with `claude -p`) without touching cut_manager.py: it would
only take another function here that returns the same list of Cut.

Central rule, same as everywhere else in the project: when in doubt, don't
cut. An unambiguous filler word ("eh", "emm") is always cut; one that's
also a real word ("este", "tipo") only if it has a real pause right next
to it, measured on the audio -- a sign of hesitation, not of fluent
speech. A repetition is only cut if it's 2 or more exact words repeated
shortly after AND there's a sign of hesitation in between (a real pause or
a filler word): repeating for emphasis ("al hablar, al hablar", "y pulas
y pulas") is part of normal speech, not a false start.
"""

import re
import unicodedata
from typing import List, Optional, Sequence

import config
from cut_manager import Cut
from silence_detector import Silence
from transcription import Word


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^\w\s]", "", text)


def _safe_end(words: List[Word], last_index: int) -> float:
    """Whisper marks a word's `end` right where the next one starts:
    cutting up to there would step on the first phoneme of the next word
    if its start came in just a bit late. A guard is left before it."""
    end = words[last_index].end
    if last_index + 1 < len(words):
        end = min(end, words[last_index + 1].start - config.ONSET_GUARD_SEC)
    return end


def _has_adjacent_pause(start: float, end: float, silences: Sequence[Silence]) -> bool:
    tol = config.FILLER_SILENCE_TOLERANCE_SEC
    return any(s.end >= start - tol and s.start <= end + tol for s in silences)


def detect_filler_words(
    words: List[Word],
    silences: Sequence[Silence] = (),
    filler_words: Optional[Sequence[str]] = None,
    ambiguous_filler_words: Optional[Sequence[str]] = None,
) -> List[Cut]:
    """Looks for the longest filler word (one or more words, e.g. "o sea")
    matching at each position.

    `filler_words`/`ambiguous_filler_words` default to config.FILLER_WORDS
    / config.AMBIGUOUS_FILLER_WORDS (Spanish) when not given -- callers
    that know the transcription's language should pass
    config.filler_words_for(language) instead (see main.py).

    Unambiguous ones are ALWAYS cut when they appear. The ones in
    AMBIGUOUS_FILLER_WORDS ("este", "tipo"...) are also real words ("en
    este video", "tipo de cosa"): cutting them unconditionally introduced
    a jump in the middle of a fluent sentence. They're only cut if the
    silence detector found a real pause right next to them (before or
    after).

    The pause is measured against silences detected by volume, NOT against
    the gaps between Whisper's timestamps: Whisper stretches the end of
    each word up to the next one, so there's never a gap between its
    words even when the pause is real (measured on a real video: 393
    words, 0 filler words "isolated" by timestamps). If the filler word is
    followed by a pause, the silence falls INSIDE the word's stretched
    interval, which is why this looks for overlap rather than exact
    adjacency."""
    filler_words = filler_words if filler_words is not None else config.FILLER_WORDS
    ambiguous_filler_words = (
        ambiguous_filler_words if ambiguous_filler_words is not None else config.AMBIGUOUS_FILLER_WORDS
    )
    normalized = [_normalize(w.text) for w in words]
    n = len(words)
    max_filler_words = max(len(m.split()) for m in filler_words)
    cuts = []
    i = 0

    while i < n:
        match_len = None
        for length in range(max_filler_words, 0, -1):
            if i + length > n:
                continue
            phrase = " ".join(normalized[i:i + length])
            if phrase in filler_words:
                match_len = length
                break

        if match_len:
            start = words[i].start
            end = _safe_end(words, i + match_len - 1)
            is_ambiguous = phrase in ambiguous_filler_words
            if end > start and (not is_ambiguous or _has_adjacent_pause(start, end, silences)):
                cuts.append(Cut(start=start, end=end))
            i += match_len
        else:
            i += 1

    return cuts


def _has_doubt_in_between(
    words: List[Word],
    normalized: List[str],
    end_of_first: int,
    start_of_second: int,
    silences: Sequence[Silence],
    filler_words: Sequence[str],
) -> bool:
    """Between the last word of the first occurrence and the first word of
    the second one there has to be a real pause (measured on the audio) or
    a filler word. Without that, the repetition is emphasis, not a
    stumble."""
    since = words[end_of_first].start
    until = words[start_of_second].start
    if any(since <= s.start < until for s in silences):
        return True
    return any(
        normalized[k] in filler_words for k in range(end_of_first + 1, start_of_second)
    )


def detect_repetitions(
    words: List[Word],
    silences: Sequence[Silence] = (),
    filler_words: Optional[Sequence[str]] = None,
) -> List[Cut]:
    """Detects a false start: the speaker begins a sentence, stumbles, and
    starts it over the same way ("I think that... I think this is
    great"). The FIRST occurrence is cut and it's kept from the second one
    onward.

    It only counts as a stumble if there's a real pause (silence detected
    by volume) or a filler word in between. Repeating in a row for
    emphasis -- "al hablar, al hablar, al hablar", "pulas y pulas y pulas"
    -- is a way of speaking, and cutting it introduced a jump in the
    middle of fluent speech (2026-09-26).

    KEY: the second occurrence has to come ALMOST RIGHT AFTER the first
    one (at most REPETITION_MAX_WORDS_BETWEEN words in between and within
    REPETITION_WINDOW_SEC). Without that condition, this used to delete
    entire normal sentences: with "I want to show you what we did this
    month with the team and what's coming", the naturally repeated "what"
    made everything in between get deleted, leaving "I want to show you
    what's coming". Repeating a common expression later in the sentence is
    NOT stumbling."""
    filler_words = filler_words if filler_words is not None else config.FILLER_WORDS
    normalized = [_normalize(w.text) for w in words]
    n = len(words)
    cuts = []
    i = 0

    while i < n:
        found = None

        for length in range(config.NGRAM_MAX, config.NGRAM_MIN - 1, -1):
            if i + length > n:
                continue
            ngram = normalized[i:i + length]
            if "" in ngram:
                continue

            first_j = i + length
            last_j = first_j + config.REPETITION_MAX_WORDS_BETWEEN
            for j in range(first_j, min(last_j, n - length) + 1):
                if words[j].start - words[i + length - 1].end > config.REPETITION_WINDOW_SEC:
                    break
                if normalized[j:j + length] == ngram:
                    found = (length, j)
                    break

            if found:
                break

        if found and _has_doubt_in_between(
            words, normalized, i + found[0] - 1, found[1], silences, filler_words
        ):
            _, j = found
            end = words[j].start - config.ONSET_GUARD_SEC
            if end > words[i].start:
                cuts.append(Cut(start=words[i].start, end=end))
            i = j
        else:
            i += 1

    return cuts
