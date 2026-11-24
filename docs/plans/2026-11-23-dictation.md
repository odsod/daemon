# Plan: dictation and the session service (stretch, for a dictation trial)

- Status: Done 2026-11-23
- Depends on: [speech](2026-11-23-speech.md) (with its dictation parts),
  [keys](2026-11-23-keys.md) (socket contract),
  [install-and-control](2026-11-23-install-and-control.md)
- Design: [ADR-0013](../adr/0013-dictation.md),
  [ADR-0004](../adr/0004-orchestration-with-systemd.md) (session unit),
  PRD [dictation](../prd/dictation.md)

## Goal

- Hold Left Alt, speak, release: the text pastes at the cursor, through
  the keys service, speech and the clipboard.
- The `session` service runs dictation, and `unmute-stale` cleans up
  after it.

## Scope

- In: everything in ADR-0013 "Module layout" and "Tests"; the
  `dictation` line in `services/session.py`; `session` in
  `install.contract.SERVICES` when the system test passes.
- Out: shortcuts (the other session component). The owner spikes in
  ADR-0013 "Build without hardware" (paste in Chrome, Obsidian and
  Konsole; Meet and Teams mute; clipboard history; latency).

## Steps

1. Pure core with table tests on the virtual-time loop: `loop`, `gate`.
2. `keys_client`, `pactl`, `mute`, `delivery`, `notify`, `last`, with the
   fakes of ADR-0013 "Tests".
3. `service.py`; enable the `dictation` line in `services/session.py` and
   its `cli.py` line in the root `cli.py`. `unmute-stale` command.
4. System test: fake keys socket, fake `pactl`, fake clipboard, real
   speech components with the inference fakes, small timeouts in real
   time. One hold gives one paste of the fixture text; order only.
5. Write in Progress log the owner trial steps: what to test first, how
   to stop it (`systemctl --user stop odsod-daemon-session`), and that
   `unmute-stale` runs on stop.

## Done when

```sh
uv run pytest src/odsod_daemon/components/{dictation,unmute_stale}
uv run pytest tests -k dictation
mise run build
```

## Progress log

- 2026-11-23: Step 1 passed: 21 virtual-time core and gate cases cover
  ordered actions, cancel, disconnect, coverage failure and the hold limit.
- 2026-11-23: Step 2 passed: 28 component checks, desktop command fakes,
  socket codec, selection restore, mute identity and late text reads.

- 2026-11-23: Step 3 passed: session composition, both CLI commands,
  ordered delivery, gate reasons and crash cleanup. 41 component checks pass.

- 2026-11-23: Step 4 system test passed in six cases with real speech and
  inference replay servers. One hold gives one fixture paste before queued
  ambient ASR; cancel and silence give none. Capture writes during the hold.
  A killed session is unmuted by the command without a session restart.
- 2026-11-23: After the system test passed, added session to the shipped
  install list. Checked its graphical-session order and ExecStopPost cleanup.

- 2026-11-23: Step 5 owner trial order, before shipping: install this tested
  build through the owner's normal deployment flow. Confirm capture is active
  and inference is reachable. Start with no meeting and a disposable document.
  Hold Left Alt, speak a short English phrase from the press, then release.
- 2026-11-23: Owner trial: repeat in Chrome, Obsidian and Konsole with the
  Swedish layout and names with å, ä and ö. Check first words, back-to-back
  holds, silence, cancel with another key, and paste while a modifier is held.
  Save text and then an image on CLIPBOARD and PRIMARY; check restoration and
  that KDE clipboard history does not contain the dictation. A failed paste
  must leave the text available for a manual paste.
- 2026-11-23: Owner trial: use a test call in Meet, then Teams. Ask the other
  end to check mute from Dictating until release and recovery within 1 s.
  The first 350 ms before the hold threshold can reach the call. Check that
  capture continues while the meeting is muted, including a second mic.
- 2026-11-23: Owner trial: read `journalctl --user -u odsod-daemon-session -f`.
  The `dictation timing` line gives release, coverage, append, text, paste and
  pasted offsets in ms. Check release-to-pasted at most 2000 ms for holds up
  to 15 s, with ambient backlog and with another host doing batch inference.
  Confirm the text appears in the intended app; the acknowledgement proves
  only that the keys service sent the chord.
- 2026-11-23: Owner stop command:
  `systemctl --user stop odsod-daemon-session`. Its `ExecStopPost` runs
  `odsodctl unmute-stale` on every stop, crash and start-limit failure. This
  restores matching meeting streams even without a session restart. The next
  start clears the mute record and reports `stale-mutes-cleared`. Complete the
  app, meeting, clipboard-history and latency trials before shipping.
- 2026-11-23: Dictation utterance IDs now use the compact ADR-0003 form
  (`dic-20261122T143005.120Z`). Health tests follow the shipped service list.
  Done when passed: 42 component checks, 7 system checks, `mise run build`.
- 2026-11-24: Live rehearsal, 5 runs, `uv run pytest -m live -s
  tests/test_dictation_live.py`, against the real servers with the ambient
  backlog at 0. Release to paste, p50 and max:
  - 10.8 s of speech: 2925 and 3000 ms (ASR 1848 ms, cleanup 858 ms).
  - 18.4 s of speech: 3506 and 3819 ms (ASR 2260 ms, cleanup at the 1 s
    limit, so raw text).
  - Cleanup timeout case: 2056 and 2072 ms (ASR 1840 ms).
  - Silence: no paste, clipboard kept, 5 of 5.
  - AC-3 (2 s) misses on an idle GPU. The loop adds about 120 ms.
- 2026-11-24: Whisper alone (large-v3, idle server): 0.5 s clip 1458 ms,
  5 s 1645 ms, 11 s 1872 ms. The encoder works on a full 30 s window, so
  short speech costs about 1.45 s. A per-request `audio_ctx` sized to the
  clip cuts this to 250 to 1080 ms, but large-v3 then returns empty or
  broken text (English and Swedish). Not usable.
- 2026-11-24: AC-3 options for the owner, with the numbers above:
  1. Accept about 3 s for 10 s of speech (change AC-3 to a 3 s target).
  2. A second whisper server with a smaller model for dictation only: the
     encoder floor drops, quality on Swedish must be benched.
  3. Skip cleanup for dictation: about 2.0 s, with raw ASR text.
  4. VAD for dictation only: trims silence, does not touch the 1.45 s
     floor. Small gain.
- 2026-11-24: Keys port review (agent team): 7 old remap rules frozen as
  `.seq` files, all pass. `io.c`: the escape chord now exits on socket
  events and device drops; a lost keyboard resets the state and lifts
  every held output key, with no fake key-ups through the tap logic (4
  `lost_*.seq`); `EVIOCSCLOCKID` failure skips the device; startup counts
  keyboards only. Open, not fixed: `SIGUSR1` `EINTR`, and the
  `record_main` checks (dev tool).
- 2026-11-24: New tests: AC-1 (53 to 106 ms to Dictating), AC-18, AC-20,
  and the `live` marker (not in `mise run build`).

## Decisions to confirm

- Desktop subprocess tests use real time because the fake executables need
  OS scheduling. Hold timers and the clipboard restore delay use virtual time.
- Each completed hold starts its text wait at once. Clipboard delivery stays
  in hold order, so a later result can meet its deadline behind an older paste.
- The system test gives executable Python pactl fakes a 2 s mute budget.
  Production keeps 150 ms. The test checks order and outcomes, not latency.
- Health tests derive expected units from `install.contract.SERVICES`, so a
  newly shipped service needs no test edit. The owner trial is not run here:
  it needs the real keys service, clipboard and meeting apps.
- 2026-11-23 (orchestrator): `session` is not in `install.contract.SERVICES`.
  Without the keys service it reports `keys-socket-missing` (Error) all day,
  so status and the tray show Error. Ship `session` together with `keys`,
  when the owner switches keyboards. The trial above needs both.
- 2026-11-24: `session` is in `install.contract.SERVICES`. Deploy it only
  after the keys cutover (keys plan, Progress log step 7), so the session
  finds the keys socket at once.
