# Plan: dictation and the session service (stretch, for a dictation trial)

- Status: Draft
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

## Decisions to confirm

- Desktop subprocess tests use real time because the fake executables need
  OS scheduling. Hold timers and the clipboard restore delay use virtual time.
- Each completed hold starts its text wait at once. Clipboard delivery stays
  in hold order, so a later result can meet its deadline behind an older paste.
