# ADR-0003: Filesystem interface

## Status

Proposed

## Date

2026-11-23

## Context

- [ADR-0002](0002-high-level-architecture.md) makes files the interface
  between components on a host.
- Agents build each component on its own. They need one shared set of roots,
  file kinds, IDs and rules, or each agent invents its own.
- The owner wants to inspect the system with `ls`, `cat` and `jq`.

## Decision

### Roots

| Root      | Location                                             | Synced            | Content                                |
| --------- | ---------------------------------------------------- | ----------------- | -------------------------------------- |
| `state/`  | `$XDG_STATE_HOME/odsod-daemon/`, mode `0700`         | No                | Audio, streams, documents, bench cases |
| `run/`    | `$XDG_RUNTIME_DIR/odsod-daemon/` (tmpfs)             | No                | Live status, health, mute, pause flag  |
| `config/` | `$XDG_CONFIG_HOME/odsod-daemon/`                     | No                | Config, glossary, prompts              |
| targets   | Directories set in config, for example a vault inbox | Not by the daemon | Copies of finished documents           |

The services only read `config/`. Only the owner edits it.

The keys service runs as root and keeps no files. Its only interface is the
dictation socket ([ADR-0007](0007-keys-service.md)).

### File kinds

1. **Audio:** raw binary, appended by one writer. See the audio section.
2. **Stream:** JSONL, one JSON object per line, one file per UTC day
   (`YYYY-MM-DD.jsonl`).
   - The writer appends whole lines, each with one `write` call.
   - Readers use only lines that end in `\n`.
   - Readers ignore fields they do not know. Adding a field is free.
     Removing or renaming a field needs an ADR.
3. **Document:** a single file that is written whole. The writer writes
   `.<name>.tmp` in the same directory and renames it into place. Readers
   ignore names that start with `.`.

### Time and IDs

- Machine timestamps are UTC, RFC 3339, millisecond precision.
- Human-facing documents use local dates in their names, because people read
  them.
- An utterance ID is `<kind>-<UTC start>`, for example
  `mic-20261122T143005.120Z`. Kinds: `mic` and `sys` (ambient), `dic`
  (dictation). IDs are unique per host.
- An interaction ID is its UTC start, for example `20261122T140000.000Z`.

### Pending work is derived, not queued

- A consumer's pending work is every input ID in the pending window that has
  no output ID yet.
- The pending window is the audio retention period (14 days). Older inputs
  are never pending, because their audio is gone.
- One exception: publishing. Its input is a finished document, which never
  expires. A `finished` record with no delivery record stays pending while
  its document exists, at any age. At startup, publishing reads all
  `finished/` and `published/` records. They are small text.
- At startup, a consumer reads its outputs for the whole pending window to
  rebuild its set of done IDs in memory. No cursor files, no job files, no
  claim and no lease.
- An output record goes in the day file of its write time, not of its input.
  It carries the input ID. A backlog that crosses UTC midnight is then done
  once.
- Each output record has an outcome:
  - `ok`: the work is done.
  - `empty`: the work is done and gave nothing, such as no speech.
  - `expired`: the input's audio is gone. The work can never be done.
  - `failed`: the work failed for good, such as a rejected request, or the
    retries for an external fault ran out.
- A record with any outcome makes its input done. External faults, such as an
  unreachable inference host, get bounded retries before `failed`. Only inputs
  with no record are pending.
- The transcription worker takes pending dictation utterances first, then
  ambient ones, oldest first.
- The interactions batch pass sends a request only when no dictation or
  ambient utterance is pending.

### Audio

- Path: `state/audio/<channel>/<YYYYMMDDTHH>Z.pcm`, channels `mic` and `sys`.
- Format: raw signed 16-bit little-endian, 16 kHz, mono. 32,000 bytes per
  second.
- Byte offset / 32,000 = seconds after the start of the hour. A reader cuts
  any time range with no index.
- When capture was not running, it seeks past the gap. The file has a hole
  that reads as silence and uses no disk.
- Capture never writes backward. If the wall clock goes back, capture waits
  until the expected offset passes the end of the file
  ([ADR-0011](0011-capture.md)).
- File size tells readers how far the audio goes. A reader that needs a time
  range waits until the file covers its end.
- Audio is kept for the retention period: 14 days, about 77 GB per host.

### Paths

- Layout rule: `state/<kind>/<writer>/`. The first level names the kind of
  data, and each kind has one record format. A kind with more than one writer
  has one subfolder per writer, such as `events/capture/` and
  `events/signals/`. Each file then has one writer, and a reader takes all
  sources of a kind with one glob, such as `events/*/`.

| Path                                                               | Kind                  | Writer                                 | Readers                                                                                    |
| ------------------------------------------------------------------ | --------------------- | -------------------------------------- | ------------------------------------------------------------------------------------------ |
| `state/audio/<channel>/<hour>Z.pcm`                                | Audio                 | capture                                | segmentation, transcription, bench; dictation and control (size only); retention (deletes) |
| `state/events/<source>/<day>.jsonl`                                | Stream                | one each: `signals`, `user`, `capture` | transcript, interactions                                                                   |
| `state/utterances/ambient/<day>.jsonl`                             | Stream                | segmentation                           | transcription, transcript, interactions, control                                           |
| `state/utterances/dictation/<day>.jsonl`                           | Stream                | dictation                              | transcription, segmentation, transcript, interactions, control                             |
| `state/coverage/<day>.jsonl`                                       | Stream                | segmentation                           | segmentation, transcript, interactions, control                                            |
| `state/asr/<backend>/<day>.jsonl`                                  | Stream                | transcription worker for that backend  | cleanup, bench                                                                             |
| `state/text/<day>.jsonl`                                           | Stream                | cleanup                                | transcript, dictation, interactions, control, bench                                        |
| `state/interactions/<day>.jsonl`                                   | Stream                | interactions                           | interactions, bench                                                                        |
| `state/finished/<source>/<day>.jsonl`                              | Stream                | one each: `transcript`, `interactions` | publish                                                                                    |
| `state/bench/<case-id>/`                                           | Documents             | bench                                  | bench                                                                                      |
| `run/status.json`                                                  | Document              | dictation                              | tray, `odsodctl status`, segmentation                                                      |
| `run/health/<service>.json`                                        | Document              | that service                           | tray, `odsodctl status`                                                                    |
| `run/paused`                                                       | Document              | `odsodctl pause`, `odsodctl resume`    | capture unit, tray, `odsodctl status`                                                      |
| `state/install/current`                                            | Document              | `odsodctl install`                     | `odsodctl version`, `odsodctl status`, bench                                               |
| `state/install/previous-commit`                                    | Document              | `odsodctl install`                     | `odsodctl status`                                                                          |
| `run/muted.json`                                                   | Document              | dictation                              | `odsodctl unmute-stale`, dictation                                                         |
| `config/config.json`, glossary, prompts                            | Documents             | owner                                  | all                                                                                        |
| `state/documents/transcripts/<local-day>-<host>.md`                | Markdown, append-only | transcript                             | publish                                                                                    |
| `state/documents/interactions/<local-day>-<HHMM>-<host>-<slug>.md` | Document              | interactions                           | publish, bench                                                                             |
| `state/published/<target>/<day>.jsonl`                             | Stream                | publish                                | publish                                                                                    |
| `<target dir>/<document name>`                                     | Document copy         | publish                                | third parties                                                                              |

- `events/user/` takes appends from several CLI calls. Each call appends one
  short line with `O_APPEND`, which is atomic on a local filesystem. Notes,
  pins and pause intents go here.
- `events/capture/` holds capture's start, stop and gap records. With the
  pause intents in `events/user/`, `transcript` gives each recording gap its
  cause.
- `run/health/<service>.json` holds the active faults of one service, each
  with its `since` time. The service is its sole writer. The `health`
  component of control merges these files with the systemd unit states, so the tray and a one-shot
  `odsodctl status` show the same state. `run/status.json` holds only the
  dictation mode.
- `run/paused` exists while the owner has paused recording. The capture unit
  does not start while it exists. Resume, logout and the daily resume timer
  remove it ([ADR-0004](0004-orchestration-with-systemd.md)).
- `state/install/current` holds what runs now, as JSON: `source` (`git` or
  `dev`), `commit`, `workspace`, `dirty` and `installed_at`. A dev install
  has no commit in the package metadata, so `install` records it here.
- `state/install/previous-commit` holds the install that ran before the last
  upgrade, as JSON (`commit`, `source`, `replaced_at`), so a failed upgrade
  names the rollback command ([ADR-0006](0006-installation.md)).
- `state/coverage/` holds `covered` records: segmentation has cut all audio
  of a channel before `end`. Readers tell silence from backlog with it.
  segmentation also restarts from it, so it needs no checkpoint file.
- `state/finished/<source>/` holds a `finished` record for each finished
  document. publish finds its work only there.
- `state/interactions/` holds one record per finished interaction: its range
  and outcome (`ok` with the document name, or `skipped` for greetings and
  noise).
- `run/muted.json` lists the capture streams that dictation muted. It is
  empty when nothing is muted. When the session service stops for any
  reason, `odsodctl unmute-stale` reads it and unmutes those streams, so a
  crash never leaves the meeting deaf to the owner. tmpfs clears it at
  reboot, when the streams are gone too.
- Utterance records hold the ID, channel, start and end. Readers cut the audio
  themselves.
- [ADR-0010](0010-contracts-and-runtime.md) fixes the seam fields of each
  stream. Subsystem ADRs add the rest.

### Output targets

- The daemon treats every consumer of its output, such as a personal vault,
  as a third party.
- Config lists targets. Each target has a name, a directory and the document
  types it gets (`transcripts`, `interactions`).
- `publish` copies each finished document to each target that wants it:
  written to a temporary name, renamed into place, then never touched again.
  The consumer can move, edit or delete the copy.
- The daemon never reads from a target. `state/published/<target>/` records
  what it delivered. Pending = `finished` records with no delivery record,
  with no age limit (see "Pending work is derived").
- The rename is the commit point. `publish` writes the delivery record right
  after it. A crash between the two delivers that copy once more after the
  restart. This is accepted: the vault's ingest agent merges duplicates.
- A document is finished when its `finished` record exists
  ([ADR-0010](0010-contracts-and-runtime.md)). `interactions` writes it
  right after the document rename.
- A daily transcript is finished when its local day has ended and none of
  that day's utterances is pending. At the latest, it is finished 48 h after
  the day ended. Then `transcript` writes an `untranscribed: <range>` gap
  line for each utterance still pending, and the transcript is final.
  `transcript` then writes its `finished` record and never appends to that
  day file again.
- Document names include the host, so targets that sync across hosts get no
  name clashes.

### Retention

- Audio expires after the retention period. `odsodctl retention`, run by
  `odsod-daemon-retention.timer` each hour and at login, deletes it. It does
  not depend on capture running, so a paused or stopped host keeps no old
  audio.
- Streams and documents stay. They are small text.
- Bench cases stay until deleted, with their audio. Each case directory is
  self-contained: the audio slice, the ASR text, the reference, its review
  state (draft or accepted, and by whom) and the source (host, time,
  channel). Retention never reads `state/bench/`.
- Only publish copies data out of `state/`, and only to configured targets.

### Change notification

- Readers watch their input directories with inotify and also scan on a timer
  (a few seconds). The scan is the source of truth.

## Alternatives considered

### Job files in queue directories

- Needs claim by rename, leases or startup recovery, and cleanup of done jobs.
- Rejected: pending work derived from inputs and outputs gives the same order
  with less state.

### SQLite as the shared store

- Gives transactions and queries.
- Rejected: not inspectable with plain tools, and every component needs a
  driver. JSONL with one writer per file needs no locking.

### Compressed audio (FLAC or Opus)

- Saves disk.
- Rejected for now: raw audio gives slicing by byte offset with no decoder.
  14 days of two channels is about 80 GB. Revisit if a host runs short of disk.

### Local time in machine files

- Rejected: daylight saving time makes hours repeat or vanish.

### Write documents straight into the vault

- Simplest, but the vault becomes part of the daemon's state. An inbox that
  moves files away breaks append-only writes and reruns.
- Rejected: the pipeline keeps its own copy and delivers finished copies.

## Consequences

- `ls state/` shows the whole pipeline. `jq` answers most questions.
- Restarts need no recovery step. Each component rebuilds from its files.
- A consumer reads 14 days of its output at startup. That is a few MB of
  text.
- Raw audio uses about 5.5 GB per day before deletion.
- Daily transcripts reach targets only after the local day ends and its
  backlog is done, at most 48 h later. Read the live log with
  `odsodctl transcript`.
- Daily stream files split at UTC midnight, not local midnight. Readers that
  need a local day read two files.
