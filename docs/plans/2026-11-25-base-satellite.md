# Plan: Base and satellites

- Status: Active
- Depends on: none
- Design: [ADR-0024](../adr/0024-base-and-satellites.md),
  [PRD ambient-recording](../prd/ambient-recording.md) AC-15,
  [PRD live-transcript](../prd/live-transcript.md) AC-17,
  [PRD publishing](../prd/publishing.md)

## Goal

- The desktop (base) processes the audio of every host. The laptop
  (satellite) records, dictates and syncs its audio and events.
- All documents reach the desktop's vault inbox.

## Scope

- In: `common.role` and `common.base`, host roots in `lib.paths`, the
  runner's per-host components, component `sync`, dictation-only
  transcription and cleanup on a satellite, `odsodctl transcript --host`,
  retention and health for host roots, docs.
- Out: Opus transport (the bench rejects it), merged transcripts across
  hosts, the handheld recorder import (next plan).

## Steps

1. Bench: bytes per hour and whisper on Opus (done, in ADR-0024).
2. `lib.paths` host roots, `config.host_name`, runner `per_host` and
   `satellite` lists.
3. Document host from the host root (transcript, interactions).
4. `sync` with real `rsync` through `tests/bin/ssh`.
5. Satellite: dictation-only transcription and cleanup.
6. Retention and health for host roots.
7. Cutover (below).

## Cutover

1. Deploy on the desktop. Nothing changes until a host root exists.
2. From the laptop: `ssh -o BatchMode=yes odsod-desktop true`.
3. Seed: stop the laptop pipeline (capture keeps recording), then copy the
   laptop `state/` minus `install/` to
   `odsod-desktop:.local/state/odsod-daemon/hosts/odsod-x1-carbon/`, with
   `published/`, so nothing publishes twice.
4. Move the laptop's 7 inbox documents to the desktop inbox, then remove
   them from the laptop working copy.
5. Laptop: deploy, set `common.role: satellite`, `common.base:
   odsod-desktop`, remove `publishing`, restart the pipeline. Capture is
   not restarted.
6. Rollback: laptop `role: base` and `publishing` back. Its audio is still
   local, so its pipeline catches up.

## Done when

- `mise run build` passes.
- A laptop utterance shows in
  `odsodctl transcript --host odsod-x1-carbon` on the desktop within 60 s.
- Laptop dictation pastes as before.
- New `*-odsod-x1-carbon*.md` documents land in the desktop inbox only.

## Progress log

- 2026-11-25: bench done. Opus changes 47 to 65% of whisper's words on
  far-field mic clips, so sync is lossless rsync. Steps 2 to 6 built;
  `mise run build` passes.
- 2026-11-26: cutover done (PRs #66, #67). Sync pause for mobile data:
  `odsodctl sync pause|resume` and the tray.

## Decisions to confirm

- Network cost: about 70 to 105 MB per recorded mic hour. The owner pauses
  sync by hand on mobile data; automatic detection of a metered network is
  not built.
