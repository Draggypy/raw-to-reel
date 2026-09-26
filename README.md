# RawToReel

**Automatic talking-head video editor: from raw to ready, without touching an editor.**

Drop a video of someone talking to camera into a folder. RawToReel cuts silences and filler words, adds word-by-word subtitles, and returns the edited video in another folder. On purpose, it **does not** cut repetitions ("look what happens here... but the opposite could happen... but this happens"): that's a common way of clarifying an idea while speaking, not a mistake. Everything runs on your own machine: no external APIs, no accounts, your video never gets uploaded anywhere.

Built for vertical content like **Reels, TikTok, and Instagram Stories**.

<p align="center">
  <img src="assets/demo.gif" alt="RawToReel demo" width="320">
  <br>
  <em>Video processed 100% automatically with RawToReel (pause cutting + animated subtitles).</em>
</p>

```
   Crudos/                         RawToReel                         Listos/
┌──────────────┐    ┌──────────────────────────────────────┐    ┌──────────────┐
│ my-video.mp4 │ ─► │ transcribes → detects → cuts →        │ ─► │ my-video.mp4 │
│ (unedited)   │    │ subtitles → renders → validates       │    │ (edited)     │
└──────────────┘    └──────────────────────────────────────┘    └──────────────┘
                                   │
                                   └─► if something fails: Crudos/fallidos/  (the original is never lost)
```

---

## What it does

1. **Transcribes** the audio locally with [faster-whisper](https://github.com/SYSTRAN/faster-whisper), with word-level timestamps.
2. **Detects** silences (by the audio's real volume) and filler words ("um", "like", "you know"...). It distinguishes pauses between sentences from the natural rhythm within a sentence, so it doesn't cut you off while you're still talking.

   > **What about repetitions ("I think that... I think this is great")?** RawToReel **does not cut them**, on purpose. When speaking, it's very common to repeat an idea to reinforce or clarify it ("look what happens here... but the opposite could happen... but this happens"), and that's not a speech error — it's a way of explaining yourself. Cutting it automatically ended up deleting parts of the message the user meant to say that way, not by accident. The editor prefers to specialize in what it can confidently tell apart — real silences and filler words — rather than guess when a repetition is a "false start" and when it's emphasis. (The repetition detector is still in the code, turned off via `CORTAR_REPETICIONES = False` in `src/config.py`, for anyone who wants to try it.)
3. **Consolidates the cuts** into the final list of segments to keep, being careful not to leave sub-second scene "flashes".
4. **Generates subtitles** (`.ass` format) already aligned to the timing of the cut video.
5. **Cuts and burns in the subtitles** with `ffmpeg`.
6. **Validates** the result. Only if it passes every check is it delivered to `Listos/`; if not, the video goes to `Crudos/fallidos/` and the original stays untouched.

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

> **Folders ready from the start:** the repository already comes with the `Crudos/` folder (where you drop your videos) and `Listos/` (where you get the final video with subtitles and no silences). You don't need to create any folder by hand; the temp and log folders are managed automatically.

## How to use it

### Basic usage

```bash
# Activate the virtual environment (if not already active)
source venv/bin/activate          # on Windows: .\venv\Scripts\Activate.ps1
python src/main.py
```

1. Copy a video into `Crudos/` (formats: `.mp4`, `.mov`, `.mkv`, `.avi`).
2. The program detects it on its own. It waits until the copy is finished (it watches for the file size to stop changing), so you can transfer files from your phone or a USB drive with no issues.
3. It processes it. When it's done, it appears in `Listos/` **with the same name**.
4. The original disappears from `Crudos/` **only once the copy in `Listos/` has been verified.**

The program stays running, watching `Crudos/`. It processes **one video at a time**, oldest to newest. To stop it: `Ctrl+C` (it finishes the video currently being processed, then exits).

### Watching what it's doing

In another terminal, no need to activate the `venv`:

```bash
python3 ver_estado.py        # on Windows: python ver_estado.py
```

Shows the live stage of each video:

```
[2026-09-24 12:30:01] my-video.mp4 -> transcribing
[2026-09-24 12:31:14] my-video.mp4 -> detecting silences
...
[2026-09-24 12:33:40] (none) -> waiting
```

The stages, in order: `extracting audio` → `transcribing` → `detecting silences` → `looking for filler words` → `consolidating cuts` → `generating subtitles` → `cutting and rendering` → `validating` → `moving to Listos`.

The full history is kept in `Logs/editor_gianni.log` (one dated line per event, including how many silences, filler words, and segments it found for each video).

### Keeping it running permanently (Linux, systemd)

If you want it to start with the machine and process whatever you drop into `Crudos/`, you can use a user service. Example (`~/.config/systemd/user/raw-to-reel.service`), adjusting the paths:

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

- **The original is never touched until the end.** A temporary copy is processed in `Temp/`. Only once the finished copy is in `Listos/` and its size matches the temporary file is the original deleted from `Crudos/`.
- **If something fails** (empty transcription, an `ffmpeg` error, a failed validation) the original is moved to `Crudos/fallidos/` so it isn't retried in a loop. The cause is recorded in `Logs/editor_gianni.log`.
- **To retry** a failed video: move it back into `Crudos/`.
- Everything under `Crudos/`, `Listos/`, `Temp/`, and `Logs/` is in `.gitignore`: your videos never end up in the repository.

## Troubleshooting

### The video ended up in `Crudos/fallidos/`

Look for the line in the log — it states the exact reason, no need to guess:

```bash
grep -B 15 "Movido a fallidos" Logs/editor_gianni.log | tail -30
```

The most common causes, from most to least frequent:

| Message in the log | What happened | What to do |
|---|---|---|
| `El video no tiene pista de audio` / `La pista de audio del video está vacía` ("The video has no audio track" / "The video's audio track is empty") | **The phone recorded video but no audio.** The file has an audio track created but with zero samples (0 bytes of sound) — this happens when another app (a call, a voice recorder, an assistant) had the microphone locked when recording started, or the mic was muted/covered. | Play the video back: if you hear nothing, that confirms it. You'll need to re-record — there's no audio to edit. |
| `la transcripción no devolvió ninguna palabra` ("the transcription returned no words") | The audio exists and has sound, but Whisper didn't recognize any speech in Spanish: volume too low, too much background noise/echo, the mic too far away, or the clip is of something else (music, ambient sound, noisy silence). | Record closer to the microphone and with less background noise. If you speak another language, adjust `IDIOMA_WHISPER`. |
| `ffmpeg falló extrayendo audio: ...` ("ffmpeg failed extracting audio") | The video container is broken or `ffmpeg` doesn't recognize the audio/video codec. Could be a file that was recording when something interrupted it (power cut, storage filled up) or an exotic format. | Run `ffprobe your-video.mp4` and check what it says about the streams. If the file looks incomplete, it's a corrupted video, not a bug in the editor. |
| `ffmpeg falló cortando un tramo` / `ffmpeg falló concatenando` / `ffmpeg falló quemando subtítulos` ("ffmpeg failed cutting a segment / concatenating / burning subtitles") | A specific `ffmpeg` step failed — the full message (in `Logs/editor_gianni.log`, never truncated) carries the actual `ffmpeg` error underneath. | Copy the full message from the log; it almost always states the concrete problem (unsupported codec, out of disk space, subtitle font not found). |
| `ERROR de validación: pesa sólo N bytes` ("only weighs N bytes") | The final file came out empty or truncated — typically from running out of disk space mid-render. | Check free space in `Temp/` and `Listos/`. |
| `ERROR de validación: no tiene stream de video/audio` ("has no video/audio stream") | The final file lost a track somewhere in the process (rare; a sign of an incomplete `ffmpeg` build). | Reinstall `ffmpeg`, making sure it has `libass` and complete audio/video codecs (see Requirements). |
| `ERROR de validación: duración esperada ...` ("expected duration...") | The final video's duration doesn't match the expected one beyond the tolerance margin. Can happen with video recorded at a **variable frame rate** (common on some phones) on very long takes or with a huge number of cuts. | If it's occasional, there's nothing to do: it's safer to reject the video than to deliver one with desync. If it happens every time with the same phone, let us know — there's room to adjust `TOLERANCIA_DURACION_POR_TRAMO_SEG`. |
| `ERROR de validación: errores decodificando` ("decoding errors") | The final file ended up corrupted somehow (rare — would be an actual bug). | Save the video from `Temp/` (it gets deleted on retry) and report it with the full log. |

### The video DID make it to `Listos/`, but something looks or sounds off

The automatic validation doesn't catch this because the file is technically valid — you have to look at it:

| Symptom | Likely cause | Where to adjust |
|---|---|---|
| No subtitles show up, or they look like an ugly/generic font | The font set in `FUENTE_SUBTITULOS` isn't installed on your system; `ffmpeg`/`libass` silently falls back to a default font (not an error). | Install the font you want to use and put its exact name in `FUENTE_SUBTITULOS` (see the licensing note in the Subtitles table). |
| Subtitles are out of sync with the audio | A sign of real audio/video desync in the result. | Check `Logs/editor_gianni.log` for that video and see how many segments it had — with a huge number of cuts the error margin accumulates (see `TOLERANCIA_DURACION_*` in Configuration). |
| Still cuts mid-thought, feels like "it cuts the moment I stop talking" | Fine-tuning of sensitivity, not a bug. | Raise `PAUSA_MINIMA_DENTRO_DE_FRASE_MS` and/or `MARGEN_SILENCIO_MS` in `src/config.py`. |
| Leaves very long silences uncut | The silence threshold is too strict for your background noise level. | Lower `MARGEN_DB_SOBRE_PISO` or carefully raise `UMBRAL_DB_MAX` (see the comments in `config.py` — they're there so you don't break the balance). |
| Cuts "um"/"like"/"this" ("este"/"tipo") that were actually part of a normal sentence | A filler-word false positive. | Remove that word from `MULETILLAS` (or from `MULETILLAS_AMBIGUAS` if it already requires a pause) in `src/config.py`. |

---

## Configuration

Everything adjustable lives in a single file: [`src/config.py`](src/config.py). Every constant has a comment next to it explaining why it has the value it has. The main ones:

### Cuts

| Constant | Default value | What it controls |
|---|---|---|
| `DURACION_MINIMA_SILENCIO_MS` | `300` | A pause shorter than this is **not detected** as silence. |
| `MARGEN_SILENCIO_MS` | `150` | How much silence is left on **each edge** of a cut. At 150, every cut pause leaves ~300 ms of audible silence. Lower it for tighter cuts; raise it if it feels like "it cuts the moment I stop talking". |
| `CORTE_MINIMO_MS` | `150` | How much a cut has to **save** (margins already subtracted) to be worth the visual jump. Prevents 20 ms micro-cuts that felt like "it cuts out of nowhere". In practice, only pauses of `2 × MARGEN + CORTE_MINIMO` = 450 ms or more get cut. |
| `PAUSA_MINIMA_DENTRO_DE_FRASE_MS` / `MARGEN_DENTRO_DE_FRASE_MS` | `1000` / `250` | A pause **in the middle of a sentence** (the previous word doesn't end in `.` `?` `!`) is speech rhythm: it's only cut if it lasts 1 s or more, leaving 500 ms of air. Between sentences the normal rule applies. Raise the first one if it feels like it's cutting while you're still talking about the same topic. |
| `TRAMO_MINIMO_SEG` | `0.5` | Prevents sub-second kept segments (they look like a flicker). |
| `FUNDIDO_AUDIO_SEG` | `0.012` | Audio fade at each cut edge, so the join doesn't produce a "click". |
| `MARGEN_DB_SOBRE_PISO` | `17` | Detector sensitivity: the "silence" threshold is the video's own noise floor plus this margin. |
| `UMBRAL_DB_MAX` | `-35` | The threshold never rises above this, to avoid entering the voice range (soft speech sits around -30 dB). |
| `SUAVIZADO_SILENCIO_MS` / `HISTERESIS_DB` | `50` / `3` | Smooth the volume curve and keep a soft voice that grazes the threshold from opening and closing silences several times a second. |
| `MULETILLAS` | `eh, emm, mmm, este, o sea, tipo, digamos` | List of filler words to cut (Spanish). Edit it to match how you speak. |
| `MULETILLAS_AMBIGUAS` | `este, tipo, o sea` | Filler words that are also real words ("in this video" — "en este video"). Only cut if they have a real pause right next to them. |
| `CORTAR_REPETICIONES` | `False` | Cut false starts ("I think that... I think that"). **Turned off on purpose**: in practice we repeat an idea to clarify or emphasize it ("look what happens here... but the opposite could happen... but this happens"), not just because we stumble, and automatic cutting doesn't tell the two apart well. Set it to `True` if you'd rather it also try to cut these repetitions. |
| `VENTANA_REPETICION_SEG` | `1.5` | (Only with `CORTAR_REPETICIONES = True`.) How close together a repetition has to be to count as a false start; it also needs a real pause or a filler word in between. |

### Transcription

| Constant | Default value | What it controls |
|---|---|---|
| `IDIOMA_WHISPER` | `"es"` | Spoken language. **Built for Spanish**: the filler-word list is too. |
| `MODELO_WHISPER` | `"small"` | Model size. `"base"` uses less RAM; `"medium"` transcribes better but is slower. |
| `DEVICE_WHISPER` / `COMPUTE_TYPE_WHISPER` | `"cpu"` / `"int8"` | With an NVIDIA GPU you can use `"cuda"` and `"float16"`. |

### Subtitles

| Constant | Default value | What it controls |
|---|---|---|
| `FUENTE_SUBTITULOS` | see note | **Font. Change it to one you have installed** (e.g. `"Arial"` or `"DejaVu Sans"`). |
| `MAX_PALABRAS_POR_CAPTION` | `1` | Words per subtitle (1 = word by word, Reels style). |
| `FRACCION_TAMANO_FUENTE` | `0.075` | Font size as a fraction of the video's height. |
| `FRACCION_MARGEN_INFERIOR` | `0.20` | Distance from the bottom edge (keeps the Instagram UI area clear). |
| `ESCALA_VERTICAL_SUBTITULOS` / `TRACKING_SUBTITULOS` | `125` / `-8` | Stretch the letters vertically and tighten letter spacing. |

> **About the font:** the default value points to a commercial typeface that **is not distributed with this repository**. If you don't have it installed, the render falls back to the system's default font. For a consistent result, pick a font you own and put its name in `FUENTE_SUBTITULOS`. If the font you use has its own license, respect it.

### Render quality and speed

| Constant | Default | What it controls |
|---|---|---|
| `PRESET_SEGMENTO` / `CRF_SEGMENTO` | `ultrafast` / `18` | Encoding of the intermediate segments (deleted once done). |
| `PRESET_FINAL` / `CRF_FINAL` | `veryfast` / `21` | Encoding of the final video. **This defines the real quality of the file you publish.** For higher quality: preset `medium` and CRF `18` (slower). |

---

## How it works internally

A single program (`src/main.py`) acts as both watcher and processor: it scans, processes, and scans again. There's no separate process observing the folder.

| Module | What it does |
|---|---|
| `main.py` | The main loop and pipeline orchestration. Handles `Ctrl+C`/`SIGTERM` with a clean shutdown. |
| `scanner.py` | Picks the next video from `Crudos/` and confirms the file is **stable** (two size checks) so it doesn't grab one mid-copy. |
| `transcription.py` | Extracts the audio to a mono 16 kHz WAV and transcribes it with faster-whisper. **Loads the model and releases it for every video** so memory doesn't build up from one video to the next. |
| `silence_detector.py` | Silence detection over the audio using numpy. Uses an **adaptive threshold**: the video's own noise floor (10th percentile of volume, with a ceiling) plus a margin, capped to a range. |
| `repetition_detector.py` | Filler words by list (active). Also detects repetitions via exact n-grams (2 to 6 words) close together, but **cutting them is turned off** (`CORTAR_REPETICIONES`, see Configuration): repeating an idea to clarify it isn't an error to fix. **No extra AI: it's all rules.** |
| `cut_manager.py` | Turns cuts into **segments to keep**; merges cuts that are too close together; enforces the minimum segment length; and translates times from the original timeline to the already-cut one (`remapear_intervalo`). It's the central module. |
| `subtitle_generator.py` | Remaps words onto the cut video, groups them into captions, and writes the `.ass` file. |
| `video_processor.py` | Everything `ffmpeg`-related: cutting by segment, concatenation, and burning in subtitles. |
| `validator.py` | Checks on the final file (see below). |
| `file_manager.py` | The safe choreography of delivering to `Listos/` and only then deleting the original. |
| `logger.py` | Text log + `Logs/estado.json` (atomic write) that `ver_estado.py` reads. |

### Design decisions worth knowing

- **Silence cuts are based on real volume, not on Whisper's timings.** Whisper tends to stretch the end of each word up to the start of the next one, "swallowing" the pause in between. If the volume detector says there's no sound there, there's no word to protect. A margin on each edge is the only protection needed.
- **Two cuts are never merged if a word starts in between them.** Merging would delete whatever's in there; a short segment is preferred over losing something that was said.
- **A segment with words in it that's too short gets widened instead** (giving a bit of silence back to the video), rather than discarded.
- **Cutting is done segment by segment, each to its own file**, with `-ss` before `-i`, and they're joined afterward **without re-encoding** (`concat` with `-c copy`). A single giant filter with a `trim` per segment made `ffmpeg` use far more memory than expected. That's why it runs fine on modest machines.
- **It doesn't assume a constant frame rate.** Phones record at a variable frame rate; cutting with `select+setpts` assuming a constant one produces audio/video desync. Here, video and audio are cut using the same interval.
- **Only the final pass re-encodes at real quality.** The intermediate segments are encoded fast (`ultrafast`) and discarded.
- **Subtitles are remapped, not re-transcribed:** the transcription's words are shifted onto the already-cut timing, and a word that's no longer in the final video doesn't produce a subtitle.
- **Filler words are cut every time they appear on the list**, without requiring a pause around them (Whisper almost never leaves timestamps with that clean a gap). The cost: "este" and "tipo" are also real words, and sometimes a legitimate use gets cut. If it bothers you, remove them from `MULETILLAS`.

### How the result is validated

Before delivering, `validator.py` runs these checks from cheapest to most expensive and stops at the first one that fails:

1. The file exists and weighs more than 10 KB.
2. `ffprobe` can open it and it has both a **video and an audio** stream.
3. The **real duration matches the expected one** (the sum of the segments). The tolerance **scales with the number of segments** (`0.15 s + 0.02 s per segment`), because the frame-level rounding of each cut accumulates: a fixed tolerance used to fail on videos with many cuts even though nothing was actually wrong.
4. It decodes completely with `ffmpeg` **without a single error**.

---

## Known limits

- **Spanish first.** The language and the filler-word list are configured for Spanish; for another language you'll need to change `IDIOMA_WHISPER` and `MULETILLAS`.
- **One video at a time.** No parallel processing (on purpose: it's easier on memory).
- **Built for one person talking to camera.** It's not a general-purpose editor: no transitions, music, zoom, or B-roll.
- **Subtitles and cuts are tuned to taste.** The defaults come from real-world use, but every voice and every microphone is different: try it with a short video and adjust `config.py`.
- **Transcription can get things wrong**, on proper nouns, slang, or noisy audio, and those errors carry over into the subtitles. Review the result before publishing.
- **Rendering is slow on CPU.** It depends heavily on the machine and the length of the video.

## Troubleshooting (setup)

| Symptom | What to check |
|---|---|
| `'git' is not recognized as an internal or external command` (Windows) | Git isn't installed or the terminal wasn't restarted. Install it with `winget install Git.Git` (or from [git-scm.com](https://git-scm.com)) and open a new PowerShell window. |
| `'python' is not recognized as an internal or external command` (Windows) | The **"Add python.exe to PATH"** box wasn't checked when installing Python. Reopen the downloaded Python installer, choose **Modify**, and check the option to add it to PATH. |
| `ExecutionPolicy` error / "running scripts is disabled" (Windows) | In PowerShell run: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (confirm with `Y`) and activate again with `.\venv\Scripts\Activate.ps1`. |
| `ffmpeg` / `ffprobe` "not found" or not recognized | They're not in the system `PATH`. On Windows: `winget install Gyan.FFmpeg` and restart PowerShell. On Linux: `sudo apt install ffmpeg`. On Mac: `brew install ffmpeg`. |
| I drop a video and nothing happens | Is the video inside the `Crudos/` folder? Is the extension `.mp4`, `.mov`, `.mkv`, or `.avi`? Is `python src/main.py` running? |
| The video ended up in `Crudos/fallidos/` | Open `Logs/editor_gianni.log`: the line with `ERROR` states why. |
| "la transcripción no devolvió ninguna palabra" ("the transcription returned no words") | The audio is empty or unintelligible. Check that the video has speech in it. |
| Subtitles come out in a font that isn't the one I wanted | Change `FUENTE_SUBTITULOS` to a font you have installed. |
| Cuts too much / feels "rushed" | Raise `DURACION_MINIMA_SILENCIO_MS` and/or `MARGEN_SILENCIO_MS`. |
| Long silences are left in | Lower `DURACION_MINIMA_SILENCIO_MS` or raise `MARGEN_DB_SOBRE_PISO`. |
| Cuts soft speech as if it were silence | Lower `MARGEN_DB_SOBRE_PISO`. |
| Runs out of memory | Use `MODELO_WHISPER = "base"` and, in the service, `MemoryMax`. |

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
│   ├── file_manager.py          # safe delivery to Listos/
│   └── logger.py                # log + estado.json
├── tests/
│   └── test_core.py             # unit and integration test suite
├── ver_estado.py                # watch progress live
├── requirements.txt
├── LICENSE
└── README.md
```

Folders created on use (ignored by git): `Crudos/`, `Crudos/fallidos/`, `Listos/`, `Temp/`, `Logs/`.

---

## 🚧 Project status: in active development and ongoing maturation

> [!NOTE]
> **RawToReel is a project in active development and constant maturation.**
> The engine is already fully functional, stable, and used to process real vertical videos. Since it's software that keeps evolving with use, **updates will be published periodically** with speed improvements, finer-tuned pause/filler detection, support for new formats, and more style options.

### How to update to the latest version

To update your local copy to the latest version at any time:

```bash
git pull origin master
pip install -r requirements.txt --upgrade
```

### Feedback and suggestions

Since it's still growing, **community feedback and reports are key**:
* If you find a cut that didn't come out as expected, or a word that behaved strangely, open an [**Issue**](https://github.com/Draggypy/raw-to-reel/issues) on GitHub including the relevant excerpt from `Logs/editor_gianni.log`.
* Suggestions, ideas, and Pull Requests are very welcome to keep maturing the project!

---

## License

MIT — see [`LICENSE`](LICENSE).
