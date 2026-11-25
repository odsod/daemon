# ADR-0016: Interactions

## Status

Proposed

## Date

2026-11-23. Changed 2026-11-25: no LLM summary.

## Context

- A day of transcript is too long to read again. The owner wants each
  meeting or talk as one short document: who took part, who said what, and
  what came out of it (`interactions` PRD).
- The live pass gives cleaned text per utterance with no speaker names
  (ADR-0002, principle 10). The batch pass adds names with full context,
  hours later if need be.
- Meeting names come from the browser's speaking indicator (ADR-0014).
  Other voices are "Others". Diarization is cut from v1 (ADR-0002).
- The brain vault agent reads every raw interaction document and writes
  its own title and summary with a frontier model. A daemon summary from
  the local LLM is duplicate work by a weaker model. Bench (2026-11-25):
  the local model looped on a 47,000-character meeting and skipped a full
  standup.
- Owner decision (2026-11-25): the daemon writes no summary and calls no
  LLM for interactions. A document has no title and no summary until the
  brain agent runs. The file name uses the calendar meeting title.

## Decision

### Purpose

- Detect where each interaction starts and ends, from utterance times and
  events.
- For each finished interaction, write one document with fixed fields,
  named speakers and notes inline, or skip it when it holds almost no
  speech and no note.
- PRD: `interactions` (AC-1 to AC-3, AC-8, AC-11 to AC-13, AC-15 to
  AC-17; AC-4 is bench, AC-14 is manual). Also `dictation` AC-24 and
  `health-and-control` (the Warning for documents that wait over 24 h).

### Components

| Component      | Service    | Job                                                          |
| -------------- | ---------- | ------------------------------------------------------------ |
| `interactions` | `pipeline` | Boundaries, then the batch pass; sole writer of both outputs |

- No commands. The PRD rules out a command to run the batch pass now
  (`health-and-control` "Not planned"). `odsodctl run interactions` runs it
  alone for debugging.
- `odsodctl run interactions --once` drains: it detects boundaries, runs
  the batch pass on every pending interaction that passes the gate, and
  exits 0 (ADR-0010 decision on `--once`). Tests and bench use it.

### Writes

| Path                                                                 | Kind     |
| -------------------------------------------------------------------- | -------- |
| `state/interactions/<day>.jsonl`                                     | Stream   |
| `state/documents/interactions/<local-day>-<HHMM>-<host>[-<slug>].md` | Document |
| `state/finished/interactions/<day>.jsonl`                            | Stream   |
| `run/health/pipeline.json`, code `interactions-waiting`              | Document |

#### `interactions/` record

| Field          | Seam  | Meaning                                        |
| -------------- | ----- | ---------------------------------------------- |
| `kind`         | yes   | `interaction`                                  |
| `id`           | yes   | UTC start, `20261122T140000.000Z` (ADR-0003)   |
| `start`, `end` | yes   | First utterance start, last utterance end      |
| `outcome`      | yes   | `ok`, `skipped` or `failed`                    |
| `document`     | yes   | File name, when `ok`                           |
| `meeting`      | yes   | `{platform, code}` or null                     |
| `error`        | yes   | One line, when `failed` (ADR-0010 conventions) |
| `end_cause`    | extra | `silence`, `meeting`, `pin`                    |
| `lines`        | extra | Speech lines after echo drop                   |

- One record per interaction, written after its document (ADR-0003). Any
  outcome makes it done. A `skipped` interaction is never tried again.

#### The document

Front matter holds every field an agent needs, with no prose to parse
(`interactions` AC-13):

```markdown
---
type: interaction
id: 20261122T140000.000Z
host: work-laptop
start: 2026-11-22T15:00:00.000+01:00
end: 2026-11-22T15:42:10.500+01:00
timezone: Europe/Stockholm
meeting:
  platform: meet
  code: abc-defg-hij
  title: Weekly sync
participants:
  - Alice Example
  - Owner Name
title: Weekly sync
---

# Weekly sync

## Transcript

[15:00:05] **Owner Name:** Shall we start with the migration? <!-- id:mic-20261122T140005.000Z -->
[15:00:12] **Alice Example:** Yes. The partitions cause gaps. <!-- id:sys-20261122T140012.000Z heard: Yes. The partition is called gaps. -->
[15:03:40] 📝 **Note:** check the CDC lag numbers
```

- Each speech line ends with an HTML comment, hidden when rendered: the
  utterance ID (`odsodctl audio play <id>`, ADR-0011), and `heard:` with
  the ASR text when cleanup changed the line (the `heard` field of the
  `text` record, ADR-0012). `--` in that text becomes `- -`, so the comment
  stays valid.
- `meeting` is null outside a meeting, else only `platform`, `code` and
  `title` (no raw event fields). `participants` holds every speaker name
  of the lines and every name from the meeting's `participants` and
  `speaking` records in the range. The labels `Others` and the unset owner
  name (`Owner`) are not people, so they are left out.
- `title` is the meeting title (`meeting.title`), or null outside a
  meeting. The H1 is the title, or `Interaction HH:MM` (local time of the
  first utterance) with no title. There is no summary section. The brain
  vault agent writes the title and summary it needs.
- `start` is the first utterance's start, except for the first interaction
  of a meeting: it starts at the `meeting-start` event, so silence before
  the first word belongs to the meeting. `id` stays the first utterance's
  start (ADR-0003).
- Times in the front matter are local with the offset, plus the IANA zone,
  so two hosts compare them with no guess (`interactions` AC-14).
- Name: `YYYY-MM-DD-HHMM-<host>-<slug>.md`, with the local day and `HHMM`
  of the first utterance's start (not the front matter `start`, which can
  be the meeting start), the host, and a slug of the meeting title (ASCII,
  lowercase, `-` between words, at most 40 characters). No meeting title,
  or a title with no ASCII letter or digit left (only emoji, say):
  `YYYY-MM-DD-HHMM-<host>.md`. If the name exists with another `id`, add
  `-2` before `.md`. The host in the name keeps hosts apart in one target
  (`publishing` AC-4). `interactions` AC-16.
- Written whole with `lib/documents` (temp name, rename). It never changes
  after that.

#### `finished/interactions/` record

| Field      | Seam  | Meaning                   |
| ---------- | ----- | ------------------------- |
| `kind`     | yes   | `finished`                |
| `document` | yes   | File name of the document |
| `type`     | yes   | `interactions`            |
| `id`       | extra | The interaction ID        |

- Written right after the document rename, before the `interactions/`
  record. publishing reads only `state/finished/*/` to find work
  (ADR-0010 decision). A `skipped` or `failed` interaction has no document
  and no `finished` record.

### Reads

| Path                    | Seam fields relied on                                                                                           |
| ----------------------- | --------------------------------------------------------------------------------------------------------------- |
| `utterances/ambient/`   | `utterance` (`id`, `channel`, `start`, `end`); (`coverage/` below)                                              |
| `coverage/`             | `covered` (`channel`, `end`): segmentation's coverage (ADR-0012)                                                |
| `utterances/dictation/` | `utterance` (`id`): the pending gate                                                                            |
| `text/`                 | `input`, `outcome`, `channel`, `start`, `end`, `text`                                                           |
| `events/signals/`       | all four kinds; `at` when present (ADR-0014)                                                                    |
| `events/user/`          | `note` (`text`), `pin`                                                                                          |
| `events/capture/`       | `start` (`prev_end`, `audio_start`), `gap` (`start`, `end`), `stop`: recording-off ranges count as covered      |
| `config/`               | section `interactions`, `common`                                                                                |
| Its own outputs         | `interactions/` for done IDs; `finished/interactions/` and `documents/interactions/` front matter after a crash |

- Interactions reads no audio. Boundaries come from times only (ADR-0005,
  "Interaction boundaries in segmentation").
- Dictation text is never read: lines come only from `text` records with
  channel `mic` or `sys` (`interactions` AC-11, `dictation` AC-24).

### Outside dependencies

- None on the inference host. Interactions call no LLM. llama-server now
  serves cleanup only ([ADR-0023](0023-inference-servers.md)).
- `lib/textmatch` for the echo match (ADR-0010).

### Internal design

#### Module layout

```
components/interactions/
├── __init__.py        SUBSYSTEM = "interactions"; run(config)
├── contract.py        InteractionRecord, DocumentMeta, parse_front_matter()
├── config.py          InteractionsConfig
├── boundaries.py      utterances + events + coverage → interactions (pure)
├── lines.py           text + notes → lines; echo drop; skip rule (pure)
├── speakers.py        speaking intervals → name per line (pure)
├── render.py          front matter, Markdown, heading, file name (pure)
├── batch.py           gate, steps, record
├── service.py         loop: follow inputs, detect, run batch
└── tests/
```

- Boundary detection reads the whole retention window, about 1 s on a busy
  day, and coverage records mark the view dirty several times a second. It
  runs at most every 30 s (`DETECT_EVERY_S`), so it never starves the other
  pipeline components of the event loop.

#### Boundaries

Pure function of ambient utterances, events and coverage. Utterances in
start order, from the end of the newest recorded interaction (or the start
of the pending window, 14 days).

- The first utterance opens an interaction. Its meeting is the meeting
  open at that time (from `meeting-start` and `meeting-end`), or none.
- The next utterance `u` closes the open interaction, and opens a new one,
  when any holds:
  - **pin:** a `pin` record falls after the open start and at or before
    `u.start`;
  - **meeting:** the meeting at `u.start` differs from the open one (a
    start, an end, or another code);
  - **silence:** `u.start` minus the open interaction's last end is at
    least its cutoff.
- With no next utterance, the open interaction closes when coverage of both
  channels passes its last end plus the cutoff, or passes a pin or meeting
  change after its last end. Coverage is segmentation's `covered` end
  in `state/coverage/`,
  moved forward across recording-off ranges from `events/capture/`. So a
  backlog never looks like silence, and a logout still ends the talk.
- Recording-off ranges, the same rule as the transcript (ADR-0015, Gaps):
  from each `start` record's `prev_end` to its `audio_start`, each `gap`
  record's `start` to `end`, and from a `stop` with no later `start` to
  `now`. A crash writes no `stop`, but the next `start` still bounds the
  range, so a crash never holds an interaction open.
- Cutoff: `meeting_cutoffs[code]` when the meeting has an entry, else
  `silence_cutoff_s` (300 s). This is the meeting profile, and the only
  thing it sets (`interactions` AC-2, PRD "Not planned").
- `end` is the last utterance end; `end_cause` records the rule.
- A pin with no utterance before it in the open range does nothing.
- Same inputs give the same interactions, so a restart finds the same IDs.

#### Pending and the gate

- Pending: closed interactions with no record, oldest first.
- The batch pass starts one interaction only when no dictation or ambient
  utterance of this host lacks a `text` record (ADR-0003 "Pending work").
- No power and no inference host check: the pass is local file work. On
  battery it waits only as long as speech waits (ADR-0012, battery rule).
- One interaction at a time. The service yields to the event loop after
  each one, so a backlog does not starve the other pipeline components.

#### Batch pass

1. **Crash check.** Look for a document with this `id` in its front matter
   (names that start with `<local-day>-<HHMM>-<host>`). If one exists,
   write its `finished` record if it lacks one, then the `ok` record, and
   stop. A crash between the document and either record then gives no
   second document and no lost delivery (`interactions` AC-8).
2. **Lines.** Each `text` record with outcome `ok`, channel `mic` or `sys`,
   whose input is an utterance of the range. Plus each `note` in the range.
   Sort by time.
3. **Echo drop.** Drop a `mic` line whose text overlaps the `sys` text in
   its window (±`echo_tolerance_s`, 2 s) by at least `echo_threshold`
   (0.6), with `lib.textmatch.overlap`, the same function and rule as the
   transcript (ADR-0015, Echo). Here all `sys` text is known, so nothing
   waits.
4. **Speakers.**
   - `mic`: `owner_name`.
   - `sys`: build intervals per name from the meeting's `speaking` records:
     a name speaks from the record's `at` until the next record without
     it. Remove the owner (`owner_name` and `owner_aliases`; the owner's
     tile speaks when mic bleed or the owner speaks). Widen the line's
     range by `speaker_pad_s` (0.5 s). The name with the largest overlap
     wins. No overlap, or no meeting: "Others".
   - This is the Go recorder's rule. Bench measures it (`interactions`
     AC-4). A wrong name never stops a document.
5. **Skip.** At most `skip_max_lines` (3) speech lines and no note line:
   `skipped`, with no document. Any note, or more speech lines: always a
   document. The rule is deterministic, so a restart gives the same
   outcome. `interactions` AC-17.
6. **Write** the document, then the `finished` record, then the
   `interactions/` record (ADR-0003 order).

#### Timing

- Inputs are followed with `lib/streams` (inotify plus a 5 s scan).
- Boundaries are recomputed only when a boundary input changes: a new
  ambient utterance, a coverage record, a `pin`, a `meeting-start` or
  `meeting-end`, or a capture record. `speaking`, `participants`, `text`
  and `note` records never move a boundary. They are read when the batch
  pass renders the document.
- The input view is kept sorted in memory. A new record is inserted, not
  resorted. A 14-day backlog with a `speaking` change every few seconds
  then costs no boundary work.
- A 5 min interaction gets its document at most 30 s (`DETECT_EVERY_S`)
  after its close, once all its speech has text. `interactions` AC-1
  allows 24 h.

### Failure modes

| Fault                                                   | What interactions does                                          | Fault code                                    |
| ------------------------------------------------------- | --------------------------------------------------------------- | --------------------------------------------- |
| Speech text pending (inference host down, battery)      | Detects boundaries; runs no batch pass                          | none (speech reports `inference-unreachable`) |
| Bad front matter in an own document, bad meeting record | A `failed` record at once; no retry: the same inputs fail again | none                                          |
| A pending interaction ended over 24 h ago               | Reports the Warning with the count and the oldest end           | `interactions-waiting`                        |
| Crash between document and records                      | Step 1 finds the document and writes the missing records        | none                                          |
| No signals (Chrome off, no indicator)                   | `sys` lines are "Others"; `meeting` may be null                 | none (signals reports)                        |
| Unexpected exception                                    | Ends the pipeline; systemd restarts it (ADR-0004)               | none                                          |

- `interactions-waiting` message: "N interaction documents waiting since
  `<local time>`". `fix` is null: the cause is pending speech text, and
  speech's own state shows it. The fault clears when no pending
  interaction is over 24 h old (`interactions` AC-12).

### Config

Section `interactions`:

```json
{
  "interactions": {
    "owner_name": "Owner",
    "owner_aliases": [],
    "silence_cutoff_s": 300,
    "meeting_cutoffs": {},
    "skip_max_lines": 3,
    "speaker_pad_s": 0.5,
    "echo_threshold": 0.6,
    "echo_tolerance_s": 2,
    "waiting_warn_h": 24
  }
}
```

- `meeting_cutoffs` maps a meeting code to a cutoff in seconds, such as
  `{"abc-defg-hij": 60}` for the permanent call.
- `owner_aliases` holds other names the platforms show for the owner's own
  tile.
- The section ignores unknown keys. The keys of the old summary (`model`,
  `chunk_chars`, `request_timeout_s`, `max_attempts`, `title_max_words`,
  `languages`, `power_check_s`) still load, with no effect. Prompt
  overrides `prompts/interactions-*.md` are no longer read.

### Tests

Component tests use a temp state root, a fake clock and JSONL inputs.

| Test              | Input                                                                                                  | Checks                                                  |
| ----------------- | ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------- |
| `test_core.py`    | Utterance timelines: 5 min gap, meeting change, pin, profile cutoff, backlog with no `covered`, logout | `interactions` AC-2                                     |
| `test_core.py`    | `speaking` timelines with overlap, owner tile, no meeting; `mic` lines that repeat `sys` lines         | Names and "Others": AC-3 (logic for AC-4); echo drop    |
| `test_core.py`    | Table: speech and note line counts around `skip_max_lines`                                             | Skip rule: AC-17                                        |
| `test_core.py`    | Table: meeting titles, emoji only, none; a taken name                                                  | Title, H1, file name, `-2`: AC-16                       |
| `test_core.py`    | Crash after the document write, before each record                                                     | One document, one `finished`: AC-8                      |
| `test_service.py` | Pending dictation text, then its record; 25 h old interaction                                          | No pass while pending; Warning set, then cleared: AC-12 |
| `test_service.py` | Old summary keys in the section                                                                        | They load with no error                                 |

- System test (root `tests/test_interactions.py`): JSONL signals,
  utterances, text, a note and dictation; no LLM listens and the host is on
  battery. One scripted meeting gives one document named after the meeting
  title, with named `sys` lines and its `ok` record (AC-1, AC-3, AC-11,
  AC-13, AC-16).
- Bench (ADR-0019) checks AC-4 on real cases.

### Build without hardware

- All of it. No step needs a model or the inference host.
- The owner must check AC-14 by hand: one meeting on two hosts.

## Alternatives considered

### A second ASR pass in the batch pass

- Might fix live-pass errors, but doubles GPU time on the shared host.
- Deferred until bench shows a gain (ADR-0005).

### A full-context cleanup pass over every line

- ADR-0005 planned it. It costs one more LLM pass over the whole
  transcript and can change what people said.
- Left out of v1: the brain vault agent reads through ASR errors, and the
  transcript stays the live-pass text. Add it if bench shows that names or terms
  suffer.

### Multi-speaker attribution with percentages

- The Go recorder writes `[Alice 70% / Bob 30%]` when two speakers overlap.
- Left out: the PRD wants one name per line. Largest overlap is simpler,
  and bench measures the error.

### A summary from the local LLM

- Until 2026-11-25 the batch pass asked llama-server for a JSON summary:
  a title of at most 8 words, an overview and labeled points, with
  map-reduce over 37,000-character chunks.
- Dropped (owner decision, 2026-11-25): the brain vault agent summarizes
  every document with a frontier model. The local model looped on a
  47,000-character meeting and skipped a full standup (bench,
  2026-11-25). The daemon summary was duplicate work of lower quality,
  and it held a llama-server slot for tens of seconds.

### Boundaries in segmentation

- Rejected in ADR-0005: boundaries are meeting rules that the owner tunes,
  not signal processing.

### Diarization, chapters, general meeting profiles

- Cut by the owner. A meeting profile sets only the silence cutoff.

## Consequences

- One document per interaction on each host, within 30 s of its close
  once speech has caught up. It has no summary, and no title outside a
  meeting, until the brain vault agent runs.
- Speaker names exist only inside Meet and Teams meetings with a working
  indicator. All else is the owner and "Others".
- Boundaries need segmentation's `coverage/` stream. Without it, an
  interaction closes only at the next utterance, pin or meeting change.
- Interactions do not depend on the inference host. Only the speech
  text they read does.
- Deliberately left out: second ASR pass, full-context cleanup,
  diarization, chapters, cross-host merge and a "run now" command.
