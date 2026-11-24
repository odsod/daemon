# ADR-0016: Interactions

## Status

Proposed

## Date

2026-11-23

## Context

- A day of transcript is too long to read again. The owner wants each
  meeting or talk as one short document: who took part, who said what, and
  what came out of it (`interactions` PRD).
- The live pass gives cleaned text per utterance with no speaker names
  (ADR-0002, principle 10). The batch pass adds names and a summary with
  full context, hours later if need be. Quality comes before speed.
- Meeting names come from the browser's speaking indicator (ADR-0014).
  Other voices are "Others". Diarization is cut from v1 (ADR-0002).
- The inference host is shared. A summary holds one of two llama-server
  slots for tens of seconds. On battery, the batch pass waits (ADR-0005).
- The Go recorder already summarizes segments: one LLM call up to 35,000
  characters, map-reduce above, JSON with `title`, `summary` and `skip`, a
  title of at most 8 words and the labels Decided, Insight, Problem,
  Context and Next. This ADR keeps those numbers and makes the output
  structured.

## Decision

### Purpose

- Detect where each interaction starts and ends, from utterance times and
  events.
- For each finished interaction, write one document with fixed fields,
  named speakers, notes inline and an English summary, or skip it as
  greetings and noise.
- PRD: `interactions` (AC-1 to AC-13; AC-14 is manual). Also
  `dictation` AC-24 and `health-and-control` (the Warning for documents
  that wait over 24 h).

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

| Path                                                               | Kind     |
| ------------------------------------------------------------------ | -------- |
| `state/interactions/<day>.jsonl`                                   | Stream   |
| `state/documents/interactions/<local-day>-<HHMM>-<host>-<slug>.md` | Document |
| `state/finished/interactions/<day>.jsonl`                          | Stream   |
| `run/health/pipeline.json`, code `interactions-waiting`            | Document |

#### `interactions/` record

| Field          | Seam  | Meaning                                                  |
| -------------- | ----- | -------------------------------------------------------- |
| `kind`         | yes   | `interaction`                                            |
| `id`           | yes   | UTC start, `20261122T140000.000Z` (ADR-0003)             |
| `start`, `end` | yes   | First utterance start, last utterance end                |
| `outcome`      | yes   | `ok`, `skipped` or `failed`                              |
| `document`     | yes   | File name, when `ok`                                     |
| `meeting`      | yes   | `{platform, code}` or null                               |
| `error`        | yes   | One line, when `failed` (ADR-0010 conventions)           |
| `end_cause`    | extra | `silence`, `meeting`, `pin`                              |
| `lines`        | extra | Speech lines after echo drop                             |
| `setup`        | extra | Model name and a hash of the rendered prompts, for bench |

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
  - Owner Name
  - Alice Example
  - Others
title: API Migration Plan
---

# API Migration Plan

## Summary

One to three sentences of overview.

- **Decided:** Move the store to Postgres.
- **Next:** Alice: write the migration plan.

## Transcript

[15:00:05] **Owner Name:** Shall we start with the migration?
[15:00:12] **Alice Example:** Yes. The partitions cause gaps.
[15:03:40] 📝 **Note:** check the CDC lag numbers
```

- `meeting` is null outside a meeting. `participants` holds the owner,
  every name from the meeting's `participants` and `speaking` records in
  the range, and "Others" when a line has it.
- Times in the front matter are local with the offset, plus the IANA zone,
  so two hosts compare them with no guess (`interactions` AC-14).
- Name: local day and `HHMM` of `start`, the host, and a slug of the title
  (ASCII, lowercase, `-` between words, at most 40 characters). If the
  name exists with another `id`, add `-2`. The host in the name keeps hosts
  apart in one target (`publishing` AC-4).
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
| `config/`               | section `interactions`, `common`, `glossary.yaml`, `prompts/interactions-*.md`                                   |
| Its own outputs         | `interactions/` for done IDs; `finished/interactions/` and `documents/interactions/` front matter after a crash |

- Interactions reads no audio. Boundaries come from times only (ADR-0005,
  "Interaction boundaries in segmentation").
- Dictation text is never read: lines come only from `text` records with
  channel `mic` or `sys` (`interactions` AC-11, `dictation` AC-24).

### Outside dependencies

- llama-server on the inference host, through `lib/inference` with
  `common.inference.llama_url`. It must support `response_format` with a
  JSON schema.
- `lib/power` for mains power, `lib/textmatch` for the echo match (ADR-0010).
- `jinja2` for prompt templates.

### Internal design

#### Module layout

```
components/interactions/
├── __init__.py        SUBSYSTEM = "interactions"; run(config)
├── contract.py        InteractionRecord, DocumentMeta, parse_front_matter()
├── config.py          InteractionsConfig
├── boundaries.py      utterances + events + coverage → interactions (pure)
├── lines.py           text + notes → lines; echo drop (pure)
├── speakers.py        speaking intervals → name per line (pure)
├── summarize.py       one call or map-reduce; schema; validation
├── render.py          front matter and Markdown (pure)
├── batch.py           gate, steps, record
├── service.py         loop: follow inputs, detect, run batch
├── prompts/
│   ├── summarize.md   jinja2 template
│   └── combine.md     jinja2 template
└── tests/
```

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
- The batch pass starts one interaction only when all hold:
  - on mains power (`lib/power`, checked every `power_check_s`, 60 s);
    `interactions` AC-7;
  - no dictation or ambient utterance of this host lacks a `text` record
    (ADR-0003 "Pending work");
  - the llama URL answers.
- One interaction at a time. A started pass runs to its end, also if the
  host goes on battery meanwhile.

#### Batch pass

1. **Crash check.** Look for a document with this `id` in its front matter
   (names that start with `<local-day>-<HHMM>-<host>-`). If one exists,
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
5. **Skip.** No speech line: `skipped`, with no LLM call. At most
   `skip_max_lines` (3) lines: the summary may answer `skip`. More lines:
   a `skip` answer is ignored. `interactions` AC-6.
6. **Summary.** See below.
7. **Write** the document, then the `finished` record, then the
   `interactions/` record (ADR-0003 order).

#### Summary

- Input text: `[HH:MM:SS] Name: text`, notes as `[HH:MM:SS] Note: text`.
- `chunk_chars` must fit one llama-server slot. With `--parallel 2` and
  `--ctx-size 32768`, a slot holds 16,384 tokens for the prompt, the
  chunk and the reply. A spike on 2026-11-23 sent 35,000 Swedish
  characters with the summary prompt: `usage.prompt_tokens` was 9,680
  (135 for the fixed prompt), or 0.273 tokens per character. With 2,048
  output tokens, a 16,384-token slot fits 37,000 characters and a
  32,768-token slot fits 82,000. The default is 37,000, safe for both.
- Up to `chunk_chars` characters: one call with the
  `interactions-summarize` prompt.
- Longer: split at line ends into chunks of at most `chunk_chars`,
  summarize each, then one call with `interactions-combine` over the
  chunk results. No chapters (PRD "Not planned").
- Every call uses `response_format` with this JSON schema:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["skip", "title", "overview", "points"],
  "properties": {
    "skip": { "type": "boolean" },
    "title": { "type": "string" },
    "overview": { "type": "string" },
    "points": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["label", "text", "owner"],
        "properties": {
          "label": {
            "type": "string",
            "enum": ["Decided", "Insight", "Problem", "Context", "Next"]
          },
          "text": { "type": "string" },
          "owner": { "type": ["string", "null"] }
        }
      }
    }
  }
}
```

- The schema ships as `prompts/summary.schema.json`. The request sends it
  as `response_format: {"type": "json_schema", "json_schema": {"name":
  "summary", "schema": …}}`. The combine call uses the same schema.

- The prompt (static rules, from the PRD):
  - write in English, also for Swedish talk; never translate the
    transcript;
  - use only what the transcript says; leave a point out when unsure;
  - an overview of 1 to 3 sentences; points only under the five labels;
    leave out labels with nothing to say;
  - a `Next` point names its owner when the transcript names one;
  - notes are the owner's own context;
  - lines from "Others" may be several people; never guess who;
  - glossary terms keep their spelling.
- Template variables: `owner_name`, `languages`, the glossary (most
  important last), `title_max_words`. Overrides in
  `config/prompts/interactions-summarize.md` and
  `config/prompts/interactions-combine.md` are templates too (ADR-0010).
- Reasoning is off for these calls. The `machine` repo runs llama-server
  with `--reasoning off` today. The request also sends
  `chat_template_kwargs: {"enable_thinking": false}`, so a server restart
  with other flags does not turn it on.
- Validation after the reply: strip reasoning blocks (`<think>…</think>`)
  as a guard;
  cut the title to `title_max_words` (8) words; cut the overview to 3
  sentences; drop points with an unknown label or empty text. AC-3, AC-5.
- `setup` in the record is the model name and a hash of the rendered
  prompts, so bench can tell setups apart (`benchmarking` AC-11).

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
- A 5 min interaction on an idle host gets its document within a few
  minutes of its close. `interactions` AC-1 allows 24 h.
- Requests use `request_timeout_s` (600 s): a long chunk on a busy slot can
  take minutes.

### Failure modes

| Fault                                     | What interactions does                                                   | Fault code                                    |
| ----------------------------------------- | ------------------------------------------------------------------------ | --------------------------------------------- |
| On battery                                | Detects boundaries; runs no batch pass                                   | none                                          |
| llama-server unreachable or timing out    | Waits; retries every 60 s; the attempt does not count                    | none (speech reports `inference-unreachable`) |
| Error reply, bad JSON, schema failure     | Retry after 1 min and 5 min; after `max_attempts` (3), a `failed` record | none                                          |
| Context too long for the model            | Counts as an attempt; the owner lowers `chunk_chars`                     | none                                          |
| A pending interaction ended over 24 h ago | Reports the Warning with the count and the oldest end                    | `interactions-waiting`                        |
| Crash between document and records        | Step 1 finds the document and writes the missing records                 | none                                          |
| No signals (Chrome off, no indicator)     | `sys` lines are "Others"; `meeting` may be null                          | none (signals reports)                        |
| Unexpected exception                      | Ends the pipeline; systemd restarts it (ADR-0004)                        | none                                          |

- `interactions-waiting` message: "N interaction documents waiting since
  `<local time>`". `fix` is null: the cause is power or the inference host,
  and their own states show it. The fault clears when no pending
  interaction is over 24 h old (`interactions` AC-12).
- Attempt counts live in memory. A restart gives a failing interaction 3
  new tries. systemd's start limit bounds the loop.

### Config

Section `interactions`:

```json
{
  "interactions": {
    "owner_name": "Owner",
    "owner_aliases": [],
    "languages": ["Swedish", "English"],
    "silence_cutoff_s": 300,
    "meeting_cutoffs": {},
    "model": "default",
    "chunk_chars": 37000,
    "request_timeout_s": 600,
    "max_attempts": 3,
    "skip_max_lines": 3,
    "title_max_words": 8,
    "speaker_pad_s": 0.5,
    "echo_threshold": 0.6,
    "echo_tolerance_s": 2,
    "waiting_warn_h": 24,
    "power_check_s": 60
  }
}
```

- `meeting_cutoffs` maps a meeting code to a cutoff in seconds, such as
  `{"abc-defg-hij": 60}` for the permanent call.
- `owner_aliases` holds other names the platforms show for the owner's own
  tile.

### Tests

Component tests use a temp state root, a fake clock, JSONL inputs in
`testdata/` and the fake llama-server of `lib/inference`.

| Test                 | Input                                                                                                  | Checks                                              |
| -------------------- | ------------------------------------------------------------------------------------------------------ | --------------------------------------------------- |
| `test_boundaries.py` | Utterance timelines: 5 min gap, meeting change, pin, profile cutoff, backlog with no `covered`, logout | `interactions` AC-2                                 |
| `test_speakers.py`   | `speaking` timelines with overlap, owner tile, no meeting                                              | Names and "Others": AC-3 (logic for AC-4)           |
| `test_echo.py`       | `mic` lines that repeat `sys` lines                                                                    | Dropped with full context                           |
| `test_document.py`   | Scripted summary reply                                                                                 | Fields, notes inline, title ≤ 8 words: AC-3, AC-13  |
| `test_summary.py`    | Replies with 5 sentences, a bad label, `<think>`, bad JSON, long input                                 | Validation, retries, map-reduce: AC-5               |
| `test_skip.py`       | 2 greeting lines; 0 lines; 10 lines with `skip: true`                                                  | AC-6                                                |
| `test_power.py`      | Fake `/sys/class/power_supply`: battery, then mains                                                    | No pass on battery; start within 5 min: AC-7        |
| `test_crash.py`      | Crash after the document write, before each record                                                     | One document, one `finished`: AC-8                  |
| `test_dictation.py`  | `dic` text inside a meeting range                                                                      | Not in document or prompt: AC-11, `dictation` AC-24 |
| `test_waiting.py`    | Pending interaction 25 h old                                                                           | Warning set, then cleared: AC-12                    |
| `test_gate.py`       | Pending utterances; fake llama down then up                                                            | No request while pending; waits; AC-1               |

- System test (root `tests/`): fake CDP (ADR-0014), JSONL utterances and
  text, fake llama. One scripted meeting gives one document with named
  `sys` lines and its `ok` record (AC-1, AC-3, AC-13).
- Bench (ADR-0019) checks AC-4, AC-9 and AC-10 on real cases. The `setup`
  field lets it group results.

### Build without hardware

- All of it, with the fakes. The summary logic is tested against scripted
  replies.
- The owner must:
  - check real summaries against the model in use (AC-5 and AC-9 need a
    real model; an agent can run it against the inference host);
  - write reference summaries for bench (AC-10);
  - check AC-14 by hand: one meeting on two hosts.

## Alternatives considered

### A second ASR pass in the batch pass

- Might fix live-pass errors, but doubles GPU time on the shared host.
- Deferred until bench shows a gain (ADR-0005).

### A full-context cleanup pass over every line

- ADR-0005 planned it. It costs one more LLM pass over the whole
  transcript and can change what people said.
- Left out of v1: the summary reads through ASR errors, and the transcript
  stays the live-pass text. Add it if bench shows that names or terms
  suffer.

### Multi-speaker attribution with percentages

- The Go recorder writes `[Alice 70% / Bob 30%]` when two speakers overlap.
- Left out: the PRD wants one name per line. Largest overlap is simpler,
  and bench measures the error.

### Free-form Markdown summary from the model

- The Go recorder asks for Markdown in a JSON string.
- Rejected: labels, overview length and title length can then only be
  checked by parsing prose. The schema makes AC-5 a validation.

### Boundaries in segmentation

- Rejected in ADR-0005: boundaries are meeting rules that the owner tunes,
  not signal processing.

### Diarization, chapters, general meeting profiles

- Cut by the owner. A meeting profile sets only the silence cutoff.

## Consequences

- One document per interaction on each host, hours late at worst, never
  on battery.
- Speaker names exist only inside Meet and Teams meetings with a working
  indicator. All else is the owner and "Others".
- Boundaries need segmentation's `coverage/` stream. Without it, an
  interaction closes only at the next utterance, pin or meeting change.
- The summary format is fixed by the schema. A change of labels is a
  change of this ADR and the PRD.
- Deliberately left out: second ASR pass, full-context cleanup,
  diarization, chapters, cross-host merge and a "run now" command.
