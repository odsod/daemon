# Plan: interactions (stretch)

- Status: Done 2026-11-23
- Depends on: [transcript](2026-11-23-transcript.md),
  [signals](2026-11-23-signals.md),
  [inference-recordings](2026-11-23-inference-recordings.md)
- Design: [ADR-0016](../adr/0016-interactions.md),
  PRD [interactions](../prd/interactions.md)

## Goal

- The `interactions` component cuts the day into interactions and writes
  one document with a summary for each.

## Scope

- In: everything in ADR-0016 "Module layout" and "Tests".
- In: `meeting_cutoffs` and its AC-2 boundary test (ADR-0016).
- Out: diarization, chapters, and meeting profile settings beyond the
  per-code silence cutoff.
  Reference summaries (owner, bench).

## Steps

1. Pure core with table tests: boundaries, pending and the gate, the batch
   pass, the summary schema and chunking.
2. Summary requests against the fake llama-server with the recorded
   replies.
3. `--once`; enable its line in `services/pipeline.py`.
4. System test with the fake CDP: one document with named `sys` lines
   (`interactions` AC-3) and one `finished` record.
5. Real-host smoke: one summary of a generated Swedish transcript against
   8179 on a temp root. Write the result shape in Progress log.

## Done when

```sh
uv run pytest src/odsod_daemon/components/interactions
uv run pytest tests -k interactions
mise run build
```

## Progress log

- 2026-11-23: Step 1: added pure boundaries, coverage across recording-off
  ranges, meeting cutoffs, speaker overlap, echo removal, summary validation,
  chunks, rendering, the gate and crash-safe batch writes. All 17 component
  tests, Ruff and component Pyright pass.

- 2026-11-23: Step 2: added schema-bound llama requests, shipped Jinja
  prompts, glossary and prompt overrides, setup hashes and map-reduce.
  Recorded summary and error replies pass; 44 interaction/inference tests
  and Pyright pass.

- 2026-11-23: Step 3: enabled interactions in pipeline and added `--once`
  draining, sorted stream views, boundary invalidation, the power/pending/host
  gate, bounded retries and the waiting warning. Fixed per-channel capture
  coverage after a failing regression check. All 26 component tests, Ruff
  and component Pyright pass.

- 2026-11-23: Step 4: CLI system fixtures use the signals, speech-text and
  transcript-finished contracts directly. Four system tests pass: named
  Swedish lines, inline note, English summary, no dictation, one document
  and one finished record after two drains, plus malformed/schema/HTTP
  failures. System-test Ruff and Pyright pass.

- 2026-11-23: Step 5 first smoke: 8179 produced one document, one ok and
  one finished record from six generated Swedish lines. The overview was
  English, but point text was Swedish, so the AC-5 smoke check failed.
  Made English explicit for the title, overview and every point. Temporary
  root and HOME were deleted.

- 2026-11-23: Step 5 repeat smoke passed against local 8179: one document,
  one `ok` interaction, one `finished` record, six speech lines. Title:
  "Database Migration to PostgreSQL" (four words). Summary: two English
  overview sentences and six English points under Decided, Problem and Next.
  Swedish transcript stayed unchanged. Front matter: type, id, host, start,
  end, timezone, meeting, participants and title. Participants: Oscar and
  Others; meeting: null; timezone: Europe/Stockholm with +01:00 times.
  Setup: default plus the rendered-prompt SHA-256. Temporary root and HOME
  were deleted after both smoke runs.

- 2026-11-23: Done when passed after the prompt correction: component
  pytest 26 passed; system pytest `-k interactions` 4 passed; `mise run
  build` 453 passed, 1 timing test deselected. Lint, formatting, types,
  import rules and C compilation passed. Plan Status left unchanged.
- 2026-11-23: Fix: `lib.textmatch.overlap` now gives 0.0 when the shorter
  text has fewer than 3 tokens (ADR-0015). A short owner reply next to
  matching `sys` text stays in the document.

## Decisions to confirm

- Front matter is plain YAML (PyYAML `safe_dump` and `safe_load`), as in
  the ADR-0016 example. Owner decision, 2026-11-23: add the YAML library
  instead of writing JSON. Times are quoted, so loaders keep them strings.
- A single transcript line longer than `chunk_chars` fails the attempt.
  Splitting that line would violate the required line-end chunk boundary.

- `--once` exits when power, pending speech or host availability blocks the
  gate. It waits through bounded model-error retries while the gate holds.
- Local document times use `TZ`, or the IANA zone of `/etc/localtime`.

- Per the workspace task, the system test seeds signals and transcript
  records directly. It does not run a CDP collector or the transcript worker.
- Cross-plan review fix: boundary detection restarts at the newest done
  interaction's start, not its end (ADR-0016 Boundaries says end). The same
  interaction is found again and skipped, and an utterance that overlaps
  its end after a pin or meeting split is no longer dropped. Confirm, then
  amend the ADR wording.
