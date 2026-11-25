# ADR-0005: Components and implementation

## Status

Proposed

## Date

2026-11-23

## Context

- [ADR-0002](0002-high-level-architecture.md) sets the capabilities and
  principles. [ADR-0003](0003-filesystem-interface.md) defines the files,
  [ADR-0004](0004-orchestration-with-systemd.md) the services,
  [ADR-0009](0009-taxonomy-and-code-organization.md) the taxonomy and
  [ADR-0010](0010-contracts-and-runtime.md) the contracts and runtime.
- Agents need one place that lists every component, its subsystem and its
  ADR, and the language, libraries and tools that all of them share.
- The best speech and audio tools (Silero VAD, language ID, ASR toolkits,
  WER) are Python libraries.
- A source study of nine dictation and meeting tools
  ([alternatives.md](../research/alternatives.md)) gave the evidence for
  many rules in the subsystem ADRs.

## Decision

This ADR is the index of components. Each subsystem ADR holds its design.

### Language and tooling

- **Python 3.14** for all code except the keys service, pinned in
  `.python-version`. Move to the next Python version when every runtime
  dependency ships wheels for it. (Python 3.15 is out, but onnxruntime has no
  3.15 wheels yet.)
- **C** for the keys service (ADR-0007), built with `gcc -Wall -Wextra -Werror`.
- **uv** manages Python, dependencies (`uv.lock`) and installs. uv comes from
  mise.
- **ruff** for lint and format. **pyright** in strict mode for types.
  **pytest** for tests. **import-linter** enforces the module boundaries
  ([ADR-0009](0009-taxonomy-and-code-organization.md)).
- `mise run build` runs all of them and compiles the keys service. It is the CI
  gate.

### Libraries

| Need                                | Library                                       |
| ----------------------------------- | --------------------------------------------- |
| CLI                                 | `typer`                                       |
| Config and stream records           | `pydantic` v2                                 |
| Concurrency                         | `asyncio` with `TaskGroup`                    |
| HTTP (whisper-server, llama-server) | `httpx` (async)                               |
| Chrome DevTools Protocol            | `websockets`                                  |
| File watching                       | `watchfiles`                                  |
| Audio arrays                        | `numpy`                                       |
| VAD                                 | Silero VAD model (ONNX) on `onnxruntime`, CPU |
| Tray icon                           | `PySide6` (`QSystemTrayIcon`, plain Qt loop)  |
| D-Bus (KWin, KGlobalAccel)          | `dbus-fast` (asyncio)                         |
| Prompt templates                    | `jinja2`                                      |
| Benchmark (optional extra `bench`)  | `jiwer`                                       |
| Logging                             | stdlib `logging` to stdout (journald)         |

- The `silero-vad` package requires torch and CUDA libraries, about 3 GB
  ([YazSes](../research/yazses.md)). The system ships the Silero ONNX model
  file and runs it on `onnxruntime` directly.
- No torch in version 1. Diarization, which needs it, is deferred (see
  "Later").
- The keys service uses only libc and Linux headers.
- whisper-server and llama-server are C++ programs. The daemon builds them
  from pinned source tarballs and runs them as user units
  ([ADR-0023](0023-inference-servers.md)). They are no Python dependency.
- A new runtime dependency needs an ADR.

### Code layout

- [ADR-0009](0009-taxonomy-and-code-organization.md) defines the terms, the
  folders, the subsystems and the dependency rules.
- [ADR-0010](0010-contracts-and-runtime.md) defines the seams, the record
  fields, the fault codes, the config, the `lib/` mechanisms and the command
  surface.
- Python folder names use underscores; the architecture name keeps its
  hyphen (`notify-failed` lives in `components/notify_failed/`).

### Components

![Architecture](../diagrams/high-level-architecture.svg)

Diagram source: [`high-level-architecture.py`](../diagrams/high-level-architecture.py),
with the shared style in [`schematic.py`](../diagrams/schematic.py). The README
shows the overview, [`overview.py`](../diagrams/overview.py). Regenerate with
`uv run docs/diagrams/<name>.py docs/diagrams/<name>.svg`.

| Subsystem    | ADR                                       | Component                              | Responsibility                                                                             | Service or command                                          | Main tools                                  |
| ------------ | ----------------------------------------- | -------------------------------------- | ------------------------------------------------------------------------------------------ | ----------------------------------------------------------- | ------------------------------------------- |
| keys         | [0007](0007-keys-service.md)              | keys                                   | Device level: remap keys; dictation key; paste keys                                        | keys                                                        | `evdev` and `uinput` ioctls (C)             |
| shortcuts    | [0008](0008-shortcuts-and-kwin-script.md) | shortcuts                              | Compositor level: register global shortcuts; install the KWin script; launch apps for KWin | session                                                     | `dbus-fast`, `systemd-run`, `kpackagetool6` |
| capture      | [0011](0011-capture.md)                   | capture                                | Record mic and system audio to the audio buffer                                            | capture                                                     | `pw-record`                                 |
| capture      | [0011](0011-capture.md)                   | retention                              | Delete expired audio                                                                       | command                                                     |                                             |
| speech       | [0012](0012-speech.md)                    | segmentation                           | Cut ambient audio into utterances                                                          | pipeline                                                    | Silero VAD                                  |
| speech       | [0012](0012-speech.md)                    | transcription                          | Turn utterances into text; one worker per ASR backend                                      | pipeline                                                    | whisper-server, Silero VAD                  |
| speech       | [0012](0012-speech.md)                    | cleanup                                | Fix ASR text with an LLM and the glossary                                                  | pipeline                                                    | llama-server                                |
| speech       | [0022](0022-dictation-asr.md)             | parakeet                               | Serve CPU speech-to-text for dictation, on the inference host only                         | pipeline                                                    | `onnx-asr`, Parakeet TDT 0.6B v2            |
| inference    | [0023](0023-inference-servers.md)         | servers                                | Pin, build and run whisper-server and llama-server on the inference host                   | command; units `odsod-daemon-whisper`, `odsod-daemon-llama` | `cmake`, HIP, whisper.cpp, llama.cpp        |
| dictation    | [0013](0013-dictation.md)                 | dictation                              | The dictation loop: meeting mute, utterance, clipboard                                     | session                                                     | keys socket, `pactl`, `wl-copy`             |
| dictation    | [0013](0013-dictation.md)                 | unmute-stale (folder `unmute_stale`)   | Unmute streams left muted                                                                  | command                                                     | `pactl`                                     |
| signals      | [0014](0014-signals.md)                   | signals                                | Meeting and speaker events from the browser                                                | pipeline                                                    | Chrome DevTools Protocol                    |
| transcript   | [0015](0015-transcript.md)                | transcript                             | Sole writer of the daily transcript (live pass)                                            | pipeline                                                    |                                             |
| transcript   | [0015](0015-transcript.md)                | note, pin                              | Owner events in the transcript                                                             | command                                                     |                                             |
| interactions | [0016](0016-interactions.md)              | interactions                           | Sole writer of interactions: boundaries, then documents (batch pass)                       | pipeline                                                    | llama-server                                |
| publishing   | [0017](0017-publishing.md)                | publish                                | Copy finished documents to configured targets                                              | pipeline                                                    |                                             |
| control      | [0018](0018-control.md)                   | tray                                   | Tray icon: mode and health; pause and resume                                               | tray                                                        | PySide6, `systemctl`                        |
| control      | [0018](0018-control.md)                   | health, status, pause, resume          | Health state from systemd and health files; pause and resume recording                     | command                                                     | `systemctl`                                 |
| control      | [0018](0018-control.md)                   | notify-failed (folder `notify_failed`) | Notify a failed unit                                                                       | command                                                     | `notify-send`                               |
| install      | [0006](0006-installation.md)              | install                                | Write and enable the units and timers; build and install the keys service                  | command                                                     | `systemctl`, `gcc`                          |
| install      | [0006](0006-installation.md)              | version                                | Print the installed commit                                                                 | command                                                     |                                             |
| bench        | [0019](0019-bench.md)                     | bench                                  | Score setups against accepted references                                                   | command                                                     | jiwer                                       |

- The runtime subsystem (`lib/`, `services/`, `cli.py`) has no components;
  [ADR-0010](0010-contracts-and-runtime.md) holds its design.

### Later

- **Diarization.** pyannote on the CPU, per host, as an optional extra. It
  names voices outside meetings ("Speaker 1", "Speaker 2") and splits
  overlapping speakers ([WhisperX](../research/whisperx.md)). Deferred from
  version 1 (owner decision, 2026-11-23): it brings torch, a Hugging Face
  token, a model download and hours of CPU on laptops. Adopt it per host when
  bench data shows the host can keep up.
- **Live shadow backends**, if offline bench runs are not enough.
- **Chapters** in long interaction documents, if pins are not enough for
  the brain vault agent.

## Alternatives considered

### Go for always-on parts, Python for ML

- A single static binary and low memory, but two toolchains, file helpers in
  two languages, and half-measures in Go where Python has the real tool (an
  energy VAD instead of Silero).
- Rejected.

### Python 3.15

- Newest, but onnxruntime has no wheels for it yet.
- Rejected for now. Move when the wheels exist.

### `silero-vad` package

- Official, but requires torch in the always-on pipeline.
- Rejected: the ONNX model on `onnxruntime` does the same with far less
  memory.

### Second ASR pass in the batch pass

- Might fix pass 1 errors, but doubles GPU time on the shared host.
- Deferred until bench data shows it helps.

### Type the text instead of pasting it

- `ydotool type` scrambles non-US layouts such as Swedish, and a killed
  `ydotool type` leaves a key stuck ([VOXD](../research/voxd.md)). `wtype`
  does not work on KDE, which has no virtual keyboard protocol
  ([Handy](../research/handy.md)).
- Rejected: paste works on every layout and for all Unicode.

### Mute a virtual meeting mic

- The meeting app would use a virtual mic that dictation mutes.
- Rejected: the owner must route every meeting app to it, and something must
  create it. Muting the apps' capture streams needs no setup.

### Mix mic and system audio into one track

- Simpler capture, but loses "owner" versus "others" for free
  ([Meetily](../research/meetily.md)).
- Rejected.

### Fixed-time chunks without VAD

- Cuts mid-sentence ([hyprwhspr](../research/hyprwhspr.md)).
- Rejected.

### Interaction boundaries in segmentation

- Segmentation already sees the silence.
- Rejected: boundaries are meeting rules that the owner tunes, not signal
  processing. Utterance times give the same silence without audio.

### Echo cancellation as the only mic channel

- Removes echo before ASR, but distorts the owner's speech when both sides
  talk, and the raw audio is gone.
- Rejected: raw `mic` stays. A `mic-ec` channel beside it is deferred
  ([ADR-0011](0011-capture.md)).

## Consequences

- Two toolchains, Python and C. The C part is one small service.
- Each always-on Python service uses on the order of 100 MB of memory.
- PySide6 is a large dependency, only for the tray icon. It runs in its own
  unit, so it never shares a process with dictation.
- No secrets, no Hugging Face token and no model download in version 1.
- Dictation needs the keys service and an inference host. Without them, Left
  Alt is a plain Alt, the tray shows why, and the rest of the system runs
  on.
- In version 1, documents name meeting speakers from the browser and call
  other voices "Others". Separate unnamed voices need diarization (Later).
- The meeting mute relies on how meeting apps react to a muted capture stream.
  Test it with Meet and Teams before dictation ships.
- The existing Go code is a reference for porting until the Python version
  replaces it.
