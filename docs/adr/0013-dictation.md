# ADR-0013: Dictation

## Status

Proposed

## Date

2026-11-23

## Context

- The owner holds Left Alt, speaks and releases. The text must appear at
  the cursor in 2 s, in GUI apps and terminals, with the Swedish layout
  (`dictation` AC-3, AC-5).
- The keys service gives the key events and sends the paste chord over one
  Unix socket ([ADR-0007](0007-keys-service.md)). Key times are wall-clock
  times. Capture's buffer has audio from before the press, so no word is
  lost to the hold threshold (ADR-0002, principle 7).
- Speech does the ASR and cleanup ([ADR-0012](0012-speech.md)). Dictation
  only writes the utterance and waits for its text in `text/`.
- The meeting must not hear the dictation. No studied tool mutes the
  meeting's mic stream ([alternatives](../research/alternatives.md)). Vibe
  Typer mutes playback streams and restores only what it changed
  ([Vibe Typer](../research/vibetyper.md)).
- A crash must never leave the meeting deaf to the owner (`dictation`
  AC-17).
- This ADR takes the dictation section out of
  [ADR-0005](0005-components-and-implementation.md) and deepens it.

## Decision

### Purpose

- Run the dictation loop: key events in, a muted meeting while the owner
  speaks, a dictation utterance, then the cleaned text pasted at the
  cursor with the clipboard restored.
- PRD: [`dictation`](../prd/dictation.md) AC-1, AC-2, AC-7, AC-9 to AC-20,
  AC-23. Speech covers the ASR and cleanup criteria (AC-3, AC-4, AC-6,
  AC-8, AC-21, AC-22, AC-24).

### Components

| Component      | Runs in                                      | Job                                                            |
| -------------- | -------------------------------------------- | -------------------------------------------------------------- |
| `dictation`    | `session` service, `odsodctl dictation last` | The loop: socket, mute, utterance, text wait, paste, status    |
| `unmute-stale` | command `odsodctl unmute-stale`              | Unmute the streams in `run/muted.json` after the session stops |

- Both have `SUBSYSTEM = "dictation"`.
- `unmute-stale` runs as `ExecStopPost=` of the session unit (ADR-0004). It
  imports only `dictation.contract` and `dictation.pactl`, which use the
  standard library and `lib/`. The `dictation` package's `__init__.py`
  imports its loop lazily inside `run()`, so this import stays light.

### Writes

| Path                                     | Kind     | Fields beyond the seam                                                                     |
| ---------------------------------------- | -------- | ------------------------------------------------------------------------------------------ |
| `state/utterances/dictation/<day>.jsonl` | Stream   | `press`: key press time. `release`: key release time (or the limit). `muted`: stream count |
| `run/status.json`                        | Document | `audio_start` while `dictating` (request Q1)                                               |
| `run/muted.json`                         | Document | none                                                                                       |
| `run/health/session.json`                | Document | Faults `mute-failed`, `stale-mutes-cleared`, `keys-socket-missing`                         |
| Keys socket                              | Messages | `paste` (ADR-0007)                                                                         |
| Clipboard (CLIPBOARD and PRIMARY)        | Wayland  | The text during a paste; the saved content after it                                        |
| Desktop notifications                    | D-Bus    | Failed dictation, failed paste                                                             |

- The utterance is `dic-<UTC start>`, channel `dic`, `start` = press minus
  `preroll_ms`, `end` = release plus `postroll_ms` (ADR-0003).
- The session service shares its health file with shortcuts
  ([ADR-0008](0008-shortcuts-and-kwin-script.md)). Each component sets and
  clears only its own codes.
- `unmute-stale` writes nothing. Only `dictation` writes `run/muted.json`.

### Reads

| Path or source             | Relied on                                                                      |
| -------------------------- | ------------------------------------------------------------------------------ |
| Keys socket                | `start`, `stop`, `cancel` with wall-clock times; `pasted`, `paste-failed`      |
| `state/audio/mic/`         | File size only: wait until it covers `end` (`lib.audio`)                       |
| `state/text/`              | `input`, `outcome`, `text`, `raw`                                              |
| `run/muted.json`           | `streams` (`id`, `app`): at dictation start and in `unmute-stale`              |
| systemd unit state         | `odsod-daemon-capture.service` active (`lib.systemd`)                          |
| Inference host             | Reachable (`lib.inference.reachable`, request Q5); `lib.power.on_mains()`      |
| `config/config.json`       | Section `dictation`; `common.inference.whisper_url`                            |
| PipeWire (through `pactl`) | Source outputs: ID, `application.name`, `node.name`, mute flag, monitor or not |

- `odsodctl dictation last` reads `utterances/dictation/` and `text/` only.

### Outside dependencies

- The keys service and its socket `/run/odsod-daemon-keys/dictation.sock`
  (ADR-0007).
- `pactl` (`pulseaudio-utils` on `pipewire-pulse`) to list, mute and unmute
  source outputs.
- `wl-clipboard` (`wl-copy`, `wl-paste`) with `--sensitive` support, on
  KWin's data-control protocol. Spike: paste and restore in Chrome,
  Obsidian and Konsole.
- `notify-send` (libnotify) for desktop notifications.
- Meet and Teams behavior on a muted capture stream. Spike before ship
  (ADR-0005, Consequences).

### Internal design

#### Module layout

```
components/dictation/
├── __init__.py    SUBSYSTEM = "dictation"; run(config) imports service lazily
├── contract.py    DictationUtterance, Status, Muted
├── config.py      DictationConfig
├── loop.py        pure state machine: events and times in, actions out
├── service.py     wires the loop to the socket, files, pactl and the clipboard
├── keys_client.py socket connect, line codec (models from keys.contract)
├── gate.py        pure: capture active, inference reachable, battery → connect or not
├── pactl.py       list, mute and unmute source outputs (stdlib only)
├── mute.py        mute set: record, mute, unmute; stale cleanup
├── delivery.py    save clipboard, write text, paste, restore
├── notify.py      notify-send
├── last.py        newest dictation and its text
├── cli.py         typer app: `odsodctl dictation last`
└── tests/         fake keys socket, fake pactl, fake wl-copy and wl-paste
components/unmute_stale/
├── __init__.py    SUBSYSTEM = "dictation"
├── cli.py         `odsodctl unmute-stale`
└── tests/
```

#### Connection gate

- Every 2 s, `gate.py` decides whether to hold the keys socket open:
  - capture unit active (it is stopped while paused, ADR-0004);
  - the whisper URL is reachable: TCP connect within 1 s, checked every
    5 s;
  - not (on battery and the whisper URL is a loopback address), the same
    rule as speech ([ADR-0012](0012-speech.md)).
- All true: connect. Any false: disconnect, so Left Alt is a plain Alt
  (ADR-0007), and set `keys` in `run/status.json` to `paused` or
  `no-inference` (`dictation` AC-23).
- The gate never disconnects during a dictation. It waits until the loop
  is idle.
- The socket path is checked each 2 s, connected or not. Missing, or a
  failed connect for 10 s: fault `keys-socket-missing` (Error) and `keys:
  no-socket`. Reconnect with backoff 1 s doubling to 10 s. This gives
  Error within 10 s of a keys stop (`dictation` AC-15).

#### States

`loop.py` is a pure state machine. Its inputs are socket messages, timer
expiries and results of actions. Its outputs are actions. `service.py`
runs the actions.

| State       | Entered on                | Leaves on                                                                                |
| ----------- | ------------------------- | ---------------------------------------------------------------------------------------- |
| `offline`   | Gate false, socket lost   | Gate true and connected → `idle`                                                         |
| `idle`      | Connected, last hold done | `start t` → `dictating`                                                                  |
| `dictating` | `start t`                 | `stop t` → `closing`; `cancel t` or disconnect → `idle`; `max_s` after press → `closing` |
| `closing`   | `stop`, or the limit      | Utterance appended and status idle → `idle`                                              |

A finished hold moves to a **delivery queue**, which runs beside the
states, so a new hold can start while an older text is on its way.

At service start: read `run/muted.json`. If it is not empty, a crash
left mutes: unmute them (below), write `streams: []`, and set
`stale-mutes-cleared` until 10 min pass or the next dictation (ADR-0004).
Then write `run/status.json` with `mode: idle`.

On `start t` (`t` is the press time):

1. Mute (below), within `mute_timeout_ms` (150 ms).
2. Write `run/status.json`: `mode: dictating`, `since: now`,
   `audio_start: t − preroll_ms`. Mute comes first, so the meeting hears
   nothing from the moment the tray shows Dictating (`dictation` AC-10).
   The tray shows it at most about 200 ms after the threshold, if it
   watches the file (request Q6; `dictation` AC-1).

On `stop t`:

1. Unmute at once (`dictation` AC-10: the meeting hears the owner again in
   1 s).
2. Wait until `mic` covers `t + postroll_ms` (at most 2 s).
3. Append the utterance, then write `mode: idle`. This order lets
   segmentation trust `idle` (ADR-0012, dictation mask).
4. Queue a delivery for the utterance ID, with deadline `t + text_timeout_s`.

On `cancel t` or a disconnect while dictating: unmute, write `mode: idle`,
append nothing (`dictation` AC-9). The audio stays ambient.

At `max_s` (120 s) after the press, the loop acts as on `stop` at that
time. A later `stop` is ignored. Whisper stays within its time budget.

If the `mic` file does not cover the end in 2 s (capture stalled), the hold
fails: notification "dictation failed", no utterance.

#### Mute

- `pactl --format=json list source-outputs`. Select every stream that:
  - records a source that is not a monitor (so screen recorders of system
    sound keep working);
  - is not capture's own (`application.name = odsod-daemon-capture`);
  - is not muted already.
- Write the selection to `run/muted.json` (atomic) before muting, so a
  crash between the two still leaves a record.
- Mute all selected streams in parallel with `pactl
  set-source-output-mute <id> 1`.
- All streams, not only those on the default mic: a meeting app may use
  another mic than the default, and the owner's voice reaches every mic in
  the room.
- **Unmute:** for each recorded stream, unmute only if a stream with that ID
  still exists with the same `application.name`. PipeWire can reuse an ID
  for a new stream, and the check keeps the owner's own mutes. A stream
  that ended is not an error. Then write `streams: []`.
- **Fail open:** a failed or late mute sets `mute-failed` (Warning).
  Dictation goes on (`dictation` AC-16). The next dictation with a full
  mute clears it.
- **`unmute-stale`:** the same unmute, run by `ExecStopPost=` after every
  stop of the session service, crash and start limit included. It leaves
  the file as it is; the next service start sees it, clears it and sets
  `stale-mutes-cleared` (ADR-0004). The meeting hears the owner again
  within a few seconds of a crash (`dictation` AC-17).

#### Text wait and delivery

- Delivery follows `text/` (`lib.streams.follow`, request Q4) for a record
  with `input` = the utterance ID.
- Deliveries run in hold order, one at a time.

| Text record                              | Action                                              |
| ---------------------------------------- | --------------------------------------------------- |
| `ok`, text not empty                     | Paste                                               |
| `empty`, or `ok` with empty text         | Nothing (`dictation` AC-7)                          |
| `failed`, `expired`, or none by deadline | Notification "dictation failed" (`dictation` AC-18) |

- Text that arrives after the deadline is never pasted and never touches
  the clipboard. `odsodctl dictation last` prints it (`dictation` AC-19).
- **Paste** (OpenWhispr, Handy):
  1. Wait while the loop is `dictating`: the owner holds Left Alt, so a
     paste now would fail.
  2. Save CLIPBOARD and PRIMARY: the first of `text/plain;charset=utf-8`
     or the first offered type, with `wl-paste --type`. Content over
     10 MB is not saved and not restored.
  3. Write the text to both with
     `wl-copy --sensitive --type 'text/plain;charset=utf-8'` (and
     `--primary`). KDE's clipboard history skips it (`dictation` AC-12).
  4. Send `paste`. The keys service waits for released modifiers, up to
     1.5 s (`dictation` AC-13), and sends `Shift+Insert`.
  5. On `pasted`: after `restore_delay_ms` (500 ms), restore both
     selections, but only if each still holds the dictated text. An empty
     saved selection is cleared (`dictation` AC-12).
  6. On `paste-failed`, or no reply in 3 s: leave the text on the
     clipboard and notify "paste failed: the text is on the clipboard"
     (`dictation` AC-20).
- Paste with `Shift+Insert` works on every layout and in Konsole, so
  delivery never asks which window has focus (`dictation` AC-5).

#### Status

- `run/status.json`: `mode` (`idle`, `dictating`), `since`, `keys`
  (`connected`, `paused`, `no-inference`, `no-socket`), and `audio_start`
  while dictating.
- Written at service start (`idle`) and on every change. The tray and
  `odsodctl status` read it ([ADR-0018](0018-control.md)); segmentation
  reads `mode` and `audio_start`.

#### `odsodctl dictation last`

- Reads the newest record in `utterances/dictation/` (today, else
  yesterday) and its `text` record. Prints the text, the press time, and
  `raw` or `late` marks. With no text yet: `pending`. `--json` prints all
  fields.

### Failure modes

| Fault                                                      | What dictation does                                                  | Code / signal                   |
| ---------------------------------------------------------- | -------------------------------------------------------------------- | ------------------------------- |
| Keys socket missing or refused                             | Reconnect with backoff; Left Alt is plain Alt                        | `keys-socket-missing` (Error)   |
| Capture stopped (pause) or not active                      | Disconnect                                                           | `keys: paused`                  |
| Inference host unreachable, or battery with a loopback URL | Disconnect                                                           | `keys: no-inference`            |
| Mute fails or exceeds 150 ms                               | Dictation goes on                                                    | `mute-failed` (Warning)         |
| Crash during a dictation                                   | `unmute-stale` runs from `ExecStopPost=`; next start clears the file | `stale-mutes-cleared` (Warning) |
| `mic` does not cover the release in 2 s                    | No utterance; notification                                           | notification                    |
| No text in 10 s, or `failed` text                          | Notification; late text only in `dictation last`                     | notification                    |
| Paste fails or no reply in 3 s                             | Text stays on the clipboard; notification                            | notification                    |
| Clipboard read or write fails                              | Notification "dictation failed"; no paste                            | notification                    |
| Socket closes during a dictation                           | As `cancel`                                                          | none                            |
| Unexpected exception                                       | The service exits; systemd restarts it; `unmute-stale` runs          | unit state                      |

### Config

Section `dictation`:

```json
{
  "dictation": {
    "preroll_ms": 300,
    "postroll_ms": 150,
    "max_s": 120,
    "text_timeout_s": 10,
    "mute_timeout_ms": 150,
    "restore_delay_ms": 500,
    "probe_interval_s": 5
  }
}
```

- The 10 s text wait is an owner decision (PRD). The hold threshold lives
  in the keys service, not here (ADR-0007).
- The dictation language, presence gate and cleanup limit are in the
  `speech` section ([ADR-0012](0012-speech.md)).

### Tests

Component tests use a fake keys socket (a Unix socket server that plays
scripted messages with times), a fake `pactl`, fake `wl-copy` and
`wl-paste` that keep the selections in a temp dir, fake `notify-send`, the
fake clock and a temp root. `text/` records are written by the test.

| Test                                                                          | Checks           |
| ----------------------------------------------------------------------------- | ---------------- |
| Loop: start → status `dictating` within 200 ms of fake time, after mute       | AC-1, AC-10      |
| Utterance starts at press minus pre-roll, not at the threshold                | AC-2             |
| Order: utterance appended before status `idle`                                | AC-24 (via mask) |
| `empty` text pastes nothing; clipboard untouched                              | AC-7             |
| Cancel: no utterance, no paste, streams unmuted                               | AC-9             |
| Mute selects non-monitor, non-capture, unmuted streams; records first         | AC-10            |
| Unmute skips an ID reused by another app; tolerates ended streams             | AC-10, AC-17     |
| Stop → unmute before coverage wait                                            | AC-10            |
| Capture fake writes during dictation; audio has no gap                        | AC-11            |
| Restore after 500 ms only if the clipboard still holds the text               | AC-12            |
| `paste` waits for keys' `pasted`; `paste-failed` leaves text and notifies     | AC-13, AC-20     |
| Fake socket gone: `keys-socket-missing` within 10 s                           | AC-15            |
| `pactl` fails: dictation still pastes; `mute-failed` set                      | AC-16            |
| Crash with `muted.json` set: `unmute-stale` unmutes; service start sets fault | AC-17            |
| No text in 10 s: notification; late text never touches the clipboard          | AC-18            |
| `dictation last` prints late text; `--json`                                   | AC-19            |
| Capture inactive or inference unreachable: socket closed; `keys` reason       | AC-23            |
| Paste waits while a new hold is active                                        | AC-13            |

System tests (root `tests/`): keys fake, capture fake, speech with fake
servers and dictation together. Hold, speak (fixture), release: text in the
clipboard fake within 2 s of fake time while ambient work is queued (AC-4).
Session killed during a dictation: streams unmuted by `unmute-stale` with
no session restart (AC-17). Session down: keys fake reports no client, and
the keys state machine gives plain Alt (AC-14, ADR-0007 tests).

### Build without hardware

- An agent builds and tests the loop, the gate, mute, delivery and both
  commands with the fakes above. No keyboard, mic, PipeWire or Wayland
  session is needed.
- The owner checks on a real host: paste in Chrome, Obsidian and Konsole
  with the Swedish layout (AC-5), the Meet and Teams mute (AC-10), and the
  clipboard history (AC-12). These spikes run before dictation ships.

## Alternatives considered

### Mute only streams on the default mic

- Rejected: a meeting app may record another mic. All non-monitor capture
  streams cover every case with the same code.

### Mute at the key press, not at the threshold

- The meeting would hear nothing at all.
- Rejected (owner decision, 2026-11-23): every Alt chord would cut the
  meeting mic for a moment.

### Paste late text when it arrives

- Rejected (`dictation` AC-18): the owner has moved on, and the text would
  land in the wrong place.

### Hold the clipboard as text only

- Rejected: an image on the clipboard would be lost. Saving one MIME type
  covers the common cases; a multi-type clipboard keeps only its first
  type, which is accepted.

### `unmute-stale` clears `run/muted.json`

- Rejected: the file then has two writers. Dictation clears it at its next
  start, and the Warning tells the owner what happened.

## Consequences

- Dictation depends on the keys service, capture and a reachable inference
  host. Without one of them, Left Alt is plain Alt and the tray says why.
- A muted stream can stay muted for a few seconds after a crash, until
  `ExecStopPost=` runs.
- Dictations longer than 2 min are cut at 2 min.
- A multi-type clipboard (such as rich text) comes back with only its first
  type after a dictation.
- No trailing space or other text is added to the dictated text. The owner
  can ask for it later if back-to-back dictations need it.
