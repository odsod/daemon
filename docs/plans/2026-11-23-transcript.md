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

- 2026-11-23: Started from `jj new python-rewrite`; `uv sync --extra
  bench` passed. Pure line, echo, gap, local-day and finish rules pass
  33 table checks, ruff and pyright.

- 2026-11-23: Writer and pipeline line implemented. Complete-line writes,
  partial-line repair, echo release, finish/cap immutability, silence,
  a 3,600-line backlog, and missing signals pass (41 component checks).
  Ruff and pyright pass.

- 2026-11-23: Added and mounted note, pin, and transcript commands, with
  stdin notes, optional pin text, day selection, and JSON. Pipeline-down
  notes replay into the day file. All 52 component checks and pyright pass.

## Decisions to confirm

- Mic text shorter than three normalized tokens is never dropped. This
  guard stays in transcript; the shared overlap helper stays unchanged.
- An open capture gap has a closed segment at each completed local
  midnight. This lets logout gaps appear before the day is finished.
- Echo hold age uses the text record timestamp, so restart does not reset
  the hold limit. Missing sys coverage holds mic text up to that limit.

- Replay orders records by write timestamp, with stable stream order for
  ties. Held mic lines append when released. Gap lines append on closure.

- A missing day prints no Markdown and returns an empty JSON lines list.
- Parsed times use the header time zone. In a repeated DST hour, the
  file format has no offset or fold marker; parsing uses the first
  occurrence of that wall-clock time.
