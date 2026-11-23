# PRD: Publishing

- Status: Accepted
- Updated: 2026-11-23
- Design: [ADR-0003](../adr/0003-filesystem-interface.md),
  [ADR-0005](../adr/0005-components-and-implementation.md)

## Problem

- The owner's second brain lives in the vault. Daily transcripts and
  interaction documents must arrive there with no action.
- The owner and the vault's ingest agent must be free to move, edit or
  delete what arrives, with no effect on the daemon.
- The vault will be version controlled. Records come from several hosts
  into the same inbox, so they must not clash.

## Behavior

- Config lists targets, such as the vault inbox. Each target names the
  document types it gets: daily transcripts, interaction documents, or
  both.
- A document is finished → it is copied to each target that wants it. The
  daemon never changes or reads the copy afterwards.
- Document names include the host, so documents from several hosts in one
  synced target never clash.
- The ingest agent moves or deletes a delivered copy → the daemon never
  writes it again.
- When a document is finished is set by its own PRD: `live-transcript` for
  daily transcripts, `interactions` for interaction documents.

### When something fails

- A target directory is missing or full → the document waits and is copied
  later. The tray shows Warning.
- A crash during delivery → one copy can arrive twice. The ingest agent
  drops the second one.

## Acceptance criteria

Numbers are targets.

1. **AC-1** Each finished document reaches each target that wants it at
   least once, and at most twice after a crash during delivery. The daemon
   never changes, reads or deletes a copy in a target. _Check: system
   test._
2. **AC-2** A finished document is in each target at most 1 min after it is
   finished, when the target is present. _Check: system test._
3. **AC-3** A target gets only the document types it names. _Check: system
   test._
4. **AC-4** Documents from two hosts in one synced target have different
   names. _Check: system test._
5. **AC-5** A missing target shows Warning at most 1 min later. The
   document reaches it at most 5 min after it returns. _Check: system
   test._
6. **AC-6** A copy that is moved or deleted from a target after its
   delivery completed is never written again, also after a restart.
   _Check: system test._

## Boundaries

### Covered by other PRDs

- When a daily transcript is finished → the `live-transcript` PRD.
- When an interaction document is finished, and what it holds → the
  `interactions` PRD.
- The Warning in the tray → the `health-and-control` PRD.

### Not planned

- Sync between hosts or to the cloud. A target is a directory; what syncs it
  is outside the daemon (ADR-0003).
- Merging duplicates across hosts, also the second copy after a crash during
  delivery. The vault's ingest agent does it (owner decision, 2026-11-23).
- Version control of targets. The daemon writes files; the vault's tools
  commit them.
- Edits that flow back from the vault. The daemon never reads a target
  (ADR-0003).

## Open questions

- None.
