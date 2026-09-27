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
import validator
import video_processor
import file_manager
import main
import scanner


def _ffmpeg(*args):
    return subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
                          capture_output=True, text=True)


def _probe_video(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height,pix_fmt", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    width, height, pix_fmt = r.stdout.strip().rstrip(",").split(",")[:3]
    return int(width), int(height), pix_fmt

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

    def test_remap_interval_uses_real_segment_durations(self):
        # Every cut file comes out a few ms longer than requested; the
        # concat demuxer offsets the next file by the REAL duration, so
        # subtitles have to as well or they drift out of sync.
        segments = [Segment(start=0.0, end=2.0), Segment(start=4.0, end=7.0)]
        remapped = cut_manager.remap_interval(4.5, 5.5, segments, real_durations=[2.04, 3.02])
        self.assertAlmostEqual(remapped[0], 2.04 + 0.5)
        self.assertAlmostEqual(remapped[1], 2.04 + 1.5)


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


class TestLanguageDetection(unittest.TestCase):

    def test_filler_words_for_spanish(self):
        filler, ambiguous = config.filler_words_for("es")
        self.assertEqual(filler, config.FILLER_WORDS)
        self.assertEqual(ambiguous, config.AMBIGUOUS_FILLER_WORDS)

    def test_filler_words_for_english(self):
        filler, ambiguous = config.filler_words_for("en")
        self.assertIn("um", filler)
        self.assertIn("like", ambiguous)
        self.assertNotIn("eh", filler)  # not the Spanish list

    def test_filler_words_for_unknown_language_falls_back_to_spanish(self):
        # Safe by construction: an unmapped language just means the Spanish
        # list is used, which won't match foreign words -- nothing gets
        # wrongly cut, it just cuts nothing extra.
        filler, ambiguous = config.filler_words_for("fr")
        self.assertEqual(filler, config.FILLER_WORDS)

    def test_english_unambiguous_filler_is_always_cut(self):
        words = [Word(t, i * 0.3, (i + 1) * 0.3) for i, t in enumerate(["I", "um", "think"])]
        filler, ambiguous = config.filler_words_for("en")
        cuts = repetition_detector.detect_filler_words(words, [], filler, ambiguous)
        self.assertEqual(len(cuts), 1)
        self.assertAlmostEqual(cuts[0].start, 0.3)

    def test_english_ambiguous_filler_in_fluent_sentence_is_not_cut(self):
        words = [Word(t, i * 0.3, (i + 1) * 0.3) for i, t in enumerate(["I", "really", "like", "this"])]
        filler, ambiguous = config.filler_words_for("en")
        self.assertEqual(repetition_detector.detect_filler_words(words, [], filler, ambiguous), [])

    def test_english_ambiguous_filler_with_pause_is_cut(self):
        words = [
            Word("so", 0.0, 1.2),
            Word("that", 1.2, 1.5),
            Word("happened", 1.5, 1.9),
        ]
        silences = [Silence(start=0.3, end=1.15)]
        filler, ambiguous = config.filler_words_for("en")
        cuts = repetition_detector.detect_filler_words(words, silences, filler, ambiguous)
        self.assertEqual(len(cuts), 1)

    def test_english_repetition_with_pause_uses_english_filler_list(self):
        # "I think... um... I think this is great": the filler word between
        # the two occurrences is what marks it as a real stumble.
        words = [
            Word("I", 0.0, 0.3), Word("think", 0.3, 0.6),
            Word("um", 0.6, 0.9),
            Word("I", 0.9, 1.2), Word("think", 1.2, 1.5), Word("great", 1.5, 1.8),
        ]
        filler, _ = config.filler_words_for("en")
        cuts = repetition_detector.detect_repetitions(words, [], filler)
        self.assertEqual(len(cuts), 1)
        self.assertAlmostEqual(cuts[0].start, 0.0)


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


class TestConcatListEscaping(unittest.TestCase):

    def test_apostrophe_in_filename_does_not_break_concat_list(self):
        # Real bug found 2026-09-26: a video named with an apostrophe (a
        # completely ordinary filename, e.g. "gianni's_video.mp4") broke
        # the concat demuxer's file list -- the unescaped quote ended the
        # path early and ffmpeg tried to open a mangled path.
        escaped = video_processor._escape_path_for_concat_list(Path("/tmp/gianni's_video_seg0.mp4"))
        self.assertNotIn("''", escaped.replace("'\\''", ""))  # no bare unescaped quote left
        self.assertIn("'\\''", escaped)

    def test_path_without_apostrophe_is_unchanged(self):
        p = Path("/tmp/plain_video_seg0.mp4")
        self.assertEqual(video_processor._escape_path_for_concat_list(p), str(p))


class TestRealFFmpegPipeline(unittest.TestCase):

    def test_synthetic_cut_and_subtitle(self):
        """Generates a synthetic 2-second video, cuts it, and burns a test .ass subtitle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            source_video = tmppath / "source.mp4"
            output_video = tmppath / "output.mp4"
            ass_path = tmppath / "test.ass"

            gen = _ffmpeg("-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=25",
                          "-f", "lavfi", "-i", "sine=frequency=1000:duration=2",
                          "-c:v", "libx264", "-c:a", "aac", str(source_video))
            self.assertEqual(gen.returncode, 0, f"Error generating synthetic video: {gen.stderr}")

            subtitle_generator.generate_ass([Caption(text="Subtitle test", start=0.2, end=1.2)], 320, 240, ass_path)
            self.assertTrue(ass_path.exists())

            segments = [Segment(start=0.0, end=1.5)]
            cut_files = video_processor.cut_segments(source_video, segments, output_video)
            try:
                video_processor.join_and_burn_subtitles([f for f, _ in cut_files], ass_path, output_video)
            finally:
                video_processor.remove_files(f for f, _ in cut_files)

            self.assertTrue(output_video.exists(), "The output video was not created")
            self.assertGreater(output_video.stat().st_size, 1000, "The output video is empty or corrupted")
            self.assertTrue(all(not f.exists() for f, _ in cut_files), "Intermediate segment files were left behind")


class TestHorizontalAndPhoneFormats(unittest.TestCase):

    def test_many_cuts_at_25fps_pass_validation(self):
        # Real bug (2026-09-27): at 25fps each cut comes out ~23ms longer
        # than requested, and the validator allowed 20ms per cut -- any
        # 25fps video with ~47+ cuts (a few minutes of horizontal footage)
        # was rejected into failed/ even though nothing was wrong.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            source = tmppath / "h25.mp4"
            gen = _ffmpeg("-f", "lavfi", "-i", "testsrc=duration=70:size=160x90:rate=25",
                          "-f", "lavfi", "-i", "anoisesrc=d=70:a=0.1",
                          "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                          "-c:a", "aac", str(source))
            self.assertEqual(gen.returncode, 0, gen.stderr)

            segments = [Segment(start=i * 1.1, end=i * 1.1 + 0.9) for i in range(60)]
            output = tmppath / "out.mp4"
            ass_path = tmppath / "empty.ass"
            subtitle_generator.generate_ass([], 160, 90, ass_path)
            cut_files = video_processor.cut_segments(source, segments, output)
            try:
                video_processor.join_and_burn_subtitles([f for f, _ in cut_files], ass_path, output)
            finally:
                video_processor.remove_files(f for f, _ in cut_files)

            result = validator.validate(output, sum(d for _, d in cut_files), len(segments))
            self.assertTrue(result.ok, result.reason)

    def test_rotated_phone_video_reports_display_dimensions(self):
        # Phones store vertical video as a landscape frame + "rotate 90";
        # ffmpeg outputs it upright, so subtitles need the upright size.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            stored = tmppath / "stored.mp4"
            rotated = tmppath / "rotated.mp4"
            gen = _ffmpeg("-f", "lavfi", "-i", "testsrc=duration=1:size=320x180:rate=25",
                          "-c:v", "libx264", "-pix_fmt", "yuv420p", str(stored))
            self.assertEqual(gen.returncode, 0, gen.stderr)
            tag = _ffmpeg("-display_rotation", "90", "-i", str(stored), "-c", "copy", str(rotated))
            if tag.returncode != 0:
                self.skipTest("this ffmpeg build can't write rotation metadata (-display_rotation needs ffmpeg 6+)")
            self.assertEqual(subtitle_generator.get_dimensions(rotated), (180, 320))

    def test_10bit_odd_sized_source_comes_out_playable(self):
        # 10-bit HDR phone footage and odd-sized screen recordings used to
        # produce High 10 / High 4:4:4 H.264 that most players can't open.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            source = tmppath / "odd10.mp4"
            gen = _ffmpeg("-f", "lavfi", "-i", "testsrc=duration=2:size=321x181:rate=30",
                          "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                          "-c:v", "libx264", "-pix_fmt", "yuv444p10le", "-c:a", "aac", str(source))
            if gen.returncode != 0:
                self.skipTest("this ffmpeg build's libx264 can't encode 10-bit 4:4:4 sources")
            cut_files = video_processor.cut_segments(source, [Segment(0.0, 1.5)], tmppath / "out.mp4")
            try:
                width, height, pix_fmt = _probe_video(cut_files[0][0])
            finally:
                video_processor.remove_files(f for f, _ in cut_files)
            self.assertEqual(pix_fmt, "yuv420p")
            self.assertEqual((width % 2, height % 2), (0, 0))
            self.assertEqual(subtitle_generator.get_dimensions(source), (width, height))

    def test_horizontal_subtitles_use_the_horizontal_bottom_margin(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ass = Path(tmpdir) / "h.ass"
            subtitle_generator.generate_ass([Caption("hi", 0.0, 1.0)], 1920, 1080, ass)
            expected = round(1080 * config.HORIZONTAL_BOTTOM_MARGIN_FRACTION)
            self.assertIn(f",{expected},1\n", ass.read_text(encoding="utf-8"))


class TestOpenFolder(unittest.TestCase):

    def test_never_blocks_even_if_the_launcher_hangs(self):
        # Real risk: on Linux, xdg-open can hang (e.g. waiting on a D-Bus
        # session that isn't there). _open_folder must never make the scan
        # loop wait for it -- it's fire-and-forget.
        import shutil, subprocess, sys, tempfile, textwrap, time

        with tempfile.TemporaryDirectory() as tmpdir:
            fake_bin = Path(tmpdir) / "bin"
            fake_bin.mkdir()
            launcher_name = "xdg-open" if sys.platform not in ("win32", "darwin") else (
                "open" if sys.platform == "darwin" else None
            )
            if launcher_name is None:
                self.skipTest("os.startfile on Windows can't be shadowed with a fake binary")
            hanging_launcher = fake_bin / launcher_name
            hanging_launcher.write_text("#!/bin/sh" + "\n" + "sleep 60" + "\n")
            hanging_launcher.chmod(0o755)

            import os
            original_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{fake_bin}:{original_path}"
            try:
                start = time.monotonic()
                main._open_folder(Path(tmpdir))
                elapsed = time.monotonic() - start
            finally:
                os.environ["PATH"] = original_path
            self.assertLess(elapsed, 2.0, "the hanging launcher blocked the caller")

    def test_never_raises_when_the_launcher_does_not_exist(self):
        main._open_folder(Path("/this/path/does/not/matter"))  # must not raise


class TestFinalize(unittest.TestCase):

    def test_original_is_preserved_in_processed_not_deleted(self):
        # Real requirement (2026-09-27): never delete the user's original,
        # even after a successful edit -- only move it somewhere the
        # scanner won't pick it back up and reprocess forever.
        with tempfile.TemporaryDirectory() as tmpdir:
            original_ready, original_processed = config.READY, config.PROCESSED
            tmppath = Path(tmpdir)
            config.READY = tmppath / "Ready"
            config.PROCESSED = tmppath / "Raw" / "processed"
            try:
                original = tmppath / "clip.mp4"
                original.write_bytes(b"original bytes")
                temp_path = tmppath / "clip_edited.mp4"
                temp_path.write_bytes(b"edited bytes")

                ok = file_manager.finalize(temp_path, original)

                self.assertTrue(ok)
                self.assertFalse(original.exists(), "should be moved out of Raw/, not left there")
                self.assertTrue(
                    (config.PROCESSED / "clip.mp4").exists(), "original must survive in Raw/processed/"
                )
                self.assertEqual((config.PROCESSED / "clip.mp4").read_bytes(), b"original bytes")
                self.assertEqual((config.READY / "clip.mp4").read_bytes(), b"edited bytes")
                self.assertFalse(temp_path.exists())
            finally:
                config.READY, config.PROCESSED = original_ready, original_processed

    def test_processed_original_would_not_be_rescanned(self):
        # Guards the reason PROCESSED is a subfolder of Raw/ instead of
        # just leaving the file in Raw/ itself: list_pending_videos only
        # looks at files directly inside Raw/, so anything moved into a
        # subfolder is naturally out of the scan loop, with no extra
        # bookkeeping needed.
        with tempfile.TemporaryDirectory() as tmpdir:
            original_raw = config.RAW
            config.RAW = Path(tmpdir)
            try:
                (config.RAW / "processed").mkdir()
                (config.RAW / "processed" / "already_done.mp4").write_bytes(b"x")
                (config.RAW / "new_video.mp4").write_bytes(b"x")
                pending = scanner.list_pending_videos()
                self.assertEqual([p.name for p in pending], ["new_video.mp4"])
            finally:
                config.RAW = original_raw


class TestFailureReason(unittest.TestCase):

    def test_failed_video_gets_an_error_txt_with_the_reason(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_failed = config.FAILED
            config.FAILED = Path(tmpdir) / "failed"
            try:
                video = Path(tmpdir) / "clip.mp4"
                video.write_bytes(b"x")
                file_manager.mark_failed(video, "the transcription returned no words")
                sidecar = config.FAILED / "clip.mp4.error.txt"
                self.assertTrue((config.FAILED / "clip.mp4").exists())
                self.assertIn("the transcription returned no words", sidecar.read_text(encoding="utf-8"))
            finally:
                config.FAILED = original_failed


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

    def test_transcribe_video_carries_the_detected_language(self):
        # transcribe_video must plumb Whisper's detected language through to
        # TranscriptionResult -- that's what main.py uses to pick the right
        # filler-word list. Whisper itself is stubbed out (no network here).
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as tmpdir:
            video = self._synthetic_video(Path(tmpdir), with_audio=True)
            fake_words = [Word("hello", 0.0, 0.3)]
            with mock.patch.object(transcription, "transcribe", return_value=(fake_words, "en")):
                result = transcription.transcribe_video(video)
            self.assertEqual(result.language, "en")
            self.assertEqual(result.words, fake_words)


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
