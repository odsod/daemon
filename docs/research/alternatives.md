# Alternatives: open-source dictation and meeting tools

> Point-in-time study (2026-11-22 and 2026-11-23). ADR-0005 to ADR-0009
> supersede the decisions and names here. For example, the keys service
> replaced `ydotool`, and `reprocessing` is now `interactions`. Read the
> ADRs for the current design.

Source study of eight open-source tools, done on 2026-11-22, plus the
closed-source Vibe Typer, studied from its binary on 2026-11-23. Each tool has
a note in this directory. Every claim in an open-source note cites a file and
line at the studied commit, or an issue. Three citations per open-source tool
were checked against the source.

## Tools studied

| Tool                        | Why                                                            |
| --------------------------- | -------------------------------------------------------------- |
| [OpenWhispr](openwhispr.md) | Popular dictation + meeting app with deep KDE Wayland handling |
| [VOXD](voxd.md)             | Python dictation tool for Linux                                |
| [Handy](handy.md)           | Most popular local dictation app                               |
| [Voxtype](voxtype.md)       | Most popular Linux tool with dictation and a meeting mode      |
| [YazSes](yazses.md)         | Python, hold Right Alt via evdev, live + batch meeting pass    |
| [hyprwhspr](hyprwhspr.md)   | Python, systemd user service, separate mic and monitor capture |
| [Meetily](meetily.md)       | Most popular local meeting recorder                            |
| [WhisperX](whisperx.md)     | Reference pipeline for VAD, batching and pyannote diarization  |
| [Vibe Typer](vibetyper.md)  | Closed source; studied later for its "mute other apps" feature |

Skipped after the landscape scan: whisrs and TuxTalk (small), Vocalinux
(dictation only), Speech Note (toggle-only portal shortcuts), Buzz, Anarlog,
nerd-dictation, whisper-writer and macOS-only tools.

## Comparison

| Tool       | Stack        | Scope            | Capture                                    | VAD                                            | ASR                                    | Cleanup                                    |
| ---------- | ------------ | ---------------- | ------------------------------------------ | ---------------------------------------------- | -------------------------------------- | ------------------------------------------ |
| OpenWhispr | Electron, C  | Both             | Browser mic; C helper on PipeWire for sink | Silero in whisper-server, off for dictation    | whisper-server, Parakeet, cloud        | llama-server or cloud, hardened prompt     |
| VOXD       | Python, Qt6  | Dictation        | PortAudio                                  | Energy (continuous mode only)                  | `whisper-cli` per utterance            | Optional LLM, fixed prompt slots           |
| Handy      | Rust, Tauri  | Dictation        | Mic at 16 kHz                              | Silero 0.3 + smoothing; pause-midpoint chunker | transcribe-cpp, many model families    | Optional LLM, hardened prompt, JSON schema |
| Voxtype    | Rust         | Both             | cpal mic; `parec` monitor for meetings     | Energy default, Silero optional                | whisper-rs + 8 engines                 | External command or LLM; phonetic fixer    |
| YazSes     | Python       | Both (room mic)  | PortAudio                                  | Energy gate + Silero ONNX presence gate 0.3    | faster-whisper (CPU), Parakeet         | Filters + local LLM with output guards     |
| hyprwhspr  | Python       | Dictation + util | PortAudio; two `parec` for meetings        | RMS silence                                    | 8 backends (whisper.cpp, onnx-asr ...) | Hook only                                  |
| Meetily    | Rust, Tauri  | Meetings         | libpulse mic + monitor, mixed to mono      | Silero 0.5 / 0.35                              | whisper-rs, Parakeet                   | None per utterance; LLM summaries          |
| WhisperX   | Python (lib) | Batch pipeline   | Whole file via ffmpeg                      | pyannote or Silero, merge + min-cut            | faster-whisper, batched                | Forced alignment (wav2vec2)                |

| Tool       | Hotkey on KDE Wayland                        | Delivery on KDE Wayland                               | Meeting features                                 | Storage                          |
| ---------- | -------------------------------------------- | ----------------------------------------------------- | ------------------------------------------------ | -------------------------------- |
| OpenWhispr | KGlobalAccel; evdev helper for modifier keys | Clipboard + `Shift+Insert` via portal, then `ydotool` | Mic + sink, WebRTC AEC, pyannote diarization     | SQLite, WebM files, vector index |
| VOXD       | DE shortcut runs a client; toggle only       | `ydotool type`; optional paste; no restore            | None                                             | YAML, temp WAVs                  |
| Handy      | Compositor binding to CLI or signal; toggle  | Clipboard + PRIMARY, `Shift+Insert`, restore          | None; mutes output while recording               | SQLite, WAVs                     |
| Voxtype    | Compositor toggle; evdev for hold            | Typing chain or paste; waits for modifier release     | Mic + monitor, PipeWire echo-cancel, summaries   | Config + runtime files           |
| YazSes     | evdev, hold Right Alt                        | `ydotool type` with Unicode checks; clipboard backup  | Live JSONL pass + batch pass + diarization extra | One directory per meeting        |
| hyprwhspr  | evdev hold, optional grab                    | Clipboard + paste chord, private `ydotoold`           | Separate mic and monitor, fixed 300 s chunks     | JSON config, tmpfs runtime       |
| Meetily    | n/a                                          | n/a                                                   | Mixed track; diarization only in paid edition    | SQLite, 30 s MP4 checkpoints     |
| WhisperX   | n/a                                          | n/a                                                   | pyannote community-1, overlap speaker assignment | Output files only                |

No tool records always-on. No tool mutes the meeting mic while dictating.
These two parts of our design have no prior art in this set.

## Findings mapped to ADRs

### Confirms our design

- **Hold-Alt needs evdev.** KWin sends press and release of a modifier-only
  shortcut together, after the key goes up
  ([OpenWhispr](openwhispr.md#hotkeys-on-waylandkde-mechanism-hold-vs-toggle)).
  Voxtype documents the same gap. YazSes and hyprwhspr use evdev for hold.
  Affects: ADR-0005 `dictation` (`keys`).
- **Paste, never type.** `ydotool type` scrambles Swedish and other non-US
  layouts, and a killed `ydotool type` leaves a key stuck
  ([VOXD](voxd.md#known-pitfalls-top-linuxwayland-issues-from-the-tracker)).
  hyprwhspr deprecated typing. OpenWhispr always pastes on Linux.
  Affects: ADR-0005 `dictation` (`delivery`).
- **`wtype` does not work on KDE.** KWin has no virtual-keyboard protocol
  ([Handy](handy.md#text-delivery-paste-vs-type-tools-clipboard-restore-per-app-unicode)).
  Our choice of `ydotool` holds.
- **Silero as ONNX on onnxruntime.** The `silero-vad` package pulls torch and
  CUDA, about 3 GB ([YazSes](yazses.md#ideas-for-the-daemon)).
  Affects: ADR-0005 libraries.
- **Keep mic and system audio apart.** Meetily mixes them into one track and
  loses "you" versus "others" for free
  ([Meetily](meetily.md#ideas-for-the-daemon)). hyprwhspr keeps them apart.
  Affects: ADR-0003 channels.
- **Talk to PipeWire, not PortAudio or ALSA.** hyprwhspr carries about 2,000
  lines of PortAudio workarounds. Meetily left cpal because ALSA probing made
  pops. VOXD falls back to 48 kHz without resampling.
  Affects: ADR-0005 `capture` (`pw-record`).
- **Keep the stream open.** Voxtype loses the first 0.7 s when PipeWire wakes
  a suspended mic on key press. Always-on capture with pre-roll avoids this.
  Affects: ADR-0002 "Keep the audio".
- **Cut long speech at the lowest speech score.** WhisperX cuts in the second
  half of a long region at the lowest VAD score. Handy cuts at pause
  midpoints. Affects: ADR-0005 `segmentation` (forced cuts).
- **No conditioning on previous text.** WhisperX turns it off by default.
  YazSes measured repetition loops on `large-v3` with it on. One utterance per
  request already gives this. Affects: ADR-0005 `transcription`.
- **Resident inference server.** VOXD starts `whisper-cli` per utterance and
  pays the model load each time. Handy reports a 70 s reload after idle
  unload on Vulkan. Affects: inference host, outside the daemon.
- **Diarize offline, assign by overlap.** WhisperX runs pyannote
  `speaker-diarization-community-1` and assigns speakers by largest time
  overlap. Affects: ADR-0005 `reprocessing` and `diarize`.
- **systemd user units.** hyprwhspr, YazSes and VOXD all ship one.
  Affects: ADR-0004.
- **Tray only, no overlay window.** A normal Qt or GTK window steals focus on
  Wayland and eats the dictated text (YazSes, Handy). Affects: ADR-0005 `tray`.
- **Live pass, then batch pass.** YazSes writes `live.jsonl` during a meeting
  and runs a batch pass after it, with a quality check that compares the two.
  Affects: ADR-0002 "Fast first, accurate later".

### Adopt

- **`Shift+Insert` as the one paste key, with text in both CLIPBOARD and
  PRIMARY.** It works in GUI apps, Konsole and terminal agents, and on every
  layout. `Ctrl+V` fails on non-Latin layouts through the portal, and
  Konsole drops a simulated `Ctrl+Shift+V` (OpenWhispr, Handy). This can
  remove the KWin window-class lookup from `delivery`.
  Affects: ADR-0005 `dictation` (`delivery`).
- **Wait until Alt is physically up before the paste chord.** Poll
  `EVIOCGKEY` with a timeout (OpenWhispr up to 1.5 s, Voxtype `ModifierGuard`).
  Handy has an open bug where the held modifier joins the paste.
  Affects: `delivery`.
- **Keep dictation out of clipboard history.** Use `wl-copy --sensitive` or
  the KDE password-manager hint, so Klipper does not store each dictation
  (Handy #2072, Voxtype #749). Pass `--type text/plain;charset=utf-8`
  (hyprwhspr). Affects: `delivery`.
- **Restore the clipboard only if it still holds our text, and not too soon.**
  Handy waits 500 ms on Linux, OpenWhispr 1200 ms on KDE Wayland. Restoring
  too soon pastes the old content (Handy #502). Affects: `delivery`.
- **Run `ydotoold` on a private socket with mode 0600** as the owner, not a
  shared root daemon (hyprwhspr, VOXD). Affects: ADR-0006, `delivery`.
- **evdev rules for `keys`:** read all real keyboards, skip virtual devices
  (our own uinput, `ydotool`), handle hotplug, never swallow a modifier
  release, and do not start dictation when another modifier is held
  (`Alt+Tab`) (YazSes, hyprwhspr). Affects: `keys`.
- **A Silero presence gate on dictation, not a VAD cut.** OpenWhispr turns
  VAD off for dictation, because cutting pauses leaves Whisper decoding near
  silence and reciting the glossary (#1454). YazSes gates at threshold 0.3 so
  one-word dictations survive. Affects: ADR-0005 `transcription`.
- **Anti-hallucination decoder thresholds for dictation only.** OpenWhispr
  sends `entropy_thold=2.8` and `logprob_thold=-1.25` and reports
  hallucinated tails fell from 2.25% to 0.06% over 4,814 dictations. It keeps
  defaults on meeting audio to avoid temperature-fallback re-decodes.
  Affects: `transcription`. Bench data should confirm.
- **Glossary in the Whisper prompt, highest priority at the tail.** Whisper
  reads about 223 prompt tokens and keeps the tail (OpenWhispr, Voxtype).
  Affects: `transcription`.
- **Drop glossary echoes and known phantoms.** Discard text that recites
  three or more glossary terms in prompt order (OpenWhispr, Handy), and known
  silence phrases such as "thanks for watching" (YazSes, hyprwhspr).
  Affects: `cleanup` (empty output keeps the ID done).
- **Harden the cleanup prompt.** Wrap the text in `<transcript>` tags, state
  that the speaker never talks to the model, never answer questions in the
  text, end with an output anchor, and strip `<think>` blocks (OpenWhispr,
  Handy, Meetily). Affects: `cleanup` prompt template.
- **Guard the cleanup output.** Reject output with a length ratio outside
  0.5 to 2.0, or that drops numbers or proper nouns, and fall back to the raw
  text (YazSes). Affects: `cleanup`.
- **Silero starting values:** threshold 0.5, negative threshold 0.35,
  pre-pad 300 ms, post-pad 400 ms, minimum speech 250 ms, with a shorter
  end-of-speech wait live than in batch (Meetily, Handy). Affects:
  `segmentation` defaults. Bench data tunes them.

### Reject

- **Typing tools for delivery** (`ydotool type`, `wtype`): layouts, Unicode,
  stuck keys.
- **Forcing XWayland, `xdotool` or AT-SPI on KDE Wayland** (OpenWhispr): cannot
  read the Wayland clipboard, crashes on placeholders, leaks file
  descriptors.
- **Mixing channels before ASR** (Meetily).
- **Fixed-time chunks without VAD** (hyprwhspr, 300 s): cuts mid-sentence.
- **PipeWire role `Communication` on sink capture** (OpenWhispr #2001): Bluetooth
  headsets record silence.
- **Small capture fragments** (Meetily #433): a 20 ms fragment can shrink the
  PipeWire quantum and glitch the live call. Use the default latency.
- **Forced alignment in the live pass** (WhisperX): a second model and more
  latency for nothing dictation needs.
- **A database for history** (all GUI apps use SQLite): files stay the
  interface (ADR-0003).

### Open questions

- **Bluetooth headset mic.** Opening a Bluetooth headset mic switches it from
  A2DP to HFP, and the stream can stall or go silent (Handy #2387, #2446).
  Always-on capture of that mic would keep the headset in low-quality mode all
  day. Should `capture` record only the built-in mic, and follow the
  headset mic only during meetings? Affects: ADR-0005 `capture`.
- **Echo of system audio in the mic.** Without a headset, the mic hears the
  meeting. Voxtype runs PipeWire `module-echo-cancel` with `monitor.mode`.
  OpenWhispr runs WebRTC AEC and a leak detector. Do we need echo handling,
  or is text dedup in `reprocessing` enough? Affects: `capture`,
  `reprocessing`.
- **Paste through the RemoteDesktop portal instead of `ydotool`.** OpenWhispr
  tries the portal first on KDE, with a restore token, and needs no daemon.
  It costs a one-time consent dialog. Affects: `delivery`, ADR-0006.
- **English prompt on Swedish audio.** hyprwhspr detects the language first
  and picks a prompt per language. This interacts with our code-switching
  strategy. Affects: `transcription`, bench.
- **Separate language ID.** Handy runs an ECAPA language-ID model on the
  first seconds of speech, limited to the owner's languages. A candidate
  strategy for the bench. Affects: `transcription`.

## Ideas by component

- **capture:** `pw-record` per channel; target nodes by name; default
  latency; no `Communication` role; detect digital silence (all zeros) as a
  muted mic and report it in health (Handy).
- **segmentation:** Silero starting values above; forced cut at the lowest
  score in the second half; separate live and batch end-of-speech waits.
- **transcription:** presence gate for dictation; dictation-only decoder
  thresholds; glossary at the prompt tail within about 223 tokens;
  `--max-len` instead of `--no-timestamps` on whisper.cpp to avoid dropped
  audio (OpenWhispr).
- **cleanup:** hardened prompt; echo and phantom filters; output guards with
  raw fallback.
- **dictation:** evdev rules; wait for Alt release; `Shift+Insert` with
  CLIPBOARD and PRIMARY; sensitive clipboard writes; guarded restore after
  about 500 ms; private `ydotoold` socket.
- **tray:** StatusNotifierItem with states (Voxtype, hyprwhspr, Handy); no
  overlay window.
- **reprocessing:** pyannote community-1 offline; assign speakers by largest
  overlap; compare batch output with live text to catch decode loops
  (YazSes).
- **bench:** OpenWhispr and Handy keep eval scripts and per-model accuracy
  data next to the code; VOXD logs per-run latency to CSV. Our stored audio
  and results give the same with real speech.
