# Vibe Typer

- Product: https://vibetyper.com, Linux AppImage `1.6.5` (studied 2026-11-23)
- License: proprietary, closed source. Stack: Rust with Tauri (GTK, WebKit),
  workspace crates `vt-audio`, `vt-backend`, `vt-core`, `vt-hotkey`,
  `vt-platform`.
- Method: the AppImage squashfs was unpacked with 7z, without running it.
  Findings come from `strings` on `usr/bin/vibe-typer`: Rust source paths,
  crate paths, log and error messages (codes such as `E-MUT-01`), D-Bus names
  and embedded scripts. There are no line citations. Logic between the strings
  is inferred and marked as such.

## Scope

- Hold-to-talk and toggle dictation for macOS, Windows and Linux (X11,
  Wayland: GNOME, KDE, COSMIC, sway, Hyprland).
- No meeting recording.
- Paid account. Transcription and AI post-processing run in the vendor cloud.

## Architecture (processes, services, IPC, state)

- One Tauri process. Source modules (from paths): `src-tauri/src/recording/`
  (`capture`, `mute`, `focus`, `inserter`, `processor`, `retry`, `selection`,
  `state`), `indicator/`, `tray.rs`, `hotkeys.rs`, `wayland_setup.rs`.
- Platform code sits in `crates/vt-platform/src/linux/`: `audio.rs`,
  `focused_app/{kde,gnome,cosmic}.rs`, `remote_desktop.rs`, `uinput.rs`,
  `wayland_clipboard.rs`, `layout/kde.rs`, `atspi.rs`.
- Inside an AppImage it moves its mount server into its own systemd scope
  (`StartTransientUnit`, "Moved the mount server into its own scope").

## Audio capture (API, rate, buffering, system audio)

- A git fork of `cpal` with ALSA and PulseAudio hosts (`src/host/alsa/`,
  `src/host/pulse`) for the mic, with its own resampler
  (`vt-audio/src/resample.rs`).
- The mic is chosen in settings ("Default System Microphone").
- Local buffer with a cap: "Recording reached maximum length for local buffer;
  later audio not kept locally [E-AUD-12]".
- Stall detection: "Mic stopped delivering audio mid-recording [E-AUD-01]".
- No system audio capture.

## VAD and segmentation

- `vt-core/src/audio/gate.rs` exists, so there is some audio gate. Its logic
  is not visible in the strings.
- "Recording stopped with no audio captured [E-AUD-13]" ends empty takes.

## ASR (backends, models, language handling, prompts, custom vocabulary)

- Cloud: `https://api.vibetyper.com`, `vt-backend/src/transcription.rs`. A
  "Live upload stalled before stop" message suggests audio streams up during
  the recording.
- Language setting with auto detection and "favorite languages".
- Custom dictionary (`vt-core/src/dictionary.rs`).

## Post-processing (LLM cleanup, prompts, glossary, replacements)

- Cloud endpoint `/api/ai/process-ai`. Tone presets: formal, casual, very
  casual (`vt-core/src/tone.rs`).
- Learns corrections: `correction/observer.rs`, `word_diff.rs` and
  `learning.rs` watch the owner edit inserted text (through AT-SPI) and suggest
  dictionary entries ("dictionary-suggestion-timeout").

## Hotkeys on Wayland/KDE (mechanism, hold vs toggle)

- Backends in `vt-hotkey/src/backend/`: `evdev`, `portal` (GlobalShortcuts,
  `ashpd`), `gnome_shell` (own GNOME Shell extension), `compositor` (sway and
  Hyprland binds), plus X11.
- `service/swallow.rs`: keeps the hotkey from also reaching the focused app.
  Warning when it fails: "the hotkey also reaches the focused app [E-HK-01]".
- Separate hotkeys for record, toggle, cancel and re-paste.
- Setup for evdev and uinput runs once through `pkexec`. It writes
  `/etc/udev/rules.d/60-vibetyper-input.rules` and
  `99-vibetyper-uinput.rules` with `TAG+="uaccess"` for `uinput` and
  `event*`, then runs `modprobe uinput` and `udevadm trigger`. The logged-in
  user then gets access without the `input` group.

## Text delivery (paste vs type, tools, clipboard restore, per-app, unicode)

- Paste and type modes. Type mode falls back to paste when the keyboard
  layout cannot type the text ("so pasting instead [E-INS-05]").
- Keys go out through a uinput device or the RemoteDesktop portal
  (`NotifyKeyboardKeycode`, with `restore_token` and `persist_mode` so the
  consent dialog shows once).
- Clipboard through `wl-clipboard-rs` on Wayland. It backs up the clipboard
  and restores it after insertion ("Couldn't restore the clipboard after
  inserting [E-INS-11]").
- Per-app paste key: an embedded list of terminals (Konsole, Yakuake, WezTerm,
  xterm, Tilix and others, plus Claude Code) gets a different chord.
- Focus: it records the target app at recording start. Before it inserts, it
  focuses that app again ("Couldn't refocus the target app before inserting
  [E-FOC-03]").
- KDE focused app: loads a KWin script through `org.kde.kwin.Scripting`. The
  script reads `workspace.activeWindow` (`resourceClass`, `pid`, `caption`)
  and calls back over D-Bus to its own interface `com.vibetyper.KWinTarget`.

## UI feedback (overlay, tray, notifications)

- Floating recording indicator with a waveform, with a separate wlroots
  path (`indicator/wlroots.rs`).
- Tray icon (Ayatana AppIndicator). Notifications through
  `org.freedesktop.Notifications`.

## Meeting features (system audio, mic mute, diarization, speakers, summaries)

No meeting features. The one related feature is **"Mute other apps while
recording"** (config key `muteSystemAudioDuringRecording`), in
`src-tauri/src/recording/mute.rs`:

- It mutes **playback**, meaning other apps' sound. It does not mute any
  mic.
- It talks to PipeWire through the PulseAudio native protocol, in process,
  with the `pulseaudio-rs` crate. It runs no `pactl` or `wpctl`.
- At record start it lists playback streams (sink inputs) and logs each one as
  `stream #N (target, vol, muted, corked)`. It reads `application.name`,
  `application.process.id` and `media.role`. It mutes streams with
  `SetSinkInputMute`. Inferred: it skips its own streams and streams that are
  already muted.
- It remembers what it muted and restores only that. A stream that ends during
  the recording is a known case: "Couldn't unmute an app whose stream ended
  while recording [E-MUT-06]".
- There is also a speaker volume path: "Speaker restore skipped: previous
  volume unknown [E-MUT-03]". Inferred: the fallback, or the macOS and Windows
  version.
- Quit restores the mute state within a 2 s budget ("Timed out restoring
  speaker volume at quit [E-MUT-05]"). Quit during a change warns: "Speakers
  may stay muted: quit during a mute change [E-MUT-04]".
- A failure does not stop the recording. The owner sees: "Could not mute your
  speakers. Please try again or turn off automatic speaker muting in
  Settings."
- The protocol client also has `SetSourceOutputMute` and `SetSourceMute`.
  There is no sign that Vibe Typer uses them.

## Data and storage

- History of transcriptions with re-transcribe and re-paste.
- Login session in the Secret Service keyring (`keyring-rs`,
  `vt-backend/src/session_store.rs`).
- Settings sync to the vendor account (`config/sync.rs`, `prefs_sync.rs`).

## Packaging and install

- AppImage with linuxdeploy GTK and GStreamer plugins. Self-updater
  (`tauri-plugin-updater`, `cdn.vibetyper.com/releases`).
- Autostart through an XDG autostart entry (`X-KDE-autostart-after=panel`).

## Tests and benchmarks

- Not visible in a binary.

## Known pitfalls (top Linux/Wayland issues from the tracker)

- No public tracker. Its error codes show the cases it handles:
  - hotkey also reaches the focused app (`E-HK-01`)
  - the target app runs as administrator (`E-HK-15`, `E-INS-02`)
  - the X11 clipboard owner does not answer (`E-PLT-07`, `E-PLT-08`)
  - the keyboard layout cannot type the text (`E-PLT-09`)
  - the mic stops mid-recording (`E-AUD-01`)
  - speakers stay muted after quit (`E-MUT-04`)

## Ideas for the recorder

- **Mute the browser's capture stream, not a virtual mic.** The PulseAudio
  protocol has `SetSourceOutputMute`. While the owner dictates, `mute` could
  mute only the meeting browser's record stream (`pactl
  set-source-output-mute`), matched by `application.process.id` or
  `application.name`. The meeting hears nothing, and `capture` still reads the
  physical mic node. This could remove the virtual meeting mic from ADR-0005.
  Test it with Meet first: Meet may react to a silent stream.
- **Restore only what the recorder changed.** Remember each stream it muted.
  Skip streams that were muted before. Handle streams that end during
  dictation.
- **Clear stale mutes at start.** A crash between mute and unmute leaves the
  meeting deaf to the owner. On start, `odsod-daemon-session` unmutes any stream
  it marked. Restore on SIGTERM with a short time budget.
- **Mute fails open.** Dictation continues and the tray shows a warning.
- **Optional playback mute while dictating.** It keeps speaker sound out of
  the dictation audio when the owner has no headset. This ties into the echo
  open question in [alternatives.md](alternatives.md).
- **udev `uaccess` rules instead of the `input` group.** Access follows the
  active seat, and no re-login is needed. Compare with ADR-0006.
- **KWin script for the active window.** It works where the KWin D-Bus API has
  no active window call. Not needed if delivery uses Shift+Insert for all apps.
