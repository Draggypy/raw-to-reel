# RawToReel

**Automatic talking-head video editor: from raw to ready, without touching an editor.**

Drop a video of someone talking to camera into a folder. RawToReel cuts silences and filler words, adds word-by-word subtitles, and returns the edited video in another folder. On purpose, it **does not** cut repetitions ("look what happens here... but the opposite could happen... but this happens"): that's a common way of clarifying an idea while speaking, not a mistake. Everything runs on your own machine: no external APIs, no accounts, your video never gets uploaded anywhere.

Works with **vertical** video (Reels, TikTok, Instagram Stories), **horizontal** video (YouTube, courses, podcasts), and square video — the orientation is detected automatically.

<p align="center">
  <img src="assets/demo.gif" alt="RawToReel demo" width="320">
  <br>
  <em>Video processed 100% automatically with RawToReel (pause cutting + animated subtitles).</em>
</p>

```
   Raw/                         RawToReel                         Ready/
┌──────────────┐    ┌──────────────────────────────────────┐    ┌──────────────┐
│ my-video.mp4 │ ─► │ transcribes → detects → cuts →        │ ─► │ my-video.mp4 │
│ (unedited)   │    │ subtitles → renders → validates       │    │ (edited)     │
└──────────────┘    └──────────────────────────────────────┘    └──────────────┘
                                   │
                                   └─► if something fails: Raw/failed/  (the original is never lost)
```

---

## What it does

1. **Transcribes** the audio locally with [faster-whisper](https://github.com/SYSTRAN/faster-whisper), with word-level timestamps.
2. **Detects** silences (by the audio's real volume) and filler words ("um", "like", "you know"...). It distinguishes pauses between sentences from the natural rhythm within a sentence, so it doesn't cut you off while you're still talking.

   > **What about repetitions ("I think that... I think this is great")?** RawToReel **does not cut them**, on purpose. When speaking, it's very common to repeat an idea to reinforce or clarify it ("look what happens here... but the opposite could happen... but this happens"), and that's not a speech error — it's a way of explaining yourself. Cutting it automatically ended up deleting parts of the message the user meant to say that way, not by accident. The editor prefers to specialize in what it can confidently tell apart — real silences and filler words — rather than guess when a repetition is a "false start" and when it's emphasis. (The repetition detector is still in the code, turned off via `CUT_REPETITIONS = False` in `src/config.py`, for anyone who wants to try it.)
3. **Consolidates the cuts** into the final list of segments to keep, being careful not to leave sub-second scene "flashes".
4. **Generates subtitles** (`.ass` format) already aligned to the timing of the cut video.
5. **Cuts and burns in the subtitles** with `ffmpeg`.
6. **Validates** the result. Only if it passes every check is it delivered to `Ready/`; if not, the video goes to `Raw/failed/` and the original stays untouched.

## Requirements and Technical Specifications

| Requirement | Detail / Specification |
|---|---|
| **Python** | Python 3.10 or higher (developed and thoroughly tested on **Python 3.12**). |
| **FFmpeg** | Version 5.0+ with `ffprobe` and native compiled `libass` support (for subtitles). |
| **Operating systems** | **Linux** (x86_64, aarch64), **Windows 10 / 11** (64-bit), **macOS** (Apple Silicon M1/M2/M3 and Intel). |
| **Hardware** | Runs 100% on **CPU** (`int8` quantization). No dedicated GPU required, though it supports NVIDIA CUDA acceleration if configured in `config.py`. |
| **RAM** | Minimum 4 GB free RAM (8 GB recommended). |
| **Storage** | ~500 MB free for the local Whisper model (downloaded once on first run) + temporary space proportional to the video being processed. |

---

## Step-by-step installation

Pick your operating system and run the following commands in your terminal:

### 🐧 Linux (Ubuntu, Debian, Linux Mint, Pop!_OS)

```bash
# 1. Install system dependencies (Python, Git, and FFmpeg with libass)
sudo apt update
sudo apt install -y python3 python3-venv git ffmpeg

# 2. Clone the repository and enter the folder
git clone https://github.com/Draggypy/raw-to-reel.git
cd raw-to-reel

# 3. Create and activate the virtual environment
python3 -m venv venv
source venv/bin/activate

# 4. Install the Python dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

> **Arch Linux:** `sudo pacman -S python git ffmpeg`
> **Fedora:** `sudo dnf install -y python3 git ffmpeg-free`

---

### 🪟 Windows (10 and 11)

> [!TIP]
> **First time setting up development tools on Windows?**
> Unlike Linux or macOS, Windows doesn't come with **Git** or **FFmpeg** preinstalled, and it's very common to forget to link Python to the system when installing it. Follow these simple steps in **PowerShell** (or the **Windows Terminal** app).

#### Step 1: Install the required programs (Git, FFmpeg, and Python)

Open a **PowerShell** terminal as a regular user and install the tools with `winget` (Windows' official package manager):

```powershell
# 1. Install Git (essential for downloading and updating the project)
winget install Git.Git

# 2. Install FFmpeg (for cutting and processing video and subtitles)
winget install Gyan.FFmpeg

# 3. Install Python 3.12 (if you don't have it yet)
winget install Python.Python.3.12
```

> [!IMPORTANT]
> **If you'd rather install Python by downloading the official installer from [python.org](https://www.python.org/downloads/):**
> On the first screen of the installer, it's **MANDATORY** to check the box at the bottom:
> ☑ **"Add python.exe to PATH"**.
> If you skip this option, the console won't recognize the `python` or `pip` commands.

#### Step 2: Restart the terminal

> [!WARNING]
> **Close the current PowerShell window and open a new one.**
> This step is essential for Windows to load the new environment variables (`PATH`). To check that everything is available, run:
> ```powershell
> git --version
> python --version
> ffmpeg -version
> ```
> If all three respond with a version number, you're ready to go.

#### Step 3: Clone the project and create the virtual environment

```powershell
# 1. Clone the repository and enter the folder
git clone https://github.com/Draggypy/raw-to-reel.git
cd raw-to-reel

# 2. Create the isolated virtual environment for dependencies
python -m venv venv

# 3. Activate the virtual environment
.\venv\Scripts\Activate.ps1
```

> [!NOTE]
> **Getting a red error saying *"running scripts is disabled on this system"*?**
> PowerShell blocks script execution by default. Enable it for your user by running:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```
> Press `Y` (Yes) and run again: `.\venv\Scripts\Activate.ps1`.
> You'll know it's active because `(venv)` will appear at the start of your command line.
> *(If you use the traditional Command Prompt `cmd.exe`, you can activate it with: `venv\Scripts\activate.bat`)*.

#### Step 4: Install the Python dependencies

With the `(venv)` environment active in your terminal:

```powershell
# 1. Upgrade pip
python -m pip install --upgrade pip

# 2. Install all required libraries (faster-whisper, torch, etc.)
pip install -r requirements.txt
```

---

### 🍎 macOS (Apple Silicon M1/M2/M3 / Intel)

Open **Terminal**:

```bash
# 1. Install dependencies with Homebrew (if you don't have Homebrew: https://brew.sh)
brew install ffmpeg python git

# 2. Clone the repository and enter the folder
git clone https://github.com/Draggypy/raw-to-reel.git
cd raw-to-reel

# 3. Create and activate the virtual environment
python3 -m venv venv
source venv/bin/activate

# 4. Install the Python dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

---

### Verifying the installation

To confirm your whole environment (FFmpeg, Whisper, and dependencies) is set up and working 100%, you can run the automated test suite:

```bash
python -m unittest tests/test_core.py -v
```

If everything's in order, you'll see every test pass with `OK`.

> **Folders ready from the start:** the repository already comes with the `Raw/` folder (where you drop your videos) and `Ready/` (where you get the final video with subtitles and no silences). You don't need to create any folder by hand; the temp and log folders are managed automatically.

## How to use it

### Basic usage

```bash
# Activate the virtual environment (if not already active)
source venv/bin/activate          # on Windows: .\venv\Scripts\Activate.ps1
python src/main.py
```

When it starts, it prints a short welcome banner and **opens the `Raw/` folder for you** in your file manager — you don't need to already know where it is:

```
  ____                 _____     ____            _
 |  _ \ __ ___      __|_   _|__ |  _ \ ___  ___| |
 | |_) / _` \ \ /\ / /  | |/ _ \| |_) / _ \/ _ \ |
 |  _ < (_| |\ V  V /   | | (_) |  _ <  __/  __/ |
 |_| \_\__,_| \_/\_/    |_|\___/|_| \_\___|\___|_|

  * Cuts silences and filler words -- keeps repetitions, they're part of how people talk
  * Word-by-word subtitles, burned in and ready to post
  * Vertical, horizontal, and square video, any frame rate
  * Runs 100% on this machine: no accounts, no uploads, nothing leaves your computer

  Drop your videos into: /home/you/raw-to-reel/Raw
  Pick up the finished ones from: /home/you/raw-to-reel/Ready
  Press Ctrl+C to stop.
```

1. A window opens showing `Raw/`. Copy a video into it (formats: `.mp4`, `.mov`, `.mkv`, `.avi`).
2. The program detects it on its own. It waits until the copy is finished (it watches for the file size to stop changing), so you can transfer files from your phone or a USB drive with no issues.
3. It processes it — the same terminal prints each stage live as it happens.
4. When it's done, the terminal prints `Done: my-video.mp4 -> ready in Ready/`, and the file appears there **with the same name**.
5. The original moves from `Raw/` into `Raw/processed/` **only once the copy in `Ready/` has been verified** -- it's never deleted, so you can always go back to it.

The program stays running, watching `Raw/`. It processes **one video at a time**, oldest to newest. To stop it: `Ctrl+C` (it finishes the video currently being processed, then exits).

It also **opens `Ready/` for you** once your batch finishes (the queue drains to empty) — one popup per batch, not per video, so dropping in five videos doesn't open five windows.

> **Running it as an unattended service** (systemd, a headless server, over SSH — see below)? There's no desktop to pop a folder open on. Set `OPEN_RAW_FOLDER_ON_START = False` and `OPEN_READY_FOLDER_ON_DONE = False` in `src/config.py`; it's harmless to leave them on either way, they just silently do nothing without a desktop environment.

### Watching what it's doing

In another terminal, no need to activate the `venv`:

```bash
python3 watch_status.py        # on Windows: python watch_status.py
```

Shows the live stage of each video:

```
[2026-09-24 12:30:01] my-video.mp4 -> transcribing
[2026-09-24 12:31:14] my-video.mp4 -> detecting silences
...
[2026-09-24 12:33:40] (none) -> waiting
```

The stages, in order: `extracting audio` → `transcribing` → `detecting silences` → `looking for filler words` → `consolidating cuts` → `cutting segments` → `generating subtitles` → `rendering` → `validating` → `moving to Ready`.

The full history is kept in `Logs/rawtoreel.log` (one dated line per event, including how many silences, filler words, and segments it found for each video).

### Keeping it running permanently (Linux, systemd)

If you want it to start with the machine and process whatever you drop into `Raw/`, you can use a user service. Example (`~/.config/systemd/user/raw-to-reel.service`), adjusting the paths:

```ini
[Unit]
Description=RawToReel - Automatic video editor

[Service]
WorkingDirectory=/path/to/raw-to-reel
ExecStart=/path/to/raw-to-reel/venv/bin/python /path/to/raw-to-reel/src/main.py
Restart=on-failure
# Recommended on small machines: don't hog resources
Nice=15
CPUQuota=200%
MemoryMax=2500M

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now raw-to-reel.service
systemctl --user status raw-to-reel.service
```

> **Careful if you move the project folder:** you'll need to update the paths in the `.service` file and run `daemon-reload` + `restart`. Otherwise the service keeps showing as "active" while watching an old folder and processes nothing.

## What happens to your files

- **The original is never touched until the end, and never deleted.** A temporary copy is processed in `Temp/`. Only once the finished copy is in `Ready/` and its size matches the temporary file does the original move from `Raw/` into `Raw/processed/`.
- **Didn't like the result?** Move the file from `Raw/processed/` back into `Raw/` and it gets edited again from scratch -- the exact same recovery path as a failed video in `Raw/failed/`.
- **If something fails** (empty transcription, an `ffmpeg` error, a failed validation) the original is moved to `Raw/failed/` so it isn't retried in a loop, and **the reason is written right next to it** as `your-video.mp4.error.txt`. The full history is also in `Logs/rawtoreel.log`.
- **To retry** a failed video: move it back into `Raw/`.
- Everything under `Raw/`, `Ready/`, `Temp/`, and `Logs/` is in `.gitignore`: your videos never end up in the repository.

## Vertical, horizontal, and square video

Any orientation works; nothing needs to be configured:

- **Orientation is detected automatically**, including phone videos stored sideways with a rotation tag (very common: many phones save a vertical video as a landscape frame plus "rotate 90"). The output always comes out upright, and the subtitles are laid out for the upright frame.
- **Subtitle placement adapts:** on vertical and square video they sit higher (`BOTTOM_MARGIN_FRACTION`, clear of the Instagram/TikTok UI); on horizontal video they sit near the bottom like regular subtitles (`HORIZONTAL_BOTTOM_MARGIN_FRACTION`).
- **Any frame rate** (24, 25, 30, 60 fps, variable) and any length. Long videos with many cuts are validated against the real length of every cut, so they don't get falsely rejected.
- **The output always plays everywhere:** 8-bit H.264 with 4:2:0 color and even dimensions, whatever the source was (10-bit HDR, 4:4:4 screen recordings, odd sizes like 1366×767 get trimmed by one pixel).

## Troubleshooting

### The video ended up in `Raw/failed/`

Open the `.error.txt` file sitting next to the video in `Raw/failed/` — it states the exact reason, no need to guess. (It's also in the log: `grep -B 15 "Moved to failed" Logs/rawtoreel.log | tail -30`.)

The most common causes, from most to least frequent:

| Message in the log | What happened | What to do |
|---|---|---|
| `The video has no audio track` / `The video's audio track is empty` | **The phone recorded video but no audio.** The file has an audio track created but with zero samples (0 bytes of sound) — this happens when another app (a call, a voice recorder, an assistant) had the microphone locked when recording started, or the mic was muted/covered. | Play the video back: if you hear nothing, that confirms it. You'll need to re-record — there's no audio to edit. |
| `the transcription returned no words` | The audio exists and has sound, but Whisper didn't recognize any speech: volume too low, too much background noise/echo, the mic too far away, or the clip is of something else (music, ambient sound, noisy silence). | Record closer to the microphone and with less background noise. |
| `ffmpeg failed extracting audio: ...` | The video container is broken or `ffmpeg` doesn't recognize the audio/video codec. Could be a file that was recording when something interrupted it (power cut, storage filled up) or an exotic format. | Run `ffprobe your-video.mp4` and check what it says about the streams. If the file looks incomplete, it's a corrupted video, not a bug in the editor. |
| `ffmpeg failed cutting a segment` / `ffmpeg failed concatenating` / `ffmpeg failed burning subtitles` | A specific `ffmpeg` step failed — the full message (in `Logs/rawtoreel.log`, never truncated) carries the actual `ffmpeg` error underneath. | Copy the full message from the log; it almost always states the concrete problem (unsupported codec, out of disk space, subtitle font not found). |
| `VALIDATION ERROR: only weighs N bytes` | The final file came out empty or truncated — typically from running out of disk space mid-render. | Check free space in `Temp/` and `Ready/`. |
| `VALIDATION ERROR: has no video/audio stream` | The final file lost a track somewhere in the process (rare; a sign of an incomplete `ffmpeg` build). | Reinstall `ffmpeg`, making sure it has `libass` and complete audio/video codecs (see Requirements). |
| `VALIDATION ERROR: expected duration ...` | Joining the cut segments lost or added content: the final video's length doesn't match the sum of the segments that were actually cut. This should be very rare. (Before 2026-09-27 this also fired falsely on long 24/25 fps videos — typical horizontal footage — because it compared against the *requested* lengths; that's fixed.) | Update to the latest version (`git pull`). If it still happens, report it with the `.error.txt` and the log. |
| `VALIDATION ERROR: errors decoding` | The final file ended up corrupted somehow (rare — would be an actual bug). | Save the video from `Temp/` (it gets deleted on retry) and report it with the full log. |

### The video DID make it to `Ready/`, but something looks or sounds off

The automatic validation doesn't catch this because the file is technically valid — you have to look at it:

| Symptom | Likely cause | Where to adjust |
|---|---|---|
| No subtitles show up, or they look like an ugly/generic font | The font set in `SUBTITLE_FONT` isn't installed on your system; `ffmpeg`/`libass` silently falls back to a default font (not an error). | Install the font you want to use and put its exact name in `SUBTITLE_FONT` (see the licensing note in the Subtitles table). |
| Subtitles are out of sync with the audio | Subtitles are timed against the real length of every cut, so they shouldn't drift. (Before 2026-09-27 they drifted by ~20 ms per cut, which added up to over a second on long videos.) If you still see it, it's a real desync. | Update to the latest version (`git pull`). If it persists, report it with the log (`Cut duration: ... real (requested ...)` shows the numbers). |
| Still cuts mid-thought, feels like "it cuts the moment I stop talking" | Fine-tuning of sensitivity, not a bug. | Raise `MIN_MIDSENTENCE_PAUSE_MS` and/or `SILENCE_MARGIN_MS` in `src/config.py`. |
| Leaves very long silences uncut | The silence threshold is too strict for your background noise level. | Lower `DB_MARGIN_OVER_FLOOR` or carefully raise `DB_THRESHOLD_MAX` (see the comments in `config.py` — they're there so you don't break the balance). |
| Cuts "um"/"like"/"este"/"tipo" that were actually part of a normal sentence | A filler-word false positive. | Remove that word from `FILLER_WORDS`/`FILLER_WORDS_EN` (or from `AMBIGUOUS_FILLER_WORDS`/`AMBIGUOUS_FILLER_WORDS_EN` if it already requires a pause) in `src/config.py`. |

---

## Configuration

Everything adjustable lives in a single file: [`src/config.py`](src/config.py). Every constant has a comment next to it explaining why it has the value it has. The main ones:

### Cuts

| Constant | Default value | What it controls |
|---|---|---|
| `MIN_SILENCE_DURATION_MS` | `300` | A pause shorter than this is **not detected** as silence. |
| `SILENCE_MARGIN_MS` | `150` | How much silence is left on **each edge** of a cut. At 150, every cut pause leaves ~300 ms of audible silence. Lower it for tighter cuts; raise it if it feels like "it cuts the moment I stop talking". |
| `MIN_CUT_MS` | `150` | How much a cut has to **save** (margins already subtracted) to be worth the visual jump. Prevents 20 ms micro-cuts that felt like "it cuts out of nowhere". In practice, only pauses of `2 × SILENCE_MARGIN_MS + MIN_CUT` = 450 ms or more get cut. |
| `MIN_MIDSENTENCE_PAUSE_MS` / `MIDSENTENCE_MARGIN_MS` | `1000` / `250` | A pause **in the middle of a sentence** (the previous word doesn't end in `.` `?` `!`) is speech rhythm: it's only cut if it lasts 1 s or more, leaving 500 ms of air. Between sentences the normal rule applies. Raise the first one if it feels like it's cutting while you're still talking about the same topic. |
| `MIN_SEGMENT_SEC` | `0.5` | Prevents sub-second kept segments (they look like a flicker). |
| `AUDIO_FADE_SEC` | `0.012` | Audio fade at each cut edge, so the join doesn't produce a "click". |
| `DB_MARGIN_OVER_FLOOR` | `17` | Detector sensitivity: the "silence" threshold is the video's own noise floor plus this margin. |
| `DB_THRESHOLD_MAX` | `-35` | The threshold never rises above this, to avoid entering the voice range (soft speech sits around -30 dB). |
| `SILENCE_SMOOTHING_MS` / `HYSTERESIS_DB` | `50` / `3` | Smooth the volume curve and keep a soft voice that grazes the threshold from opening and closing silences several times a second. |
| `FILLER_WORDS` / `FILLER_WORDS_EN` | Spanish / English lists | Filler words to cut, one list per language. The one used is picked automatically from what Whisper detected (see `WHISPER_LANGUAGE`). Edit either to match how you speak. |
| `AMBIGUOUS_FILLER_WORDS` / `AMBIGUOUS_FILLER_WORDS_EN` | `este, tipo, o sea` / `like, so, well, i mean, you know, kind of, sort of` | Filler words that are also real words ("in this video", "I really **like** this"). Only cut if they have a real pause right next to them. |
| `CUT_REPETITIONS` | `False` | Cut false starts ("I think that... I think that"). **Turned off on purpose**: in practice we repeat an idea to clarify or emphasize it ("look what happens here... but the opposite could happen... but this happens"), not just because we stumble, and automatic cutting doesn't tell the two apart well. Set it to `True` if you'd rather it also try to cut these repetitions. |
| `REPETITION_WINDOW_SEC` | `1.5` | (Only with `CUT_REPETITIONS = True`.) How close together a repetition has to be to count as a false start; it also needs a real pause or a filler word in between. |

### Transcription

| Constant | Default value | What it controls |
|---|---|---|
| `WHISPER_LANGUAGE` | `None` | Spoken language. `None` **auto-detects** it from the audio (currently picks between the Spanish and English filler-word lists; anything else Whisper detects falls back to the Spanish list). Pin it to `"es"` or `"en"` if auto-detection ever guesses wrong on a specific voice. |
| `WHISPER_MODEL` | `"small"` | Model size. `"base"` uses less RAM; `"medium"` transcribes better but is slower. |
| `WHISPER_DEVICE` / `WHISPER_COMPUTE_TYPE` | `"cpu"` / `"int8"` | With an NVIDIA GPU you can use `"cuda"` and `"float16"`. |

### Subtitles

| Constant | Default value | What it controls |
|---|---|---|
| `SUBTITLE_FONT` | see note | **Font. Change it to one you have installed** (e.g. `"Arial"` or `"DejaVu Sans"`). |
| `MAX_WORDS_PER_CAPTION` | `1` | Words per subtitle (1 = word by word, Reels style). |
| `FONT_SIZE_FRACTION` | `0.075` | Font size as a fraction of the video's height. |
| `BOTTOM_MARGIN_FRACTION` | `0.20` | Distance from the bottom edge on **vertical/square** video (keeps the Instagram/TikTok UI area clear). |
| `HORIZONTAL_BOTTOM_MARGIN_FRACTION` | `0.10` | Distance from the bottom edge on **horizontal** video. |
| `SUBTITLE_VERTICAL_SCALE` / `SUBTITLE_TRACKING` | `125` / `-8` | Stretch the letters vertically and tighten letter spacing. |

> **About the font:** the default value points to a commercial typeface that **is not distributed with this repository**. If you don't have it installed, the render falls back to the system's default font. For a consistent result, pick a font you own and put its name in `SUBTITLE_FONT`. If the font you use has its own license, respect it.

### Render quality and speed

| Constant | Default | What it controls |
|---|---|---|
| `SEGMENT_PRESET` / `SEGMENT_CRF` | `ultrafast` / `18` | Encoding of the intermediate segments (deleted once done). |
| `FINAL_PRESET` / `FINAL_CRF` | `veryfast` / `21` | Encoding of the final video. **This defines the real quality of the file you publish.** For higher quality: preset `medium` and CRF `18` (slower). |
| `OUTPUT_PIXEL_FORMAT` | `yuv420p` | Pixel format of every encode. 8-bit 4:2:0 is the only one that plays everywhere; don't change it unless you know your target supports more. |

---

## How it works internally

A single program (`src/main.py`) acts as both watcher and processor: it scans, processes, and scans again. There's no separate process observing the folder.

| Module | What it does |
|---|---|
| `main.py` | The main loop and pipeline orchestration. Handles `Ctrl+C`/`SIGTERM` with a clean shutdown. |
| `scanner.py` | Picks the next video from `Raw/` and confirms the file is **stable** (two size checks) so it doesn't grab one mid-copy. |
| `transcription.py` | Extracts the audio to a mono 16 kHz WAV and transcribes it with faster-whisper. **Loads the model and releases it for every video** so memory doesn't build up from one video to the next. |
| `silence_detector.py` | Silence detection over the audio using numpy. Uses an **adaptive threshold**: the video's own noise floor (10th percentile of volume, with a ceiling) plus a margin, capped to a range. |
| `repetition_detector.py` | Filler words by list (active). Also detects repetitions via exact n-grams (2 to 6 words) close together, but **cutting them is turned off** (`CUT_REPETITIONS`, see Configuration): repeating an idea to clarify it isn't an error to fix. **No extra AI: it's all rules.** |
| `cut_manager.py` | Turns cuts into **segments to keep**; merges cuts that are too close together; enforces the minimum segment length; and translates times from the original timeline to the already-cut one (`remap_interval`). It's the central module. |
| `subtitle_generator.py` | Remaps words onto the cut video, groups them into captions, and writes the `.ass` file. |
| `video_processor.py` | Everything `ffmpeg`-related: cutting by segment, concatenation, and burning in subtitles. |
| `validator.py` | Checks on the final file (see below). |
| `file_manager.py` | The safe choreography of delivering to `Ready/` and only then deleting the original. |
| `logger.py` | Text log + `Logs/status.json` (atomic write) that `watch_status.py` reads. |

### Design decisions worth knowing

- **Silence cuts are based on real volume, not on Whisper's timings.** Whisper tends to stretch the end of each word up to the start of the next one, "swallowing" the pause in between. If the volume detector says there's no sound there, there's no word to protect. A margin on each edge is the only protection needed.
- **Two cuts are never merged if a word starts in between them.** Merging would delete whatever's in there; a short segment is preferred over losing something that was said.
- **A segment with words in it that's too short gets widened instead** (giving a bit of silence back to the video), rather than discarded.
- **Cutting is done segment by segment, each to its own file**, with `-ss` before `-i`, and they're joined afterward **without re-encoding** (`concat` with `-c copy`). A single giant filter with a `trim` per segment made `ffmpeg` use far more memory than expected. That's why it runs fine on modest machines.
- **It doesn't assume a constant frame rate.** Phones record at a variable frame rate; cutting with `select+setpts` assuming a constant one produces audio/video desync. Here, video and audio are cut using the same interval.
- **Only the final pass re-encodes at real quality.** The intermediate segments are encoded fast (`ultrafast`) and discarded.
- **Subtitles are remapped, not re-transcribed:** the transcription's words are shifted onto the already-cut timing, and a word that's no longer in the final video doesn't produce a subtitle.
- **Filler words are cut every time they appear on the list**, without requiring a pause around them (Whisper almost never leaves timestamps with that clean a gap). The cost: "este" and "tipo" are also real words, and sometimes a legitimate use gets cut. If it bothers you, remove them from `FILLER_WORDS`.
- **Language is auto-detected, not assumed.** `transcribe_video` reads back Whisper's own detected language (`info.language`) and `config.filler_words_for()` maps it to the matching filler-word list -- Spanish and English today. Detecting the language wrong would only affect which filler words get cut, never the transcription itself (Whisper still transcribes in whatever language it heard).

### How the result is validated

Before delivering, `validator.py` runs these checks from cheapest to most expensive and stops at the first one that fails:

1. The file exists and weighs more than 10 KB.
2. `ffprobe` can open it and it has both a **video and an audio** stream.
3. The **final duration matches the sum of the real durations of the cut segments** (each one measured with `ffprobe` right after cutting). Every cut lands on a frame boundary and comes out a few milliseconds longer than requested (~23 ms at 25 fps, ~8 ms at 60 fps); comparing against the *real* lengths means that rounding can't pile up into a false failure, and the subtitles are timed against those same real lengths so they stay in sync. Tolerance: `0.15 s + 0.02 s per segment`.
4. It decodes completely with `ffmpeg` **without a single error**.

---

## Known limits

- **Spanish and English, auto-detected.** Any other language transcribes fine (Whisper supports ~100), but falls back to the Spanish filler-word list, so filler words in that language won't be cut. Add a `FILLER_WORDS_<LANG>` list and a line in `config.filler_words_for()` to support another one.
- **One video at a time.** No parallel processing (on purpose: it's easier on memory).
- **Built for one person talking to camera.** It's not a general-purpose editor: no transitions, music, zoom, or B-roll.
- **Subtitles and cuts are tuned to taste.** The defaults come from real-world use, but every voice and every microphone is different: try it with a short video and adjust `config.py`.
- **Transcription can get things wrong**, on proper nouns, slang, or noisy audio, and those errors carry over into the subtitles. Review the result before publishing.
- **HDR is converted to standard 8-bit video without tone mapping.** HDR phone footage (e.g. iPhone's default HDR mode) plays everywhere after editing, but its colors can look slightly washed out. For the best color, record in SDR or turn HDR off in the camera settings.
- **Rendering is slow on CPU.** It depends heavily on the machine and the length of the video.

## Troubleshooting (setup)

| Symptom | What to check |
|---|---|
| `'git' is not recognized as an internal or external command` (Windows) | Git isn't installed or the terminal wasn't restarted. Install it with `winget install Git.Git` (or from [git-scm.com](https://git-scm.com)) and open a new PowerShell window. |
| `'python' is not recognized as an internal or external command` (Windows) | The **"Add python.exe to PATH"** box wasn't checked when installing Python. Reopen the downloaded Python installer, choose **Modify**, and check the option to add it to PATH. |
| `ExecutionPolicy` error / "running scripts is disabled" (Windows) | In PowerShell run: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (confirm with `Y`) and activate again with `.\venv\Scripts\Activate.ps1`. |
| `ffmpeg` / `ffprobe` "not found" or not recognized | They're not in the system `PATH`. On Windows: `winget install Gyan.FFmpeg` and restart PowerShell. On Linux: `sudo apt install ffmpeg`. On Mac: `brew install ffmpeg`. |
| I drop a video and nothing happens | Is the video inside the `Raw/` folder? Is the extension `.mp4`, `.mov`, `.mkv`, or `.avi`? Is `python src/main.py` running? |
| The video ended up in `Raw/failed/` | Open the `.error.txt` next to it: it states why (also in `Logs/rawtoreel.log`). See [Troubleshooting](#troubleshooting) for what each reason means. |
| "the transcription returned no words" | The audio is empty or unintelligible. Check that the video has speech in it. |
| Subtitles come out in a font that isn't the one I wanted | Change `SUBTITLE_FONT` to a font you have installed. |
| Cuts too much / feels "rushed" | Raise `MIN_SILENCE_DURATION_MS` and/or `SILENCE_MARGIN_MS`. |
| Long silences are left in | Lower `MIN_SILENCE_DURATION_MS` or raise `DB_MARGIN_OVER_FLOOR`. |
| Cuts soft speech as if it were silence | Lower `DB_MARGIN_OVER_FLOOR`. |
| Runs out of memory | Use `WHISPER_MODEL = "base"` and, in the service, `MemoryMax`. |

## Repository structure

```
raw-to-reel/
├── .github/
│   └── workflows/
│       └── test-windows.yml     # automated CI on Windows Server
├── src/
│   ├── main.py                  # main loop + pipeline
│   ├── config.py                # ALL of the adjustable configuration
│   ├── scanner.py                # picks and stabilizes the next video
│   ├── transcription.py         # audio + faster-whisper
│   ├── silence_detector.py      # silence by volume (adaptive threshold)
│   ├── repetition_detector.py   # filler words and repetitions
│   ├── cut_manager.py           # cuts -> segments + time remapping
│   ├── subtitle_generator.py    # captions + .ass file
│   ├── video_processor.py       # ffmpeg: cutting, joining, burning subtitles
│   ├── validator.py             # checks on the result
│   ├── file_manager.py          # safe delivery to Ready/
│   └── logger.py                # log + status.json
├── tests/
│   └── test_core.py             # unit and integration test suite
├── watch_status.py                # watch progress live
├── requirements.txt
├── LICENSE
└── README.md
```

Folders created on use (ignored by git): `Raw/`, `Raw/failed/`, `Raw/processed/`, `Ready/`, `Temp/`, `Logs/`.

---

## 🚧 Project status: in active development and ongoing maturation

> [!NOTE]
> **RawToReel is a project in active development and constant maturation.**
> The engine is already fully functional, stable, and used to process real vertical and horizontal videos. Since it's software that keeps evolving with use, **updates will be published periodically** with speed improvements, finer-tuned pause/filler detection, support for new formats, and more style options.

### How to update to the latest version

To update your local copy to the latest version at any time:

```bash
git pull origin master
pip install -r requirements.txt --upgrade
```

### Feedback and suggestions

Since it's still growing, **community feedback and reports are key**:
* If you find a cut that didn't come out as expected, or a word that behaved strangely, open an [**Issue**](https://github.com/Draggypy/raw-to-reel/issues) on GitHub including the relevant excerpt from `Logs/rawtoreel.log`.
* Suggestions, ideas, and Pull Requests are very welcome to keep maturing the project!

---

## License

MIT — see [`LICENSE`](LICENSE).
