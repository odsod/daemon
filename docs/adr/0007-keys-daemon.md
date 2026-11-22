# ADR-0007: Keys daemon and dictation socket

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
- `EVIOCGRAB` gives the keys daemon every key event. No other process can read
  the physical keyboards.
- Dictation pastes with a simulated key chord. Tools that inject keys from a
  second device race the owner's fingers: a held Alt joins the chord
  ([Handy](../research/handy.md)), so they poll the key state and wait
  ([OpenWhispr](../research/openwhispr.md), [Voxtype](../research/voxtype.md)).
- Many apps show their menu bar on a bare Alt release.

## Decision

### The keys daemon owns all keyboard I/O

- `odsod-keys` moves into this repo as `odsod-daemon-keys`. It keeps all its
  current remapping.
- It adds two jobs: the **dictation key** and **paste injection**.
- No other daemon reads `/dev/input` or writes `/dev/uinput`.

### Dictation key: Left Alt held alone

- Left Alt down: the daemon holds the press back.
- Another key before the hold threshold: the daemon sends Alt and the key, as
  a normal chord (`Alt+Tab` works).
- Released before the threshold: the daemon sends an Alt tap, as today.
- Held alone past the threshold, with a client connected: dictation starts.
  The Alt press never reaches an application, so no menu bar opens.
- Release during dictation: dictation stops.
- Another key during dictation: dictation is cancelled, and the daemon sends
  Alt and the key as a late chord.
- No client connected: Left Alt behaves as a plain Alt. The keyboard never
  depends on the session daemon.
- Right Alt (AltGr) is never a dictation key, because Swedish symbols need it.
- The threshold is a constant in the code, tuned by use.

### Paste: `Shift+Insert` from the virtual keyboard

- On a `paste` request, the daemon waits until no physical modifier is down
  (at most 1.5 s), then sends `Shift+Insert` on its virtual keyboard.
- The daemon tracks the physical key state itself, so no other process polls
  it.
- `Shift+Insert` pastes in GUI apps and in terminals such as Konsole, on every
  layout ([OpenWhispr](../research/openwhispr.md),
  [Handy](../research/handy.md)). No per-app key choice, so no lookup of the
  active window.

### The dictation socket

- Path: `/run/odsod-daemon-keys/dictation.sock`, a Unix stream socket, mode
  `0600`, owned by the owner. `install --system` sets the owner. The daemon
  also checks the peer's user ID (`SO_PEERCRED`).
- One client at a time: the session daemon. A new connection replaces the old
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
- A new message type, or a change to one, needs an ADR. `contracts/` holds the
  Python model of each message.

## Alternatives considered

### evdev in the session daemon

- The common design in other tools (YazSes, hyprwhspr).
- Rejected: the grab hides the physical keyboards. Reading the virtual
  keyboard works, but Alt then reaches the apps, and paste still needs a
  second injection path.

### KDE global shortcut

- No root, no evdev.
- Rejected: a modifier-only shortcut gives press and release together, so no
  hold.

### `ydotool` for paste

- Rejected: one more daemon, its socket and `uinput` access for the owner,
  and it races the held Alt. The keys daemon already has a virtual keyboard.

### RemoteDesktop portal for paste

- KWin injects keys for the app after a one-time consent dialog. No root and
  no daemon ([OpenWhispr](../research/openwhispr.md)).
- Rejected: the dialog comes back when its token is lost, the session must be
  kept open over D-Bus, and it still races the held Alt. It is the fallback if
  the system must ever run without the keys daemon.

### Files instead of a socket

- Rejected: paste is a request with a reply, key events need millisecond
  delivery, and a root daemon must not write into the owner's directories.

### Keys daemon in Python

- One language for the whole repo.
- Rejected: the C daemon works and is small. Key timing must not depend on a
  garbage collector, and a rewrite adds risk for no gain.

### Keys logic inside the session daemon, as root

- Rejected: a root GUI process with inference clients would hold the keyboard
  grab. A bug there could freeze typing.

## Consequences

- One process owns the keyboard. Remaps, the dictation key and paste cannot
  conflict.
- The session daemon needs no input group, no udev rules and no injection
  tool.
- A keys daemon bug can break typing for every app. The daemon stays small,
  and a crash releases the grab, so the raw keyboard comes back at once.
- The dictation key is fixed in code. A change needs a rebuild and
  `install --system`.
- Left Alt taps and chords reach apps a threshold later than before, only
  when Left Alt is pressed alone first.
