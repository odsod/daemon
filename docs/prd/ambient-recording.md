# PRD: Ambient recording

- Status: Accepted
- Updated: 2026-11-23
- Design: [ADR-0002](../adr/0002-high-level-architecture.md),
  [ADR-0003](../adr/0003-filesystem-interface.md),
  [ADR-0004](../adr/0004-orchestration-with-systemd.md),
  [ADR-0005](../adr/0005-components-and-implementation.md)

## Problem

- The owner forgets most of what is said in meetings, calls and talks at the
  desk: decisions, promises, names and the reasons behind them.
- The owner wants a second brain: a record of what was said that the owner
  can search, and that AI agents can use as context for their work.
- What is worth keeping is often clear only later. So the record must start
  before the owner knows that a talk matters, with no action from the owner.
- Speech-to-text makes errors. For two weeks after a talk, kept audio lets
  the system redo its text with a better model or prompt, and lets the owner
  compare models on their own speech.

## Behavior

- Owner logs in → mic and system audio record, with no action.
- Owner talks, or a meeting plays → the owner's voice and the other side are
  kept apart (mic and system audio).
- Owner speaks into a mic → recording captures that mic. Owner plugs in a
  mic or picks another input → recording follows it, with no action.
- Owner switches the output device (speakers, headset, HDMI) → system audio
  follows the new default output.
- Owner mutes the mic (mute key or KDE) → the tray shows a neutral "mic
  muted" mark, not an alarm.
- Owner or an agent pauses (tray or `odsodctl pause`) → recording stops, and
  the tray and `odsodctl status` show Paused. A pause has no timer. Resume
  (tray or `odsodctl resume`), a logout, a reboot or the start of the next
  local day starts recording again.
- Owner runs `odsodctl status` → sees whether recording runs, and when the
  newest audio was written.
- Audio stays on the host for 14 days, then is deleted. Transcripts and
  documents stay. Audio in a bench case stays until the case is deleted
  (`benchmarking`).
- Meetings never notice the recorder: no change in call sound or device mode.

### When something fails

- Recording crashes or stalls → it restarts by itself. The owner sees nothing
  unless it keeps failing; then the tray shows Error.
- The mic delivers only digital silence, and the owner did not mute it → the
  tray shows Error.
- The mic in use disappears → recording moves to another available mic.
- The inference host or the pipeline is down → recording goes on. Text
  catches up from the stored audio later.
- No graphical session (a host reached over SSH) → recording goes on.
  `odsodctl status` shows its state.

## Acceptance criteria

Timings, coverage and CPU use are proposed targets for the owner to confirm.
Disk use follows from the audio format and the two channels: about 77 GB per
host for 14 days, which the owner accepts.

1. **AC-1** Recording of both channels starts at most 10 s after login.
   _Check: manual._
2. **AC-2** Outside pauses, recorded audio covers at least 99.9% of a 24 h
   day (gaps at most 90 s in total). _Check: manual, 24 h run._
3. **AC-3** A crash of the capture service leaves a gap of at most 5 s.
   _Check: system test._
4. **AC-4** An upgrade leaves a gap of at most 10 s. _Check: manual._
5. **AC-5** At most 1 s after Pause, from the tray or `odsodctl pause`, no
   new audio is recorded, and the tray and `odsodctl status` show Paused.
   _Check: system test._
6. **AC-6** Resume, from the tray or `odsodctl resume`, starts recording
   again in at most 5 s. _Check: system test._
7. **AC-7** Audio older than 14 days is gone at most 1 h later. Transcripts
   and documents stay. _Check: system test._
8. **AC-8** With headphones, sound played on the host is only in system
   audio, and the owner's voice is only in mic audio. _Check: manual._
9. **AC-9** After a switch of output device, system audio records from the
   new device in at most 5 s. _Check: manual._
10. **AC-10** In a Meet or Teams call, the other side hears no difference with
    recording on or off, and a Bluetooth headset stays in stereo mode.
    _Check: manual._
11. **AC-11** Recording uses at most 2% of one CPU core on average and at
    most 5.6 GB of disk per day. _Check: bench._
12. **AC-12** Digital silence on a mic that the owner did not mute, for 60 s,
    shows Error in the tray at most 70 s after it starts. _Check: system
    test._
13. **AC-13** If audio stops advancing, recording restarts in at most 60 s.
    If it does not recover, the tray shows Error in at most 2 min. _Check:
    system test._
14. **AC-14** One hour with the inference host down leaves no gap in the
    audio. _Check: system test._
15. **AC-15** Only the owner's user account can read recorded audio. Audio
    leaves the host only in requests to the configured inference host.
    _Check: manual._
16. **AC-16** After the owner plugs in a mic or picks another input,
    recording captures that mic in at most 5 s. When the mic in use
    disappears, recording captures another available mic in at most 5 s.
    _Check: manual._
17. **AC-17** When the owner mutes the mic, the tray shows "mic muted" in at
    most 5 s, and shows no Error. _Check: system test._
18. **AC-18** A pause still on at 00:00 local time ends then. Recording
    starts again in at most 5 s. _Check: system test._

## Boundaries

### Covered by other PRDs

- The daily transcript, notes and pins → the `live-transcript` PRD.
- Interaction documents, speaker names and summaries → the
  `interactions-and-publishing` PRD.
- Dictation, which uses the same audio → the `dictation` PRD.
- The meeting's echo in the mic: recording keeps the raw mic, and the
  transcript PRDs remove duplicate text.
- Tray states and `odsodctl status` in full → the `health-and-control` PRD.

### Not planned

- Recording before login. Capture runs in the owner's session (ADR-0004).
- Audio shared between hosts. Hosts share only inference servers (ADR-0002).
- Channels beyond the mic and system audio, such as per-app capture
  (ADR-0005).
- Automatic pause when the screen locks. While the host runs, the system
  records and transcribes as much as it can (owner decision, 2026-11-23).
- Audio playback and export, for now. The stored audio lets a later feature
  play or export any range of the last 14 days, with no change to recording
  (ADR-0003).

## Open questions

- None.
