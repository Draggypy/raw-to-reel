"""Unit and cross-platform (Linux / Windows) compatibility tests for
RawToReel. Runs with Python's standard unittest (no extra dependencies
required).
"""

import os
import sys
import unittest
import tempfile
import subprocess
from pathlib import Path

# Add src to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

import config
import cut_manager
from cut_manager import Cut, Segment
import repetition_detector
import silence_detector
from silence_detector import Silence
from transcription import Word
import subtitle_generator
from subtitle_generator import Caption
import transcription
import video_processor

MARGIN = config.SILENCE_MARGIN_MS / 1000
MIDSENTENCE_MARGIN = config.MIDSENTENCE_MARGIN_MS / 1000
MIDSENTENCE_PAUSE = config.MIN_MIDSENTENCE_PAUSE_MS / 1000
MIN_CUT = config.MIN_CUT_MS / 1000


class TestCutManager(unittest.TestCase):

    def test_cuts_from_silences(self):
        silences = [
            Silence(start=1.0, end=3.0),
            Silence(start=5.0, end=5.1),  # Too short for the margin
        ]
        cuts = cut_manager.cuts_from_silences(silences)
        self.assertEqual(len(cuts), 1)
        # The cut must respect the safety margin
        self.assertAlmostEqual(cuts[0].start, 1.0 + MARGIN)
        self.assertAlmostEqual(cuts[0].end, 3.0 - MARGIN)

    def test_micro_cut_is_discarded(self):
        # Pause just above the minimum silence: after both margins it
        # would leave a ~20ms cut -- a visual jump for nothing.
        just_below = 2 * MARGIN + MIN_CUT - 0.02
        just_above = 2 * MARGIN + MIN_CUT + 0.02
        silences = [
            Silence(start=1.0, end=1.0 + just_below),
            Silence(start=5.0, end=5.0 + just_above),
        ]
        cuts = cut_manager.cuts_from_silences(silences)
        self.assertEqual(len(cuts), 1)
        self.assertAlmostEqual(cuts[0].start, 5.0 + MARGIN)

    def test_cut_does_not_step_on_word_start(self):
        # Volume says silence from 1.0 to 3.0, but Whisper heard a word
        # starting at 2.0: that's soft voice, the cut ends a margin before it.
        silences = [Silence(start=1.0, end=3.0)]
        words = [Word("soft", 2.0, 2.4)]
        cuts = cut_manager.cuts_from_silences(silences, words)
        self.assertEqual(len(cuts), 1)
        self.assertAlmostEqual(cuts[0].start, 1.0 + MARGIN)
        self.assertAlmostEqual(cuts[0].end, 2.0 - MARGIN)

    def test_cut_with_word_at_the_start_is_discarded(self):
        # A word starting almost at the beginning of the silence leaves
        # nothing useful to cut.
        silences = [Silence(start=1.0, end=3.0)]
        words = [Word("yes", 1.1, 1.3)]
        self.assertEqual(cut_manager.cuts_from_silences(silences, words), [])

    def test_word_outside_the_silence_has_no_effect(self):
        silences = [Silence(start=1.0, end=3.0)]
        words = [Word("before.", 0.2, 0.9), Word("After", 3.0, 3.5)]
        cuts = cut_manager.cuts_from_silences(silences, words)
        self.assertEqual(len(cuts), 1)
        self.assertAlmostEqual(cuts[0].end, 3.0 - MARGIN)

    def test_short_midsentence_pause_is_not_cut(self):
        # "we are talking [0.8s] about a topic": a breath mid-sentence,
        # speech rhythm -- not touched even if it exceeds the general minimum.
        words = [Word("we", 0.0, 0.5), Word("are", 0.5, 1.0), Word("talking", 1.8, 2.0)]
        silences = [Silence(start=1.0, end=1.0 + MIDSENTENCE_PAUSE - 0.2)]
        self.assertEqual(cut_manager.cuts_from_silences(silences, words), [])

    def test_long_midsentence_pause_is_cut_leaving_more_air(self):
        words = [Word("we", 0.0, 0.5), Word("are", 0.5, 1.0), Word("talking", 2.6, 2.8)]
        silences = [Silence(start=1.0, end=2.6)]
        cuts = cut_manager.cuts_from_silences(silences, words)
        self.assertEqual(len(cuts), 1)
        self.assertAlmostEqual(cuts[0].start, 1.0 + MIDSENTENCE_MARGIN)
        self.assertAlmostEqual(cuts[0].end, 2.6 - MIDSENTENCE_MARGIN)

    def test_pause_between_sentences_is_cut_with_normal_margin(self):
        words = [Word("topic.", 0.5, 1.0), Word("Now", 1.6, 1.9)]
        silences = [Silence(start=1.0, end=1.6)]
        cuts = cut_manager.cuts_from_silences(silences, words)
        self.assertEqual(len(cuts), 1)
        self.assertAlmostEqual(cuts[0].start, 1.0 + MARGIN)
        self.assertAlmostEqual(cuts[0].end, 1.6 - MARGIN)

    def test_comma_and_ellipsis(self):
        silences = [Silence(start=1.0, end=1.8)]
        with_comma = [Word("topic,", 0.5, 1.0)]
        self.assertEqual(cut_manager.cuts_from_silences(silences, with_comma), [])
        with_ellipsis = [Word("topic...", 0.5, 1.0)]
        self.assertEqual(len(cut_manager.cuts_from_silences(silences, with_ellipsis)), 1)

    def test_remap_interval(self):
        # A 10s video, cut: keeps [0, 2] and [4, 7]
        segments = [Segment(start=0.0, end=2.0), Segment(start=4.0, end=7.0)]

        # A word in [0.5, 1.5] within segment 1
        remapped = cut_manager.remap_interval(0.5, 1.5, segments)
        self.assertIsNotNone(remapped)
        self.assertAlmostEqual(remapped[0], 0.5)
        self.assertAlmostEqual(remapped[1], 1.5)

        # A word in [4.5, 5.5] within segment 2 (new time = 2 + (4.5 - 4) = 2.5)
        remapped2 = cut_manager.remap_interval(4.5, 5.5, segments)
        self.assertIsNotNone(remapped2)
        self.assertAlmostEqual(remapped2[0], 2.5)
        self.assertAlmostEqual(remapped2[1], 3.5)

        # A word in [2.5, 3.5] (removed zone)
        remapped_empty = cut_manager.remap_interval(2.5, 3.5, segments)
        self.assertIsNone(remapped_empty)


def _synthetic_db(*segments):
    """dB curve in SILENCE_WINDOW_MS windows: (duration_sec, level_db)."""
    window = config.SILENCE_WINDOW_MS / 1000
    parts = [np.full(round(dur / window), level, dtype=float) for dur, level in segments]
    return np.concatenate(parts)


class TestSilenceDetector(unittest.TestCase):

    def test_clear_pause_is_detected(self):
        db = _synthetic_db((2.0, -25.0), (1.0, -50.0), (2.0, -25.0))
        silences = silence_detector._silences_from_db(db)
        self.assertEqual(len(silences), 1)
        self.assertAlmostEqual(silences[0].start, 2.0, delta=0.06)
        self.assertAlmostEqual(silences[0].end, 3.0, delta=0.06)

    def test_soft_voice_is_not_silence(self):
        # Soft voice at -30dB (within the measured voice range) on a video
        # with a high floor: the threshold used to be able to rise to -28
        # and cut it.
        db = _synthetic_db((2.0, -22.0), (1.0, -30.0), (2.0, -22.0))
        self.assertEqual(silence_detector._silences_from_db(db), [])

    def test_oscillation_around_threshold_does_not_fragment(self):
        # Voice grazing the threshold, alternating every 10ms +-2dB around a
        # threshold of ~-38dB: without smoothing or hysteresis this used to
        # produce dozens of one-window cuts. Should yield zero silences.
        floor = _synthetic_db((1.0, -55.0))
        voice = _synthetic_db((2.0, -25.0))
        oscillating = np.tile([-36.0, -40.0], 50)  # 1s alternating
        db = np.concatenate([floor, voice, oscillating, voice])
        silences = silence_detector._silences_from_db(db)
        # the only silence is the initial floor; the oscillating zone (3s-4s) isn't
        self.assertEqual(len(silences), 1)
        self.assertLessEqual(silences[0].end, 1.06)

    def test_hysteresis_closes_silence_on_voice(self):
        # Real silence followed by a word just above the threshold: the
        # silence has to close right there, not eat into the word.
        db = _synthetic_db((1.0, -55.0), (1.0, -25.0), (1.0, -55.0), (0.5, -37.0), (1.0, -25.0))
        silences = silence_detector._silences_from_db(db)
        self.assertEqual(len(silences), 2)
        self.assertAlmostEqual(silences[1].end, 3.0, delta=0.06)


class TestFillerWords(unittest.TestCase):

    def _words(self, *texts, step=0.3):
        # Whisper stretches the end of each word up to the start of the next one
        return [Word(t, i * step, (i + 1) * step) for i, t in enumerate(texts)]

    def test_unambiguous_filler_word_is_always_cut(self):
        words = self._words("yo", "eh", "creo")
        cuts = repetition_detector.detect_filler_words(words)
        self.assertEqual(len(cuts), 1)
        self.assertAlmostEqual(cuts[0].start, 0.3)
        # guard before the start of "creo"
        self.assertAlmostEqual(cuts[0].end, 0.6 - config.ONSET_GUARD_SEC)

    def test_este_in_a_fluent_sentence_is_not_cut(self):
        words = self._words("en", "este", "video", "vamos")
        self.assertEqual(repetition_detector.detect_filler_words(words, []), [])

    def test_este_with_adjacent_pause_is_cut(self):
        # hesitant "este": Whisper stretches it over the pause that follows
        words = [
            Word("y", 0.0, 0.3),
            Word("este", 0.3, 1.5),
            Word("bueno", 1.5, 1.9),
        ]
        silences = [Silence(start=0.7, end=1.45)]
        cuts = repetition_detector.detect_filler_words(words, silences)
        self.assertEqual(len(cuts), 1)
        self.assertAlmostEqual(cuts[0].start, 0.3)

    def test_multiword_o_sea_with_pause(self):
        words = self._words("o", "sea", "vamos")
        silences = [Silence(start=-0.5, end=0.05)]
        cuts = repetition_detector.detect_filler_words(words, silences)
        self.assertEqual(len(cuts), 1)
        self.assertAlmostEqual(cuts[0].start, 0.0)

    def test_repetition_with_pause_in_between_is_cut(self):
        # "yo creo... [pause] yo creo que si": a real stumble
        words = self._words("yo", "creo", "yo", "creo", "que", "si")
        silences = [Silence(start=0.45, end=0.6)]
        cuts = repetition_detector.detect_repetitions(words, silences)
        self.assertEqual(len(cuts), 1)
        self.assertAlmostEqual(cuts[0].start, 0.0)
        self.assertAlmostEqual(cuts[0].end, 0.6 - config.ONSET_GUARD_SEC)

    def test_repetition_for_emphasis_is_not_cut(self):
        # repeated back-to-back for emphasis, no pause
        words = self._words("y", "pulas", "y", "pulas", "y", "pulas", "eso")
        self.assertEqual(repetition_detector.detect_repetitions(words, []), [])

    def test_repetition_with_filler_word_in_between_is_cut(self):
        words = self._words("yo", "creo", "eh", "yo", "creo", "que")
        cuts = repetition_detector.detect_repetitions(words, [])
        self.assertEqual(len(cuts), 1)
        self.assertAlmostEqual(cuts[0].start, 0.0)
        self.assertAlmostEqual(cuts[0].end, 0.9 - config.ONSET_GUARD_SEC)


class TestSubtitleGenerator(unittest.TestCase):

    def test_format_ass_time(self):
        self.assertEqual(subtitle_generator._format_ass_time(0.0), "0:00:00.00")
        self.assertEqual(subtitle_generator._format_ass_time(65.5), "0:01:05.50")
        self.assertEqual(subtitle_generator._format_ass_time(3661.12), "1:01:01.12")

    def test_group_into_captions(self):
        words = [
            Word(text="Hello", start=0.1, end=0.4),
            Word(text="world", start=0.5, end=0.9),
            Word(text="this", start=2.0, end=2.3),
            Word(text="is", start=2.4, end=2.6),
            Word(text="a", start=2.7, end=2.9),
            Word(text="test", start=3.0, end=3.4),
        ]
        captions = subtitle_generator.group_into_captions(words)
        self.assertGreater(len(captions), 0)
        # Every caption must have text and a time range
        for cap in captions:
            self.assertTrue(len(cap.text) > 0)
            self.assertGreater(cap.end, cap.start)


class TestFilterPathWindowsCompat(unittest.TestCase):

    def test_escape_posix_path(self):
        p = Path("/tmp/subtitles.ass")
        escaped = video_processor._escape_path_for_filter(p)
        self.assertTrue(escaped.startswith("'") and escaped.endswith("'"))
        self.assertIn("/tmp/subtitles.ass", escaped)

    def test_escape_windows_style_path(self):
        # Simulates a path with colons and Windows-style backslashes
        class FakeWindowsPath:
            def __str__(self):
                return "C:\\Users\\runneradmin\\AppData\\Local\\Temp\\video.ass"

        escaped_text = video_processor._escape_path_for_filter(FakeWindowsPath())
        # In FFmpeg, ':' must be escaped as '\:' so the ass= filter doesn't fail
        self.assertIn("C\\:", escaped_text)


class TestRealFFmpegPipeline(unittest.TestCase):

    def test_synthetic_cut_and_subtitle(self):
        """Generates a synthetic 2-second video, cuts it, and burns a test .ass subtitle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            source_video = tmppath / "source.mp4"
            output_video = tmppath / "output.mp4"
            ass_path = tmppath / "test.ass"

            # 1. Create a synthetic video with ffmpeg (2 seconds with audio)
            gen_cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=25",
                "-f", "lavfi", "-i", "sine=frequency=1000:duration=2",
                "-c:v", "libx264", "-c:a", "aac",
                str(source_video)
            ]
            gen_result = subprocess.run(gen_cmd, capture_output=True, text=True)
            self.assertEqual(gen_result.returncode, 0, f"Error generating synthetic video: {gen_result.stderr}")

            # 2. Generate a basic .ass file
            captions = [
                Caption(text="Subtitle test", start=0.2, end=1.2)
            ]
            subtitle_generator.generate_ass(captions, 320, 240, ass_path)
            self.assertTrue(ass_path.exists())

            # 3. Cut segment [0.0 - 1.5] and burn the subtitle
            segments = [Segment(start=0.0, end=1.5)]
            video_processor.cut_and_add_subtitles(source_video, segments, ass_path, output_video)

            self.assertTrue(output_video.exists(), "The output video was not created")
            self.assertGreater(output_video.stat().st_size, 1000, "The output video is empty or corrupted")


class TestUsableAudio(unittest.TestCase):

    def _synthetic_video(self, tmppath, with_audio):
        destination = tmppath / ("with_audio.mp4" if with_audio else "without_audio.mp4")
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=25"]
        if with_audio:
            cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "aac"]
        cmd += ["-c:v", "libx264", str(destination)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        return destination

    def test_video_without_audio_track_fails_with_clear_message(self):
        # Real case: a phone recorded video but no audio samples at all.
        # ffmpeg used to fail with "Output file does not contain any stream".
        with tempfile.TemporaryDirectory() as tmpdir:
            video = self._synthetic_video(Path(tmpdir), with_audio=False)
            with self.assertRaises(RuntimeError) as ctx:
                transcription.extract_audio(video)
            self.assertIn("audio", str(ctx.exception).lower())
            self.assertNotIn("does not contain any stream", str(ctx.exception))

    def test_video_with_audio_passes_the_check(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            video = self._synthetic_video(Path(tmpdir), with_audio=True)
            transcription.verify_audio_usable(video)  # must not raise


class TestWhisperEngine(unittest.TestCase):

    def test_faster_whisper_loads_model_on_cpu(self):
        """Checks that faster-whisper and the ctranslate2 runtime initialize correctly."""
        from faster_whisper import WhisperModel
        # Using the 'tiny' model for a quick, lightweight test (~39MB)
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        self.assertIsNotNone(model)
        del model


if __name__ == "__main__":
    unittest.main()
