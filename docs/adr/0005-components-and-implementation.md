# ADR-0005: Components and implementation

## Status

Proposed

## Date

2026-11-23

## Context

- [ADR-0002](0002-high-level-architecture.md) sets the capabilities and
  principles. [ADR-0003](0003-filesystem-interface.md) defines the files,
  [ADR-0004](0004-orchestration-with-systemd.md) the services and
  [ADR-0007](0007-keys-daemon.md) the keys daemon.
- Agents need to know exactly which components exist, what each one does, and
  how to build it: language, libraries, tools and code layout.
- The best speech and audio tools (Silero VAD, pyannote, language ID, ASR
  toolkits, WER) are Python libraries.
- A source study of nine dictation and meeting tools
  ([alternatives.md](../research/alternatives.md)) gave the evidence for the
  rules below. Each rule names its source.
- The `machine` repo turns off WirePlumber's switch to the Bluetooth headset
  profile. A headset offers only its stereo sink and no mic, so capture never
  forces a headset into low-quality call mode.
- This ADR is longer than one page, because it covers every component. Each
  component ADR can supersede its section.

## Decision

### Language and tooling

- **Python 3.14** for all code except the keys daemon, pinned in
  `.python-version`. Move to the next Python version when every runtime
  dependency ships wheels for it. (Python 3.15 is out, but onnxruntime has no
  3.15 wheels yet.)
- **C** for the keys daemon (ADR-0007), built with `gcc -Wall -Wextra -Werror`.
- **uv** manages Python, dependencies (`uv.lock`) and installs. uv comes from
  mise.
- **ruff** for lint and format. **pyright** in strict mode for types.
  **pytest** for tests. **import-linter** enforces the module boundaries below.
- `mise run build` runs all of them and compiles the keys daemon. It is the CI
  gate.

### Libraries

| Need                                   | Library                                       |
| -------------------------------------- | --------------------------------------------- |
| CLI                                    | `typer`                                       |
| Config and stream records              | `pydantic` v2                                 |
| Concurrency                            | `asyncio` with `TaskGroup`                    |
| HTTP (whisper-server, llama-server)    | `httpx` (async)                               |
| Chrome DevTools Protocol               | `websockets`                                  |
| File watching                          | `watchfiles`                                  |
| Audio arrays                           | `numpy`                                       |
| VAD                                    | Silero VAD model (ONNX) on `onnxruntime`, CPU |
| Tray icon                              | `PySide6` (`QSystemTrayIcon`, `QtAsyncio`)    |
| D-Bus (KWin, KGlobalAccel)             | `dbus-fast` (asyncio)                         |
| Prompt templates                       | `jinja2`                                      |
| Diarization (optional extra `diarize`) | `pyannote.audio`                              |
| Benchmark (optional extra `bench`)     | `jiwer`                                       |
| Logging                                | stdlib `logging` to stdout (journald)         |

- The `silero-vad` package requires torch and CUDA libraries, about 3 GB
  ([YazSes](../research/yazses.md)). The system ships the Silero ONNX model
  file and runs it on `onnxruntime` directly.
- torch comes only with the `diarize` extra. It never loads in a long-running
  daemon.
- The keys daemon uses only libc and Linux headers.
- A new runtime dependency needs an ADR.

### Code layout

```
pyproject.toml, uv.lock, .python-version
keys/                 # ADR-0007: odsod-daemon-keys.c, unit template
kwin/                 # ADR-0008: KWin script package (metadata.json, main.js)
src/odsod_daemon/
  cli.py              # typer app: one subcommand per component and command
  config.py           # pydantic config models, meeting profiles
  contracts/          # pydantic models for every stream record, document, socket and D-Bus message
  files/              # ADR-0003: paths, streams, documents, audio, pending, watch
  clients/            # wire clients: whisper, llm, cdp, keys socket. No business logic.
  health/             # unit states, audio freshness, backlog (tray, status)
  components/         # one package per Python component (table below)
  systemd/            # unit templates, sd_notify, install
  prompts/            # jinja2 templates
  models/             # Silero VAD ONNX file
tests/                # mirrors src/odsod_daemon; file-in, file-out fixtures
```

- **Boundaries (import-linter):** a component imports only `contracts`,
  `files`, `clients`, `config` and `health`, never another component.
  Components talk only through files, the keys socket and D-Bus.
- **`health`** is a shared module, not a component: unit states from systemd,
  audio freshness and backlog from files. `tray` and `odsodctl status` use
  it.
- **Contracts are code.** Each stream in ADR-0003, each socket message in
  ADR-0007 and each D-Bus message in ADR-0008 has one pydantic model in `contracts/`. A change to a model is a
  change to the interface.
- **Each component** exposes one async `run(config)` entry point and can run
  alone: `odsodctl run <component>`.
- **One CLI, `odsodctl`,** for the owner and for the units. The units start
  each daemon with `odsodctl run <daemon>`. The keys daemon is its own binary,
  `odsod-daemon-keys`.
- **Tests** feed input files to a component and compare output files. A fake
  HTTP server stands in for the inference host. A fake keys socket stands in
  for the keys daemon.

### Components

![Architecture](../diagrams/high-level-architecture.svg)

Diagram source: [`high-level-architecture.py`](../diagrams/high-level-architecture.py).
Regenerate with
`uv run docs/diagrams/high-level-architecture.py docs/diagrams/high-level-architecture.svg`.

| Component         | Responsibility                                             | Daemon or command | Main tools                       |
| ----------------- | ---------------------------------------------------------- | ----------------- | -------------------------------- |
| keys              | Remap keys; dictation key; paste keys                      | keys              | `evdev` and `uinput` ioctls (C)  |
| capture           | Record mic and system audio to the audio buffer            | capture           | `pw-record`                      |
| dictation         | The dictation loop: meeting mute, utterance, clipboard     | session           | keys socket, `pactl`, `wl-copy`  |
| tray              | Tray icon: mode and health; pause and resume               | session           | PySide6, `systemctl`             |
| shortcuts         | Register global shortcuts; launch apps for the KWin script | session           | `dbus-fast`, `systemd-run`       |
| segmentation      | Cut ambient audio into utterances; detect interaction ends | pipeline          | Silero VAD                       |
| transcription     | Turn utterances into text; one worker per ASR backend      | pipeline          | whisper-server, Silero VAD       |
| cleanup           | Fix ASR text with an LLM and the glossary                  | pipeline          | llama-server                     |
| transcript        | Sole writer of the daily transcript                        | pipeline          |                                  |
| signals           | Meeting and speaker events from the browser                | pipeline          | Chrome DevTools Protocol         |
| reprocessing      | Diarize, name speakers, summarize finished interactions    | pipeline          | `odsodctl diarize`, llama-server |
| publish           | Copy finished documents to configured targets              | pipeline          |                                  |
| note, pin, status | Owner events; health view                                  | command           | `systemctl`                      |
| install           | Write and enable the units; build keys; install KWin script | command          | `systemctl`, `gcc`, `kpackagetool6` |
| models            | Download models at install time                            | command           | Hugging Face client              |
| diarize           | Diarize one audio slice (one-shot)                         | command           | pyannote                         |
| bench             | Score backends and strategies against references           | command           | jiwer                            |
| version           | Print the installed commit                                 | command           |                                  |

### keys

- Defined in [ADR-0007](0007-keys-daemon.md).

### capture

- Runs one `pw-record --raw --rate 16000 --channels 1 --format s16` per
  channel as an asyncio subprocess. PipeWire resamples and mixes down.
- `mic` targets the physical mic by node name. `sys` targets the default
  sink's monitor.
- Sets its own stream properties (application name `odsod-daemon-capture`),
  so dictation never mutes capture.
- Uses the default PipeWire latency and no media role. A small fragment can
  shrink the graph quantum and glitch a live call
  ([Meetily](../research/meetily.md)). Role `Communication` made Bluetooth
  capture record silence ([OpenWhispr](../research/openwhispr.md)).
- Writes 100 ms blocks at the offset given by wall-clock start plus sample
  count. Pings the watchdog on each block. Deletes expired hour files.
- Flags a channel that delivers only digital zeros for a configured time, for
  `health` ([Handy](../research/handy.md)).
- **Echo:** without a headset, `mic` hears the meeting. Text dedup is the
  baseline (see `transcript` and `reprocessing`). A PipeWire
  `module-echo-cancel` source in monitor mode
  ([Voxtype](../research/voxtype.md)) is a bench experiment: config adds it
  as the extra channel `mic-ec`, never as the default source. A later ADR
  adopts it if bench data shows a gain. Echo cancellation is lossy when both
  sides talk, so raw `mic` is always kept.

### dictation

- One control loop, kept in memory, because its steps depend on each other's
  timing. Modules: `mute`, `delivery`.
- Connects to the keys socket and gets `start`, `stop` and `cancel` with key
  timestamps.
- `mute`, on `start`: mutes every capture stream on the physical mic except
  capture's own, with `pactl`. The meeting app hears nothing, and `capture`
  still records the owner.
  - Mutes only streams that were not muted already, and records them in
    `run/muted.json` before it mutes.
  - On `stop` or `cancel`: unmutes only those streams. A stream that ended
    meanwhile is not an error.
  - At start: unmutes every stream left in `run/muted.json` by a crash.
  - Fails open: if muting fails, dictation goes on and the tray warns.
  - Source: the stream-level mute design of
    [Vibe Typer](../research/vibetyper.md), applied to capture streams
    instead of playback.
- On `stop`: appends a dictation utterance (from the `start` timestamp minus
  pre-roll to the `stop` timestamp) and waits for its text in `state/text/`.
- `delivery` pastes the text
  ([OpenWhispr](../research/openwhispr.md), [Handy](../research/handy.md)):
  - Saves the current clipboard.
  - Writes the text to CLIPBOARD and PRIMARY with
    `wl-copy --sensitive --type 'text/plain;charset=utf-8'`, so the KDE
    clipboard history does not keep it.
  - Sends `paste` to the keys socket. The keys daemon sends `Shift+Insert`,
    which pastes in GUI apps and terminals, on every layout.
  - After `pasted` and about 500 ms, restores the old clipboard, but only if
    the clipboard still holds the dictated text.
- Writes its mode (idle, dictating) to `run/status.json`.

### tray

- Shows the tray icon with PySide6 on the asyncio loop (`QtAsyncio`).
- Shows the mode from `run/status.json` and health from the `health` module.
- Pause and resume run `systemctl --user stop|start odsod-daemon-capture`.
- No overlay window. A normal window steals focus on Wayland and catches the
  pasted text ([YazSes](../research/yazses.md)).
- Runs in the same daemon as `dictation`, because both need the graphical
  session. They share no code or memory, so `tray` can move to its own unit
  without code changes if it ever proves unstable.

### shortcuts

- Defined in [ADR-0008](0008-shortcuts-and-kwin-script.md).

### segmentation

- Runs Silero VAD on new audio per channel. Cuts utterances at pauses, with a
  minimum and maximum length. A forced cut goes at the lowest speech
  probability in the second half of the utterance, not at the exact limit
  ([WhisperX](../research/whisperx.md)).
- VAD settings (threshold, minimum pause, padding) are config values per
  channel. Bench data tunes them.
- Writes an interaction when silence passes the configured cutoff, the
  meeting changes or the owner pins.
- The silence cutoff is a config value, default 5 minutes. In a meeting that
  stays open for hours, it is the main way to split the meeting into
  interactions, so the owner tunes it.
- **Meeting profiles** override behavior per meeting. Config lists profiles
  matched by meeting URL (for Meet, the meeting code, such as
  `abc-defg-hij`). A profile can set the silence cutoff and later other
  settings. Example: a permanent pair-coding room gets a short cutoff, so each
  topic becomes its own interaction. With no matching profile, the defaults
  apply.

### transcription

- One worker per configured backend. Takes pending dictation first, then
  ambient, oldest first.
- Cuts the audio slice, wraps it as WAV in memory and posts it to
  whisper-server.
- Puts the glossary in the Whisper prompt, most important terms last. Whisper
  keeps only the tail of a long prompt.
- No conditioning on previous text. One utterance per request already gives
  this.
- **Dictation is not ambient.** A dictation utterance is the owner's whole key
  hold:
  - No VAD cuts inside it. Cut pauses make Whisper decode near-silence and
    recite the glossary ([OpenWhispr](../research/openwhispr.md)).
  - A Silero presence gate instead: no speech means empty text, with no
    request ([YazSes](../research/yazses.md)).
  - Stricter decoder thresholds against hallucinated tails, for dictation
    only. Bench data confirms the values.
- Shadow backends get a configured sample of utterances, for benchmark data.
- The code-switching strategy is a config choice. Bench data picks the
  default.

### cleanup

- Sends raw text with the glossary prompt to llama-server. Same order as
  transcription: dictation first.
- The prompt wraps the text in tags, states that the speaker never talks to
  the model, and forbids answers to questions in the text. Cleanup strips
  reasoning blocks from the reply ([OpenWhispr](../research/openwhispr.md),
  [Handy](../research/handy.md)).
- Writes empty text for silence hallucinations: text that recites the
  glossary, or a known phantom phrase. Empty text still marks the ID as done.
- Guards the reply: if its length is far from the input length, or it drops
  numbers or names, cleanup writes the raw text instead
  ([YazSes](../research/yazses.md)).

### transcript

- Merges cleaned text and events (notes, pins, meetings) into the daily
  transcript. Lines carry their own timestamps.
- Appends in arrival order. A dictation line can come before an older ambient
  line.
- Drops a `mic` line that repeats a `sys` line from the same time window
  (echo). The component ADR defines the match and how long to wait for the
  `sys` text.

### signals

- Polls meeting tabs over the Chrome DevTools Protocol, detects the platform,
  meeting changes, participants and the speaking indicator. Writes events.

### reprocessing

- For each finished interaction: runs `odsodctl diarize` as a subprocess
  on the audio slice, names the clusters by overlap with speaker events, and
  assigns a speaker to each pass 1 utterance by largest overlap with the turns
  ([WhisperX](../research/whisperx.md)).
- Removes echo with full context: `mic` text that repeats `sys` text.
- Then cleans up with full context and summarizes (map-reduce for long
  interactions).
- Pass 1 text is reused, not transcribed again. Bench data decides if a
  second ASR pass is worth the GPU time.
- Starts `odsodctl diarize` only on mains power: a power supply of type
  `Mains` reports `online`. A host with no `Mains` supply (the desktop) counts
  as on mains. Peripheral batteries, such as a pen, do not count. On battery,
  interactions stay pending in files and run once the host is plugged in.
- Starts it at idle priority: `nice 19` and the idle CPU and IO scheduling
  classes. It then uses only CPU that nothing else wants.

### diarize

- One-shot: audio slice in, speaker turns out (JSON). Runs pyannote
  `speaker-diarization-community-1` on the CPU. Batch work has no deadline,
  and this avoids ROCm.
- Caps torch at a configured number of threads (default 4), so one run never
  takes every core.
- Runs offline (`HF_HUB_OFFLINE=1`). `odsodctl models fetch` downloads the
  model once at install time ([ADR-0006](0006-installation.md)). Needs the
  `diarize` extra.

### publish

- Copies finished documents to targets and records each delivery.

### note, pin, status, install, models, version

- `note` and `pin` append one line to `events/user/`.
- `status` reads unit states from systemd and freshness and backlog from
  files.
- `install` writes the user units and installs the KWin script (ADR-0008).
  `install --system` builds and installs the keys daemon (ADR-0004).
- `models fetch` downloads the pyannote model with the owner's Hugging Face
  login. Silero ships in the package.
- `version` prints the installed commit (ADR-0006).

### bench

- Builds cases from stored audio and ASR results, supports review to write
  `ref.txt`, reports WER per backend, strategy and VAD setting.

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

### Second ASR pass in reprocessing

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

### Echo cancellation as the only mic channel

- Removes echo before ASR, but distorts the owner's speech when both sides
  talk, and the raw audio is gone.
- Rejected: raw `mic` stays. `mic-ec` is an experiment beside it.

## Consequences

- Two toolchains, Python and C. The C part is one small daemon.
- Each always-on Python daemon uses on the order of 100 MB of memory.
- PySide6 is a large dependency, only for the tray icon.
- The pyannote model needs a Hugging Face account and a token at install
  time. Running daemons never use it.
- Dictation needs the keys daemon. Without it, the tray shows an error and the
  rest of the system runs on.
- The meeting mute relies on how meeting apps react to a muted capture stream.
  Test it with Meet and Teams before dictation ships.
- The existing Go code is a reference for porting until the Python version
  replaces it.
