# Plan: interactions (stretch)

- Status: Draft
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

## Decisions to confirm

- Front matter uses JSON syntax, which is valid YAML. The public
  `parse_front_matter()` reads that form without a new YAML dependency.
- A single transcript line longer than `chunk_chars` fails the attempt.
  Splitting that line would violate the required line-end chunk boundary.
