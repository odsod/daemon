# ADR-0017: Publishing

## Status

Proposed

## Date

2026-11-23

## Context

- The owner's second brain is the vault. Finished daily transcripts and
  interaction documents must reach its inbox with no action (`publishing`
  PRD).
- The daemon treats every target as a third party. It never reads a
  target, and the owner or the ingest agent may move, edit or delete what
  arrives (ADR-0002, principle 12; ADR-0003 "Output targets").
- Without reads from the target, exactly-once delivery is impossible. A
  crash between the rename into the target and the delivery record gives
  a second copy. The owner accepts this: the ingest agent drops it
  (ADR-0003).
- The vault syncs across hosts, so names must not clash (ADR-0003: names
  carry the host).

## Decision

### Purpose

- Copy each finished document to each target that wants its type, at
  least once, and record each delivery.
- PRD: `publishing` (AC-1 to AC-6). Also `live-transcript` AC-12 (the
  transcript reaches targets) and `interactions` "a finished document →
  publishing delivers it".

### Components

| Component | Service    | Job                                                     |
| --------- | ---------- | ------------------------------------------------------- |
| `publish` | `pipeline` | Deliver finished documents; sole writer of `published/` |

- `odsodctl run publish --once` drains: it delivers every pending
  document to every present target and exits 0 (ADR-0010 decision on
  `--once`).
- No commands. `odsodctl run publish` runs it alone for debugging. Status
  of deliveries is in `published/`, readable with `jq`.

### Writes

| Path                                              | Kind          |
| ------------------------------------------------- | ------------- |
| `state/published/<target>/<day>.jsonl`            | Stream        |
| `<target dir>/.<document>.tmp`                    | Temp file     |
| `<target dir>/<document>`                         | Document copy |
| `run/health/pipeline.json`, code `target-missing` | Document      |

#### `published/<target>/` record

| Field      | Seam  | Meaning                                 |
| ---------- | ----- | --------------------------------------- |
| `kind`     | yes   | `delivery`                              |
| `document` | yes   | File name, the same in state and target |
| `target`   | yes   | Target name from config                 |
| `type`     | extra | `transcripts` or `interactions`         |
| `bytes`    | extra | Size of the copy                        |
| `sha256`   | extra | Hash of the copy                        |

- One stream per target, so a new target starts with an empty history.
- The first record of a target's stream is kind `start`, with `since`: the
  time publishing first saw the target in config. It is internal: only
  publishing reads it.
- `document` is the input ID of this derived work (ADR-0003). There is no
  `outcome` field: a delivery is written only on success. A document that
  cannot be delivered stays pending and shows as a fault. This is a
  deliberate exception to the outcome convention of ADR-0010: a target
  that comes back must still get the document (`publishing` AC-5).

### Reads

| Path                                             | What it relies on                                 |
| ------------------------------------------------ | ------------------------------------------------- |
| `finished/transcript/`, `finished/interactions/` | `finished` records: `document`, `type` (ADR-0010) |
| `documents/<type>/<document>`                    | The named file, read whole to copy it             |
| `published/<target>/`                            | Its own records, to rebuild the delivered set     |
| `config/config.json`                             | Section `publishing`                              |

- It never reads a target directory's contents. It only checks that the
  directory exists, and writes into it (`publishing` AC-1).
- A document is finished when its `finished` record exists. publishing
  finds work only in `state/finished/*/`, never by listing or parsing
  documents (ADR-0010 decision). The record's `type` names the folder:
  `transcripts` or `interactions`.

### Outside dependencies

- The local filesystem of each target directory. What syncs it (Syncthing,
  git) is outside the daemon (`publishing` "Not planned").
- No libraries beyond `lib/`.

### Internal design

#### Module layout

```
components/publish/
├── __init__.py      SUBSYSTEM = "publishing"; run(config)
├── contract.py      Delivery
├── config.py        PublishingConfig, Target
├── pending.py       finished documents minus delivered, per target (pure)
├── deliver.py       copy, fsync, rename; error mapping
├── service.py       loop: watch, scan, deliver, record, faults
└── tests/
```

#### Pending

- For each target and each document type it names: every `finished`
  record of that type with `ts` at or after the target's `since`, with no
  delivery record for its `document` in that target's stream.
- This is the one exception to the 14-day pending window (ADR-0003). A
  finished document is text that never expires, so it stays pending while
  its source exists. A target that comes back after 30 days still gets
  every document (`publishing` AC-1, AC-5).
- At start, read all `finished/` records and each target's whole stream
  into in-memory sets. These are small text streams: one line per
  document.
- A target added later gets the documents finished after it first
  appeared, not all history. To backfill, the owner copies files by hand.
- A document that the owner deletes from `state/documents/` stops being
  pending.

#### Delivery

For one document and one target:

1. Check that the target directory exists and is a directory. The daemon
   never creates it: a missing directory often means an unmounted disk or
   a vault that moved, and a new empty directory would hide that.
2. Copy to `<dir>/.<document>.tmp`, `fsync` the file.
3. Rename to `<dir>/<document>`, then `fsync` the directory. The rename is
   the commit point (ADR-0003).
4. Append the delivery record.

- A crash between 3 and 4 delivers the copy once more after the restart.
  The rename replaces the first copy if it is still there. If the ingest
  agent moved it, a second copy arrives. Both are accepted (`publishing`
  AC-1: at most twice).
- A crash between 2 and 3 leaves a temp file with a leading dot. The next
  delivery of that document overwrites it. Tools that follow the dot rule
  ignore it.
- The copy is never touched again after step 4 (`publishing` AC-6).
- Deliveries run one at a time, oldest document first. Documents are small
  text.

#### Timing

- Follow `state/finished/*/` with `lib/streams` (inotify plus a scan every
  `scan_s`, 5 s). The scan is the source of truth
  (ADR-0003). A new document reaches a present target within seconds
  (`publishing` AC-2: 1 min).
- A transcript file changes on every line, but publish never looks at it
  before its `finished` record exists.
- A target with a fault is retried every `retry_s` (30 s). The document
  then arrives within 30 s of the target's return (`publishing` AC-5:
  5 min).

### Failure modes

| Fault                                    | What publish does                                 | Fault code       |
| ---------------------------------------- | ------------------------------------------------- | ---------------- |
| Target directory missing                 | Keeps the document pending; retries every 30 s    | `target-missing` |
| Target full (`ENOSPC`, `EDQUOT`)         | Removes its temp file; retries every 30 s         | `target-missing` |
| No permission (`EACCES`, `EROFS`)        | Same as missing                                   | `target-missing` |
| Crash between rename and record          | One more copy after restart (accepted)            | none             |
| Document vanishes from state before copy | Skips it                                          | none             |
| Unexpected exception                     | Ends the pipeline; systemd restarts it (ADR-0004) | none             |

- `target-missing` is one fault per target, keyed by the target name
  (`lib.healthfile`, ADR-0010), so one target's success never clears
  another target's fault. Message: "Target `<name>`
  missing or full: `<dir>` (`<reason>`)". `fix` is null: only the owner
  can mount, create or free the directory. The fault starts on the first
  failed try, so it shows within one scan (`publishing` AC-5: 1 min). It
  clears on the next success for that target.
- One target's fault never holds back another target.

### Config

Section `publishing`:

```json
{
  "publishing": {
    "targets": [
      {
        "name": "vault",
        "dir": "~/Code/git.lan/odsod/brain/inbox",
        "types": ["transcripts", "interactions"]
      }
    ],
    "scan_s": 5,
    "retry_s": 30
  }
}
```

- `name` matches `[a-z0-9-]+` and is unique. It names the stream
  directory, so a rename of a target starts a new history with a new
  `since`, and redelivers nothing.
- `dir` may start with `~`. Config load expands it. It must be absolute
  after that.
- `types` is a non-empty subset of `transcripts` and `interactions`
  (`publishing` AC-3).
- No targets: publish runs and does nothing.

### Tests

Component tests use temp dirs for state and targets, and a fake clock.

| Test                   | Setup                                                                                          | Checks                                                                   |
| ---------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `test_deliver.py`      | Finished transcript and interaction document; two targets                                      | Copy equal to source; one record each: `publishing` AC-1                 |
| `test_unfinished.py`   | Transcript with no `finished` record, then the record                                          | Not delivered, then delivered: `live-transcript` AC-12                   |
| `test_latency.py`      | Fake clock; new document                                                                       | Delivered within 1 min: AC-2                                             |
| `test_types.py`        | Target with only `interactions`                                                                | Gets no transcript: AC-3                                                 |
| `test_names.py`        | Documents of two hosts in one target                                                           | Different names: AC-4                                                    |
| `test_missing.py`      | Target dir absent, then created; full disk (a `tmpfs` with a small size, or a mocked `ENOSPC`) | Fault within 1 min; delivery within 5 min of return; fault cleared: AC-5 |
| `test_moved.py`        | Delete the copy after delivery; restart                                                        | Never written again: AC-6                                                |
| `test_long_absence.py` | Target dir absent for 30 days of fake time, then created                                       | Every document finished in that time is delivered: AC-1, AC-5            |
| `test_two_faults.py`   | Two targets missing; one returns                                                               | Only the returning target's fault clears                                 |
| `test_crash.py`        | Crash after rename, before record                                                              | At most one extra copy: AC-1                                             |
| `test_never_reads.py`  | Target with a file of the same name and other content; target files made unreadable            | Publish never opens a target file for reading: AC-1                      |

- System test (root `tests/`): transcript finishes a day, interactions
  writes a document, publish delivers both to a temp target
  (`live-transcript` AC-12, `interactions` "publishing delivers it").

### Build without hardware

- All of it. Targets are temp directories.
- The owner sets the real target in the host's `config.json` and checks
  that the vault's ingest agent handles a second copy.

## Alternatives considered

### Write documents straight into the vault

- Rejected in ADR-0003: the vault becomes part of the daemon's state, and
  an inbox that moves files breaks appends and reruns.

### Exactly-once delivery

- Needs a read of the target before the copy, or a lock file in it.
- Rejected: the daemon never reads a target, and the ingest agent already
  merges duplicates.

### A `failed` delivery record

- Would follow the outcome convention of ADR-0010.
- Rejected: a `failed` record makes the document done, so a target that
  comes back never gets it. Missing targets are temporary, and the fault
  shows them.

### Create a missing target directory

- Rejected: it hides an unmounted disk or a moved vault behind an empty
  directory.

### Hard links instead of copies

- Save disk.
- Rejected: an edit in the vault would change the daemon's own copy, and
  links do not cross filesystems.

## Consequences

- The vault gets each document at least once. After a crash in the
  delivery window, it can get two.
- A target that is gone for any time gets all its documents when it
  returns, as long as they stay in `state/documents/`.
- Renaming a target in config starts it fresh. A new target gets no
  history. The owner copies old documents by hand if needed.
- Deliberately left out: sync, version control and merges in targets,
  edits that flow back, and delivery to anything but a local directory.
