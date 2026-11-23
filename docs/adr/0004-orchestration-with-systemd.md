# ADR-0004: Orchestration with systemd

## Status

Proposed

## Date

2026-11-23

## Context

- [ADR-0002](0002-high-level-architecture.md) splits the system into daemons
  by lifecycle. Something must start, stop, restart and watch them.
- The system targets one platform: Fedora, KDE Plasma on Wayland, PipeWire and
  systemd.
- The repo is self-contained software. The `machine` repo installs and
  configures it.
- Silent failure is the worst outcome for an always-on recorder: it looks fine
  and records nothing.
- The keys daemon must run before login and needs root for `/dev/input` and
  `/dev/uinput`. The other daemons belong to the owner's session.

## Decision

### systemd units supervise every daemon

| Unit                            | Scope  | Runs                                                      | Wanted by                  | Watchdog               |
| ------------------------------- | ------ | --------------------------------------------------------- | -------------------------- | ---------------------- |
| `odsod-daemon-keys.service`     | system | `odsod-daemon-keys` (C)                                   | `multi-user.target`        | No                     |
| `odsod-daemon-capture.service`  | user   | `odsodctl run capture`                                    | `default.target`           | Yes, on audio progress |
| `odsod-daemon-pipeline.service` | user   | `odsodctl run pipeline`                                   | `default.target`           | Yes, on main loop      |
| `odsod-daemon-session.service`  | user   | `odsodctl run session` (`dictation`, `tray`, `shortcuts`) | `graphical-session.target` | No                     |
| `odsod-daemon.target`           | user   | Groups the user units above                               | `default.target`           |                        |

- All services use `Restart=always`, a short `RestartSec`, and a start limit
  to stop crash loops.
- The keys service runs at high priority (`Nice=-20`), because key timing must
  not depend on load.
- Capture and pipeline start after PipeWire and WirePlumber. Session is
  `PartOf=graphical-session.target`.
- A system unit cannot join a user target, so `odsod-daemon.target` groups only
  the user units.
- Logs go to stdout and end up in journald:
  `journalctl -u odsod-daemon-keys` and
  `journalctl --user -u 'odsod-daemon-*'`.
- Commands (`note`, `status`, `bench`) have no unit.
- Batch tools that need torch, such as diarization, run as one-shot
  subcommands started by a component, with input and output in files. torch
  never loads in a long-running daemon.
- No daemon forks into the background. systemd does what a classic daemon did
  for itself: detach from the terminal, set the working directory, redirect
  output.

### Crash-only daemons

- On an unexpected internal error, a daemon exits with a non-zero code.
  systemd restarts it. No internal supervisors or retry trees.
- A restart is cheap because each daemon rebuilds its state from files
  ([ADR-0003](0003-filesystem-interface.md)).
- When the keys daemon exits, the kernel releases its keyboard grabs. The
  keyboard works unmapped until the restart, and nothing stays stuck.
- When the session daemon restarts, dictation unmutes every stream listed in
  `run/muted.json`.
- External faults are not crashes. When the inference host is out of reach,
  pipeline retries with backoff and work stays pending in files. When the keys
  socket is missing, session reconnects with backoff and the tray shows that
  dictation is unavailable.

### Watchdog pings mean progress

- Python daemons send `WATCHDOG=1` through `sd_notify` (one datagram to
  `$NOTIFY_SOCKET`, no library).
- Capture pings only when audio bytes advance. A stalled audio stream then
  causes a restart instead of silent loss.
- Pipeline pings from its main loop. It can idle with no speech, so its ping
  means "not stuck", not "busy".

### The tray icon reports health

systemd does not tell the owner when a unit gives up. The tray does.

| State     | Condition                                                                                                 |
| --------- | --------------------------------------------------------------------------------------------------------- |
| Running   | Capture active and audio fresh                                                                            |
| Paused    | Capture stopped by the owner                                                                              |
| Dictating | Session state                                                                                             |
| Warning   | Backlog grows; a meeting mute failed; stale mutes cleared at start                                        |
| Error     | Capture failed, stalled, hit its start limit, or the mic delivers only digital zeros; keys socket missing |

- `odsodctl status` shows the same states in a terminal.
- A mic that delivers only zeros is muted at the source. Capture still
  advances, so only the tray catches it.

### Pause is a service stop

- Pause runs `systemctl --user stop odsod-daemon-capture`. Resume starts it.
- systemd never restarts a unit that was stopped on purpose.
- Pause does not survive a reboot. Recording resumes, which suits an always-on
  recorder.
- Pause does not touch the keys daemon or dictation.

### Unit installation

- Unit templates ship as package data.
- `odsodctl install` writes the user units to `~/.config/systemd/user/`,
  with the absolute path of the installed `odsodctl` command, runs
  `daemon-reload`, and enables and restarts `odsod-daemon.target`. It also
  writes the D-Bus activation file that starts the session service on a call
  from the KWin script ([ADR-0008](0008-shortcuts-and-kwin-script.md)).
- `odsodctl install --system`, run with sudo, builds and installs the keys
  daemon and its system unit ([ADR-0007](0007-keys-daemon.md)).
- [ADR-0006](0006-installation.md) covers how the package itself gets
  installed and upgraded.

## Alternatives considered

### A custom watchdog or supervisor process

- Duplicates what systemd already does, and needs its own supervision.
- Rejected.

### Unit files in the `machine` repo

- Matches how whisper-server is set up today, and how the keyboard daemon was
  installed.
- Rejected: units are part of the system's contract. Agents must change them
  in the same commit as the code.

### Restart on external faults

- Rejected: a restart does not bring the inference host back, and a loop of
  restarts hides the real cause.

### Keys daemon as a user unit

- It would need the owner in the `input` group and access to `/dev/uinput`.
- Rejected: it must run before login, and the remapping must not depend on a
  user session.

## Consequences

- No supervision code beyond `sd_notify`.
- Every failure ends up in one of two places: a restart in the journal, or a
  state in the tray.
- Recording needs a logged-in user session. Recording while logged out is
  not supported.
- An upgrade restarts capture, which leaves an audio gap of a few seconds.
- Installing the keys daemon needs sudo once per host and on each upgrade of
  the C code.
