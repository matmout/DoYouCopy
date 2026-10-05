# DoYouCopy: detailed guide

**100 % local and offline** speech-to-text for Windows: faster-whisper (`large-v3-turbo` or `large-v3`) accelerated by **ROCm** on AMD Radeon GPUs (tested on an RX 7800 XT, gfx1101), with a native PySide6 window.

*Version française : [GUIDE.fr.md](GUIDE.fr.md).*

| Live mode, dark theme | Finished transcript, light theme |
|---|---|
| ![Live mode](apercu-direct-sombre.png) | ![Finished](apercu-termine-clair.png) |

- **Universal dictation**: hold Ctrl+Shift+Space in any application, speak, release: the text is pasted there.
- Recording from the microphone (Ctrl+R), or opening / dragging and dropping an audio or video file (wav, mp3, m4a, flac, ogg, mp4…).
- **Live mode** (Ctrl+L): the text appears while you speak.
- Progressive display: each segment appears as soon as it is decoded.
- Choice of model: **turbo** (fast, beam 1) or **large-v3** (precise, beam 5).
- Forced language or automatic detection, silence filter (Silero VAD).
- **Vocabulary**: preferred words, replacements, spoken punctuation commands.
- Copy (plain text, timestamped, Markdown) and export to **TXT**, **SRT**, **WebVTT**, **Markdown**, **Word** and **JSON**.
- Automatic fallback to the CPU (int8) if the GPU is unavailable.
- Interface in **English** or **French**: it follows the Windows display language, and can be changed in *Settings → General → Interface language*.

## How AMD acceleration works

faster-whisper relies on [CTranslate2](https://github.com/OpenNMT/CTranslate2). Since v4.7.0, CTranslate2 publishes **official ROCm wheels for Windows** (asset `rocm-python-wheels-Windows.zip`), built for gfx1030, gfx110x (including the RX 7800 XT), gfx115x and gfx120x. They rely on the ROCm 7.2 runtime that AMD distributes as pip packages (`rocm_sdk_core`, `rocm_sdk_libraries_custom`). There is **nothing to compile** and **the HIP SDK is not needed**.

The AMD GPU shows up as CTranslate2's `"cuda"` device: that is the historical name of the GPU backend, which goes through HIP here.

## Installation (users)

Download and run `DoYouCopy-Setup-<version>.exe` (Windows 10 / 11, 64-bit). It installs into your profile, **without administrator rights**. The installer offers two shortcuts: **in the Start menu** (checked by default) and **on the desktop**. You can add or remove them later in the settings (General → Shortcuts). At the end:

1. the installer **detects the graphics card** and downloads the matching acceleration from the official sources, with pinned versions and SHA-256 checksums:

   | Card | Acceleration | Download |
   |---|---|---|
   | NVIDIA GeForce GTX 900 and newer, RTX | CUDA 12 (cuBLAS + cuDNN 9) | ~1.2 GB |
   | AMD Radeon RX 6800 / 6900, RX 7000, RX 9000, Radeon 780M / 880M / 890M | ROCm 7.2 | ~1.2 GB |
   | Others (Intel, older AMD, no card) | none: processor | — |

   The card is then actually tested. If that fails (driver too old), DoYouCopy uses the processor and says why.
2. at **first start**, the Turbo model (~1.6 GB) downloads with a progress bar. The Precise model (~3 GB) downloads the first time you choose it.

Without acceleration, a "**Slower transcription on this computer**" banner gives the reason. If a compatible card is present, the **Install acceleration** button downloads what is needed, then restarts DoYouCopy.

The installer is not signed yet: Windows SmartScreen shows "Windows protected your PC". Click **More info**, then **Run anyway**.

Uninstalling (Settings → Apps) removes the application, its shortcuts (including those created from the settings) and the graphics acceleration. It also offers to delete the history (dictations, transcripts and audio recordings), the models and the settings.

The application is also available on the **Microsoft Store**: see [STORE.fr.md](STORE.fr.md) for what differs in that version.

## Installation (development, from source)

Requirements:

1. A recent **AMD Software: Adrenalin Edition** driver ([amd.com](https://www.amd.com/en/support/download/drivers.html)).
2. **Python 3.10 to 3.14 x64** (installed from python.org; the `py` launcher must be available). The script uses 3.13 by default.
3. About 8 GB of disk space: 1.1 GB of ROCm runtime, ~0.3 GB of dependencies, ~4.6 GB for the two models.

Then, from the root of the repository:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_rocm.ps1
```

The script:

1. creates `.venv` (option `-Python 3.12` to use another version);
2. installs the ROCm 7.2 runtime from `repo.radeon.com`;
3. downloads the CTranslate2 4.8.2 ROCm wheel matching the Python version and installs it;
4. installs DoYouCopy and its dependencies (`constraints.txt` stops pip from replacing ctranslate2 with the CUDA build from PyPI);
5. runs `scripts/check_gpu.py`, then downloads the two models (unless `-SkipModels` is given).

The models are stored in `%LOCALAPPDATA%\DoYouCopy\models`. To change this location, set the `DOYOUCOPY_MODELS_DIR` environment variable or the `models_dir` setting. Once the models are present, the application no longer needs the network: it always loads the local cache first.

## Usage

```powershell
.\.venv\Scripts\doyoucopy.exe
# or
.\.venv\Scripts\python.exe -m doyoucopy
```

| Shortcut | Action |
|---|---|
| Ctrl+R | Start / stop recording |
| Ctrl+L | Start / stop live mode |
| Ctrl+O | Import a file |
| Ctrl+S | Export to TXT (the "Export" menu offers the other formats) |
| Ctrl+Shift+Space | Universal dictation, from any application (can be changed) |
| Ctrl+H | Show / hide the history |
| Ctrl+E | Edit the transcript |
| Ctrl+Space | Play / pause the audio |
| Ctrl+← | Go back 5 seconds |

The big microphone button starts and stops capturing in the mode chosen above it (Recording or Live), from the source chosen next to it: **Microphone**, **Computer** (what comes out of the speakers: a Teams/Zoom meeting, a video) or **Both**, mixed. Computer capture uses the Windows default output device; tell the participants before recording a meeting. At the top, the choice of model (**Light**, **Turbo**, **Precise**) and of language. The **Settings** button opens the quick settings: silences, timestamps, vocabulary, microphone, theme. **All settings…** opens the full window.

## Settings

Every change applies at once and is saved in `%APPDATA%\DoYouCopy\settings.json`. If this file is damaged, or edited by hand with an invalid value, only that value goes back to its default (a warning is written to the log).

Shortcuts and starting with Windows are not settings: the checkboxes show the files actually present (`.lnk` shortcuts, `Run` registry key). From source, the shortcut runs `pythonw.exe -m doyoucopy` with the application's icon.

| Section | Settings |
|---|---|
| General | theme, text size, timestamps, **interface language** (the Windows one, French or English; applied at the next start), microphone, notification area, start with Windows, **shortcuts on the desktop and in the Start menu**, back to default settings (the vocabulary is kept) |
| Transcription | spoken language, several languages in the same audio, **translation into English**, context (topic, names, style), vocabulary, search quality (*beam size*), use of the previous text, **batched file transcription** (3 to 4× faster on GPU) |
| Silences | silence filter (VAD) with its sensitivity and the minimum pause, removal of text invented during long silences, "no speech" threshold, repetition penalty |
| Dictation | shortcut, Hold / Toggle mode, paste or copy, space after the text, voice commands, sound |
| Live mode | interval between passes, end-of-sentence silence |
| Exports | Ctrl+S format, characters per line and lines per subtitle |
| History | automatic saving, dictations kept or not, audio of recordings kept (FLAC) and how long, opening the folder, clearing everything |
| Models | model in use, downloaded models (size, deletion), models folder, strict offline mode |
| Hardware | **running on the graphics card or the processor**, precision (float16, int8_float16, int8…), processor threads, card status and acceleration install, **diagnostic information** and logs folder |

Switching from GPU to processor (and back), the precision, the threads and the models folder apply without restarting: the model is reloaded after the current transcription. The interface language applies at the next start; the settings window offers to restart right away. The available models:

| Model | Size | Use |
|---|---|---|
| Light (small) | 0.5 GB | computers without a graphics card |
| Turbo (large-v3-turbo) | 1.6 GB | the best trade-off (default) |
| Precise (large-v3) | 3.1 GB | the best accuracy; the only one that translates well into English |

## Universal dictation

DoYouCopy stays in the notification area with the model loaded. From any application:

- **Hold** (default): keep **Ctrl+Shift+Space** pressed while you speak, release to insert the text;
- **Toggle**: press once to start, again to stop;
- **Esc** cancels the current dictation.

A pill at the bottom of the screen shows the microphone level, then the transcription status. It never takes the focus. The text is pasted into the active window (clipboard then Ctrl+V, the previous clipboard content is restored), or only copied if you choose "Copy only".

The **Dictation** section of the settings changes the shortcut (with Ctrl, Alt, Shift or Win, or a single F key), the mode, the output, the sound, staying in the notification area and starting with Windows. Closing the window sends it to the notification area; **Quit** is in the icon's menu.

Limits:

- Windows blocks simulated typing into a window run **as administrator**. Use "Copy only" then, and Ctrl+V.
- Dictation waits until a transcription or live session running in the main window has finished.

## Vocabulary

**Settings → Vocabulary…**:

- **Preferred words**: names, acronyms, jargon. They are passed to the decoder (faster-whisper's `hotwords`) for every transcription.
- **Replacements**: "Heard → Write", on whole words, case-insensitive. A pattern between slashes (`/(\d+) per ?cent/` → ` %`) is a regular expression.
- **Voice commands**, in universal dictation. In English: *comma, full stop, period (at the end of the dictation), question mark, exclamation mark, semicolon, colon, ellipsis, new line, new paragraph, open / close quote, open / close parenthesis*. In French: « virgule », « point final », « point d'interrogation », « à la ligne », « nouveau paragraphe », « ouvrez / fermez les guillemets »… The French word « point » on its own is never interpreted: it is too common.

## Exports

| Format | Content |
|---|---|
| TXT | one segment per line |
| SRT, WebVTT | subtitles of at most 2 lines of 42 characters, preferably cut after punctuation, timed to the word |
| Markdown | one paragraph per segment, preceded by its timestamp |
| Word (.docx) | one paragraph per segment |
| JSON | segments and words with their timestamps |

## Live mode

The **Live** mode transcribes continuously, without waiting for the end of a recording:

- **grey italic** text is provisional: it is the current hypothesis, which may still change;
- **black** text is confirmed: it no longer moves.

When stopped, the text is grouped into sentences. Copy and exports work as for a recording.

Whisper cannot process a continuous audio stream. DoYouCopy therefore transcribes a sliding window of audio again every second, following the LocalAgreement method of [whisper_streaming](https://github.com/ufal/whisper_streaming), implemented in `core/live.py`:

- a word is confirmed when **two successive passes** agree on it and it does not end at the edge of the window. That is where Whisper tends to "guess" the rest of the sentence;
- words already confirmed are recognised in the next passes thanks to their timestamps, then skipped;
- the audio is only cut at safe places: in a pause detected by Silero VAD, or at an already confirmed segment boundary if you speak for more than 15 s without a pause;
- no pass runs during silences, which avoids hallucinations.

Pass duration measured on an RX 7800 XT (simulation on a 42 s recording) and the resulting latencies:

| Model | Average pass (measured) | Provisional text (estimated) | Confirmed text (estimated) |
|---|---|---|---|
| turbo (recommended) | ~0.4 s | ~1 to 1.5 s after speech | ~2 s, or at the first pause |
| large-v3 | ~0.9 s | ~2 s | ~3 s |

## Building the installer

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
```

Requirements: the development `.venv` and [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`). The script:

1. bundles the CTranslate2 wheel from PyPI (CPU + CUDA), checked against its checksum;
2. builds the application with PyInstaller in folder mode, without console or UPX;
3. checks that the executable loads its engine (`DoYouCopy.exe --probe`);
4. compiles `dist\DoYouCopy-Setup-<version>.exe` with Inno Setup (~90 MB). The installer itself is in English and French.

To sign the installer, pass `-CertFile cert.pfx` (password in `DOYOUCOPY_SIGN_PASSWORD`) or `-CertThumbprint <thumbprint>`. The script then uses `signtool` from the Windows SDK.

Executable options:

| Option | Role |
|---|---|
| `--setup-runtime` | detects the card and installs its acceleration (run by the installer) |
| `--probe file.json` | writes what CTranslate2 sees (number of GPUs, compute types) |
| `--minimized` | starts in the notification area (start with Windows) |

The acceleration is installed in `%LOCALAPPDATA%\DoYouCopy\runtime` (`DOYOUCOPY_RUNTIME_DIR` variable for another location). The log of the packaged application is in `%LOCALAPPDATA%\DoYouCopy\logs`.

## Building the Microsoft Store package (MSIX)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1 -SkipInstaller
powershell -ExecutionPolicy Bypass -File scripts\build_msix.ps1
```

Requirements: the Windows SDK (`makeappx`, `makepri`). The package `dist\DoYouCopy-<version>-x64.msix` is not signed: the Store signs it on submission. `-DevSign` signs it with a test certificate to install it on your own machine, `-Wack` runs the certification tests. The package declares English (default) and French. Identity, behaviour differences and submission steps: [STORE.fr.md](STORE.fr.md) (in French).

## History

Every transcript (recording, live, file) is saved automatically in `%LOCALAPPDATA%\DoYouCopy\history`, a SQLite database with full-text search (FTS5). Long sessions are saved every 30 seconds: a crash only loses the last few seconds. The **History** panel (Ctrl+H) lists the sessions: search ignores accents and matches word beginnings, a click opens a transcript, a right click renames it (F2), adds it to the favourites or deletes it (Del).

The audio of microphone and live recordings is kept as FLAC (about 60 MB per hour), then deleted after 30 days by default; the text stays. Deleting a transcript also deletes its audio, even if it is open in the player; at startup, audio files that no longer belong to any transcript (deletion refused by Windows, crash during encoding) are removed. Imported files are not copied: the player plays the original file as long as it exists. The text of universal dictations is kept too (never their audio), unless the option is turned off in the settings.

## Synchronised editor

When the audio is available, a player appears under the transcript: play, back 5 s, speed from 0.5× to 2×. The spoken word is highlighted, and clicking a word moves playback there. Words the model is unsure of (probability below 50 %, imported files) are underlined in red.

**Edit** (Ctrl+E) makes the text editable: one line per segment, so that the timestamps stay right for subtitles. Click **Edit** again to confirm; the corrections are saved in the history. A right click on a passage offers **Transcribe again with the large-v3 (precise) model**: only the selected segments go through large-v3 again, then the current model is reloaded.

## Diagnostics

**Settings > Hardware > Copy diagnostic information** copies a report to attach to a bug report: Windows, graphics card and driver, cards seen by CTranslate2, library versions, models present, settings and the latest errors of the log. The report contains no transcript, no vocabulary and no context; its headings are in French. The application log is in `%LOCALAPPDATA%\DoYouCopy\logs\doyoucopy.log` (**Open the logs folder** button).

```powershell
.\.venv\Scripts\python.exe scripts\check_gpu.py
```

This script shows the CTranslate2 version, whether the ROCm runtime is present and the number of HIP GPUs, then loads the `tiny` model in float16 on the GPU.

- **`GPU HIP : 0`**: check the Adrenalin driver. Also check that `pip show ctranslate2` points to the ROCm wheel, otherwise run the install script again.
- **The chip at the bottom right says "Processor · int8"**: the GPU could not be initialised. The banner gives the reason, and the details are in the log.

## Architecture

```
src/doyoucopy/
  app.py              bootstrap: GPU detection (before Qt), engine, interface language, window
  config.py           JSON settings (%APPDATA%\DoYouCopy\settings.json), checked value by value
  session.py          SessionController: capture, transcription, corrections, current result (no Qt Widgets)
  history_controller.py  HistoryController: current entry, autosave, kept audio and dictations (no Qt Widgets)
  diagnostics.py      log, uncaught exceptions, diagnostic report
  i18n.py             interface language: tr("French text") -> translation, chosen at startup
  locales/en.py       English translations (key = the French text)
  storage/
    history.py        SQLite + FTS5 history, audio retention
    audio.py          kept audio as FLAC (PyAV), WAV fallback
  gpu/rocm_env.py     device choice: ROCm GPU (float16) or CPU (int8)
  core/
    types.py          Segment, ModelSpec, TranscribeOptions, DeviceConfig…
    models.py         model registry (turbo / precise)
    engine.py         TranscriptionEngine Protocol + FasterWhisperEngine
    live.py           live mode: sliding window + LocalAgreement
    textproc.py       replacements and voice commands (pure functions)
    model_download.py model downloaded at first start, with progress
  audio/
    recorder.py       16 kHz mono microphone capture (sounddevice)
    loopback.py       computer audio: WASAPI loopback (COM through ctypes)
    sources.py        source choice, microphone + computer mix
  runtime/
    gpu_detect.py     card detection (WMI): NVIDIA, compatible AMD or processor
    packages.py       pinned accelerations (URL, version, SHA-256)
    install.py        download with resume, and unpacking of the wheels
    store.py          location and activation (sys.path, DLL) before importing ctranslate2
    startup.py        startup choice, GPU test (--probe), explanation of the processor fallback
  download.py         HTTP downloads: progress, resume, cancellation, SHA-256
  desktop/
    com.py            minimal COM through ctypes (shared with loopback.py)
    shortcuts.py      desktop / Start menu shortcuts (.lnk with the app's AppUserModelID)
  options.py          TranscribeOptions built from the settings (file, live, dictation)
  dictation/
    controller.py     universal dictation: state machine shortcut → microphone → text
    hotkey.py         global shortcut (WH_KEYBOARD_LL keyboard hook, reinstalled every 15 s)
    inject.py         paste into the active window (SendInput), clipboard restored
    autostart.py      start with Windows (HKCU Run key)
    sounds.py         synthesised sounds
  export/             exporters registered by extension (txt, srt, vtt, md, docx, json)
    subtitles.py      subtitle splitting (2 × 42 characters)
  ui/
    workers.py        ModelWorker: the single thread that owns the model
    main_window.py    window: layout, display of the session and the history, editing
    app_icon.py       application icon (window, taskbar, .ico of the exe and the shortcuts)
    history_panel.py  history side panel
    tray.py           notification area icon
    settings_dialog.py  full settings window, by section
    vocabulary_dialog.py  preferred words, replacements, voice commands
    theme.py          colour tokens (dark / light), generated QSS, Geist fonts
    widgets/          microphone button, waveform, segmented control, transcript card
                      (synchronised words, edit mode), audio player, settings popover,
                      notifications, dictation pill
    resources/fonts/  Geist and Geist Mono (OFL licence)
scripts/              install_rocm.ps1, check_gpu.py, download_models.py,
                      snapshot_ui.py (screenshots of the interface in every state, --lang en|fr),
                      build_installer.ps1, make_build_assets.py (icon, version), build_msix.ps1
packaging/            PyInstaller: doyoucopy.spec, launcher.py; msix/ (manifest, Strings/<language>)
installer/            Inno Setup: doyoucopy.iss
tests/                unit tests + end-to-end GPU test (-m gpu)
```

Principles:

- **The interface only depends on the `TranscriptionEngine` Protocol.** Another backend (whisper.cpp Vulkan, transformers…) can be added in `core/` without touching the UI.
- **A single thread (`ModelWorker`) owns the model.** Requests (loading, transcription) go through queued Qt signals: no concurrent access to the GPU, and the UI never freezes.
- **The model is also released on that thread, on exit.** With the ROCm build of CTranslate2, releasing a GPU model from another thread kills the process (code 127). After a processor model, that thread cannot even end: it is left alive and the application exits through `os._exit`, once the history and the settings are saved.
- **Segments are emitted one by one** from faster-whisper's generator. That is what produces the progressive display and allows cancelling between two segments.
- **Adding a model** means adding a `ModelSpec` entry in `core/models.py`. **Adding an export format** means creating a class with `suffix`, `label` and `render()`, then calling `register()`.
- **Every displayed text goes through `tr()`** (`i18n.py`), written in French in the code; `locales/en.py` gives its English version. A module-level constant is marked with `N_()` and translated where it is shown. `tests/test_i18n.py` fails when a translation is missing, no longer used, or loses a `{placeholder}`. **Adding a language** means a `locales/<code>.py` file and its code in `i18n.py`.
- **Logic stays out of the widgets.** `SessionController` (capture, transcription) and `HistoryController` (what is saved, and when) are tested without a window; `MainWindow` displays and relays.
- **Windows silently removes a keyboard hook that is too slow.** The global shortcut is therefore reinstalled periodically (`KeyboardHook.reinstall`), without a gap: the new hook is set before the old one is removed.

Live mode and universal dictation also go through `ModelWorker`: the GPU keeps a single user. Dictation has its own signals (`dictation_finished`), so that its text does not appear in the main window.

Next steps: see [ROADMAP.md](ROADMAP.md) (in French).

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest           # unit tests
.\.venv\Scripts\python.exe -m ruff check .      # static analysis (rules in pyproject.toml)
.\.venv\Scripts\python.exe -m pytest -m gpu    # real transcription on the GPU (Windows speech synthesis)
.\.venv\Scripts\python.exe -m pytest -m hardware  # real capture of the computer audio (plays a sound)
```
