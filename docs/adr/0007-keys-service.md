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

### The keys service owns all keyboard I/O

- `odsod-keys` moves into this repo as `odsod-daemon-keys`. It keeps all its
  current remapping.
- It adds two jobs: the **dictation key** and **paste injection**.
- It also reads pointer devices (mice, touchpads), without a grab. Pointer
  events still reach the apps directly. The service only needs to know when
  a button or wheel event happens.
- No other process reads `/dev/input` or writes `/dev/uinput`.

### Dictation key: Left Alt held alone

- Left Alt down: the service holds the press back.
- Another key before the hold threshold: the service sends Alt and the key, as
  a normal chord (`Alt+Tab` works).
- A pointer button or wheel event while Left Alt is held counts as another
  key: the service sends Alt at once, and no dictation starts. Alt+click,
  Alt+drag and Alt+scroll work. During dictation, it cancels the dictation
  and sends Alt.
- Released before the threshold: the service sends an Alt tap, as today.
- Held alone past the threshold, with a client connected: dictation starts.
  The Alt press never reaches an application, so no menu bar opens.
- Release during dictation: dictation stops.
- Another key during dictation: dictation is cancelled, and the service sends
  Alt and the key as a late chord.
- No client connected: Left Alt behaves as a plain Alt. The keyboard never
  depends on the session service. The session service disconnects on
  purpose while recording is paused or no inference host is reachable
  ([ADR-0004](0004-orchestration-with-systemd.md)).
- Right Alt (AltGr) is never a dictation key, because Swedish symbols need it.
- The threshold is a constant in the code: 350 ms, the same as the
  remapper's tap window. The owner tunes it from use.

### Paste: `Shift+Insert` from the virtual keyboard

- On a `paste` request, the service waits until no physical modifier is down
  (at most 1.5 s), then sends `Shift+Insert` on its virtual keyboard.
- The service tracks the physical key state itself, so no other process polls
  it.
- `Shift+Insert` pastes in GUI apps and in terminals such as Konsole, on every
  layout ([OpenWhispr](../research/openwhispr.md),
  [Handy](../research/handy.md)). No per-app key choice, so no lookup of the
  active window.

### The dictation socket

- Path: `/run/odsod-daemon-keys/dictation.sock`, a Unix stream socket, mode
  `0600`, owned by the owner. `install --system` sets the owner. The service
  also checks the peer's user ID (`SO_PEERCRED`).
- One client at a time: the session service. A new connection replaces the old
  one.
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
  utterance from the audio buffer, so no words are lost to the threshold.
- A disconnect during dictation ends the dictation on both sides. Neither side
  keeps state across a reconnect.
- A new message type, or a change to one, needs an ADR. `components/keys/contract.py`
  holds the Python model of each message.

### Code shape and tests

- The C code has two parts:
  - a pure state machine: input events and socket messages in, output
    events and socket messages out, with times as input. No I/O, no clock.
  - a thin I/O layer: evdev, uinput, inotify, the socket and the clock.
- `mise run build` compiles the service and runs the state machine on
  recorded event sequences: chords, taps, holds, Alt with a click,
  dictation, cancel, paste with a held modifier, the escape chord. CI needs
  no `/dev/uinput`.
- Key latency is measured in the process, from the read of an event to the
  write of its output. The service logs it on request. No bench is needed.

### Escape chord

- Both Shift keys and Esc held together for 3 s: the service releases every
  grab and exits. This chord is hard-coded and handled before any remap.
- It is the way out of a bug that swallows keys or holds a modifier without
  a crash. systemd restarts the service after `RestartSec`, and
  `systemctl stop` keeps it off.

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
