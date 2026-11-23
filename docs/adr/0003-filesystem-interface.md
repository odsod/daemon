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
| `run/`    | `$XDG_RUNTIME_DIR/odsod-daemon/` (tmpfs)             | No                | Live status, mute record               |
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

- A consumer's pending work is every input ID that has no output ID yet.
- At startup, a consumer reads today's outputs to rebuild its set of done IDs
  in memory. No cursor files, no job files, no claim and no lease.
- The transcription worker takes pending dictation utterances first, then
  ambient ones, oldest first.
- The interactions batch pass sends a request only when no dictation or ambient utterance is
  pending.

### Audio

- Path: `state/audio/<channel>/<YYYYMMDDTHH>Z.pcm`, channels `mic` and `sys`.
- Config can add an extra channel for a bench experiment, such as `mic-ec`
  (echo-cancelled mic, [ADR-0005](0005-components-and-implementation.md)).
  Utterances use only `mic` and `sys`.
- Format: raw signed 16-bit little-endian, 16 kHz, mono. 32,000 bytes per
  second.
- Byte offset / 32,000 = seconds after the start of the hour. A reader cuts
  any time range with no index.
- When capture was not running, it seeks past the gap. The file has a hole
  that reads as silence and uses no disk.
- File size tells readers how far the audio goes.
- Capture deletes hour files older than the retention period (14 days,
  about 77 GB per host) when it opens a new hour.

### Paths

| Path                                                               | Kind                  | Writer                                | Readers                                          |
| ------------------------------------------------------------------ | --------------------- | ------------------------------------- | ------------------------------------------------ |
| `state/audio/<channel>/<hour>Z.pcm`                                | Audio                 | capture                               | segmentation, transcription, interactions, bench |
| `state/events/<source>/<day>.jsonl`                                | Stream                | one source each: `signals`, `user`    | transcript, interactions                         |
| `state/utterances/ambient/<day>.jsonl`                             | Stream                | segmentation                          | transcription, interactions                      |
| `state/utterances/dictation/<day>.jsonl`                           | Stream                | dictation                             | transcription                                    |
| `state/asr/<backend>/<day>.jsonl`                                  | Stream                | transcription worker for that backend | cleanup, bench                                   |
| `state/text/<day>.jsonl`                                           | Stream                | cleanup                               | transcript, dictation                            |
| `state/interactions/<day>.jsonl`                                   | Stream                | interactions                          | interactions                                     |
| `state/bench/<case-id>/`                                           | Documents             | bench                                 | bench                                            |
| `run/status.json`                                                  | Document              | dictation                             | tray, `odsodctl status`                          |
| `run/muted.json`                                                   | Document              | dictation                             | dictation (after a restart)                      |
| `config/config.json`, glossary, prompts                            | Documents             | owner                                 | all                                              |
| `state/documents/transcripts/<local-day>-<host>.md`                | Markdown, append-only | transcript                            | publish                                          |
| `state/documents/interactions/<local-day>-<HHMM>-<host>-<slug>.md` | Document              | interactions                          | publish                                          |
| `state/published/<target>/<day>.jsonl`                             | Stream                | publish                               | publish                                          |
| `<target dir>/<document name>`                                     | Document copy         | publish                               | third parties                                    |

- `events/user/` takes appends from several CLI calls. Each call appends one
  short line with `O_APPEND`, which is atomic on a local filesystem.
- `run/muted.json` lists the capture streams that dictation muted. It is
  empty when nothing is muted. After a crash, dictation reads it at start and
  unmutes those streams, so a crash never leaves the meeting deaf to the
  owner. tmpfs clears it at reboot, when the streams are gone too.
- Utterance records hold the ID, channel, start and end. Readers cut the audio
  themselves.
- Component ADRs define the fields of each stream.

### Output targets

- The daemon treats every consumer of its output, such as a personal vault,
  as a third party.
- Config lists targets. Each target has a name, a directory and the document
  types it gets (`transcripts`, `interactions`).
- `publish` copies each finished document to each target that wants it:
  written to a temporary name, renamed into place, then never touched again.
  The consumer can move, edit or delete the copy.
- The daemon never reads from a target. `state/published/<target>/` records
  what it delivered. Pending = finished documents with no delivery record.
- An interaction document is finished when `interactions` writes it. A daily
  transcript is finished when its local day ends.
- Document names include the host, so targets that sync across hosts get no
  name clashes.

### Retention

- Audio expires after the retention period. Capture deletes it.
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
- A consumer reads today's output at startup. That is cheap for one day of
  text.
- Raw audio uses about 5.5 GB per day before deletion.
- Daily transcripts reach targets only after the local day ends. Read the live
  log in `state/documents/transcripts/`.
- Daily stream files split at UTC midnight, not local midnight. Readers that
  need a local day read two files.
