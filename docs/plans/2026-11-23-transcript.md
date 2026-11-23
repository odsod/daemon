# Plan: transcript, note and pin

- Status: Done 2026-11-23
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

- 2026-11-23: Drain mode uses the same writer flush, without followers
  or waits. Ready lines and eligible finishes drain; mic lines stay held
  until coverage or the hold limit permits them. All 54 component checks,
  ruff, and pyright pass.

- 2026-11-23: Four process-kill system tests pass: fixture audio through
  speech and transcript, restart at each output stage, exactly one line
  per text record, one dictation line, no duplicate mic line, and no
  signals stream required. A failing cap-range precision check now passes
  after comparing timestamp instants instead of timestamp strings.
- 2026-11-23: Isolated smoke passed with fake inference and the English
  audio fixture: the three speech drains followed by `uv run odsodctl run
  transcript --once` produced one day file, 2 text records, and 2 matching
  lines. JSON reading also passed. The temp `ODSOD_DAEMON_ROOT` was deleted.
- 2026-11-23: Final Done when gates pass: 56 component tests, 4 transcript
  system tests, and `mise run build` (ruff, formatting, pyright, import
  rules, keys compile, and 437 tests; one timing test deselected). All
  five work steps have local commits. No deployment or remote writes.
- 2026-11-23: Fix: the 3-token echo guard moves from `transcript/echo.py`
  into `lib.textmatch.overlap`, as ADR-0015 says. interactions now keeps
  short owner replies such as "Yes" too. The guard runs before the
  containment rule.
- 2026-11-23: Fix: an open recording-off range that crosses local midnight
  now gives the finished day its pre-midnight gap line, once (ADR-0015 Gaps,
  `live-transcript` AC-14). The cut part is keyed by its midnight end, so
  the closed range after the morning restart matches it and writes no
  duplicate. An open range is never a `restart`.

## Decisions to confirm

- Mic text shorter than three normalized tokens is never dropped. This
  guard stays in transcript; the shared overlap helper stays unchanged.
- An open capture gap stays open across local midnight. Gap lines are
  written only when capture restarts, with one segment per local day.
- Echo hold age uses the text record timestamp, so restart does not reset
  the hold limit. Missing sys coverage holds mic text up to that limit.

- Replay orders records by write timestamp, with stable stream order for
  ties. Held mic lines append when released. Gap lines append on closure.

- A missing day prints no Markdown and returns an empty JSON lines list.
- Parsed times use the header time zone. In a repeated DST hour, the
  file format has no offset or fold marker; parsing uses the first
  occurrence of that wall-clock time.

- Publishing remains outside this plan. The tests check the finished
  stream as the delivery seam, without starting publishing.
