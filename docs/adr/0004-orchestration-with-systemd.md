# ADR-0004: Orchestration with systemd

## Status

Proposed

## Date

2026-11-23

## Context

- [ADR-0002](0002-high-level-architecture.md) splits the system into services
  by lifecycle. Something must start, stop, restart and watch them.
- The system targets one platform: Fedora, KDE Plasma on Wayland, PipeWire and
  systemd.
- The repo is self-contained software. The `machine` repo installs and
  configures it.
- Silent failure is the worst outcome for an always-on recorder: it looks fine
  and records nothing.
- The keys service must run before login and needs root for `/dev/input` and
  `/dev/uinput`. The other services belong to the owner's session.

## Decision

### systemd units supervise every service

| Unit                                  | Scope  | Runs                                               | Wanted by                      | Watchdog                            |
| ------------------------------------- | ------ | -------------------------------------------------- | ------------------------------ | ----------------------------------- |
| `odsod-daemon-keys.service`           | system | `odsod-daemon-keys` (C)                            | `multi-user.target`            | No                                  |
| `odsod-daemon-capture.service`        | user   | `odsodctl run capture`                             | `default.target`               | `WatchdogSec=30`, on audio progress |
| `odsod-daemon-pipeline.service`       | user   | `odsodctl run pipeline`                            | `default.target`               | Yes, on main loop                   |
| `odsod-daemon-session.service`        | user   | `odsodctl run session` (`dictation`, `shortcuts`)  | `graphical-session.target`     | No                                  |
| `odsod-daemon-tray.service`           | user   | `odsodctl run tray`                                | `graphical-session.target`     | No                                  |
| `odsod-daemon-resume.timer`           | user   | `odsodctl resume --by timer` at 00:00 local time   | `timers.target`                |                                     |
| `odsod-daemon-retention.timer`        | user   | `odsodctl retention`, hourly and at login          | `timers.target`                |                                     |
| `odsod-daemon-notify@.service`        | user   | `odsodctl notify-failed %i`, one-shot              | `OnFailure=` of each user unit |                                     |
| `odsod-daemon-notify-system@.service` | system | `odsodctl notify-failed %i` as the owner, one-shot | `OnFailure=` of the keys unit  |                                     |
| `odsod-daemon.target`                 | user   | Groups the user units above                        | `default.target`               |                                     |

- All services use `Restart=always`, a short `RestartSec`, and a start limit
  to stop crash loops.
- The keys service runs at high priority (`Nice=-20`), because key timing must
  not depend on load.
- Capture and session start after PipeWire and WirePlumber: capture
  records through them, and dictation mutes streams with `pactl`. Pipeline
  reads only files and HTTP, so it needs no such order.
- Session and tray are `PartOf=graphical-session.target`.
- The tray runs in its own unit, with the plain Qt event loop and no
  QtAsyncio. It reads the status and health files on a timer. Qt then never
  shares a loop with dictation, and a tray crash never touches a mute or a
  paste (owner decision, 2026-11-23).
- Every unit, the keys unit too, has
  `OnFailure=odsod-daemon-notify@%n.service`. When a unit fails or hits its
  start limit, the one-shot sends a desktop notification with `notify-send`
  that names the unit and the command that restarts it. It loads no Qt and
  does not depend on the session or tray services. A system unit cannot
  start a user unit, so the keys unit uses the system twin
  `odsod-daemon-notify-system@.service`. It runs the same command with
  `User=` set to the owner and the owner's session bus address.
  `install --system` writes it. `notify-send` comes from `libnotify`, which
  `daemon:setup` installs.
- Capture pings the watchdog only while every channel wrote audio in the
  last 5 s. With `WatchdogSec=30`, a hung capture restarts within about
  30 s (`ambient-recording` AC-13).
- A system unit cannot join a user target, so `odsod-daemon.target` groups only
  the user units.
- Logs go to stdout and end up in journald:
  `journalctl -u odsod-daemon-keys` and
  `journalctl --user -u 'odsod-daemon-*'`.
- Commands (`note`, `status`, `bench`) have no unit.
- No service loads torch. v1 has no diarization
  ([ADR-0002](0002-high-level-architecture.md)). If a later extra adds a
  torch tool, it runs as a one-shot subcommand with input and output in
  files.
- No service forks into the background. systemd does what a classic daemon did
  for itself: detach from the terminal, set the working directory, redirect
  output.

### Crash-only services

- On an unexpected internal error, a service exits with a non-zero code.
  systemd restarts it. No internal supervisors or retry trees.
- A restart is cheap because each service rebuilds its state from files
  ([ADR-0003](0003-filesystem-interface.md)).
- When the keys service exits, the kernel releases its keyboard grabs. The
  keyboard works unmapped until the restart, and nothing stays stuck.
- The session unit has `ExecStopPost=odsodctl unmute-stale`. It unmutes
  every stream listed in `run/muted.json` each time the service stops, also
  after a crash and after the start limit. It loads no Qt and no dictation
  code. Dictation also unmutes stale streams when it starts.
- External faults are not crashes. When the inference host is out of reach,
  pipeline retries with backoff and work stays pending in files. When the keys
  socket is missing, session reconnects with backoff and the tray shows that
  dictation is unavailable.
- Session connects to the keys socket only while capture runs and an
  inference host is reachable. Otherwise it disconnects, so Left Alt is a
  plain Alt and no dictation can give silence or wait for a timeout.

### Watchdog pings mean progress

- Python services send `WATCHDOG=1` through `sd_notify` (one datagram to
  `$NOTIFY_SOCKET`, no library).
- Capture pings only when audio bytes advance. A stalled audio stream then
  causes a restart instead of silent loss.
- Pipeline pings from its main loop. It can idle with no speech, so its ping
  means "not stuck", not "busy".

### The tray icon reports health

systemd does not tell the owner when a unit gives up. The tray and the
notify unit do.

- Each service writes its own active faults, with the time each one
  started, to `run/health/<service>.json`. the `health` component of control merges these files
  with the systemd unit states. The tray and `odsodctl status` use
  the `health` component, so they always agree.

| State     | Condition                                                                                                                                                                                                                                                           | Exit code |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| Error     | Capture failed, stalled or hit its start limit; any service hit its start limit; keys socket missing                                                                                                                                                                | 2         |
| Dictating | Session state                                                                                                                                                                                                                                                       | 0         |
| Warning   | Backlog grows; inference host unreachable; a publish target missing or full; a meeting mute failed; the mic gives only digital silence that the owner did not mute (hardware switch?); a meeting tab with no speaking indicator for 5 min; stale mutes were cleared | 1         |
| Paused    | `run/paused` exists and capture is stopped                                                                                                                                                                                                                          | 0         |
| Mic muted | The owner muted the mic source. Shown as a mark, not an alarm                                                                                                                                                                                                       | 0         |
| Running   | Capture active and audio fresh                                                                                                                                                                                                                                      | 0         |

- When several states apply, the first row wins.
- "Stale mutes were cleared" clears after 10 min or at the next dictation.
- A dev install is a mark, not a state: the tray shows a separate dev mark,
  and `odsodctl status` shows `dev: true`. It does not change the state or
  the exit code ([ADR-0006](0006-installation.md)).
- `odsodctl status` shows the same states in a terminal.
- A mic muted at the source delivers only zeros. Capture still advances, so
  only the health check catches it. The mute flag of the PipeWire source
  tells an owner mute (Mic muted) from a hardware switch or a fault
  (Warning).
- Desktop notifications only for events that need the owner now: a failed
  dictation, a failed paste
  ([ADR-0013](0013-dictation.md)), a new Error, once
  per cause, and a failed unit (from the notify unit). They go through the
  freedesktop notification service on D-Bus.

### `odsodctl` controls what the tray controls

- Every tray action has an `odsodctl` command, so agents can control the
  system: `odsodctl pause`, `odsodctl resume`, `odsodctl status`.
- Query and control commands take `--json`: `status`, `version`,
  `transcript`, `shortcuts`, `dictation last`, `bench list`, `bench report`,
  `pause`, `resume`, `note` and `pin`. Service and setup commands (`run`,
  `install`, `retention`, `unmute-stale`, `notify-failed`) do not.
- `odsodctl status` exits with the Nagios plugin codes: 0 OK, 1 Warning,
  2 Error, 3 unknown.
- Generic service control stays with `systemctl`. `odsodctl` does not wrap
  it. Status reasons name the command that fixes them, for the unit's
  scope: `systemctl --user restart odsod-daemon-<service>` for user units,
  `sudo systemctl restart odsod-daemon-keys` for the keys unit.

### Pause is a flag and a service stop

- `odsodctl pause` writes `run/paused`, then runs
  `systemctl --user stop odsod-daemon-capture`. `odsodctl resume` removes
  the flag and starts capture. The tray does the same.
- The capture unit has `ExecCondition=` on the flag. A start while paused,
  such as from `odsodctl install`, a deploy or an upgrade, does not start
  capture. An install keeps a pause.
- systemd never restarts a unit that was stopped on purpose.
- A pause has no timer. It ends at resume, logout, reboot or the start of
  the next local day. `run/` is on tmpfs, so logout and reboot clear the
  flag.
- `odsod-daemon-resume.timer` runs `odsodctl resume --by timer` at 00:00
  local time each day. It removes the flag and starts capture. Starting a running unit does nothing, so the timer
  only ends pauses.
- Pause does not touch the keys service. It turns dictation off: dictation
  cuts its audio from capture's buffer, so session disconnects from the
  keys socket while capture is stopped, and Left Alt is a plain Alt.

### Retention is a timer

- `odsod-daemon-retention.timer` runs `odsodctl retention` every hour and
  at login. It deletes audio hour files older than the retention period
  ([ADR-0003](0003-filesystem-interface.md)).
- Capture deletes nothing. Retention then holds also while capture is
  paused, stopped or failing.

### Unit installation

- Unit templates ship as package data.
- `odsodctl install` writes the user units and timers to
  `~/.config/systemd/user/`, with the absolute path of the installed
  `odsodctl` command, runs `daemon-reload`, enables the target and both
  timers, and restarts `odsod-daemon.target`. It also
  writes the D-Bus activation file that starts the session service on a call
  from the KWin script ([ADR-0008](0008-shortcuts-and-kwin-script.md)).
- `odsodctl install --system`, run with sudo, builds and installs the keys
  service, its system unit and its `OnFailure=` drop-in
  ([ADR-0007](0007-keys-service.md)).
- [ADR-0006](0006-installation.md) covers how the package itself gets
  installed and upgraded.

## Alternatives considered

### A custom watchdog or supervisor process

- Duplicates what systemd already does, and needs its own supervision.
- Rejected.

### Unit files in the `machine` repo

- Matches how whisper-server is set up today, and how the keyboard service was
  installed.
- Rejected: units are part of the system's contract. Agents must change them
  in the same commit as the code.

### Restart on external faults

- Rejected: a restart does not bring the inference host back, and a loop of
  restarts hides the real cause.

### Keys service as a user unit

- It would need the owner in the `input` group and access to `/dev/uinput`.
- Rejected: it must run before login, and the remapping must not depend on a
  user session.

## Consequences

- No supervision code beyond `sd_notify`.
- Every failure ends up in one of three places: a restart in the journal, a
  state in the tray, or a notification from the notify unit.
- Five services and three helper units. The tray and notify units are small,
  and they keep Qt and failure reporting apart from dictation.
- Recording needs a logged-in user session. Recording while logged out is
  not supported.
- An upgrade restarts capture, which leaves an audio gap of a few seconds.
  An upgrade during a pause keeps the pause.
- Dictation is off while recording is paused.
- Installing the keys service needs sudo once per host and on each upgrade of
  the C code.
