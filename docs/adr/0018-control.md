# ADR-0018: Control

## Status

Proposed

## Date

2026-11-23

## Context

- The owner relies on the daemon without watching it. A silent failure is
  the worst outcome ([ADR-0004](0004-orchestration-with-systemd.md)).
- [ADR-0010](0010-contracts-and-runtime.md) makes control the one owner of
  the health state. Services only report their own faults in
  `run/health/<service>.json`. control merges them with the systemd unit
  states and adds the states that no service can report.
- [ADR-0004](0004-orchestration-with-systemd.md) fixes the state table, the
  exit codes, the pause flag and the notify unit. This ADR designs the code
  that implements them.
- [ADR-0005](0005-components-and-implementation.md) held the first design of
  the tray and the commands. This ADR replaces those sections.

## Decision

### Purpose

- One glance tells the owner if the daemon records, if dictation works, and
  what is wrong ([PRD health-and-control](../prd/health-and-control.md)).
- Agents check and control the daemon from a terminal, with the same result
  as the tray (`health-and-control` AC-3, AC-5, AC-10).
- The owner pauses and resumes recording
  ([PRD ambient-recording](../prd/ambient-recording.md) AC-5, AC-6, AC-18,
  AC-19).
- A service that fails for good gives one desktop notification, also with
  the tray down (`health-and-control` AC-14).

### Components

| Component       | Service or command                 | Job                                                                  |
| --------------- | ---------------------------------- | -------------------------------------------------------------------- |
| `health`        | Library of the subsystem, no entry | Read all sources into a snapshot; evaluate the snapshot to one state |
| `status`        | `odsodctl status`                  | Print the health state; exit with the Nagios code                    |
| `pause`         | `odsodctl pause`                   | Write the pause flag and intent; stop capture                        |
| `resume`        | `odsodctl resume`                  | Remove the flag; write the intent; start capture                     |
| `tray`          | `tray` service                     | Tray icon, menu, Pause and Resume, notifications for new Errors      |
| `notify-failed` | `odsodctl notify-failed <unit>`    | One desktop notification for a unit that failed for good             |

- `health` has no `run()` and no command. `status` and `tray` call it. Both
  call the same `evaluate()` on the same kind of snapshot, so they always
  agree (`health-and-control` AC-3).
- The folder of `notify-failed` is `components/notify_failed/`, because
  Python names cannot hold `-`.

### Writes

| Path or output                  | Component               | Kind       | Fields                                          |
| ------------------------------- | ----------------------- | ---------- | ----------------------------------------------- |
| `run/paused`                    | `pause`                 | Document   | `since` (seam)                                  |
| `run/paused` (removal)          | `resume`                | Document   | (none)                                          |
| `state/events/user/<day>.jsonl` | `pause`, `resume`       | Stream     | `pause`, `resume` (seam); beyond the seam: `by` |
| Desktop notifications           | `tray`, `notify-failed` | D-Bus      | Title, body, urgency                            |
| stdout of `odsodctl status`     | `status`                | Text, JSON | `StatusReport`, below                           |

- `by` in a `pause` or `resume` record is `cli`, `tray` or `timer`. The
  tray and the resume timer pass `--by`. Readers that do not know the field
  ignore it.
- `pause` and `resume` write a record only when the state changes. A resume
  with no flag writes no `resume` record, so the daily resume timer adds no
  record each night.
- control writes no health file. Its own findings exist only in the
  evaluated state.

`StatusReport` (in `components/health/contract.py`), the model behind the
tray and `odsodctl status --json`:

| Field          | Content                                                                                        |
| -------------- | ---------------------------------------------------------------------------------------------- |
| `state`        | `error`, `dictating`, `warning`, `paused`, `mic-muted`, `running` or `unknown`                 |
| `exit_code`    | 0, 1, 2 or 3                                                                                   |
| `reasons`      | List of `code`, `severity` (`error`, `warning`, `mark`), `service`, `since`, `message`, `fix`  |
| `services`     | Per unit: `unit`, `scope` (`user`, `system`), `expected`, `active_state`, `sub_state`, `since` |
| `newest_audio` | Per channel (`mic`, `sys`): UTC time, or null                                                  |
| `backlog`      | `count`, `seconds`, `oldest` (UTC start, or null)                                              |
| `mode`         | `idle` or `dictating`                                                                          |
| `dictation`    | `available` (bool) and `reason` (`keys` value of `run/status.json`, or `session-down`)         |
| `paused_since` | UTC time, or null                                                                              |
| `dev`          | Bool, with `commit` and `workspace` of the install                                             |
| `ts`           | Time of the evaluation                                                                         |

### Reads

| Path or source                             | Seam fields relied on                                                | Used for                      |
| ------------------------------------------ | -------------------------------------------------------------------- | ----------------------------- |
| `run/health/<service>.json`                | `service`, `ts`, `faults[].code`, `since`, `message`, `fix`          | Service faults                |
| `run/status.json`                          | `mode`, `since`, `keys`                                              | Dictating; why no dictation   |
| `run/paused`                               | `since`                                                              | Paused                        |
| Audio buffer, newest hour file per channel | File size only, through `lib.audio` (no samples)                     | Newest audio; audio staleness |
| `state/utterances/ambient/`, `dictation/`  | `id`, `start`, `end`                                                 | Backlog                       |
| `state/text/`                              | `input`                                                              | Backlog                       |
| `state/coverage/`                          | `channel`, `end` (kind `covered`)                                    | Backlog of unsegmented audio  |
| `state/install/current`, `previous-commit` | `source`, `commit`, `workspace` ([ADR-0006](0006-installation.md))   | Dev mark; rollback command    |
| systemd, user and system manager           | `ActiveState`, `SubState`, `Result`, `StateChangeTimestamp` per unit | Unit states                   |
| `config/config.json`                       | Section `control`                                                    | Thresholds                    |

- A health file counts only while its unit is `active` (ADR-0010). A crashed
  service then never shows old faults.
- `run/status.json` counts only while the session unit is active.
- control does not read `events/capture/`, `interactions/` or
  `published/<target>/` in this version. pipeline reports
  `interactions-waiting` and `target-missing` itself.

### Outside dependencies

| System or tool                       | Used by                  | For                                                   |
| ------------------------------------ | ------------------------ | ----------------------------------------------------- |
| systemd user and system manager      | `health` (`lib.systemd`) | Unit states over D-Bus                                |
| `systemctl --user stop`/`start`      | `pause`, `resume`        | Stop and start capture (ADR-0004)                     |
| `notify-send` (libnotify)            | `tray`, `notify-failed`  | Desktop notifications through the freedesktop service |
| PySide6 (`QSystemTrayIcon`, `QMenu`) | `tray`                   | Icon and menu on the plain Qt loop                    |
| KDE Plasma status notifier           | `tray`                   | Shows the icon                                        |

- `notify-send` is the one way to notify, so `notify-failed` loads no Qt and
  no D-Bus library.

### Internal design

#### Module layout

```
components/health/
├── __init__.py        SUBSYSTEM = "control"; no run()
├── contract.py        StatusReport, Reason, State, ServiceState, Backlog
├── snapshot.py        Snapshot model; gather(paths, clock, systemd) -> Snapshot
├── evaluate.py        evaluate(snapshot, config) -> StatusReport (pure)
├── backlog.py         BacklogTracker: full rebuild and incremental update
├── units.py           Expected units; fix commands per scope
└── tests/
components/status/     cli.py (typer), render.py (text form)
components/pause/      cli.py, flag.py (write, remove, read run/paused), contract.py
components/resume/     cli.py, contract.py (uses pause.flag)
components/tray/       __init__.py run(config), app.py, worker.py, menu.py, icons/*.svg
components/notify_failed/  cli.py, notify.py (notify-send wrapper)
```

- `tray` imports `notify_failed.notify` and `pause.flag` (same subsystem).
  `notify_failed` imports nothing from `tray`, so it never loads Qt.

#### Snapshot and evaluation

`gather()` reads every source once. `evaluate()` is a pure function of the
snapshot, the config and the time. All rules live in `evaluate()`, so a table
test covers every state.

Expected units:

| Unit                            | Scope  | Expected when                                                        | Fix when down                                    |
| ------------------------------- | ------ | -------------------------------------------------------------------- | ------------------------------------------------ |
| `odsod-daemon-capture.service`  | user   | `run/paused` does not exist and `graphical-session.target` is active | `systemctl --user restart odsod-daemon-capture`  |
| `odsod-daemon-pipeline.service` | user   | Always                                                               | `systemctl --user restart odsod-daemon-pipeline` |
| `odsod-daemon-session.service`  | user   | `graphical-session.target` is active                                 | `systemctl --user restart odsod-daemon-session`  |
| `odsod-daemon-tray.service`     | user   | `graphical-session.target` is active                                 | `systemctl --user restart odsod-daemon-tray`     |
| `odsod-daemon-keys.service`     | system | Always                                                               | `sudo systemctl restart odsod-daemon-keys`       |

- Session and tray are not expected without a graphical session, such as a
  host reached over SSH with nobody logged in on screen. `status` then
  reports them as `expected: false` and raises no Error
  (`health-and-control` AC-4).

Reasons, from the snapshot:

| Code                | Severity    | Condition                                                              | Source      |
| ------------------- | ----------- | ---------------------------------------------------------------------- | ----------- |
| `unit-failed`       | error       | An expected unit is `failed` (crash loop hit its start limit, or exit) | control     |
| `unit-down`         | error       | An expected unit is not `active` for more than `unit_grace_s`          | control     |
| `audio-stale`       | error       | Capture is active and the newest audio is older than `audio_stale_s`   | control     |
| `backlog`           | warning     | A pending utterance ended more than `backlog_warning_s` ago            | control     |
| service fault codes | as ADR-0010 | Listed in the health file of an active unit                            | the service |
| `mic-muted`         | mark        | Listed in capture's health file                                        | capture     |
| `health-unreadable` | warning     | A health file of an active unit is not valid JSON                      | control     |

- `unit-down` has a grace time, because a crash restart takes a moment.
  Capture's 5 s crash gap (`ambient-recording` AC-3) then never flashes
  Error. `failed` needs no grace (`health-and-control` AC-7).
- `audio-stale` covers a capture that hangs without a crash and without a
  health file update. The watchdog restarts capture first; this reason is
  the backstop for `ambient-recording` AC-13 (Error in 2 min).
- `unit-failed` and `unit-down` add the rollback command when the last
  install changed the commit: "If this started after the upgrade, run
  `mise run daemon:setup <previous commit>` in the machine repo"
  (`install-and-upgrade` AC-15). The previous commit comes from
  `state/install/previous-commit`.
- Each reason's `since` is the unit's `StateChangeTimestamp`, the fault's
  `since`, the newest audio time or the oldest pending utterance end
  (`health-and-control` AC-2).
- Each `message` is one sentence that names the cause, built from a fixed
  template per code. Service faults keep the service's own `message`.

State, first match wins (`health-and-control` AC-12):

1. `error`: any reason with severity `error`.
2. `dictating`: session active and `run/status.json` `mode` is `dictating`.
3. `warning`: any reason with severity `warning`.
4. `paused`: `run/paused` exists and capture is not active.
5. `mic-muted`: the `mic-muted` mark is present.
6. `running`: none of the above.

- The dev mark never changes the state or the exit code
  (`health-and-control` AC-15).
- Exit codes: `error` 2, `warning` 1, all others 0. `unknown` 3: the user
  manager does not answer, or `gather()` raises
  (`health-and-control` AC-11).
- `dictation.available` is true when the session is active and `keys` is
  `connected`. Otherwise `reason` gives why: `paused`, `no-inference`,
  `no-socket` or `session-down` (`dictation` AC-23: "the tray shows why").

#### Backlog

- Pending = utterance IDs in `utterances/ambient/` and
  `utterances/dictation/` with no `text/` record that names them as `input`.
- The window is the full pending window: `common.retention_days` (14) UTC
  day files, the same as speech ([ADR-0003](0003-filesystem-interface.md)).
  A shorter window would hide pending work that still delays the batch
  pass (`health-and-control` AC-9).
- The backlog parses lines with plain `json.loads` and reads only `id`,
  `input`, `start` and `end`. No model per line. This keeps a one-shot
  `status` within 1 s on 14 days of streams (`health-and-control` AC-4).
- `BacklogTracker.rebuild()` reads the window. `status` calls it once.
- `BacklogTracker.update()` follows new lines with `lib.streams` and updates
  the sets in memory. The tray calls it on each tick, so a tick reads only
  new lines.
- Audio that segmentation has not reached yet also counts. Per channel,
  the newest `covered` `end` in `state/coverage/` is compared with the
  newest audio. A gap older than `backlog_warning_s` adds its length to
  `seconds`, and its start can be `oldest`. This catches a segmentation
  that falls behind and so gives no utterances to count.
- A gap under 5 s between `covered` and the newest audio is ignored.
  Segmentation lags the live audio by design (ADR-0012), and the last
  seconds before a capture stop drain only after the stop.
- `seconds` is the sum of `end - start` of pending utterances. `count` and
  `seconds` appear in the Warning message (`health-and-control` AC-9).

#### Audio freshness

- `lib.audio` gives the time that the current hour file covers, from its
  size: hour start plus size / 32,000 s. control reads the current and the
  previous hour file, and takes the newest time per channel.
- control never opens audio for reading.

#### status

- `odsodctl status [--json]` runs `gather()` once, then `evaluate()`.
- Text form: first line is the state and the dev mark. Then one block per
  reason (message, since, fix), the services, the newest audio, the backlog
  and the dictation availability.
- `--json` prints `StatusReport` as one JSON document. It holds every field
  of the text form (`health-and-control` AC-10).
- On any exception it prints the error, `state: unknown`, and exits 3.
- It needs no graphical session. With no `XDG_RUNTIME_DIR`, `lib.paths`
  uses `/run/user/<uid>` (`health-and-control` AC-4).

#### pause and resume

`odsodctl pause [--json] [--by cli|tray|login]`:

1. If `run/paused` exists, print "already paused since …" and exit 0.
2. Write `run/paused` with `since` (atomic, ADR-0003).
3. Append a `pause` record to `events/user/` with one `O_APPEND` write.
4. Run `systemctl --user stop odsod-daemon-capture.service` and wait for it.
5. Print the new state. Exit 0, or 1 if the stop failed (the flag stays).

`odsodctl resume [--json] [--by cli|tray|timer|login]`:

1. If `run/paused` exists: remove it, then append a `resume` record.
2. If `graphical-session.target` is active, run
   `systemctl --user start odsod-daemon-capture.service` and wait for it.
   Capture is `Type=notify`, so the start returns when capture records.
   With no graphical session (over SSH, or the timer while logged out),
   resume only removes the flag; capture starts at the next login.
3. Print the new state. Exit 0, or 1 if the start failed.

- The flag goes first in pause and last in resume. The capture unit's
  `ExecCondition=` on the flag then blocks any start in between, also from
  an install (`ambient-recording` AC-19).
- The resume timer runs `odsodctl resume --by timer` at 00:00 local time
  (`ambient-recording` AC-18). `odsod-daemon-login.service` runs
  `odsodctl resume --by login` when the graphical session starts, so a
  login ends a pause. [ADR-0006](0006-installation.md) owns the
  unit.
- `--json` prints `state`, `paused_since` and `changed`.

#### tray

- `tray` runs Qt on the main thread with the plain Qt event loop
  (ADR-0004). One worker thread runs its own asyncio loop.
- The worker ticks every `tray_interval_s` (1 s): `BacklogTracker.update()`,
  `gather()`, `evaluate()`. It sends the `StatusReport` to the Qt thread with
  a queued Qt signal. A slow D-Bus call never blocks the Qt loop.
- The worker also watches `run/status.json` with inotify (low debounce, the
  same mechanism as `lib.streams` follow). A change of `mode` triggers an
  `evaluate()` at once, with the last snapshot and the new mode, and sends
  the report. The icon then shows Dictating at most 200 ms after dictation
  writes the file (`dictation` AC-1). The 1 s tick stays for systemd, files
  and backlog.
- The icon changes in the slot that receives the report. A tick plus the
  evaluation is well under 2 s (`health-and-control` AC-1, AC-16).
- Icons: one SVG per state in `components/tray/icons/`, and a dev variant
  of each with a small corner mark. A dev install switches to the dev
  variant (`health-and-control` AC-15).
- Tooltip: the state and the first reason's message.
- Menu, rebuilt on each change of the report:
  - one disabled line per reason: message, since (local time), fix;
  - one line on dictation when it is unavailable, with the reason;
  - Pause or Resume.
- Pause and Resume start `odsodctl pause --by tray` or
  `odsodctl resume --by tray` with `QProcess`. The effect is the same as
  from a terminal (`health-and-control` AC-5), and the Qt loop never waits.
- Notifications for new Errors:
  - The worker keeps the set of active error causes (`code` plus `service`)
    in memory. A cause that enters the set gives one notification. A cause
    that stays gives none. A cause that leaves and comes back gives a new
    one (`health-and-control` AC-6).
  - `unit-failed` gives no tray notification. `notify-failed` already sends
    one for it, also with the tray down.
  - A tray restart forgets the set and notifies the Errors that are active
    again. Tray restarts are rare; this is accepted.

#### notify-failed

- `odsodctl notify-failed <unit>` runs from `odsod-daemon-notify@.service`
  (ADR-0004). systemd starts it only when a unit enters `failed`, which with
  `Restart=always` means the start limit was hit.
- It maps the unit to its fix command by scope (table above) and runs
  `notify-send --urgency=critical --app-name=odsod-daemon` with the title
  "odsod-daemon: <service> failed" and the body "<fix>. Details:
  `odsodctl status`."
- It imports no Qt and reads no file, so it works with the tray and the
  session down (`health-and-control` AC-14).
- For the system keys unit, the drop-in from `install --system` runs it as
  the owner with the owner's session bus address
  ([ADR-0006](0006-installation.md)).

#### Timing

| Target                                 | Design                                    | AC                               |
| -------------------------------------- | ----------------------------------------- | -------------------------------- |
| Tray follows a condition in 2 s        | 1 s tick, evaluation under 200 ms         | `health-and-control` AC-1        |
| Tray shows Dictating in 200 ms         | Watch on `run/status.json`, no tick wait  | `dictation` AC-1                 |
| Start limit shows Error in 10 s        | `failed` has no grace; 1 s tick           | `health-and-control` AC-7        |
| Session down shows in 10 s             | `unit_grace_s` 5 s plus 1 s tick          | `health-and-control` AC-8, AC-16 |
| `status` answers in 1 s                | One gather; 14-day backlog, `json.loads`  | `health-and-control` AC-4        |
| Paused in 1 s                          | Flag, then a synchronous stop of capture  | `ambient-recording` AC-5         |
| Mic muted in 5 s                       | capture's mark plus 1 s tick              | `ambient-recording` AC-17        |
| Notification for a failed unit in 30 s | `OnFailure=` runs `notify-failed` at once | `health-and-control` AC-14       |

### Failure modes

| Fault                                   | What control does                                                                                  | Code or state                |
| --------------------------------------- | -------------------------------------------------------------------------------------------------- | ---------------------------- |
| User manager does not answer            | `status` prints the error and exits 3; tray shows the Error icon with "cannot read service states" | `unknown`; tray Error        |
| A health file is not valid JSON         | Treat it as one fault: "health file of <service> unreadable"                                       | `health-unreadable`, warning |
| `run/status.json` is missing or invalid | Mode `idle`; dictation `available: false`, reason `session-down`                                   | none                         |
| `systemctl stop` fails in `pause`       | Keep the flag, print the error, exit 1                                                             | none                         |
| `systemctl start` fails in `resume`     | Print the error, exit 1. The unit state shows in `status`                                          | `unit-failed` or `unit-down` |
| `notify-send` fails                     | Log one line to the journal. No retry                                                              | none                         |
| Tray crashes                            | systemd restarts it. `status` shows `unit-down` for the tray                                       | `unit-down`                  |
| Tray hits its start limit               | `notify-failed` notifies; `status` shows Error                                                     | `unit-failed`                |
| Stream line half written                | `lib.streams` skips lines with no `\n` (ADR-0003)                                                  | none                         |

### Config

Section `control`:

```json
{
  "control": {
    "tray_interval_s": 1.0,
    "unit_grace_s": 5,
    "audio_stale_s": 120,
    "backlog_warning_s": 600
  }
}
```

- `backlog_warning_s` is the 10 min of `health-and-control` AC-9.
- `audio_stale_s` is the 2 min of `ambient-recording` AC-13.
- No other key. The state order and the exit codes are fixed in code.

### Tests

Component tests use the runtime fixtures (ADR-0010): a temp root, a fake
clock and the fake systemd unit-state source. A fake `systemctl` and a fake
`notify-send` record their calls.

| Test                                                                                                | Checks                                                  |
| --------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| `evaluate()` table: one snapshot per state, and pairs of states for the order                       | `health-and-control` AC-12, AC-11                       |
| Each reason has a one-sentence message and `since`                                                  | `health-and-control` AC-2                               |
| Each unit reason names the fix for its scope (`--user` or `sudo`)                                   | `health-and-control` AC-13                              |
| Unit `failed` gives Error at once; not active past the grace gives Error                            | `health-and-control` AC-7, AC-8, AC-16                  |
| No graphical session: session and tray not expected, no Error                                       | `health-and-control` AC-4                               |
| Pending utterance older than 10 min gives Warning with count and seconds                            | `health-and-control` AC-9                               |
| `BacklogTracker.update()` after appends equals `rebuild()`                                          | `health-and-control` AC-3                               |
| Dev install: dev true, same state and exit code as without                                          | `health-and-control` AC-15, `install-and-upgrade` AC-13 |
| Failed unit after a commit change names `daemon:setup <previous>`                                   | `install-and-upgrade` AC-15                             |
| `mic-muted` mark gives state `mic-muted`, exit 0                                                    | `ambient-recording` AC-17                               |
| Capture active, audio older than 120 s gives Error                                                  | `ambient-recording` AC-13                               |
| `status --json` holds every field of the text form                                                  | `health-and-control` AC-10                              |
| `status` on 14 days of synthetic streams (10,000 utterances a day) runs in under 1 s                | `health-and-control` AC-4                               |
| A pending utterance 10 days old counts in `count`, `seconds` and `oldest`                           | `health-and-control` AC-9                               |
| A covered gap under 5 s gives no backlog; one over 10 min does                                      | `health-and-control` AC-9                               |
| A `mode` change in `run/status.json` reaches the icon slot in under 200 ms (Qt offscreen)           | `dictation` AC-1                                        |
| `pause`: flag, then record, then stop; second pause changes nothing                                 | `ambient-recording` AC-5                                |
| `resume`: removes flag, record, start; no flag gives no record                                      | `ambient-recording` AC-6, AC-18                         |
| Tray worker: a report reaches the icon slot in under 2 s (Qt offscreen platform)                    | `health-and-control` AC-1, AC-16                        |
| Tray and `status` give equal reports from one snapshot                                              | `health-and-control` AC-3                               |
| Tray Pause runs the same command as the CLI                                                         | `health-and-control` AC-5                               |
| An Error that lasts 1 h of fake time gives one notification; `unit-failed` gives none from the tray | `health-and-control` AC-6                               |
| `notify-failed` imports no Qt and calls `notify-send` once with the fix                             | `health-and-control` AC-14                              |

System tests in `tests/`:

- Capture stub writes audio, pause stops it, `status` shows Paused
  (`ambient-recording` AC-5), and resume starts it (AC-6).
- Install with `run/paused` present does not start the capture stub
  (`ambient-recording` AC-19, `install-and-upgrade` AC-14).

### Build without hardware

- An agent builds and tests all of control with no owner hardware: every
  source is a file in a temp root or a fake (systemd, `systemctl`,
  `notify-send`), and Qt runs with `QT_QPA_PLATFORM=offscreen`.
- The owner checks on a real host:
  - the icons and the menu in the Plasma panel;
  - the look of notifications;
  - `odsodctl status` over SSH with and without a graphical session;
  - a real start-limit hit (`systemctl --user kill` in a loop) gives Error
    in 10 s and one notification.

## Alternatives considered

### Each service writes its whole state; control only reads

- Simpler control, but no service can see its own crash, its own start
  limit, or the backlog across services.
- Rejected: ADR-0010 makes control the one owner of the state.

### The tray on QtAsyncio

- One loop for Qt and asyncio.
- Rejected: ADR-0004 keeps the plain Qt loop. A worker thread with its own
  asyncio loop gives the same with no new dependency.

### The tray calls the pause code in process

- No subprocess.
- Rejected: a subprocess is exactly the CLI path, so the tray and the
  terminal can never differ (`health-and-control` AC-5), and a slow stop
  never blocks Qt.

### Backlog over a 3-day window

- Fewer lines for a one-shot `status`.
- Rejected: closing a transcript after 48 h does not transcribe its audio.
  Older pending utterances would vanish from status while speech still
  works on them. Plain `json.loads` of four fields keeps 14 days within
  1 s.

### Tray on the 1 s tick only

- One timer for everything.
- Rejected: Dictating must show in 200 ms (`dictation` AC-1).

### Remember notified Errors in `run/`

- No repeat after a tray restart.
- Rejected: one more file for a rare case.

### Read the PipeWire mute flag in control

- Rejected: PipeWire belongs to capture (ADR-0009, subsystem rule 3).
  capture reports `mic-muted` as a mark.

## Consequences

- One pure function decides the state. A new fault code from a service
  needs no change in control, only its severity in ADR-0010.
- control depends on capture for the Mic muted mark, and on operations for
  the install record.
- control reads three streams for the backlog. A change to their seam
  fields changes this ADR.
- `odsodctl status` works over SSH; the tray needs the graphical session.
- Seam decisions (orchestrator, 2026-11-23): control reads the audio
  buffer (size only), utterances, text and coverage; capture reports the
  `mic-muted` mark; operations writes `state/install/current`;
  `lib.systemd` reads the system bus.
