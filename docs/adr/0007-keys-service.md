# ADR-0007: Keys service and dictation socket

## Status

Proposed

## Date

2026-11-23

## Context

- The owner's keyboard remapper, `odsod-keys`, lived in the `machine` repo: a
  small C program that runs as a root system service.
  - It grabs every physical keyboard with `EVIOCGRAB`, follows hotplug with
    inotify on `/dev/input/`, and writes remapped events to its own `uinput`
    virtual keyboard.
  - It overloads keys: Caps Lock and Left Ctrl are Ctrl when held and Esc when
    tapped; Space held is a Meta layer.
  - It never holds `Meta_L` across a layer, because KDE opens the launcher on
    a bare `Meta_L` release.
- Dictation needs a hold key. A hold of a modifier alone cannot come from KDE:
  KWin delivers the press and release of a modifier-only shortcut together,
  after the key goes up ([OpenWhispr](../research/openwhispr.md)). Every tool
  with hold-to-talk on Wayland reads evdev.
- `EVIOCGRAB` gives the keys service every key event. No other process can read
  the physical keyboards.
- Dictation pastes with a simulated key chord. Tools that inject keys from a
  second device race the owner's fingers: a held Alt joins the chord
  ([Handy](../research/handy.md)), so they poll the key state and wait
  ([OpenWhispr](../research/openwhispr.md), [Voxtype](../research/voxtype.md)).
- Many apps show their menu bar on a bare Alt release.

## Decision

### Purpose

- Own all keyboard I/O: remap keys for every app from boot, detect the
  dictation key, and send the paste chord.
- PRD: [`keyboard`](../prd/keyboard.md) (all ACs). Supports
  [`dictation`](../prd/dictation.md) AC-2, AC-9, AC-13, AC-14 and
  [`global-shortcuts`](../prd/global-shortcuts.md) (Space as Meta).
- `odsod-keys` moves into this repo as `odsod-daemon-keys`. It keeps all its
  current remapping and adds two jobs: the dictation key and paste
  injection.
- **Port source:** `keys/odsod-keys.c` in the `machine` repo. It mixes logic
  with I/O and wall-clock reads, so the port is a restructure into
  `state.c` and `io.c`, not a file move.
- No other process reads `/dev/input` or writes `/dev/uinput`.

### Components

| Component | Runs in                                           | Job                                                      |
| --------- | ------------------------------------------------- | -------------------------------------------------------- |
| `keys`    | `odsod-daemon-keys.service`, system unit, as root | Remap keys; dictation key; paste chord; dictation socket |

- `SUBSYSTEM = "keys"`. The service is its own C binary,
  `odsod-daemon-keys`, not `odsodctl run`.
- `odsodctl install --system` builds and installs it
  ([ADR-0006](0006-installation.md)). The component owns its system unit
  template.
- `contract.py` exports the package-data names of the C source directory
  and the system unit template as constants (`C_SOURCE_DIR`,
  `SYSTEM_UNIT`). The install subsystem imports them to build and install the service
  without reaching into keys internals (ADR-0010 seam; ADR-0009, rule 2).

### Writes

| Target                         | What                                                        |
| ------------------------------ | ----------------------------------------------------------- |
| `/dev/uinput` virtual keyboard | All remapped key events and the paste chord                 |
| Dictation socket               | `start`, `stop`, `cancel`, `pasted`, `paste-failed` (below) |
| `/run/odsod-daemon-keys/`      | The socket file only (`ExecStartPre=` makes it, owner's)    |
| stdout (journald)              | Device changes, client connects, key latency on request     |

- The keys service keeps no files and writes no health file (ADR-0003). The
  session service reports `keys-socket-missing`
  ([ADR-0013](0013-dictation.md)), and control reports the unit state
  ([ADR-0018](0018-control.md)).

### Reads

| Source                   | What                                                             |
| ------------------------ | ---------------------------------------------------------------- |
| `/dev/input/event*`      | Keyboards, grabbed. Pointer devices, read without a grab         |
| inotify on `/dev/input/` | Hotplug                                                          |
| Dictation socket         | `paste` from the session service; the peer's UID (`SO_PEERCRED`) |

- It reads no config file. All values are constants in the code.

### Outside dependencies

- Linux evdev and uinput ioctls, inotify, Unix sockets. libc only.
- systemd: the system unit, `ExecStartPre=` makes
  `/run/odsod-daemon-keys/` with the owner's uid and gid (not
  `RuntimeDirectory=`: systemd sets its owner again before `ExecStart`),
  `Nice=-20`, `Restart=always`, `OnFailure=` drop-in (ADR-0004).
- `gcc` at install time (`-Wall -Wextra -Werror`), from the host.

### Internal design

#### Module layout

```
components/keys/
├── __init__.py            SUBSYSTEM = "keys"
├── contract.py            socket message models (parse, format);
│                          C_SOURCE_DIR, SYSTEM_UNIT package-data names
├── c/
│   ├── state.h, state.c   pure state machine: events and times in, outputs out
│   ├── io.c               main: evdev, uinput, inotify, socket, clocks
│   └── replay.c           test driver: runs state.c on a sequence file
├── odsod-daemon-keys.service   system unit template
└── tests/
    ├── test_sequences.py  builds replay.c, runs every sequence, compares output
    ├── test_contract.py   message round trips
    └── testdata/*.seq     recorded and written key sequences with expected output
```

- `state.c` holds no I/O and reads no clock. Each input carries its own
  monotonic time, and timers are inputs too ("now is t"). So every case
  replays the same way.
- `io.c` is thin: it reads devices with `poll`, gives events to the state
  machine, writes its outputs, and owns the socket.

#### Remaps (unchanged)

| Key       | Tapped (released within 350 ms, alone) | Held or with another key                        |
| --------- | -------------------------------------- | ----------------------------------------------- |
| Caps Lock | Esc                                    | Ctrl                                            |
| Left Ctrl | Esc                                    | Ctrl                                            |
| Esc       | Caps Lock                              | Caps Lock                                       |
| Space     | Space                                  | Meta layer, once another key comes after 150 ms |
| Left Alt  | Alt tap                                | Alt chord, or dictation (below)                 |
| Right Alt | AltGr, always                          | AltGr; never dictation (Swedish symbols)        |

- Space held alone and released late gives nothing. Keys pressed while
  Space is pending are queued and come after the Space tap, in order
  (`keyboard` AC-4, AC-6).
- The Meta layer never sends a bare Meta press, so the KDE launcher never
  opens by mistake (`keyboard` AC-5).
- The Left Alt stage runs before the other remaps, so a held-back Alt goes
  out before the remap of the next key.

#### Dictation key: Left Alt held alone

- Left Alt down: the service holds the press back.
- Another key before the threshold: the service sends Alt and the key, as
  a normal chord (`Alt+Tab` works).
- Left Alt pressed while another key is already down: Alt goes out at once,
  as a chord. No dictation.
- A pointer button or wheel event while Left Alt is held counts as another
  key: the service sends Alt at once, and no dictation starts. Alt+click,
  Alt+drag and Alt+scroll work. During dictation, it cancels the dictation
  and sends Alt (`keyboard` AC-16).
- Released before the threshold: the service sends an Alt tap, as today
  (`keyboard` AC-7).
- Held alone past the threshold, with a client connected: dictation starts.
  The Alt press never reaches an application, so no menu bar opens
  (`keyboard` AC-8).
- Release during dictation: dictation stops.
- Another key during dictation: dictation is cancelled, and the service
  sends Alt and the key as a late chord (`keyboard` AC-9).
- No client connected: Left Alt behaves as a plain Alt. The keyboard never
  depends on the session service (`keyboard` AC-11). The session service
  disconnects on purpose while recording is paused or no inference host is
  reachable ([ADR-0004](0004-orchestration-with-systemd.md)).
- The threshold is a constant: 350 ms, the same as the tap window. The
  owner tunes it from use.

| State         | Event                       | Output                                   | Next          |
| ------------- | --------------------------- | ---------------------------------------- | ------------- |
| `alt-idle`    | Left Alt down, nothing held | nothing                                  | `alt-pending` |
| `alt-idle`    | Left Alt down, a key held   | Alt down                                 | `alt-chord`   |
| `alt-pending` | key or pointer event        | Alt down, the event                      | `alt-chord`   |
| `alt-pending` | Left Alt up                 | Alt down, Alt up                         | `alt-idle`    |
| `alt-pending` | 350 ms, client connected    | `start <press time>`                     | `alt-dictate` |
| `alt-pending` | 350 ms, no client           | nothing (still a tap or chord candidate) | `alt-pending` |
| `alt-dictate` | Left Alt up                 | `stop <time>`                            | `alt-idle`    |
| `alt-dictate` | key or pointer event        | `cancel <time>`, Alt down, the event     | `alt-chord`   |
| `alt-dictate` | client gone                 | nothing (both sides end the dictation)   | `alt-swallow` |
| `alt-swallow` | Left Alt up                 | nothing                                  | `alt-idle`    |
| `alt-chord`   | Left Alt up                 | Alt up                                   | `alt-idle`    |

- With no client, a long lone hold of Left Alt ends as an Alt tap at the
  release, as a plain Alt would.

#### Paste: `Shift+Insert` from the virtual keyboard

- On a `paste` request, the service waits until no physical modifier is
  down (at most 1.5 s), then sends `Shift+Insert` on its virtual keyboard
  and replies `pasted`. After 1.5 s it replies
  `paste-failed modifier-held` and sends nothing (`dictation` AC-13).
- The service tracks the physical key state itself, so no other process
  polls it.

#### Enter after the paste: a Left Alt tap while the text is pending

- A dictation `stop` opens a 12 s submit window. A Left Alt tap alone in
  the window sends nothing and marks the dictation for Enter. The paste,
  a failed paste, the end of the window, a disconnect or a lost keyboard
  closes it. Outside the window a tap is a plain Alt tap, so normal taps
  get no delay.
- After a marked paste, the service sends `Enter` 150 ms later, so the app
  applies the paste first (Voxtype issue 862: Enter right after a paste can
  land before the text). With a modifier held it waits in 50 ms steps for
  up to 1.5 s after the paste, then drops the Enter: Enter with a modifier
  is another command.
- The session needs no change: the keys service owns the tap and the
  Enter (`dictation` AC-29).
- `Shift+Insert` pastes in GUI apps and in terminals such as Konsole, on
  every layout ([OpenWhispr](../research/openwhispr.md),
  [Handy](../research/handy.md)). No per-app key choice, so no lookup of
  the active window.

#### The dictation socket

- Path: `/run/odsod-daemon-keys/dictation.sock`, a Unix stream socket, mode
  `0600`, owned by the owner. `install --system` sets the owner. The
  service also checks the peer's user ID (`SO_PEERCRED`) and closes any
  other peer.
- One client at a time: the session service. A new connection replaces the
  old one.
- Messages are text lines that end in `\n`. Timestamps are the wall-clock
  time of the key event, UTC, RFC 3339 with milliseconds.

| Direction       | Message                 | Meaning                                                      |
| --------------- | ----------------------- | ------------------------------------------------------------ |
| keys to session | `start <time>`          | Dictation key held past the threshold                        |
| keys to session | `stop <time>`           | Dictation key released                                       |
| keys to session | `cancel <time>`         | Another key pressed during dictation                         |
| session to keys | `paste`                 | Send the paste chord                                         |
| keys to session | `pasted`                | Chord sent                                                   |
| keys to session | `paste-failed <reason>` | Chord not sent, for example a modifier held past the timeout |

- `start` carries the press time, not the threshold time. Dictation cuts the
  utterance from the audio buffer, so no words are lost to the threshold
  (`dictation` AC-2).
- **Clocks:** `io.c` sets each device to the monotonic clock
  (`EVIOCSCLOCKID`) for the state machine, and converts an event's time to
  wall time with the offset `CLOCK_REALTIME − CLOCK_MONOTONIC` read at the
  event. A clock step then never breaks the tap timing.
- **Never block on the socket.** The socket is non-blocking. If a write
  would block, the service drops the client, as if it disconnected. Key
  handling never waits for the session service.
- A disconnect during dictation ends the dictation on both sides. Neither
  side keeps state across a reconnect.
- A new message type, or a change to one, needs an ADR.
  `components/keys/contract.py` holds the Python model of each message.

#### Escape chord

- Both Shift keys and Esc held together for 3 s: the service releases every
  grab and exits. The chord is checked on the physical codes, before any
  remap (Esc is Caps Lock after the remap).
- It is the way out of a bug that swallows keys or holds a modifier without
  a crash. systemd restarts the service after `RestartSec`, and
  `systemctl stop` keeps it off (`keyboard` AC-17).

#### Devices

- A keyboard is a device with `EV_KEY` and letter keys. The service grabs
  it. Its own virtual device is skipped by name.
- A pointer is a device with `BTN_LEFT` or `REL_WHEEL`. The service reads
  it without a grab, so pointer events still reach the apps directly.
- inotify on `/dev/input/` adds new devices within 2 s (`keyboard` AC-12).
  A device that fails a read is closed and dropped.

#### Latency

- Key latency is measured in the process, from the read of an event to the
  write of its output. The service logs a summary on `SIGUSR1`. No bench is
  needed (`keyboard` AC-15).

### Failure modes

| Fault                                  | What the service does                                                                                               | Signal to the owner                         |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| Crash                                  | The kernel releases the grabs; the plain keyboard works; systemd restarts                                           | `OnFailure=` notification after start limit |
| Keys lost or stuck, no crash           | Escape chord releases the grabs and exits                                                                           | systemd restarts it                         |
| `/dev/uinput` cannot be opened         | Exits non-zero before any grab                                                                                      | unit failed → Error                         |
| Device removed or read error           | Drops the device; a lost keyboard releases held keys, stops a dictation, resets overloads and sends a waiting paste | none                                        |
| Client slow (write would block)        | Drops the client                                                                                                    | session reconnects                          |
| Peer with another UID                  | Closes the connection                                                                                               | log line                                    |
| `paste` while a modifier is held 1.5 s | `paste-failed modifier-held`                                                                                        | dictation notifies                          |
| No client                              | Left Alt is plain Alt                                                                                               | session's `keys` reason                     |

- On `SIGTERM` the service releases every grab and sends key-up for every
  key it holds down, so no key stays down (`keyboard` AC-14).

### Config

- None. The keys service reads no file. Constants in `state.h`:

| Constant            | Value  |
| ------------------- | ------ |
| Tap window          | 350 ms |
| Space hold (Meta)   | 150 ms |
| Dictation threshold | 350 ms |
| Paste modifier wait | 1.5 s  |
| Submit window       | 12 s   |
| Enter after paste   | 150 ms |
| Escape chord hold   | 3 s    |

- A change needs a rebuild and `install --system`. Per-app remaps and a
  configurable key are left out (`keyboard` PRD, Not planned).

### Tests

- `mise run build` compiles the service and `replay.c`, then runs every
  sequence in `testdata/`. CI needs no `/dev/uinput`.
- A sequence file lists timed inputs (key, pointer, socket message,
  client connect and disconnect) and the expected outputs. Grammar, one
  event per line, `#` starts a comment, times in ms from the start of the
  file, in order:

```
<ms> in  key  <code> down|up|repeat     # code: Linux KEY_* name
<ms> in  btn  <code> down|up            # BTN_* name, from a pointer device
<ms> in  rel  <code> <value>            # REL_* name, such as REL_WHEEL
<ms> in  sock connect|disconnect
<ms> in  sock paste
<ms> out key  <code> down|up            # sent on the virtual keyboard
<ms> out sock start|stop|cancel <ms>    # second number: the key time sent
<ms> out sock pasted|paste-failed
<ms> out grab release                   # escape chord
```

- `replay.c` feeds the `in` lines to `state.c` and prints the `out` lines.
  The test compares them with the expected `out` lines, exactly.
- `io.c` has a `--record <file>` mode that writes `in` lines from the
  real devices, so the owner can record fast typing for AC-6 later.

#### Build order

1. Port today's remaps from `odsod-keys.c` into `state.c` with no new
   behavior. Write sequences that freeze today's behavior: each one the
   old program's output for the same input. These pass before any change.
2. Then add the Left Alt machine, pointer devices, the socket and the
   escape chord, each with its own sequences.
3. **Owner gate:** before the first `install --system` on a real host, the
   owner tests the escape chord there, with a second way in (SSH) open.

| Sequences                                                 | Checks                 |
| --------------------------------------------------------- | ---------------------- |
| Caps Lock and Left Ctrl tap, hold, chord                  | `keyboard` AC-1, AC-2  |
| Esc gives Caps Lock                                       | AC-3                   |
| Space tap with keys during the tap; Space hold chords     | AC-4, AC-5             |
| Recorded fast typing with rollover                        | AC-6                   |
| Left Alt tap, chord, hold with and without a client       | AC-7, AC-8, AC-11      |
| Key during dictation: `cancel`, Alt and the key           | AC-9; `dictation` AC-9 |
| Right Alt held 1 s: no `start`; AltGr chords pass         | AC-10                  |
| Alt with click, drag and scroll, also past 350 ms         | AC-16                  |
| Escape chord: grabs released, key-ups for held keys       | AC-17, AC-14           |
| `start` carries the press time                            | `dictation` AC-2       |
| `paste` with Alt held 1 s, then 2 s                       | `dictation` AC-13      |
| Client gone during dictation: Alt swallowed, no stuck key | AC-14                  |

- `test_contract.py` checks that every message parses and formats both
  ways, and that the Python models match the table above.
- The latency counter (read to write, in the process) is an owner check on
  a real host with `/dev/uinput` (AC-15), not a CI test.

### Build without hardware

- An agent builds the C code and runs every sequence with no input
  device, no root and no uinput. The session side uses the fake keys socket
  ([ADR-0013](0013-dictation.md)).
- Recorded fast typing (AC-6) needs the owner's keyboard and `--record`.
  Until then, written sequences with rollover cover AC-6.
- The owner checks on a real host: the escape chord first (owner gate),
  hotplug (`keyboard` AC-12), remaps at
  the login screen (AC-13), restart time after a crash (AC-14), the latency
  log (AC-15), and AltGr symbols on the Swedish layout (AC-10).

## Alternatives considered

### evdev in the session service

- The common design in other tools (YazSes, hyprwhspr).
- Rejected: the grab hides the physical keyboards. Reading the virtual
  keyboard works, but Alt then reaches the apps, and paste still needs a
  second injection path.

### KDE global shortcut

- No root, no evdev.
- Rejected: a modifier-only shortcut gives press and release together, so no
  hold.

### `ydotool` for paste

- Rejected: one more background process, its socket and `uinput` access for the owner,
  and it races the held Alt. The keys service already has a virtual keyboard.

### RemoteDesktop portal for paste

- KWin injects keys for the app after a one-time consent dialog. No root and
  no background process ([OpenWhispr](../research/openwhispr.md)).
- Rejected: the dialog comes back when its token is lost, the session must be
  kept open over D-Bus, and it still races the held Alt. It is the fallback if
  the system must ever run without the keys service.

### Files instead of a socket

- Rejected: paste is a request with a reply, key events need millisecond
  delivery, and a root service must not write into the owner's directories.

### Keys service in Python

- One language for the whole repo.
- Rejected: the C program works and is small. Key timing must not depend on a
  garbage collector, and a rewrite adds risk for no gain.

### Keys logic inside the session service, as root

- Rejected: a root GUI process with inference clients would hold the keyboard
  grab. A bug there could freeze typing.

## Consequences

- One process owns the keyboard. Remaps, the dictation key and paste cannot
  conflict.
- The session service needs no input group, no udev rules and no injection
  tool.
- A keys service bug can break typing for every app. The service stays small,
  a crash releases the grab, and the escape chord releases it when the
  service does not crash. Tests on recorded sequences catch most such bugs
  before an install.
- The dictation key is fixed in code. A change needs a rebuild and
  `install --system`.
- A lone Left Alt tap reaches apps at its release, not its press. Apps act
  on the release, so the owner sees no delay. Chords are not delayed: Alt
  goes out with the second key.
- A Left Alt held past the threshold before a chord starts dictation for a
  moment. The second key cancels it and sends the chord.
