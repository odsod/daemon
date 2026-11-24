# ADR-0011: Capture

## Status

Proposed

## Date

2026-11-23

## Context

- Every other subsystem works on stored audio
  ([ADR-0002](0002-high-level-architecture.md), principle 7). If capture
  loses audio, or stores it at the wrong time, nothing downstream can fix it.
- [ADR-0003](0003-filesystem-interface.md) fixes the buffer format: raw
  s16le, 16 kHz, mono, one file per channel and UTC hour, byte offset equals
  time. [ADR-0010](0010-contracts-and-runtime.md) fixes the seam fields of
  `events/capture/` and the fault codes `capture-stalled` and `mic-silent`.
- Dictation cuts its audio by key timestamps, which are wall-clock times
  (ADR-0007). Sound card clocks drift, NTP steps the wall clock, and a
  laptop suspends. Audio time must still match wall time within 200 ms
  (`ambient-recording` AC-20).
- Silent failure is the worst outcome (ADR-0004). A stalled stream or a mic
  that gives only zeros must show in the tray.
- This ADR takes the capture and retention sections out of
  [ADR-0005](0005-components-and-implementation.md) and deepens them.

## Decision

### Purpose

- Record mic and system audio, always, to the audio buffer, with correct
  wall-clock times. Delete audio after the retention period.
- PRD: [`ambient-recording`](../prd/ambient-recording.md) (all ACs except
  AC-18 and AC-19, which control and the units own).
- Capture knows nothing about speech, meetings or dictation.

### Components

| Component   | Runs in                                        | Job                                                     |
| ----------- | ---------------------------------------------- | ------------------------------------------------------- |
| `capture`   | `capture` service (`odsod-daemon-capture`)     | Run one `pw-record` per channel; write the audio buffer |
| `retention` | command `odsodctl retention`, run by its timer | Delete audio hour files older than the retention period |

- Both have `SUBSYSTEM = "capture"`.
- The capture service holds only the `capture` component, so changes
  elsewhere never cause audio gaps (ADR-0002, principle 13).

### Writes

| Path                                       | Kind     | Records and fields beyond the seam                   |
| ------------------------------------------ | -------- | ---------------------------------------------------- |
| `state/audio/<channel>/<YYYYMMDDTHH>Z.pcm` | Audio    | Format per ADR-0003. Mode `0600`, directories `0700` |
| `state/events/capture/<day>.jsonl`         | Stream   | `start`, `stop`, `gap` (below)                       |
| `run/health/capture.json`                  | Document | Faults `capture-stalled`, `mic-silent`, `mic-muted`  |

Records in `events/capture/`:

| Kind    | Seam fields               | Extra fields                                                                                             |
| ------- | ------------------------- | -------------------------------------------------------------------------------------------------------- |
| `start` | `channel`                 | `audio_start`: time of the first sample. `prev_end`: end of the channel's existing audio, or null        |
| `stop`  | `channel`                 | `reason`: `shutdown` (SIGTERM). A crash writes no `stop`                                                 |
| `gap`   | `channel`, `start`, `end` | `reason`: `suspend`, `clock` (wall clock stepped forward), `stall` (`pw-record` restarted after a stall) |

- `start` is written when the channel's first block is on disk, so its
  `audio_start` is real audio, not an intent.
- A `gap` is written for each hole of 1 s or more inside one process run.
  The time between a `stop` (or crash) and the next `start` is not a `gap`
  record: `prev_end` and `audio_start` give its range. transcript names the
  cause ([ADR-0015](0015-transcript.md)).
- Retention writes no record. It only deletes.

### Reads

| Path                     | What capture relies on                                                 |
| ------------------------ | ---------------------------------------------------------------------- |
| `state/audio/<channel>/` | Its own files: the size of the newest file gives `prev_end` at start   |
| `config/config.json`     | Section `capture`; `common.retention_days` (retention)                 |
| `run/paused`             | Not read by the code. The unit's `ExecCondition=` checks it (ADR-0004) |

### Outside dependencies

- PipeWire and WirePlumber, through `pw-record` (from `pipewire-utils`) and
  `pactl` (from `pulseaudio-utils`, on `pipewire-pulse`). Capture is the
  only subsystem that reads PipeWire state (ADR-0009, rule 3). dictation
  also runs `pactl`, but only to mute other apps' streams.
- WirePlumber moves a stream that has no fixed target to the new default
  device, and to another device when its device disappears. Capture relies
  on this for `ambient-recording` AC-9 and AC-16 and adds no device logic.
- The `machine` repo turns off WirePlumber's switch to the Bluetooth
  headset profile (ADR-0005). Capture never opens a headset mic in call
  mode (`ambient-recording` AC-10).
- systemd: `sd_notify` for `READY=1` and `WATCHDOG=1` (`lib.systemd`).
- Python: `numpy` for zero checks. No other library.

### Internal design

#### Module layout

```
components/capture/
├── __init__.py   SUBSYSTEM, run(config)
├── contract.py   CaptureStart, CaptureStop, CaptureGap; fault codes;
│                 CAPTURE_APP_NAME = "odsod-daemon-capture"
├── config.py     CaptureConfig
├── service.py    the TaskGroup: one channel task per channel, source watch,
│                 suspend watch, watchdog
├── channel.py    pw-record subprocess; read 100 ms blocks; restart on stall
├── anchor.py     pure: (block, arrival time) → write offset, hole, drop
├── writer.py     hour files: pwrite at offset, split at the hour boundary
├── source.py     pactl subscribe: mute flag and name of the default source
├── checks.py     pure: zeros, stall and mute → faults with `since`
└── tests/
components/retention/
├── __init__.py   SUBSYSTEM = "capture"
├── retention.py  pure: list of files, now, period → files to delete
├── cli.py        typer app: `odsodctl retention`
└── tests/
```

#### Channels

| Channel | `pw-record` arguments (all: `--rate 16000 --channels 1 --format s16 --raw -`)        |
| ------- | ------------------------------------------------------------------------------------ |
| `mic`   | No target: follows the default source                                                |
| `sys`   | `-P '{ stream.capture.sink = true }'`, no target: follows the default sink's monitor |

- Every stream sets `application.name` to `CAPTURE_APP_NAME`
  (`odsod-daemon-capture`) and `node.name = odsod-daemon-capture-<channel>`.
  `CAPTURE_APP_NAME` is a constant in `components/capture/contract.py`, a
  seam in [ADR-0010](0010-contracts-and-runtime.md). dictation imports it
  and skips streams with this name when it mutes
  ([ADR-0013](0013-dictation.md)). A rename then changes both sides.
- Two channels only in v1: `mic` and `sys`. An extra echo-cancelled
  channel (`mic-ec`) is deferred (see Later).
- No `--latency` and no media role. A small fragment can shrink the graph
  quantum and glitch a live call (Meetily). Role `Communication` records
  silence on Bluetooth (OpenWhispr). This gives `ambient-recording` AC-10.
- PipeWire resamples and mixes down to 16 kHz mono.

#### Block loop and time anchoring

Each channel task reads 3,200 bytes (100 ms) at a time from `pw-record`'s
stdout and gives each block to `anchor.py`, with its arrival time from
`lib.clock`.

- The anchor holds `t0`, the wall time of the first sample, and `n`, the
  samples written since. A block arrives at its end, after the
  `pw-record` buffer and the pipe. So the anchor computes `t0` from the
  first block as
  `t0 = arrival − block duration (100 ms) − capture_latency_ms`.
  `capture_latency_ms` is a config value. The owner's capture spike sets
  its default: the owner taps a key near the mic ten times, and the spike
  compares the keys service's press times with the audio onsets in the
  buffer. The expected end of a block is `t0 + n / 16000`.
- On each block it computes `drift = arrival − expected end`, smoothed as
  the median of the last 10 blocks, so pipe jitter never moves the anchor.
- `drift > +150 ms` (audio behind the wall clock: lost samples, a forward
  clock step): seek forward. The writer leaves a hole of `drift`, which
  reads as zeros and uses no disk. A hole of 1 s or more gets a `gap`
  record with reason `clock`.
- `drift < −150 ms` (audio ahead: the wall clock stepped back, or the card
  runs fast): drop whole blocks until the wall clock passes the end of the
  file. Capture never writes backward (ADR-0003).
- The 150 ms threshold keeps the error inside the 200 ms of
  `ambient-recording` AC-20, with room for pipe latency. A sound card that
  drifts 50 ppm gets one 150 ms correction about every 50 min.
- At a new `pw-record` process, the anchor restarts with the same `t0`
  rule from its first block.

#### Writer

- Offset in a file is `(time − hour start) × 32,000` bytes, rounded down to
  an even byte. A block that crosses the hour is split over two files.
- `os.pwrite` on a file opened with `O_WRONLY | O_CREAT`, mode `0600`. No
  `fsync`: a crash of the process keeps the page cache. A kernel crash can
  lose a few seconds, which is accepted.
- File size is the coverage that readers wait on (`lib.audio`). The writer
  never truncates.

#### Stall, suspend and restart

- **Stall:** a channel that delivers no block for `stall_restart_s` (10 s)
  gets its `pw-record` killed and started again. The hole gets a `gap` with
  reason `stall`.
- **Watchdog:** capture sends `WATCHDOG=1` only while both channels (`mic`
  and `sys`) wrote a block in the last 5 s. The unit sets `WatchdogSec=30`. A
  stall that a `pw-record` restart does not fix restarts the whole service
  within 60 s (`ambient-recording` AC-13).
- **`capture-stalled` (Error):** set when a channel has no new audio for
  `stall_error_s` (60 s). The stall starts at the end of the channel's
  newest audio (from the file size) or at the service start, whichever is
  later. Old audio from before a pause then never counts as a stall. A
  stall that began before a watchdog restart shows Error about 90 s after
  it began, inside the 2 min of AC-13.
- **Suspend:** a task compares `CLOCK_BOOTTIME − CLOCK_MONOTONIC` each
  second. When it grows by more than 1 s, the host has resumed. Capture
  restarts every `pw-record` and writes a `gap` with reason `suspend` from
  the last block before the suspend to the first block after it
  (AC-20). systemd's watchdog runs on the monotonic clock, so a suspend
  never trips it.
- **SIGTERM** (pause, logout, upgrade): kill every `pw-record`, write a
  `stop` per channel, exit 0. This takes well under 1 s
  (`ambient-recording` AC-5).
- **Start:** a service restart takes about 1 s to the first block, inside
  the 5 s of `ambient-recording` AC-3.

#### Mic checks

- `source.py` runs `pactl subscribe` and, on each `source` or `server`
  event and every 60 s, reads the mute flag of the default source with
  `pactl --format=json`.
- **`mic-muted` (Mark):** set while the default source is
  muted. Cleared when it is unmuted. Within 5 s (`ambient-recording`
  AC-17).
- **`mic-silent` (Mark, as a hardware mute; owner decision 2026-11-24):**
  set when every sample of the `mic` channel has been exactly zero for
  `mic_silent_s` (5 s) while the source is not muted. `since` is the first zero block. Cleared by the first block with a
  non-zero sample. The check runs on each block, so the fault shows at
  about 60 s, inside the 70 s of AC-12. A hardware switch gives the same
  zeros with no mute flag, so this is never an Error (ADR-0004).
- `sys` gets no zero check: no playback is normal.

#### Echo

- `mic` is always the raw mic. Text dedup in transcript and interactions
  is the baseline. An echo-cancel source is deferred (see Later), and is
  never the default source. Utterances use only `mic` and `sys`
  (ADR-0003).

#### Retention

- `odsodctl retention` lists `state/audio/*/` and deletes each hour file
  whose hour start is older than `common.retention_days`. It runs each hour
  and at login from `odsod-daemon-retention.timer` (ADR-0004).
- An hour file goes when its first second turns 14 days old, so its newest
  audio goes up to 1 h early. Audio is never more than 1 h past the period
  (`ambient-recording` AC-7). Early is the safe side for privacy.
- It skips names it cannot parse, follows no symlinks, and never reads
  `state/bench/`. It does not depend on capture running.

### Failure modes

| Fault                                    | What capture does                                                            | Code              |
| ---------------------------------------- | ---------------------------------------------------------------------------- | ----------------- |
| `pw-record` exits or stalls              | Restarts it after 10 s; `gap` with reason `stall`                            | none (self-heals) |
| Stall not fixed by the restart           | Stops the watchdog ping; systemd restarts the service at 30 s                | none              |
| No new audio for 60 s on a channel       | Fault, Error. Restarts go on until the start limit                           | `capture-stalled` |
| Mic gives only zeros for 5 s, not muted  | Fault, Mark (hardware mute). Recording goes on                                     | `mic-silent`      |
| Owner mutes the default source           | Mark. Recording goes on (zeros)                                              | `mic-muted`       |
| Clock step or card drift                 | Re-anchors: hole or dropped blocks. `gap` with reason `clock` if 1 s or more | none              |
| Resume from suspend                      | Restarts `pw-record`; `gap` with reason `suspend`                            | none              |
| Disk full or write error                 | Raises: the process exits non-zero; systemd restarts it; start limit → Error | none (unit state) |
| No PipeWire at start                     | `pw-record` gives no block; stall path above                                 | `capture-stalled` |
| Retention cannot delete a file           | Logs and goes on with the other files; exits non-zero at the end             | none (timer log)  |

- A disk-full fault code is left out on purpose. It is rare, and the unit
  failure shows Error and names the journal.

### Config

Section `capture`:

```json
{
  "capture": {
    "stall_restart_s": 10,
    "stall_error_s": 60,
    "mic_silent_s": 5,
    "reanchor_ms": 150,
    "capture_latency_ms": 0
  }
}
```

- `capture_latency_ms`: the default 0 is a placeholder until the owner's
  capture spike measures the real value on the owner's host.
- Retention reads `common.retention_days` (14). It has no section.
- Block size (100 ms), the watchdog window (5 s) and the gap record
  threshold (1 s) are constants.

### Tests

Component tests run on the virtual-time event loop of `lib.clock`
(ADR-0010), with a temp `state/` root and a
fake `pw-record`: a script that writes scripted PCM to stdout with set
delays, pauses and exits. A fake `pactl` prints scripted `subscribe` events
and mute states.

| Test                                                                                 | Checks                    |
| ------------------------------------------------------------------------------------ | ------------------------- |
| `anchor`: 24 h of blocks with 50 ppm drift stay within 150 ms of wall time           | `ambient-recording` AC-20 |
| `anchor`: `t0` = first arrival − 100 ms − `capture_latency_ms`                       | AC-20                     |
| `anchor`: clock step +1 s and −1 s; no backward write; one `gap` for +1 s            | AC-20                     |
| Suspend: BOOTTIME jump; `pw-record` restarted; `gap` reason `suspend`                | AC-20                     |
| Writer: offset = time; block split at the hour; hole reads as zeros                  | ADR-0003 format           |
| Fake `pw-record` goes quiet: restart at 10 s; `gap` reason `stall`                   | AC-13                     |
| Quiet for good: watchdog pings stop; `capture-stalled` 60 s after audio end or start | AC-13                     |
| Zeros for 5 s, not muted: `mic-silent` by 6 s; cleared by one sample                 | AC-12                     |
| Zeros while muted: `mic-muted`, no `mic-silent`                                      | AC-12, AC-17              |
| SIGTERM: `stop` records and exit within 1 s; no block after it                       | AC-5                      |
| Restart: `start` has `prev_end` from the file size                                   | `live-transcript` AC-14   |
| Retention: hour start older than 14 days deleted; younger kept; bench kept           | AC-7                      |
| File and directory modes are `0600` and `0700`                                       | AC-15                     |

System tests (root `tests/`, fake `pw-record`):

System tests run in real time with small config values, and check order
and outcomes, not latency (ADR-0010):

- Kill the service and start it again: the hole between the files matches
  `prev_end` and `audio_start` of the new `start` record. The 5 s gap of
  AC-3 is an owner check on a real host.
- Pipeline and inference fakes down: capture writes audio with no gap
  (AC-14).

### Build without hardware

- An agent builds and tests everything above with fakes: the anchor, the
  writer, stall and suspend handling, the mic checks and retention. No
  sound card and no PipeWire are needed.
- The owner runs the capture spike before the build: the `capture_latency_ms`
  default, and that `pw-record` with `stream.capture.sink = true` records
  the monitor.
- The owner checks on a real host: start after login (AC-1), restart gap
  (AC-3), a 24 h
  coverage run (AC-2), upgrade gap (AC-4), headphones keep the channels
  apart (AC-8), output switch (AC-9), a Meet or Teams call sounds the same
  and a Bluetooth headset stays in stereo (AC-10), CPU and disk (AC-11),
  plug and unplug a mic (AC-16), and that audio files are private (AC-15).

## Alternatives considered

### Restart the whole service on any stall

- Simplest: let the watchdog do it all.
- Rejected as the only path: restarting one `pw-record` costs less and
  keeps the other channel running. The watchdog stays as the backstop.

### Sample count only, no re-anchoring

- Rejected: drift and clock steps move audio time away from key times, and
  dictation cuts the wrong audio (AC-20).

### Resample to the wall clock (stretch audio)

- Avoids holes and dropped blocks.
- Rejected: more code for a 150 ms correction every hour or so. A hole of
  150 ms in rare cases is accepted.

### A state file for the stall `since`

- Rejected: the audio file size already gives the end of the newest audio.

### Read the mute flag in control

- Rejected: PipeWire belongs to capture (ADR-0009, rule 3), and capture
  needs the flag anyway for `mic-silent`.

## Later

- **Extra echo-cancelled channel (`mic-ec`)**, deferred (owner decision,
  2026-11-23). No bench path can score it yet, and each extra channel adds
  about 39 GB over 14 days, a subprocess and another watchdog case. A
  bounded spike adds it when bench can pair its text with the raw `mic`
  text of the same case.

## Consequences

- Audio times match wall times within 150 ms, at the cost of rare 150 ms
  holes or drops.
- Capture writes one file per channel and hour, and a few event records
  per day.
- A dead PipeWire shows as Error within 2 min, not as silence.
- The mic stream keeps the mic open all day, so dictation never loses its
  first words to a waking device.
- Retention deletes up to 1 h early.
