"""Central configuration for RawToReel.

Each implementation phase adds its own adjustable constants here, as they
become needed -- it wasn't all filled in from day one.
"""

from pathlib import Path

# --- Project paths ---
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "Raw"
FAILED = RAW / "failed"
READY = ROOT / "Ready"
TEMP = ROOT / "Temp"
LOGS = ROOT / "Logs"

# --- Accepted video formats ---
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}

# --- Scanning Raw/ ---
SCAN_INTERVAL_SEC = 5    # how often to check when there's nothing to process
STABILITY_CHECKS = 2     # how many stable-size confirmations are required
STABILITY_WAIT_SEC = 2   # seconds to wait between stability checks
# Opens Raw/ in the desktop file manager the moment the program starts, so
# a first-time user doesn't have to already know that folder exists or
# where to find it -- they run the program, a window pops up, they drop
# videos in it. Silently does nothing if it can't (no desktop environment
# -- e.g. running as a headless systemd service on a server, or over SSH).
# Turn this off for that kind of unattended setup.
OPEN_RAW_FOLDER_ON_START = True

# --- Whisper (transcription) ---
WHISPER_MODEL = "small"       # "base" as a fallback if RAM usage needs to come down
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"  # quantized, much lighter on CPU
# None = auto-detect from the first ~30s of audio (faster-whisper's own
# language identification). Works for Spanish or English without touching
# this file -- FILLER_WORDS_BY_LANGUAGE below picks the right filler-word
# list for whichever one Whisper detects. Pin it to "es" or "en" only if
# auto-detection ever gets it wrong on a specific voice/recording.
WHISPER_LANGUAGE = None

# --- Silence detection ---
# ADAPTIVE threshold (this video's own noise floor + margin), not a fixed
# number -- values inherited and already validated from the previous system.
SILENCE_WINDOW_MS = 10          # size of the volume analysis window
# Voice energy swings a lot from one 10ms window to the next (stops,
# fricatives, word endings). Without smoothing, a voice speaking near the
# threshold flips between silence/voice several times a second, and that
# showed up as "it cuts, and out of nowhere cuts again" (2026-09-26). The
# dB curve is averaged over a window of this size before comparing.
SILENCE_SMOOTHING_MS = 50
# Hysteresis: to ENTER silence, the signal has to drop this much below the
# threshold; to LEAVE it, just touching it again is enough. Biased in favor
# of voice: a soft syllable grazing the threshold doesn't open a silence,
# but any hint of voice closes one.
HYSTERESIS_DB = 3.0
# Measured on the user's real audio (2026-08-24): voice lives between -30
# and -17 dB, and silence between -55 and -45 dB. With a margin of 10 the
# threshold came out at -44.8 dB, right against the noise floor: everything
# between -44 and -38 dB (perfectly audible silence, i.e. a pause) counted
# as voice and wasn't cut. With 17 the threshold lands around -38 dB, which
# is where the "how much silence do I detect" curve flattens out -- beyond
# that point it starts eating into soft voice instead of gaining real pauses.
DB_MARGIN_OVER_FLOOR = 17
DB_THRESHOLD_MIN = -40.0        # the threshold is never stricter than this...
# Lowered from -28 to -35 (2026-09-26): measured voice lives between -30 and
# -17dB. With the ceiling at -28, on a video with a high noise floor the
# threshold reached -28dB and treated soft voice (sentence endings, soft
# consonants) as silence -- cutting mid-speech. -35 sits 5dB below the
# softest voice measured and 10dB above the silence ceiling (-45).
DB_THRESHOLD_MAX = -35.0        # ...nor more permissive than this
# Ceiling of the NOISE FLOOR itself (not of the final threshold) -- added
# 2026-09-20, feedback: "some videos won't even let you talk, it cuts all
# the time". Measured in real logs: cut density ranged from 0.15/sec
# (natural) to 0.83/sec (almost one cut per second) depending on the video.
# The 10th percentile of volume ASSUMES at least 10% of the clip is real
# silence -- if a video has little real pause (the user talks almost
# nonstop in that take), that 10th percentile ends up falling inside soft
# voice/soft consonants, not silence, and the computed threshold (floor +
# 17dB) creeps upward and starts treating normal voice as silence. The
# -45dB already documented above as the real ceiling of "silence" (measured
# range: -55 to -45dB) is the correct limit for the floor itself, before
# adding the margin.
NOISE_FLOOR_MAX_DB = -45.0

# How much buffer to leave on each edge of a silence before cutting, so as
# not to eat into the end/start of a word. Lowered from 200ms to 50ms
# (2026-08-24, feedback after testing with a real video): with 200ms, no
# pause shorter than ~600ms ever got cut -- the video ended up full of gaps
# the user didn't want at all ("cuts should always happen, it's just
# someone talking"). 50ms is the value the previous system already had
# tuned for the same thing.
# Raised from 50 to 150 (2026-09-20, feedback after the first real human
# review of the result): with 50ms, a 300ms+ silence ended up as ~100ms
# total after the cut (2x50) -- practically nothing; the user felt like "it
# cuts the moment I stop talking" and "you can't hear any silence at all".
# This is not the same as MIN_SILENCE_DURATION_MS (which decides which
# pauses get cut); this one decides how much silence stays audible AFTER
# cutting. With 150, 2x150=300ms of silence remain after every cut -- the
# number the user asked for literally. It still cuts any real silence of
# 300ms+, just leaves a natural remainder instead of a sharp jump.
SILENCE_MARGIN_MS = 150

# A silence shorter than this is not cut -- it simply doesn't clear the
# margin. It has to be more than double SILENCE_MARGIN_MS, otherwise a
# silence right at that limit would leave nothing useful in the middle
# after applying the margin on both edges.
# Raised from 150 to 250 (2026-08-27, feedback after real use): 150ms was
# cutting normal breathing pauses within a spoken sentence -- the user
# described the cuts as "exaggerated", especially at the start of the
# video (a softer voice onset at the beginning of speech falls below the
# dB threshold more easily, and with only a 150ms floor any micro-pause
# there got cut). 250ms lets those short pauses through while still
# cutting real silences.
# Raised from 250 to 300 (2026-09-12, per "Tareas a realizar.md": "the cut
# is already too aggressive... it cuts for the smallest silence that
# exists"). Same kind of adjustment as 2026-08-27, one more step: it was
# still cutting short pauses within speech.
MIN_SILENCE_DURATION_MS = 300

# How much a cut has to SAVE, margins already subtracted, to be worth the
# visual jump. Added 2026-09-26: with a minimum silence of 300 and a
# margin of 150, a 320ms pause produced a 20ms cut -- the head jumps, the
# audio makes a "click", and the video barely gets any shorter. These
# micro-cuts were a big part of "it cuts out of nowhere" mid-sentence.
# With 150, only pauses that leave at least 150ms out get cut (i.e. pauses
# of 2*SILENCE_MARGIN_MS + 150 = 450ms or more).
MIN_CUT_MS = 150

# --- Pauses WITHIN a sentence vs. BETWEEN sentences (2026-09-26) ---
# A pause within a sentence (taking a breath, searching for a word, the
# dramatic pause before the important part) is speech rhythm, not dead
# air. Cutting it with the same rule as a pause between sentences was the
# "I'm talking about the same topic for 10 seconds and out of nowhere it
# cuts" problem. It's told apart using the punctuation Whisper already
# returns for each word: if the last word before the silence ends in
# . ? ! or an ellipsis, the pause is between sentences and gets cut as
# usual. If not (no punctuation, or a comma), a noticeably longer pause is
# required to touch it, and more of the silence is left so the rhythm
# still sounds natural. If Whisper doesn't punctuate a stretch (it
# happens sometimes), everything falls into "within a sentence" and gets
# cut LESS -- the safe side.
MIN_MIDSENTENCE_PAUSE_MS = 1000
MIDSENTENCE_MARGIN_MS = 250    # 2x250 = 500ms of pause stay audible
SENTENCE_END_PUNCTUATION = ".?!…"

# A cut never steps on the start of a word according to Whisper: if
# Whisper transcribed a word that starts inside a silence detected by
# volume, that's soft voice, not silence. The cut is trimmed to end this
# margin before that word's start (the same margin used on volume-based
# edges is reused). Only word STARTS are looked at: Whisper's word endings
# stretch to the next word and aren't useful for this (see
# cut_manager.cuts_from_silences).
# Extra guard before the start of the word that follows a cut filler word
# or repetition: Whisper marks a word's `end` right where the next one
# starts, so cutting "up to the end" would step on the first phoneme of
# the next word if its start came in just a bit late.
ONSET_GUARD_SEC = 0.05

# --- Cut consolidation ---
# A kept segment shorter than this, caught between two cuts, gets merged
# with them instead of staying as a sub-second scene flash (the "critical
# problem" that already happened in the previous system). If the segment
# has a word inside it, it isn't deleted: it gets widened up to this
# minimum, borrowing silence from the sides.
# Raised from 0.3 to 0.5 (2026-09-26): two cuts 300ms apart from each
# other feel like a burst of jumps; half a second is the minimum for a
# scene between two cuts to read as a scene and not as a flicker.
MIN_SEGMENT_SEC = 0.5

# --- Filler words and repetitions (Phase 11) ---
# Rule-based detection, with no dependency on any external service (point
# 17 of the spec: no unnecessary AI systems here). Filler words are cut
# every time they appear on the list (without requiring an isolated pause
# -- see repetition_detector.py, changed 2026-08-24 based on real
# feedback). Repetitions still require 2+ exact words -- a single repeated
# word is too common in normal speech to be a reliable signal.
# Turned off 2026-09-26 based on direct feedback: "we repeat things
# because we want to be specific" ("look what happens here, but the
# opposite could happen, but this happens"). Even with the rule requiring
# a pause or a filler word in between, cutting repetitions introduced
# jumps into fluent speech. The editor specializes in silences and filler
# words; the code stays in place to try it again by setting this to True.
CUT_REPETITIONS = False
# NOTE: these are literal Spanish filler words on purpose -- this list has
# to match what a Spanish speaker actually says, translating the values
# themselves would break detection, not just the code around it. Same
# reasoning for the English list right below: it's real English filler
# words, not a translation of the Spanish ones.
FILLER_WORDS = {"eh", "emm", "mmm", "este", "o sea", "tipo", "digamos"}
# These are also real words ("in THIS video" -- "en ESTE video", "THAT
# KIND of thing" -- "TIPO de cosa", "I MEAN..." -- "O SEA que..."). Cutting
# them unconditionally introduced a jump in the middle of a fluent sentence
# (2026-09-26). They're only cut if the silence detector found a real pause
# right next to them (before or after) -- a sign of hesitation, not of a
# sentence. The ones not on this list ("eh", "emm", "mmm", "digamos") have
# no legitimate use within a sentence and are always cut.
AMBIGUOUS_FILLER_WORDS = {"este", "tipo", "o sea"}

# English equivalent, added 2026-09-27 alongside WHISPER_LANGUAGE
# auto-detection. "um"/"uh"/"erm" have no legitimate use inside a sentence
# (unambiguous, always cut, same role as "eh"/"emm" above). Everything
# else on the ambiguous list is also a normal word or phrase ("I really
# LIKE this", "SO, that happened", "I MEAN it") -- same rule as Spanish's
# "este"/"tipo": only cut with a real pause right next to them.
FILLER_WORDS_EN = {"um", "uh", "erm", "like", "so", "well", "i mean", "you know", "kind of", "sort of"}
AMBIGUOUS_FILLER_WORDS_EN = {"like", "so", "well", "i mean", "you know", "kind of", "sort of"}

# Which filler-word list to use for a given Whisper-detected language code.
# Spanish is the fallback for anything Whisper detects that isn't English --
# matches the "Spanish first" default this project has always had.
FILLER_WORDS_BY_LANGUAGE = {"es": FILLER_WORDS, "en": FILLER_WORDS_EN}
AMBIGUOUS_FILLER_WORDS_BY_LANGUAGE = {"es": AMBIGUOUS_FILLER_WORDS, "en": AMBIGUOUS_FILLER_WORDS_EN}


def filler_words_for(language):
    """(filler_words, ambiguous_filler_words) for a Whisper language code.
    Falls back to Spanish for any language other than English -- safe by
    construction: an unrecognized filler-word list just means nothing
    matches, so nothing gets cut, never the wrong thing."""
    return (
        FILLER_WORDS_BY_LANGUAGE.get(language, FILLER_WORDS),
        AMBIGUOUS_FILLER_WORDS_BY_LANGUAGE.get(language, AMBIGUOUS_FILLER_WORDS),
    )
# How close (in seconds) a detected silence has to be to the ambiguous
# filler word to count it as "isolated". Measured against the real audio,
# not against Whisper's timestamps (which never leave gaps).
FILLER_SILENCE_TOLERANCE_SEC = 0.2
NGRAM_MIN = 2              # minimum exact repeated words to count as a self-correction
NGRAM_MAX = 6
# A repetition has to come almost right after the first one to count as a
# false start. With loose values (a 6s window, any distance in words) this
# used to delete entire normal sentences -- see repetition_detector.py.
REPETITION_WINDOW_SEC = 1.5       # from the end of the 1st occurrence to the start of the 2nd
REPETITION_MAX_WORDS_BETWEEN = 1  # lets one filler word slip through in between, nothing more

# --- Encoding (render speed) ---
# The render does TWO encoding passes: first each segment separately, then
# a final pass to burn in the subtitles. On this machine (2 cores, no GPU)
# both passes at "medium" took 21 minutes for a 47s 1080p video. The
# segments are intermediate files that get deleted, so they're encoded at
# "ultrafast" with a finer CRF (the quality loss isn't noticeable and it
# avoids carrying it over to the final pass); only the final pass defines
# the real quality of the video that gets published.
SEGMENT_PRESET = "ultrafast"
SEGMENT_CRF = 18
FINAL_PRESET = "veryfast"
FINAL_CRF = 21
# Audio fade-in/fade-out on each cut segment. Even when a cut falls inside
# a silence, the background noise isn't zero, and the jump from one sample
# to the next is audible as a "click" that gives the cut away (2026-09-26).
# 12ms is inaudible as a fade and enough for the join to sound continuous.
AUDIO_FADE_SEC = 0.012
# Output pixel format for every encode. 8-bit 4:2:0 is the only format
# that plays everywhere (phones, browsers, Instagram, TikTok, WhatsApp).
# Without forcing it, libx264 inherits the source format: a 10-bit HDR
# phone video became High 10 H.264 and a 4:4:4 screen recording became
# High 4:4:4 -- both pass validation but won't play on most devices.
OUTPUT_PIXEL_FORMAT = "yuv420p"

# --- Validation ---
MIN_SIZE_BYTES = 10_000     # below this, it's discarded as empty/truncated
# The final video is compared against the sum of the REAL durations of
# the cut segment files (measured with ffprobe, see
# video_processor.cut_segments), not against the requested durations.
# Frame rounding already happened inside those files, so the only thing
# left to catch is the join/burn step losing or adding content -- a
# segment is never shorter than MIN_SEGMENT_SEC, so a dropped segment
# still blows well past this tolerance.
# History: this used to compare against the requested durations with
# 20ms of slack per segment. The real excess per cut is ~23ms at 25fps
# and ~21ms at 24fps, so any 24/25fps video with enough cuts (~47 at
# 25fps, typical of a few minutes of horizontal footage) was rejected
# into failed/ even though nothing was wrong (2026-09-27).
DURATION_TOLERANCE_BASE_SEC = 0.15        # base margin
DURATION_TOLERANCE_PER_SEGMENT_SEC = 0.02  # extra margin per segment (join timestamp rounding)

# --- Subtitles ---
# Tiempos Headline (Klim Type Foundry), Regular weight -- confirmed
# 2026-08-25 after several rounds of real comparison against the user's own
# Instagram content. The real family name ("Tiempos Headline") does NOT
# work here: the file is an evaluation/web-embed build, and libass resolves
# the LEGACY name from the ttf's `name` table, not the typographic name --
# "Copyright Klim Type Foundry" is that legacy name (confirmed with
# fontTools). Only the Regular weight is installed at
# ~/.local/share/fonts/TiemposHeadline-Regular.ttf to avoid ambiguity with
# other weights sharing the same internal name.
#
# LICENSE WARNING: this file is an evaluation build ("Not Licensed for
# Desktop Use" is literally its internal style name) -- there's no desktop
# license purchased for it. The user chose to use it anyway for their own
# Instagram content, knowingly. If this were ever used to deliver video to
# a third party (not the case for this project), the real license would
# need to be purchased at klim.co.nz first.
SUBTITLE_FONT = "Copyright Klim Type Foundry"
# One word per caption (2026-08-25, feedback after comparing against the
# user's own Instagram content: subtitles there go one word at a time, not
# two -- they go by faster).
MAX_WORDS_PER_CAPTION = 1
CAPTION_PAUSE_CUT_SEC = 0.4     # a pause longer than this starts a new caption
# Raised from 0.062 to 0.085 and then lowered to 0.075 (2026-08-25): 0.085
# was "the biggest" from the first comparison, but shortly after the user
# asked to shrink it "just a little" -- 0.075 was confirmed as the final
# point after comparing 0.070/0.075/0.080/0.085 side by side.
FONT_SIZE_FRACTION = 0.075
# Lowered from 0.028 to 0.004 and then to 0.0025 (2026-08-25): at 0.028 the
# outline (54px on a 119px font, ~45% of the letter height) was so thick
# the strokes fused into a solid black blob behind the text -- most
# noticeable on accents and tight letter pairs. 0.0025 (~5px at the current
# font size) gives a thin stroke that defines the letter without fattening
# it, confirmed as the sweet spot after comparing 3/5/7px.
OUTLINE_FRACTION = 0.0025
# Stretches the letters vertically without widening the sides (ScaleX
# stays at 100) -- confirmed 2026-08-25 after comparing 115/125/135: 125
# gives the most "condensed and tall" feel without distorting.
SUBTITLE_VERTICAL_SCALE = 125
# Negative tracking (tightens the letters). Confirmed at -8 after several
# rounds of comparison at different font sizes -- see the note in
# subtitle_generator about why this is applied as a \fsp override instead
# of the Style's Spacing field (libass ignores negative Spacing).
SUBTITLE_TRACKING = -8
BOTTOM_MARGIN_FRACTION = 0.20  # vertical/square video: safe zone to avoid clashing with the Instagram/TikTok UI
# Horizontal video (wider than tall, e.g. YouTube) has no app UI covering
# the bottom fifth of the frame, so 0.20 left the captions floating too
# high. 0.10 is the usual placement for horizontal subtitles.
HORIZONTAL_BOTTOM_MARGIN_FRACTION = 0.10
