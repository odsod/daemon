# Plan: publishing (stretch)

- Status: Done 2026-11-23
- Depends on: [transcript](2026-11-23-transcript.md)
- Design: [ADR-0017](../adr/0017-publishing.md),
  PRD [publishing](../prd/publishing.md)

## Goal

- The `publish` component copies finished documents to the configured
  target directories.

## Scope

- In: everything in ADR-0017 "Module layout" and "Tests".
- Out: the real target (the owner sets it in the `machine` repo config).
  With no target configured, publishing does nothing on the data day.

## Steps

1. Pending and delivery with table tests on temp targets.
2. `--once`; enable its line in `services/pipeline.py`.
3. System test: transcript `finished` record to one copy in a temp
   target; a second run copies nothing.

## Done when

```sh
uv run pytest src/odsod_daemon/components/publish
mise run build
```

## Progress log

- 2026-11-23: Step 1 done. Added config, pending, deliver and service;
  31 component tests pass.
- 2026-11-23: Step 2 done. `--once` drains and exits 0; `publish` runs in
  `services/pipeline.py`.
- 2026-11-23: Step 3 done. `tests/test_publish.py` copies a finished
  transcript once and a second run copies nothing. `mise run build`: 532
  passed.
- 2026-11-23: Fix: a scan with nothing pending for a target now clears its
  `target-missing` fault when the target directory is present and writable.
  Before, only a delivery cleared it, so a fault could stay with no document
  left to deliver.

## Decisions to confirm

- The first `publish --once` run writes the target's `start` and `since`.
  The system test runs it once before the finished record appears, so the
  record is new work, not history.
- A finished record with `ts` equal to `since` is pending: "at or after".
- A target's `target-missing` fault stays until a document for that target
  is delivered. With no pending work, the fault is not cleared.
