# Plan: publishing (stretch)

- Status: Draft
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

## Decisions to confirm
