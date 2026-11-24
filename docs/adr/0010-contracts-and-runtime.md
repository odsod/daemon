# ADR-0010: Contracts and runtime

## Status

Proposed

## Date

2026-11-23

## Context

- [ADR-0009](0009-taxonomy-and-code-organization.md) divides the daemon into
  subsystems. Each subsystem gets its own ADR, and agents design and build
  them in parallel.
- Parallel work fails when two subsystems read one contract in two ways. The
  seams must be fixed before the subsystem ADRs are written.
- [ADR-0003](0003-filesystem-interface.md) fixes the paths, the file kinds,
  the IDs and the pending-work rule. It leaves the fields of each stream to
  later ADRs.
- The runtime subsystem is the code that every other subsystem uses: `lib/`,
  `services/` and `cli.py`. It holds no business decision.

## Decision

### Scope of the runtime subsystem

| Part        | Holds                                                               | Never holds                       |
| ----------- | ------------------------------------------------------------------- | --------------------------------- |
| `lib/`      | Mechanism: file kinds, pending work, clock, config loading, clients | A business rule, a stream it owns |
| `services/` | Composition: which components run in which process                  | Behavior                          |
| `cli.py`    | The `odsodctl` entry point. Mounts the commands of each component   | Behavior                          |

### The seams

Every interface that crosses a subsystem border. The writer subsystem owns
the model in its component's `contract.py` (ADR-0009, rule 6). The fields
below are the seam: readers may rely on them, and the writer must keep them.
A subsystem ADR can add fields. Paths that only one subsystem reads, such
as a checkpoint, are internal: its ADR defines them, and ADR-0003 lists
them.

| Interface                                                             | Writer                                                  | Readers                                                                  |
| --------------------------------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------ |
| Audio buffer                                                          | capture                                                 | speech, dictation and control (file size only), bench; retention deletes |
| `events/capture/`                                                     | capture                                                 | transcript, interactions                                                 |
| `CAPTURE_APP_NAME` constant                                           | capture (`contract.py`)                                 | dictation (skips capture's own PipeWire streams)                         |
| `events/signals/`                                                     | signals                                                 | transcript, interactions                                                 |
| `events/user/`                                                        | transcript (`note`, `pin`), control (`pause`, `resume`) | transcript, interactions                                                 |
| `utterances/ambient/`                                                 | speech                                                  | transcript, interactions, control                                        |
| `utterances/dictation/`                                               | dictation                                               | speech, transcript, interactions, control                                |
| `coverage/`                                                           | speech                                                  | transcript, interactions, control                                        |
| `asr/<backend>/`                                                      | speech                                                  | bench                                                                    |
| `text/`                                                               | speech                                                  | transcript, dictation, interactions, control, bench                      |
| `interactions/`                                                       | interactions                                            | bench                                                                    |
| `documents/transcripts/`                                              | transcript                                              | publishing                                                               |
| `documents/interactions/`                                             | interactions                                            | publishing, bench                                                        |
| `finished/<source>/`                                                  | transcript, interactions (one source each)              | publishing                                                               |
| `published/<target>/`                                                 | publishing                                              | publishing                                                               |
| `run/health/<service>.json`                                           | each service                                            | control                                                                  |
| `run/status.json`                                                     | dictation                                               | control, speech                                                          |
| `run/muted.json`                                                      | dictation                                               | dictation (`unmute-stale`)                                               |
| `run/paused`                                                          | control                                                 | capture unit, control                                                    |
| `state/install/current`                                               | install                                                 | control, bench                                                           |
| `state/install/previous-commit`                                       | install                                                 | control                                                                  |
| `config/glossary.yaml`                                                | owner                                                   | speech, interactions, bench                                              |
| `speech` config section, prompts `cleanup.md`, `cleanup-dictation.md` | owner (speech owns the schema)                          | speech, bench (sandbox overrides)                                        |
| Keys package-data constants                                           | keys (`contract.py`)                                    | install (`install --system` builds and installs keys)                    |
| Keys socket                                                           | keys                                                    | dictation ([ADR-0007](0007-keys-service.md))                             |
| KWin D-Bus calls                                                      | shortcuts                                               | shortcuts ([ADR-0008](0008-shortcuts-and-kwin-script.md))                |

A `contract.py` holds models and interface constants, such as an
application name or a package-data resource name. It holds no behavior.

`events/user/` has two writer subsystems. Each record kind has one writer,
and every write is one atomic `O_APPEND` line (ADR-0003), so they never
clash.

### Record conventions

- Every stream record has `ts`: the UTC time of the write (ADR-0003 format).
- Every record has `kind`, a short lowercase string. Readers skip kinds they
  do not know. A new kind is free; a changed kind needs an ADR.
- An output record of derived work (ADR-0003) has `input`, the input ID,
  and `outcome`: `ok`, `empty`, `expired` or `failed`. `failed` records
  have `error`, one line of text.
- One exception: a `delivery` record in `published/<target>/` has no
  `outcome`. publishing writes it only after a copy succeeded, and the
  document name is its input ID. A target that is missing must get the
  document later (`publishing` AC-5), so a failure never makes it done.
- Time ranges are `start` and `end`, UTC, inclusive start, exclusive end.
- No record holds audio. Readers cut audio by time from the buffer.

### Seam fields

Required fields per stream. `ts` and `kind` are implied.

| Stream                  | Kind            | Fields                                                                                                                                                                       |
| ----------------------- | --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `events/capture/`       | `start`         | `channel`, `audio_start` (time of the first sample), `prev_end` (end of the existing audio of the channel, or null)                                                          |
|                         | `stop`          | `channel`                                                                                                                                                                    |
|                         | `gap`           | `channel`, `start`, `end`, `reason` (`suspend`, `clock`, `stall`, or null)                                                                                                   |
| `events/signals/`       | `meeting-start` | `platform` (`meet`, `teams`), `code`, `title`, `at` (time of the change, before debounce)                                                                                    |
|                         | `meeting-end`   | `platform`, `code`, `at`                                                                                                                                                     |
|                         | `participants`  | `platform`, `code`, `names` (list, full set after the change)                                                                                                                |
|                         | `speaking`      | `platform`, `code`, `names` (list of who speaks now; empty list for nobody), `at`                                                                                            |
| `events/user/`          | `note`          | `text`                                                                                                                                                                       |
|                         | `pin`           | `text` (may be empty)                                                                                                                                                        |
|                         | `pause`         | (none; `by` beyond the seam, ADR-0018)                                                                                                                                       |
| `utterances/ambient/`   | `utterance`     | `id`, `channel` (`mic`, `sys`), `start`, `end`                                                                                                                               |
| `utterances/dictation/` | `utterance`     | `id`, `channel` (`dic`), `start`, `end`                                                                                                                                      |
| `coverage/`             | `covered`       | `channel` (`mic`, `sys`), `end`: no utterance of that channel will start before `end`                                                                                        |
| `asr/<backend>/`        | `asr`           | `input`, `outcome`, `text`, `language` (ISO 639-1), `setup` (fingerprint of model and settings), `ms` (request duration)                                                     |
| `text/`                 | `text`          | `input`, `outcome`, `channel`, `start`, `end`, `text`, `language`, `raw` (true when cleanup was skipped), `setup` (fingerprint of LLM model, prompt hash and settings), `ms` |
| `interactions/`         | `interaction`   | `id`, `start`, `end`, `outcome` (`ok`, `skipped`, `failed`), `document` (name, when `ok`)                                                                                    |
| `finished/<source>/`    | `finished`      | `document` (file name), `type` (`transcripts`, `interactions`)                                                                                                               |
| `published/<target>/`   | `delivery`      | `document`, `target`                                                                                                                                                         |

Notes:

- Speaker names come from `speaking` records by overlap. A `speaking`
  record holds the state until the next one. Signals writes one only when the
  set changes, and an empty one when the meeting ends.
- `text/` carries `channel`, `start` and `end`, so its readers never need to
  join with `utterances/`.
- speech writes a `covered` record at each utterance and at least every
  60 s while segmentation advances. It tells silence from backlog: an
  interaction never ends on silence that is not yet segmented
  (`interactions` AC-2), and a day is never finished while its audio is not
  yet cut (`live-transcript` AC-12).
- A document is finished when its `finished` record exists. interactions
  writes it right after the document rename. transcript writes it when the
  day is final, and writes nothing to the day file after it. publishing
  finds its work only in `finished/` ([ADR-0017](0017-publishing.md)).
- `raw: true` marks dictation text pasted without cleanup after the 1 s
  limit (ADR-0002, principle 9).
- A crash writes no `stop`. The next `start` gives the hole exactly: from
  `prev_end` to `audio_start`. Readers derive recording-off ranges from
  `start` records plus `gap` records, which covers clean stops and crashes
  alike. A `stop` with no later `start` is an open range that ends at now.
- `at` is when signals saw the change; `ts` is when it wrote the record.
  Speaker overlap uses `at`.
- `ms` is the request duration in milliseconds. bench reads it.
- Records may carry other fields, such as `resume` records in
  `events/user/` or `meeting` in `interactions/`. No other subsystem relies
  on them, so they are not seam fields.

### Run documents

| Path                            | Fields                                                                                                                                |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `run/health/<service>.json`     | `service`, `ts`, `faults`: list of `code`, `key` (or null), `since`, `message`, `fix` (a command, or null)                            |
| `run/status.json`               | `mode` (`idle`, `dictating`), `since`, `keys` (`connected`, `paused`, `no-inference`, `no-socket`), `audio_start` (while `dictating`) |
| `state/install/current`         | `source` (`git`, `dev`), `commit`, `workspace` (or null), `dirty`, `installed_at`                                                     |
| `state/install/previous-commit` | `commit`, `source`                                                                                                                    |
| `run/muted.json`                | `streams`: list of `id` (PipeWire stream ID) and `app`                                                                                |
| `run/paused`                    | `since`                                                                                                                               |

- A service rewrites its whole health file on each change, and at least
  once a minute. control treats a health file as void while its unit is not
  active, so a crashed service never shows old faults.
- `audio_start` is the start of the open dictation utterance (key press
  minus pre-roll). segmentation reads it and never emits a `mic` utterance
  that overlaps an open dictation (`live-transcript` AC-16).
- A fault is one entry per `(code, key)`. `key` tells apart faults of one
  code within a service, such as `whisper` and `llama` for
  `inference-unreachable`, or the target name for `target-missing`. Clearing
  one key never clears another.
- `fix` names the right command for the unit scope
  ([ADR-0004](0004-orchestration-with-systemd.md)).

### Fault codes

The fault code fixes the severity. Severity `Mark` shows a state but never
changes the exit code: it ranks as the Mic muted state. control owns the
precedence of states
([PRD health-and-control](../prd/health-and-control.md)).

| Code                    | Writer   | Severity |
| ----------------------- | -------- | -------- |
| `capture-stalled`       | capture  | Error    |
| `mic-silent`            | capture  | Mark     |
| `inference-unreachable` | pipeline | Warning  |
| `target-missing`        | pipeline | Warning  |
| `no-speaking-indicator` | pipeline | Warning  |
| `interactions-waiting`  | pipeline | Warning  |
| `mute-failed`           | session  | Warning  |
| `stale-mutes-cleared`   | session  | Warning  |
| `keys-socket-missing`   | session  | Error    |
| `mic-muted`             | capture  | Mark     |

control adds the states that no service can report itself: a unit that
failed or hit its start limit, the keys unit included (Error); stale audio
from a hung capture (Error); the backlog of untranscribed audio (Warning);
an unreadable health file (`health-unreadable`, Warning); Paused; and the
dev mark. PipeWire belongs to capture, so capture reports
Mic muted as `mic-muted`.

### Config

- One file, `config/config.json`. The top level holds one section per
  subsystem, named as the subsystem, plus `common`.
- `common`: `host` (default: the hostname), `retention_days` (14),
  `inference` (`whisper_url`, `llama_url`, both localhost or tailnet,
  ADR-0002). Each URL is the full endpoint, such as
  `http://host:8178/v1/audio/transcriptions`, not a base URL.
- `lib.pending` reads `common.retention_days` once, so every consumer uses
  the same pending window.
- Each subsystem owns its section. Its component loads it with
  `lib.config.section("<subsystem>", Model)`. `lib/` never imports a section
  model.
- `odsodctl config check` loads every section and reports all errors. A
  service refuses to start on an invalid section of its own and writes the
  error to its log.
- `config/glossary.yaml`: entries with `term`, `note` and `heard_as`, most
  important last ([ADR-0021](0021-glossary.md)). speech, interactions and
  bench read it through `lib.glossary`.
- `config/prompts/<name>.md`: optional prompt overrides. The subsystem that
  owns the prompt names it.

### `lib/` mechanisms

| Module       | Gives                                                                                                                  |
| ------------ | ---------------------------------------------------------------------------------------------------------------------- |
| `paths`      | The roots from the XDG variables. `ODSOD_DAEMON_ROOT` overrides all three, for tests and the bench sandbox             |
| `clock`      | `wall()`, `monotonic()`, `boottime()`, `sleep()` and `timeout()`. The only source of time for components               |
| `streams`    | Append one record; read a day range; follow new lines within 20 ms of the write (inotify), a timer scan as backstop    |
| `documents`  | Atomic write (temp name, rename); read                                                                                 |
| `audio`      | Cut a time range of a channel; `covered_until(channel)` from the file size; wait until the file covers a time          |
| `pending`    | Pending inputs: input IDs in the window minus output IDs; bounded retry with backoff                                   |
| `config`     | Load a section into a model; list errors                                                                               |
| `healthfile` | Set and clear faults of this service by `(code, key)`; rewrite the file                                                |
| `inference`  | Async clients for whisper-server and llama-server; URL check; `reachable(url, timeout)`; `is_loopback(url)`; fakes     |
| `systemd`    | Unit states over D-Bus, user and system bus (`ActiveState`, `SubState`, `Result`, `StateChangeTimestamp`); `sd_notify` |
| `power`      | `on_mains()` from `/sys/class/power_supply`. Device batteries (scope `Device`, such as a pen or a mouse) do not count  |
| `textmatch`  | `overlap(a, b)`: token overlap of two texts, 0.0 to 1.0. Each caller keeps its own threshold                           |
| `cli`        | `--json` output: one result model renders as text or JSON                                                              |

- `pending` gives the mechanism; the consumer gives the input and output
  streams and its retry policy.
- `inference` checks URLs: localhost or a tailnet address
  (`100.64.0.0/10`, `fd7a:115c:a1e0::/48` or a `*.ts.net` name). Anything
  else fails at config load. `reachable` is a TCP connect with a timeout.
  dictation and speech use it, so both agree when no inference host is
  reachable. `is_loopback` tells a local server, which never runs on
  battery (`live-transcript` AC-15).
- `streams.follow` sets a low watchfiles debounce. The default 1.6 s alone
  would break `dictation` AC-3, which crosses three streams. The target is
  20 ms. CI checks p95 under 100 ms over 1,000 appends, in a test marked
  `timing`. bench and the owner measure the real dictation latency.
- `power.on_mains()` is False only when a battery with a scope other than
  `Device` reports `Discharging` and no `Mains` supply is online. No supply,
  or only device batteries, gives True. A desktop with a pen battery is on
  mains.
- `clock`: components never call `time.time`, `time.monotonic`,
  `datetime.now` or `asyncio.wait_for` with a raw number. They use
  `lib.clock`, so tests control all time.

### Time in tests

- Component tests run on a virtual-time event loop (the pytest plugin
  `looptime`, a dev dependency). `sleep(3600)`, `timeout()` and httpx
  timeouts then pass in virtual time, with no wait.
- System tests across processes run in real time with small config values,
  such as cutoffs of tens of milliseconds. They check order and outcomes,
  never latency.
- Latency criteria, such as `dictation` AC-3, AC-4 and AC-21, are bench
  measures and owner checks, not CI tests.

### Services

| Service    | Subsystems and components                                                                    |
| ---------- | -------------------------------------------------------------------------------------------- |
| `capture`  | capture                                                                                      |
| `pipeline` | speech (segmentation, transcription, cleanup), signals, transcript, interactions, publishing |
| `session`  | dictation, shortcuts                                                                         |
| `tray`     | control (tray)                                                                               |

- A service file builds its components and runs them in one
  `asyncio.TaskGroup`. An exception in any component ends the process with a
  non-zero code. systemd restarts it (crash-only, ADR-0004).
- A service sends `READY=1` when every component has started, and the
  watchdog ping that its unit asks for.

### Command surface

| Command                                            | Subsystem  | `--json` | Notes                                              |
| -------------------------------------------------- | ---------- | -------- | -------------------------------------------------- |
| `run <service \| component> [--once]`              | runtime    | No       | Units use it. `--once`: drain pending work, exit 0 |
| `config check`                                     | runtime    | Yes      | All sections                                       |
| `status`                                           | control    | Yes      | Exit codes 0 to 3 (ADR-0004)                       |
| `pause`, `resume` `[--by cli\|tray\|timer\|login]` | control    | Yes      | The timer and login units pass `--by`              |
| `notify-failed <unit>`                             | control    | No       | Run by the notify units (ADR-0004)                 |
| `note <text>`, `pin [text]`                        | transcript | Yes      |                                                    |
| `transcript [--day]`                               | transcript | Yes      |                                                    |
| `dictation last`                                   | dictation  | Yes      |                                                    |
| `unmute-stale`                                     | dictation  | No       | `ExecStopPost` of the session unit                 |
| `retention`                                        | capture    | No       | Run by the retention timer                         |
| `audio play\|export <id> [--pad]`                  | capture    | Yes      | Re-listen to one utterance                         |
| `shortcuts`                                        | shortcuts  | Yes      |                                                    |
| `bench cases\|list\|run\|accept\|delete\|report`   | bench      | Yes      | Extra `bench`                                      |
| `install [--system]`                               | install    | No       |                                                    |
| `version`                                          | install    | Yes      |                                                    |

- Each component that has commands exports a typer app from `cli.py` in its
  folder. The root `cli.py` mounts them and adds `run` and `config check`.
- Every derived-work component supports `--once`. Tests use it, and bench
  uses it.

### Bench runs speech in a sandbox

- `contract.py` holds models only. bench never imports speech code.
- To score a setup, bench builds a temp root (`state/`, `run/`, `config/`
  with the setup's config and prompts), writes the case audio and utterance
  records into it, runs `odsodctl run transcription --once` and
  `odsodctl run cleanup --once` with `ODSOD_DAEMON_ROOT` set, and reads
  `asr/` and `text/` back ([ADR-0019](0019-bench.md)).
- bench then scores the same code that runs live, through file seams only.

### Import rules

- import-linter checks the tiers: `cli` → `services` → `components` →
  `lib`.
- An architecture test in `tests/test_architecture.py` checks the seams:
  - every component's `__init__.py` sets `SUBSYSTEM` to a name in the
    ADR-0009 table;
  - an import of a component in another subsystem goes to its `contract`
    module only;
  - `lib/` imports no component;
  - no code outside `lib/clock` calls `time.time`, `time.monotonic` or
    `datetime.now`.
- Both run in `mise run build`.

### Test fixtures

Every subsystem must be buildable and testable with no owner hardware.
The runtime subsystem gives:

- A temp root for `state/`, `run/` and `config/`, and the virtual-time loop.
- Fake whisper-server and llama-server (`lib/inference`): a stdlib HTTP
  server on `127.0.0.1:0`, started by a pytest fixture. It replays request
  and response pairs recorded from the real servers, stored in
  `lib/inference/testdata/`, with scripted delays and status codes. The
  same fake serves in-process tests and `--once` subprocesses.
- A fake systemd unit-state source (`lib/systemd`).
- Audio fixtures: short recordings of speech in Swedish and English, and
  silence, in `testdata/` of the subsystem that needs them. Synthetic audio
  (tones, silence, zeros) from a helper.

Fakes for an outside system that only one subsystem uses live in that
subsystem: PipeWire in capture, the browser in signals, the keys socket in
dictation, KWin in shortcuts.

### Subsystem ADR outline

Each subsystem ADR has these sections, in this order, under `## Decision`:

1. **Purpose:** what the subsystem does for the owner, and its PRDs.
2. **Components:** each component, its service or command, and its job.
3. **Writes:** each path and record kind it owns, with fields beyond the
   seam.
4. **Reads:** each path it reads, and the seam fields it relies on.
5. **Outside dependencies:** systems, tools and libraries.
6. **Internal design:** module layout, states, timing and algorithms.
7. **Failure modes:** each fault, what the subsystem does, and the fault
   code it reports.
8. **Config:** its config section, with defaults.
9. **Tests:** component tests, fixtures and fakes, and the PRD criteria each
   test checks.
10. **Build without hardware:** what an agent can build and test with no
    owner hardware, and what needs the owner.

## Alternatives considered

### Fields of each stream only in the subsystem ADRs (ADR-0003 as written)

- Each writer documents its own records.
- Rejected for the seams: parallel writers would guess the fields they read.
  The seam fields are fixed here; each writer still owns its model and adds
  fields freely.

### One central `contracts/` package

- Rejected in ADR-0009: the writer owns the contract. This ADR fixes the seam
  in prose; the code stays with the writer.

### One config file per subsystem

- Each subsystem edits only its file.
- Rejected: the owner keeps one file per host in the `machine` repo. Sections
  give the same ownership in one file.

### import-linter for the seam rule too

- import-linter can forbid imports with wildcards, but "only `contract`
  across subsystems" needs one contract per subsystem pair, and the list
  changes with every component.
- Rejected: one architecture test reads `SUBSYSTEM` and checks all imports.
  It stays correct as components move.

## Consequences

- Subsystem ADRs can be written and built in parallel. Each reads only this
  ADR, ADR-0003 and the contracts it uses.
- A change to a seam field changes this ADR and every reader's ADR.
- The health state has one owner (control). Services only report faults.
- Every subsystem must ship fixtures and run its tests with no hardware.
