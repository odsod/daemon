# VOXD

- Repo: https://github.com/jakovius/voxd @ 9c067c6f41ede6392d4f47c7475a46b689a30ce4 (studied 2026-11-22)
- License: MIT ([LICENSE](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/LICENSE#L1-L21)). Stars: 309 (36 forks, 31 open issues per GitHub API). Last release: [v1.7.0](https://github.com/jakovius/voxd/releases/tag/v1.7.0) (2025-10-22). Stack: Python 3.9+ (`hatchling`), PyQt6, pyqtgraph, `sounddevice` (PortAudio), NumPy, PyYAML, `pyperclip`, `requests`, `psutil`, `whisper.cpp` (`whisper-cli`), `llama.cpp` (`llama-server`), `ydotool`/`xdotool`, `wl-copy`/`xclip`/`xsel` ([pyproject.toml](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/pyproject.toml#L1-L31)).

## Scope

- Linux-only voice-typing and dictation tool with four runtime modes: interactive/quick-action CLI (`voxd`, `voxd --rh`), frameless floating PyQt6 GUI (`voxd --gui`), system tray daemon (`voxd --tray`), and beta VAD-triggered continuous dictation (`voxd --flux`) plus a VAD tuner (`voxd --flux-tuner`) ([src/voxd/**main**.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/__main__.py#L314-L319), [src/voxd/**main**.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/__main__.py#L525-L545)).
- Runs local offline ASR via `whisper-cli` and optional local or cloud LLM text post-processing ("AIPP") ([README.md](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/README.md#L6-L34)).
- Does not target macOS or Windows; does not do meeting recording, speaker diarization, or system audio capture.

## Architecture (processes, services, IPC, state)

- Single foreground/background Python process per chosen UI mode (`cli`, `gui`, `tray`, `flux`). A second short-lived `voxd --trigger-record` process acts as the hotkey client ([src/voxd/**main**.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/__main__.py#L415-L419)).
- IPC uses a Unix domain stream socket at `~/.config/voxd/voxd.sock`. The server binds the socket in a daemon thread and invokes `trigger_callback()` when it receives `b"trigger_record"`; there is no reply or ack protocol ([src/voxd/utils/ipc_server.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/utils/ipc_server.py#L5-L28), [src/voxd/utils/ipc_client.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/utils/ipc_client.py#L4-L17)).
- In GUI and Tray modes, each recording cycle spawns a new `CoreProcessThread(QThread)` that instantiates fresh `AudioRecorder`, `WhisperTranscriber`, `SimulatedTyper`, and `ClipboardManager` objects ([src/voxd/core/voxd_core.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/voxd_core.py#L15-L61)).
- Subprocesses spawned at runtime:
  - `whisper-cli` is invoked fresh per utterance via `subprocess.run()` ([src/voxd/core/transcriber.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/transcriber.py#L59-L69)). It is not a persistent server.
  - `llama-server` is started lazily on first AIPP call by `LlamaServerManager` (`subprocess.Popen` with `preexec_fn=os.setsid`, polled on `GET http://127.0.0.1:8080/health`, stopped via `atexit` SIGTERM/SIGKILL to its process group) ([src/voxd/core/llama_server_manager.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/llama_server_manager.py#L18-L141)).
  - `ydotool` or `xdotool` runs per utterance via `subprocess.run()` ([src/voxd/core/typer.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/typer.py#L226-L238)).
- User services:
  - `voxd-tray.service` (systemd user unit) runs `/usr/bin/voxd --tray` with `YDOTOOL_SOCKET=%h/.ydotool_socket`; toggled via `voxd --autostart true|false` with XDG autostart fallback (`~/.config/autostart/voxd-tray.desktop`) ([packaging/voxd-tray.service](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/packaging/voxd-tray.service#L1-L15), [src/voxd/**main**.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/__main__.py#L175-L305)).
  - `ydotoold.service` (systemd user unit) runs `/usr/bin/voxd-ydotoold`, which execs `ydotoold --socket-path="$HOME/.ydotool_socket" --socket-own="$OWNER_UID:$OWNER_GID"` ([packaging/ydotoold.service](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/packaging/ydotoold.service#L1-L11), [packaging/voxd-ydotoold](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/packaging/voxd-ydotoold#L74-L75)).
- State lives in `AppConfig` (YAML singleton) and in-memory `SessionLogger.entries`. GUI mode watches `config.yaml` with `QFileSystemWatcher` to sync external edits ([src/voxd/gui/gui_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/gui/gui_main.py#L157-L162)).

## Audio capture (API, rate, buffering, system audio)

- API: `sounddevice.InputStream` (PortAudio) in mono ([src/voxd/core/recorder.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/recorder.py#L1-L77)).
- Device selection: uses `audio_input_device` if set, otherwise `"pulse"` when `audio_prefer_pulse: true` (default) ([src/voxd/core/recorder.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/recorder.py#L48-L50)).
- Sample rate and fallback: `AudioRecorder` requests `16000` Hz. If opening fails, it queries `default_samplerate` (fallback `48000` Hz), retries `"pulse"` if not tried, then opens with `device=None` ([src/voxd/core/recorder.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/recorder.py#L81-L116)). `AudioRecorder` does not resample when it falls back to 48 kHz; it writes the WAV at `self.fs`. By contrast, `FluxRunner` opens at the device's `default_samplerate` and linearly resamples segments to 16 kHz with `np.interp` before writing WAV ([src/voxd/flux/flux_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/flux/flux_main.py#L219-L225), [src/voxd/flux/flux_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/flux/flux_main.py#L435-L445)).
- Buffering: `record_chunked: true` (default) streams 16-bit PCM directly into rotating WAV files (`chunk_0001.wav`, 300 s each) under `/tmp/voxd_temp/`, then stitches them into `last_recording.wav` (or a timestamped file) on stop ([src/voxd/core/recorder.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/recorder.py#L22-L68), [src/voxd/core/recorder.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/recorder.py#L161-L194)). When `record_chunked: false`, frames accumulate in a Python list in RAM.
- Mic gain autoset: on startup (when `mic_autoset_enabled: true`, default), VOXD unmutes `@DEFAULT_SOURCE@` and forces input volume to `0.45` (45%) via `wpctl` -> `pactl` -> `amixer` ([src/voxd/**main**.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/__main__.py#L37-L115), [src/voxd/defaults/default_config.yaml](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/defaults/default_config.yaml#L20-L22)).
- Audio preprocessing: `audio_preproc.py` attenuates peaks above `-3.0 dBFS` (no boosting) and warns if clipped samples >= 1% ([src/voxd/core/audio_preproc.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/audio_preproc.py#L81-L115)). Note: only `core_runner.py` calls `preprocess_wav`; `CoreProcessThread` (GUI/Tray) and `cli_main.py` do not call it ([src/voxd/utils/core_runner.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/utils/core_runner.py#L65-L75), [src/voxd/core/voxd_core.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/voxd_core.py#L69-L75)).
- System audio / loopback capture: Not found. Checked `src/voxd/core/recorder.py`, `src/voxd/flux/flux_main.py`, and repo-wide search for `loopback` and monitor sources.

## VAD and segmentation

- Only used in Flux mode (`voxd --flux`) and Flux Tuner (`voxd --flux-tuner`). Standard hotkey modes do not run VAD.
- Backend: custom energy-based `FluxVAD` using NumPy RMS dBFS on 30 ms frames. Silero VAD was explicitly removed (`## Silero backend removed`) ([src/voxd/flux/flux_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/flux/flux_main.py#L110-L212)).
- Dynamic noise-floor tracking with hysteresis:
  ```python
  start_thr = max(self.noise_db + self.start_margin_db, self.abs_start_db)
  keep_thr  = max(self.noise_db + self.keep_margin_db,  self.abs_keep_db)
  ```
  ([src/voxd/flux/flux_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/flux/flux_main.py#L165-L197))
- Default parameters in `default_config.yaml` and `flux_main.py` ([src/voxd/defaults/default_config.yaml](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/defaults/default_config.yaml#L27-L54), [src/voxd/flux/flux_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/flux/flux_main.py#L224-L258)):
  - Frame size: `30 ms`
  - Calibration window: `flux_calibration_sec: 5` (updates `noise_db` and FFT noise spectrum baseline before listening)
  - Noise EMA: `flux_noise_ema: 0.05` (updated only while not speaking), spectral EMA `flux_noise_spec_ema: 0.02`
  - Margins & absolute floors: `flux_energy_start_margin_db: 6.0`, `flux_energy_keep_margin_db: 3.0`, `flux_energy_abs_start_db: -33.0`, `flux_energy_abs_keep_db: -37.0`
  - Timing gates: `flux_min_speech_ms: 200`, `flux_min_silence_ms: 500`, `flux_pre_roll_ms: 180` (ring buffer `deque`), `flux_post_roll_ms: 150`, `flux_min_segment_ms: 600`, `flux_cooldown_ms: 250`
  - Segment energy filter: drops segments with overall RMS below `flux_min_rms_dbfs: -45.0` ([src/voxd/flux/flux_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/flux/flux_main.py#L415-L425)).
- Optional post-segment spectral subtraction (`NoiseSuppressor`, STFT overlap-add with Hanning window, `hop_ratio=0.5`, `floor_db=-85.0`) runs off the detection path when `flux_noise_subtract_enabled: true` ([src/voxd/flux/flux_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/flux/flux_main.py#L48-L108), [src/voxd/flux/flux_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/flux/flux_main.py#L427-L432)).
- Each finalized segment is dispatched to a new daemon thread `_do_transcribe()` without a queue or serialization lock, so overlapping utterances can race on `flux_last.wav` and typing ([src/voxd/flux/flux_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/flux/flux_main.py#L401-L412)).

## ASR (backends, models, language handling, prompts, custom vocabulary)

- Backend: `whisper.cpp` CLI (`whisper-cli`) only ([src/voxd/core/transcriber.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/transcriber.py#L10-L91)). No other ASR backend exists.
- Invocation command:
  ```python
  cmd = [
      self.binary_path,
      "-m", self.model_path,
      "-f", str(audio_file),
      "-l", self.language,
      "-of", str(self.output_dir / audio_file.stem),
      "-otxt"
  ]
  ```
  ([src/voxd/core/transcriber.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/transcriber.py#L59-L66))
- Output parsing: reads `<output_dir>/<stem>.txt`, strips `[00:00.000]` and `(00:00)` timestamps with regex, collapses whitespace ([src/voxd/core/transcriber.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/transcriber.py#L92-L106)).
- Models: 33 GGML models from Hugging Face (`ggerganov/whisper.cpp`), from `tiny` to `large-v3` and `large-v3-turbo` (including `q5_0`/`q5_1`/`q8_0` quantized variants and `small.en-tdrz`), verified with SHA-1 and stored in `~/.local/share/voxd/models/` ([src/voxd/models.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/models.py#L22-L72), [src/voxd/models.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/models.py#L118-L158)). Default model is `ggml-base.en.bin` ([src/voxd/utils/setup_user.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/utils/setup_user.py#L65-L73)). Note: `_download()` disables TLS certificate verification (`ssl._create_unverified_context`) ([src/voxd/models.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/models.py#L97-L98)).
- Language handling: ISO 639-1 table (184 codes) plus `auto`, default `en`. Settable via `config.yaml`, GUI/Tray Language dialog, or session-only `-l/--lang` CLI flag. Warns if a non-English language is paired with a `*.en.bin` model ([src/voxd/utils/languages.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/utils/languages.py#L1-L60), [src/voxd/core/transcriber.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/transcriber.py#L38-L44)).
- Whisper prompts / custom vocabulary / extra CLI flags: Not found. `WhisperTranscriber.transcribe()` builds a fixed argument list with no `--prompt`, no custom vocabulary, and no passthrough flags (also requested in [issue #6](https://github.com/jakovius/voxd/issues/6) and [issue #24](https://github.com/jakovius/voxd/issues/24)). Checked `src/voxd/core/transcriber.py` and `src/voxd/core/config.py`.

## Post-processing (LLM cleanup, prompts, glossary, replacements)

- Optional "AIPP" (AI Post-Processing), disabled by default (`aipp_enabled: false`) and forced off on `FluxRunner.run()` startup ([src/voxd/defaults/default_config.yaml](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/defaults/default_config.yaml#L57-L59), [src/voxd/flux/flux_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/flux/flux_main.py#L464-L466)).
- Providers in `src/voxd/core/aipp.py`:
  - `llamacpp_server` (default): `POST http://localhost:8080/v1/chat/completions`, `max_tokens: 512`, `temperature: 0.7`, `timeout: 30` s, default model `qwen2.5-3b-instruct-q4_k_m.gguf` ([src/voxd/core/aipp.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/aipp.py#L119-L147)).
  - `ollama`: `POST http://localhost:11434/api/generate` (`stream: False`, `timeout: 20`) ([src/voxd/core/aipp.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/aipp.py#L51-L61)).
  - `openai`, `anthropic`, `xai`: direct `requests.post` using `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `XAI_API_KEY` env vars (`timeout: 20`) ([src/voxd/core/aipp.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/aipp.py#L64-L116)).
  - Retries once after `0.5` s on network error, then falls back to returning the raw transcript ([src/voxd/core/aipp.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/aipp.py#L26-L48)).
- Prompt construction: concatenates the selected prompt and transcript into a single `user` message (`full_prompt = f"{prompt}\n{text.strip()}"`), with no system message ([src/voxd/core/aipp.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/aipp.py#L20)).
- Four fixed editable prompt slots (`default`, `prompt1`, `prompt2`, `prompt3`); defaults ([src/voxd/defaults/default_config.yaml](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/defaults/default_config.yaml#L85-L89)):
  ```yaml
  default: "Rewrite the following input so that it is clean and concise. Do not add any additional text or commentary. Just the rewritten text."
  prompt1: "Interpret the following text to the best of your ability as a C programming language code and output it as such. Do not add any additional text or commentary. Just the corresponding C code."
  prompt2: "Interpret the following text to the best of your ability as a Python programming language code and output it as such. Do not add any additional text or commentary. Just the corresponding Python code."
  prompt3: "Rewrite the following text as a three-verse poem."
  ```
- Glossary / custom word replacements / regex rules: Not found. Checked `src/voxd/core/aipp.py`, `src/voxd/core/config.py`, and `src/voxd/core/transcriber.py`.

## Hotkeys on Wayland/KDE (mechanism, hold vs toggle)

- Mechanism: VOXD does not register or grab global hotkeys itself. The user binds a desktop/compositor shortcut (KDE System Settings, GNOME Custom Shortcuts, Hyprland/Sway config) to run `bash -c 'voxd --trigger-record'` ([README.md](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/README.md#L103-L113), [src/voxd/**main**.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/__main__.py#L518-L520)).
- That command connects to `~/.config/voxd/voxd.sock` and sends `b"trigger_record"` ([src/voxd/utils/ipc_client.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/utils/ipc_client.py#L7-L17)).
- Hold vs toggle: toggle only. First press starts recording, second press stops recording and runs transcription; in Flux mode, it toggles listening vs paused ([src/voxd/tray/tray_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/tray/tray_main.py#L127-L138), [src/voxd/flux/flux_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/flux/flux_main.py#L492-L498)). Push-to-talk (hold-to-record) is not found; checked `src/voxd/utils/ipc_server.py`, `src/voxd/utils/ipc_client.py`, `src/voxd/gui/gui_main.py`, and `src/voxd/tray/tray_main.py`.
- No XDG Desktop Portal GlobalShortcuts or evdev listener is implemented.

## Text delivery (paste vs type, tools, clipboard restore, per-app, unicode)

- Backend detection: checks `$WAYLAND_DISPLAY` -> `"wayland"`, `$DISPLAY` -> `"x11"`, else `$XDG_SESSION_TYPE` ([src/voxd/core/typer.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/typer.py#L11-L33)). Picks `ydotool` on Wayland and `xdotool` on X11, falling back across both ([src/voxd/core/typer.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/typer.py#L93-L118)).
- Type vs paste mode: controlled by `typing_delay` (default `1` ms).
  - `typing_delay > 0` (default): simulated keystroke typing via `ydotool type -d <ms> <text>` or `xdotool type --delay <ms> <text>`, after sleeping `typing_start_delay` (`0.15` s default) to let hotkey modifiers release ([src/voxd/core/typer.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/typer.py#L253-L289)). `_run_tool()` enforces a hard `timeout=10` s ([src/voxd/core/typer.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/typer.py#L226-L233)).
  - `typing_delay <= 0`: paste mode via `_paste()`:
    ```python
    pyperclip.copy(t)
    ...
    time.sleep(0.10)
    if self.start_delay > 0:
        time.sleep(self.start_delay)
    ...
    if use_ctrl_v:
        # Ctrl+V: Ctrl(29) + V(47)
        subprocess.run(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"], ...)
    else:
        # Default Ctrl+Shift+V: Ctrl(29) + Shift(42) + V(47)
        subprocess.run(["ydotool", "key", "29:1", "42:1", "47:1", "47:0", "42:0", "29:0"], ...)
    ```
    ([src/voxd/core/typer.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/typer.py#L294-L345))
- Clipboard tools: `ClipboardManager` selects `wl-copy` (Wayland), `xclip -selection clipboard`, `xsel -i`, or `pyperclip` ([src/voxd/core/clipboard.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/clipboard.py#L11-L48)). However, `SimulatedTyper._paste()` bypasses `ClipboardManager` and calls `pyperclip.copy()` directly, which breaks on Wayland when `pyperclip` picks a non-persisting backend ([src/voxd/core/typer.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/typer.py#L304), [issue #41](https://github.com/jakovius/voxd/issues/41)).
- Clipboard restore: Not found. VOXD intentionally leaves the transcript in the clipboard (`transcripts ALWAYS picked up into clipboard`) and never reads or restores the previous clipboard contents ([src/voxd/core/clipboard.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/clipboard.py#L27-L54), [src/voxd/core/typer.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/typer.py#L294-L353)).
- Per-app paste/window detection: Not found. `ctrl_v_paste` is a single global boolean (`false` = `Ctrl+Shift+V`, `true` = `Ctrl+V`) ([src/voxd/core/typer.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/typer.py#L315-L317)). Checked `src/voxd/core/typer.py` and `src/voxd/core/config.py`.
- Unicode and non-US keyboard layouts: broken in default typing mode (`typing_delay > 0`) because `ydotool type` injects raw US-QWERTY uinput keycodes; non-US layouts (PT-BR, Colemak, QWERTZ, Swedish, AZERTY) and diacritics (Czech) are scrambled ([issue #19](https://github.com/jakovius/voxd/issues/19), [issue #40](https://github.com/jakovius/voxd/issues/40)).
- Trailing space: `append_trailing_space: true` appends a single space after `text.rstrip()` ([src/voxd/core/typer.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/typer.py#L272-L278)).

## UI feedback (overlay, tray, notifications)

- Floating GUI (`voxd --gui`): 340x162 frameless always-on-top translucent PyQt6 window (`FramelessWindowHint | WindowStaysOnTopHint`, `WA_TranslucentBackground`) positioned at bottom-right; uses `windowHandle().startSystemMove()` for Wayland dragging ([src/voxd/gui/gui_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/gui/gui_main.py#L33-L45), [src/voxd/gui/gui_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/gui/gui_main.py#L223-L229), [src/voxd/gui/gui_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/gui/gui_main.py#L671-L694)). Minimizes itself when status switches to `"Typing"` and restores on `"Ready"` ([src/voxd/gui/gui_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/gui/gui_main.py#L516-L517), [src/voxd/gui/gui_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/gui/gui_main.py#L636-L637)). Pulses the main button at ~30 FPS (orange for recording, green for transcribing/typing) and shows an 80-char transcript preview ([src/voxd/gui/gui_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/gui/gui_main.py#L536-L561), [src/voxd/gui/gui_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/gui/gui_main.py#L616-L623)).
- System tray (`voxd --tray`, and also shown in GUI mode): `QSystemTrayIcon` animated across 9 PNG frames (`voxd-1.png`..`voxd-9.png`, 500 ms period) during recording and 4 frames (1000 ms period) during transcribing/typing, with tooltip `VOXD - <status>` and a context menu for Start/Stop, Whisper Models, AIPP, Session Log, Language, Settings, Performance, Quit ([src/voxd/tray/tray_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/tray/tray_main.py#L30-L125)).
- Flux GUI (`voxd --flux`): 300x220 PyQt6 + `pyqtgraph` live normalized energy plot with dynamic Start/Keep threshold lines, Listening/Paused toggle, 5 s recalibrate button, and EMA drift toggle ([src/voxd/flux/flux_gui.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/flux/flux_gui.py#L21-L169)).
- Desktop notifications (`notify-send`, `QSystemTrayIcon.showMessage`): Not found. `tray_main.py` has only a placeholder comment `# Optionally, show a notification here` ([src/voxd/tray/tray_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/tray/tray_main.py#L143)). Checked `src/voxd/tray/tray_main.py`, `src/voxd/gui/gui_main.py`, and repo-wide grep.

## Meeting features (system audio, mic mute, diarization, speakers, summaries)

- System audio capture: Not found (checked `src/voxd/core/recorder.py`, `src/voxd/flux/flux_main.py`).
- Mic mute detection/controls: VOXD unmutes the default mic at startup if `mic_autoset_enabled: true` ([src/voxd/**main**.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/__main__.py#L64-L90)), but has no meeting mute-sync or push-to-mute feature.
- Speaker diarization / speaker labels: Not found. The model catalogue lists `small.en-tdrz` (tinydiarize) ([src/voxd/models.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/models.py#L48)), but `WhisperTranscriber` never passes `-tdrz` to `whisper-cli` and does not parse speaker turns ([src/voxd/core/transcriber.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/transcriber.py#L59-L66)).
- Meeting summaries / notes: Not found (only single-utterance AIPP rewriting in `src/voxd/core/aipp.py`).

## Data and storage

- Config: `~/.config/voxd/config.yaml` (respects `$XDG_CONFIG_HOME`) ([src/voxd/paths.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/paths.py#L17-L20)).
- IPC socket: `~/.config/voxd/voxd.sock` ([src/voxd/utils/ipc_server.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/utils/ipc_server.py#L5-L6)).
- Data dir (`~/.local/share/voxd/`, respects `$XDG_DATA_HOME`):
  - `models/`: Whisper GGML `.bin` files ([src/voxd/models.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/models.py#L71)).
  - `llamacpp_models/`: GGUF LLM models ([src/voxd/paths.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/paths.py#L171)).
  - `bin/`: downloaded prebuilt `whisper-cli`, `llama-server`, `ydotool`, `ydotoold` ([src/voxd/utils/setup_user.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/utils/setup_user.py#L213-L216), [src/voxd/utils/setup_user.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/utils/setup_user.py#L354)).
  - `output/`: `whisper-cli` `.txt` outputs ([src/voxd/paths.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/paths.py#L75-L76)).
  - `recordings/`: preserved timestamped WAVs when `--save-audio` or `save_recordings: true` ([src/voxd/paths.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/paths.py#L79-L80)).
  - `voxd_perf_data.csv`: optional per-run latency/model/system CSV when `perf_collect: true` ([src/voxd/utils/performance.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/utils/performance.py#L8-L20)).
- Temp audio: `/tmp/voxd_temp/` (`chunk_XXXX.wav`, `last_recording.wav`, `flux_last.wav`) ([src/voxd/core/recorder.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/recorder.py#L18-L20), [src/voxd/flux/flux_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/flux/flux_main.py#L410-L412)).
- Session logs: held in RAM (`SessionLogger.entries`) as `[YYYY-MM-DD HH:MM:SS] <text>` and written only when the user manually saves via a Qt/Tk file dialog ([src/voxd/core/logger.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/logger.py#L6-L94)). No SQLite or persistent transcript history database.

## Packaging and install

- Native packages built in CI via `nfpm` for `.deb`, `.rpm`, and `.pkg.tar.zst` (`amd64` and `arm64`) ([.github/workflows/release-packages.yml](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/.github/workflows/release-packages.yml#L18-L88), [packaging/nfpm.yaml](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/packaging/nfpm.yaml#L1-L131)).
- Package contents: source tree under `/opt/voxd/src`, `/usr/bin/voxd` wrapper, `/usr/bin/voxd-ydotoold`, `/etc/udev/rules.d/99-uinput.rules` (`MODE="0660", GROUP="input", TAG+="uaccess"`), and systemd user units `/usr/lib/systemd/user/{ydotoold,voxd-tray}.service` ([packaging/nfpm.yaml](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/packaging/nfpm.yaml#L13-L48), [packaging/99-uinput.rules](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/packaging/99-uinput.rules#L1)).
- `postinstall.sh` creates the `input` group, loads `uinput`, adds `$SUDO_USER` to `input`, and creates `/opt/voxd/.venv` (`--system-site-packages`) via `pip install` for missing Python deps like `sounddevice` ([packaging/postinstall.sh](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/packaging/postinstall.sh#L4-L113)).
- First run invokes `voxd --setup`, which downloads `ggml-base.en.bin`, `qwen2.5-3b-instruct-q4_k_m.gguf`, and CPU-variant prebuilts (`avx2`/`sse42`/`neon`) of `whisper-cli`, `llama-server`, and `ydotool`/`ydotoold` from `jakovius/voxd-prebuilts` ([packaging/voxd.wrapper](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/packaging/voxd.wrapper#L110-L121), [src/voxd/utils/setup_user.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/utils/setup_user.py#L205-L447), [src/voxd/utils/whisper_auto.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/utils/whisper_auto.py#L107-L237)).
- Source install: `./setup.sh` installs distro packages, creates `.venv`, compiles `whisper.cpp` (and `ydotool` if needed), and installs `.desktop` launchers ([setup.sh](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/setup.sh#L1-L150)).
- No Flatpak or AppImage (open requests: [issue #17](https://github.com/jakovius/voxd/issues/17), [issue #28](https://github.com/jakovius/voxd/issues/28)).

## Tests and benchmarks

- Test suite: 15 pytest files with 26 unit tests under `tests/`, all running headless (`QT_QPA_PLATFORM=offscreen`) with stubbed `sounddevice`, `pyperclip`, and `whisper-cli` subprocesses ([tests/conftest.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/tests/conftest.py#L8-L141)). No CI workflow runs `pytest` (`.github/workflows/` contains only `release-packages.yml`).
- Benchmarks: Not found as automated scripts. The app includes an opt-in runtime CSV logger (`voxd_perf_data.csv`) recording `rec_dur`, `trans_dur`, `trans_eff` (s/char), `aipp_dur`, `usr_trans_acc`, `sys_mem`, and `sys_cpu` ([src/voxd/utils/performance.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/utils/performance.py#L8-L61), [src/voxd/core/voxd_core.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/voxd_core.py#L121-L149)).

## Known pitfalls (top Linux/Wayland issues from the tracker)

- **Hard 10 s `ydotool` timeout truncates at ~285 chars and locks a keyboard key until reboot** ([issue #20](https://github.com/jakovius/voxd/issues/20), [issue #34](https://github.com/jakovius/voxd/issues/34)): `_run_tool()` kills `ydotool type` after `timeout=10` s ([src/voxd/core/typer.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/typer.py#L229)). Because `ydotool` defaults to 20 ms key-hold, SIGKILL lands between key-down and key-up on Kubuntu/Wayland, leaving the uinput key permanently pressed.
- **Paste mode (`typing_delay <= 0`) silently fails on Wayland** ([issue #41](https://github.com/jakovius/voxd/issues/41)): `SimulatedTyper._paste()` calls `pyperclip.copy()` instead of `ClipboardManager` (`wl-copy`), and `pyperclip`'s GTK backend loses the clipboard without a GTK event loop ([src/voxd/core/typer.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/typer.py#L304)).
- **`ydotool type` scrambles non-US keyboard layouts and Unicode diacritics** ([issue #19](https://github.com/jakovius/voxd/issues/19), [issue #40](https://github.com/jakovius/voxd/issues/40)): reported on KDE with PT-BR, Colemak, QWERTZ, Swedish, AZERTY, and Czech because `ydotool type` injects raw US keycodes.
- **PipeWire / PortAudio `paInvalidSampleRate` and silent `[BLANK_AUDIO]`** ([issue #43](https://github.com/jakovius/voxd/issues/43), [issue #5](https://github.com/jakovius/voxd/issues/5)): `sounddevice` requesting 16 kHz on ALSA/PipeWire fails or opens the wrong device; `AudioRecorder` falls back to 48 kHz without resampling.
- **No way to pass flags to `whisper-cli` (e.g., `--no-gpu`)** ([issue #24](https://github.com/jakovius/voxd/issues/24), [issue #6](https://github.com/jakovius/voxd/issues/6)): broken GPU drivers crash `whisper.cpp` because `WhisperTranscriber` hardcodes its CLI args.
- **Python version whitelist breaks on Python 3.14+** ([issue #29](https://github.com/jakovius/voxd/issues/29)): `voxd.wrapper` hardcodes `3.9|3.10|3.11|3.12|3.13` ([packaging/voxd.wrapper](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/packaging/voxd.wrapper#L47-L49)).
- **Global stylesheet cascade makes GUI dialogs white-on-white** ([issue #39](https://github.com/jakovius/voxd/issues/39)): `VoxdApp` sets `QWidget { color: white; }` which cascades into child dialogs with light system backgrounds ([src/voxd/gui/gui_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/gui/gui_main.py#L39-L43)).

## Ideas for the daemon

### Copy

- **Udev uinput rule + per-user `ydotoold.service` with `--socket-own`**: `TAG+="uaccess"` in [packaging/99-uinput.rules](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/packaging/99-uinput.rules#L1) paired with a user-owned socket (`%h/.ydotool_socket`) avoids running `ydotoold` as root or world-writable sockets.
- **Post-hotkey modifier release delay (`typing_start_delay`)**: waiting ~150 ms before sending a paste shortcut prevents the user's held hotkey modifier (like Alt) from colliding with `Ctrl+V` ([src/voxd/core/typer.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/typer.py#L51-L55)).
- **Rotating disk chunks for long recordings**: streaming PCM directly to rotating WAV chunks in `AudioRecorder` keeps RAM flat during long sessions instead of buffering hours of audio in memory ([src/voxd/core/recorder.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/recorder.py#L55-L68)).
- **Process-group lifecycle management for local `llama-server`**: launching with `os.setsid`, polling `/health`, and killing the process group on exit is clean and avoids orphan servers ([src/voxd/core/llama_server_manager.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/llama_server_manager.py#L76-L140)).
- **Wayland frameless drag via `windowHandle().startSystemMove()`**: works cleanly on KWin/Wayland where manual `move()` calls fail ([src/voxd/gui/gui_main.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/gui/gui_main.py#L674-L689)).

### Avoid

- **Do not use `ydotool type` for text delivery**: it mangles non-US layouts and Unicode ([issue #19](https://github.com/jakovius/voxd/issues/19), [issue #40](https://github.com/jakovius/voxd/issues/40)), and killing it on timeout leaves a uinput key stuck until reboot ([issue #34](https://github.com/jakovius/voxd/issues/34)). Use clipboard paste (`wl-copy` + `ydotool key` for `Ctrl+V`/`Ctrl+Shift+V`) with clipboard save/restore instead.
- **Do not use `pyperclip` on Wayland**: call `wl-copy` (and `wl-paste`) directly so clipboard ownership persists properly across Wayland compositors ([issue #41](https://github.com/jakovius/voxd/issues/41)).
- **Do not spawn `whisper-cli` per utterance**: cold-loading the GGML model on every dictation adds latency; use a persistent `whisper-server` (and expose GPU/thread flags).
- **Do not silently rewrite the OS microphone volume**: forcing `@DEFAULT_SOURCE@` to 45% on startup ([src/voxd/**main**.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/__main__.py#L37-L74)) interferes with calls and other audio apps.
- **Do not skip resampling on fallback sample rates**: `AudioRecorder` falls back from 16 kHz to 48 kHz without resampling ([src/voxd/core/recorder.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/core/recorder.py#L85-L96)); always resample to 16 kHz mono before Silero VAD and Whisper.
- **Do not rely on DE shortcuts alone if hold-Alt is required**: DE custom shortcuts only fire on press (toggle); hold-to-dictate needs an evdev/libinput listener or compositor release hook.
- **Do not disable TLS verification when downloading models**: avoid `ssl._create_unverified_context` ([src/voxd/models.py](https://github.com/jakovius/voxd/blob/9c067c6f41ede6392d4f47c7475a46b689a30ce4/src/voxd/models.py#L98)).
