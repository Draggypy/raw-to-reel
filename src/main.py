"""RawToReel -- entry point.

Loop: find a stable video in Raw/, process it fully, repeat. One video at
a time, always. No separate watcher: this same program does the scanning
and the processing.

Real pipeline (Phases 3-11, all already integrated here): transcribe ->
detect silences + filler words/repetitions -> consolidate cuts (without
stepping on word starts) -> generate remapped subtitles -> cut + burn
subtitles with ffmpeg -> validate. Only if all of that goes well is
file_manager.finalize() called, and only then does it move the result to
Ready/ and delete the original from Raw/.
"""

import signal
import time
from pathlib import Path
from typing import List, Optional

import config
import cut_manager
import file_manager
import logger
import repetition_detector
import scanner
import silence_detector
import subtitle_generator
import transcription
import validator
import video_processor

_keep_running = True


def _handle_stop_signal(signum, frame):
    global _keep_running
    logger.log(f"Signal {signum} received, finishing after the current video (if any)")
    _keep_running = False


def process_video(video: Path) -> Optional[str]:
    """Processes one video end to end. Returns None on success, or the
    human-readable reason it failed (written next to the video in
    Raw/failed/ so the user doesn't have to dig through the log)."""
    logger.log(f"Processing: {video.name}")
    temp_path = config.TEMP / video.name
    segment_files: List[Path] = []

    try:
        result = transcription.transcribe_video(video)

        if not result.words:
            reason = "the transcription returned no words, nothing to keep"
            logger.log(f"WARNING: {reason}")
            return reason

        logger.update_status(video.name, "detecting silences")
        silences = silence_detector.detect_silences(result.audio_path)
        logger.log(f"Silences detected: {len(silences)}")

        width, height = subtitle_generator.get_dimensions(video)
        total_duration = video_processor.get_total_duration(video)
        orientation = "horizontal" if width > height else "vertical" if height > width else "square"
        logger.log(f"Output size: {width}x{height} ({orientation})")

        try:
            result.audio_path.unlink()
        except OSError:
            pass  # not critical, it's just the intermediate WAV

        logger.update_status(video.name, "looking for filler words")
        filler_cuts = repetition_detector.detect_filler_words(result.words, silences)
        repetition_cuts = (
            repetition_detector.detect_repetitions(result.words, silences)
            if config.CUT_REPETITIONS
            else []
        )
        logger.log(
            f"Filler words: {len(filler_cuts)}, repetitions: {len(repetition_cuts)}"
        )

        logger.update_status(video.name, "consolidating cuts")
        cuts = (
            cut_manager.cuts_from_silences(silences, result.words)
            + filler_cuts
            + repetition_cuts
        )
        segments = cut_manager.consolidate(cuts, total_duration, result.words)
        logger.log(f"Segments to keep: {len(segments)} (out of {total_duration:.1f}s original)")

        if not segments:
            reason = "no segment was left to keep"
            logger.log(f"ERROR: {reason}")
            return reason

        logger.update_status(video.name, "cutting segments")
        config.TEMP.mkdir(parents=True, exist_ok=True)
        cut_files = video_processor.cut_segments(video, segments, temp_path)
        segment_files = [path for path, _ in cut_files]
        real_durations = [duration for _, duration in cut_files]
        expected_duration = sum(real_durations)
        logger.log(
            f"Cut duration: {expected_duration:.2f}s real "
            f"(requested {sum(s.duration for s in segments):.2f}s)"
        )

        logger.update_status(video.name, "generating subtitles")
        remapped_words = subtitle_generator.remap_words(result.words, segments, real_durations)
        captions = subtitle_generator.group_into_captions(remapped_words)
        ass_path = config.TEMP / f"{video.stem}.ass"
        subtitle_generator.generate_ass(captions, width, height, ass_path)

        logger.update_status(video.name, "rendering")
        video_processor.join_and_burn_subtitles(segment_files, ass_path, temp_path)

        try:
            ass_path.unlink()
        except OSError:
            pass

        logger.update_status(video.name, "validating")
        validation_result = validator.validate(temp_path, expected_duration, len(segments))
        if not validation_result.ok:
            reason = f"validation failed: {validation_result.reason}"
            logger.log(f"VALIDATION ERROR: {validation_result.reason}")
            return reason

    except Exception as e:
        logger.log(f"ERROR processing video: {e}")
        return f"error processing video: {e}"
    finally:
        video_processor.remove_files(segment_files)

    logger.update_status(video.name, "moving to Ready")
    if file_manager.finalize(temp_path, video):
        logger.log(f"Done: {video.name}")
        return None
    logger.log(f"Failed: {video.name}")
    return "the finished video could not be copied to Ready/ (see Logs/rawtoreel.log)"


def main() -> None:
    signal.signal(signal.SIGINT, _handle_stop_signal)
    signal.signal(signal.SIGTERM, _handle_stop_signal)

    logger.log("RawToReel starting")

    while _keep_running:
        video = scanner.next_video()

        if video is None:
            logger.update_status(None, "waiting")
            time.sleep(config.SCAN_INTERVAL_SEC)
            continue

        failure_reason = process_video(video)
        if failure_reason is not None:
            file_manager.mark_failed(video, failure_reason)

    logger.log("RawToReel stopping")
    logger.update_status(None, "stopped")


if __name__ == "__main__":
    main()
