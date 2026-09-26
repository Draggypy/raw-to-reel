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


def process_video(video: Path) -> bool:
    logger.log(f"Processing: {video.name}")

    try:
        result = transcription.transcribe_video(video)

        if not result.words:
            logger.log("WARNING: the transcription returned no words, nothing to keep")
            return False

        logger.update_status(video.name, "detecting silences")
        silences = silence_detector.detect_silences(result.audio_path)
        logger.log(f"Silences detected: {len(silences)}")

        width, height = subtitle_generator.get_dimensions(video)
        total_duration = video_processor.get_total_duration(video)

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
            logger.log("ERROR: no segment was left to keep")
            return False

        logger.update_status(video.name, "generating subtitles")
        remapped_words = subtitle_generator.remap_words(result.words, segments)
        captions = subtitle_generator.group_into_captions(remapped_words)

        config.TEMP.mkdir(parents=True, exist_ok=True)
        ass_path = config.TEMP / f"{video.stem}.ass"
        subtitle_generator.generate_ass(captions, width, height, ass_path)

        logger.update_status(video.name, "cutting and rendering")
        temp_path = config.TEMP / video.name
        video_processor.cut_and_add_subtitles(video, segments, ass_path, temp_path)

        try:
            ass_path.unlink()
        except OSError:
            pass

        logger.update_status(video.name, "validating")
        validation_result = validator.validate(temp_path, segments)
        if not validation_result.ok:
            logger.log(f"VALIDATION ERROR: {validation_result.reason}")
            return False

    except Exception as e:
        logger.log(f"ERROR processing video: {e}")
        return False

    logger.update_status(video.name, "moving to Ready")
    ok = file_manager.finalize(temp_path, video)
    logger.log(f"Done: {video.name}" if ok else f"Failed: {video.name}")
    return ok


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

        success = process_video(video)
        if not success:
            file_manager.mark_failed(video)

    logger.log("RawToReel stopping")
    logger.update_status(None, "stopped")


if __name__ == "__main__":
    main()
