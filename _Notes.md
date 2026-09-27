# RawToReel — Dev Notes

Talking-head video processor: cuts silences, conservatively cuts filler words/repetitions, burns subtitles. Runs as a systemd service (originally `gianni-edit.service`) — only watches `Raw/`, no need to launch it by hand.

## ⚠️ Incident fixed 2026-09-14: the service was running "into thin air"

The real folder had been moved to `Escritorio/System/Gianni Edit/` at some earlier point, but the systemd service still had the old path (`Escritorio/Gianni Edit/`) in memory — it kept showing "active" per `systemctl status`, but it was writing its state into an almost-empty folder and never saw the videos landing in the real `Raw/`. It stayed a zombie: looked like it was running, did nothing.

**Fixed by moving everything to `~/Vault/`:** the service was stopped, everything was consolidated into `~/Vault/RawToReel/` (the real copy, with `venv/`, `src/`, `Raw/`, `Logs/` with real history), `ExecStart` in `~/.config/systemd/user/gianni-edit.service` was updated to the new path, and it was restarted. Verified via `/proc/<pid>/cwd` and the timestamps on `Logs/status.json`, which now writes where it should.

**Lesson for next time this folder gets moved:** after moving it, `ExecStart` in the `.service` file has to be updated and `systemctl --user daemon-reload && systemctl --user restart gianni-edit.service` has to be run — otherwise the same silent bug repeats itself.

## Key parameters (`src/config.py`)

- `MIN_SILENCE_DURATION_MS = 300` — floor for how much silence is needed to cut (raised from 250 on 2026-09-13).
- `SILENCE_MARGIN_MS = 150` — buffer on each edge of a cut so as not to eat into a word (raised from 50 on 2026-09-20).
- `MIN_CUT_MS = 150` — a cut that saves less than this doesn't happen (added 2026-09-26: it eliminated 20ms micro-cuts that felt like "out of nowhere" jumps).
- `MIN_SEGMENT_SEC = 0.5` — prevents sub-second scene flashes (raised from 0.3 on 2026-09-26).
- `DB_THRESHOLD_MAX = -35` — threshold ceiling, out of the voice range (lowered from -28 on 2026-09-26).
- Detector with smoothing (50ms) + hysteresis (3dB), and cuts never step on a word start according to Whisper.
- `AMBIGUOUS_FILLER_WORDS = {este, tipo, o sea}` — only cut with a real pause right next to them.
- `MIN_MIDSENTENCE_PAUSE_MS = 1000` / `MIDSENTENCE_MARGIN_MS = 250` — a pause in the middle of a sentence (per Whisper's punctuation) is only cut if it lasts 1s+, and leaves 500ms of air (2026-09-26, feedback: "talking about the same topic for 10 seconds and it cuts out of nowhere").
- `CUT_REPETITIONS = False` — turned off 2026-09-26: we repeat things to specify/emphasize, and cutting it was "hallucinating". The editor specializes in silences + filler words. The code stays in place to re-enable with True.
- `AUDIO_FADE_SEC = 0.012` — audio fade in/out per segment so the cut doesn't click.

## Incident 2026-09-26: videos going to failed/ "for no reason"

`VID_20260926_033221.mp4` (Xiaomi, HEVC 1080p, 29.8s) was going to `failed/`.
Real cause: the audio track was **empty** — 0 samples, no codec
(codec_tag 0x0000), an 8-byte `stbl`, `mdhd duration=0`. The phone recorded
video and no audio at all. ffmpeg used to fail with "Output file does not
contain any stream", which explains nothing. Now
`transcription.verify_audio_usable` catches this beforehand and the log
clearly states the video has no audio. Not a cutting bug: with no audio
there's nothing to edit.

## Incident 2026-09-26: the codebase was rewritten in English

Everything (identifiers, comments, log messages, the README) used to be in
Spanish. Rewritten in English top to bottom, targeting an English-speaking
audience, keeping the folders/files that map to real filesystem paths in
sync (`Crudos/` → `Raw/`, `Listos/` → `Ready/`, `fallidos/` → `failed/`,
`ver_estado.py` → `watch_status.py`, `editor_gianni.log` →
`rawtoreel.log`, `estado.json` → `status.json`). On purpose, `FILLER_WORDS`
and `AMBIGUOUS_FILLER_WORDS` keep their Spanish values ("eh", "o sea",
"tipo"...) and `WHISPER_LANGUAGE` stays `"es"`: the product still
transcribes and edits Spanish speech, only the codebase's own language
changed.

## Pending

Human quality review (subtitles, how the cut feels) — the mechanical validation passes, but nobody has closely listened to/watched the result yet.

## Incident 2026-09-27: horizontal videos going to failed/

User report: "lots of horizontal videos go to failed/". Reproduced with a
5-minute horizontal 25fps video: `expected duration 285.43s, real 287.04s
(tolerance 1.35s for 60 segments)`. Root cause: every cut comes out a few
ms longer than requested (frame rounding + AAC framing) — measured ~23ms
per cut at 25fps, ~21ms at 24fps, ~20ms at 30fps, ~8ms at 60fps — while the
validator allowed 20ms per cut against the *requested* durations. Short
30fps vertical Reels never hit it; longer 24/25fps horizontal footage did
after ~47 cuts (25fps) / ~94 cuts (24fps). The same drift made subtitles
fall out of sync by over a second at the end of long videos.

Fix: `video_processor.cut_segments` measures each cut file's real duration;
subtitles are remapped with those real durations and the validator compares
against their sum. Also fixed in the same pass: rotation-tagged phone video
got subtitles laid out for the wrong orientation (`get_dimensions` now
applies rotation), 10-bit/4:4:4 sources produced unplayable High 10/High
4:4:4 H.264 (output now forced to yuv420p with even dimensions), horizontal
subtitles get their own bottom margin, and every failed video gets a
`<name>.error.txt` next to it with the reason.
