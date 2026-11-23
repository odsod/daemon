# Plan: transcript, note and pin

- Status: Draft
- Depends on: [speech](2026-11-23-speech.md) (contracts only; the pure
  parts can start after [python-scaffold](2026-11-23-python-scaffold.md))
- Design: [ADR-0015](../adr/0015-transcript.md),
  PRD [live-transcript](../prd/live-transcript.md)

## Goal

- The `transcript` component writes the daily transcript and the
  `finished/transcript/` record from `text/`, signals and user events.
- `odsodctl note`, `pin` and `transcript` work.

## Scope

- In: everything in ADR-0015 "Module layout" and "Tests".
- Out: participant lines (rejected in ADR-0015). Publishing.

## Steps

1. Pure core with table tests: lines, day assignment, echo drop, gaps,
   finish (ADR-0015 "Internal design").
2. Main loop and restart rules; enable its line in `services/pipeline.py`.
3. `note`, `pin` and `transcript` commands, with `--json`; enable their
   lines in the root `cli.py`.
4. `--once`.
5. System test: fixture audio through speech and transcript to one day
   file, with a kill between steps. A signals stream that does not exist
   yet must not block the day file.

## Done when

```sh
uv run pytest src/odsod_daemon/components/{transcript,note,pin}
uv run pytest tests -k transcript
mise run build
```

- `odsodctl run transcript --once` on a temp root with speech output gives
  one day file whose lines match the `text` records.

## Progress log

## Decisions to confirm
