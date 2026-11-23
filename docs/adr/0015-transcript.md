# ADR-0015: Transcript

## Status

Proposed

## Date

2026-11-23

## Context

- The owner and agents need today's record of what was said while the day
  runs, and a finished record per day in the vault (`live-transcript`).
- Speech text arrives per utterance in `text/`, out of order: dictation
  first, then ambient, oldest first (ADR-0003). Meetings, notes, pins and
  recording gaps arrive as events.
- Without a headset, the meeting's voices reach the mic. The same phrase
  then comes as `sys` text and as `mic` text (`live-transcript` AC-6).
- The daily transcript is append-only Markdown (ADR-0003). It is finished
  when its local day has ended and none of its utterances is pending, at
  the latest 48 h after the day ended.
- The Go recorder writes one line per chunk in the form
  `[HH:MM:SS] <emoji> **<tag>** <text>` and drops `mic` text that overlaps
  `sys` text by 60% of tokens. The owner reads that format today. This ADR
  keeps the line format and the match, and adds IDs, gaps and the finish.

## Decision

### Purpose

- Write one daily transcript per host and local day, within seconds of
  speech: speech lines with their source, dictation, notes, pins, meeting
  starts and ends, and recording gaps with their cause.
- Finish each day's transcript once, so publishing can deliver it.
- Give the owner and agents `odsodctl note`, `pin` and `transcript`.
- PRD: `live-transcript` (all ACs except the bench ACs that belong to
  speech). Also `health-and-control` (`--json` on its commands, AC-10).

### Components

| Component    | Service or command     | Job                                                   |
| ------------ | ---------------------- | ----------------------------------------------------- |
| `transcript` | `pipeline`             | Sole writer of `documents/transcripts/`               |
| `transcript` | `odsodctl transcript`  | Print a day's transcript, as text or JSON (read-only) |
| `note`       | `odsodctl note <text>` | Append a `note` record to `events/user/`              |
| `pin`        | `odsodctl pin [text]`  | Append a `pin` record to `events/user/`               |

- `odsodctl transcript` lives in the `transcript` folder and never runs
  the service loop (ADR-0009).
- `note` and `pin` are one tiny component each. Both use the record models
  in `components/note/contract.py` and `components/pin/contract.py`.
  `note -` reads the text from stdin, for agents that pipe text.
- `odsodctl run transcript --once` drains: it writes every ready line,
  finishes every day whose rule holds, and exits 0 (ADR-0010 decision on
  `--once`). Held `mic` lines stay held. Tests use it.

### Writes

| Path                                                | Kind                  | Writer       |
| --------------------------------------------------- | --------------------- | ------------ |
| `state/documents/transcripts/<local-day>-<host>.md` | Markdown, append-only | `transcript` |
| `state/finished/transcript/<day>.jsonl`             | Stream                | `transcript` |
| `state/events/user/<day>.jsonl`, kind `note`        | Stream                | `note`       |
| `state/events/user/<day>.jsonl`, kind `pin`         | Stream                | `pin`        |

#### `events/user/` records

| Kind   | Seam fields        | Extra fields |
| ------ | ------------------ | ------------ |
| `note` | `text`             | none         |
| `pin`  | `text` (may be "") | none         |

- Each record is one `O_APPEND` write of one line (ADR-0003). control
  writes `pause` and `resume` to the same files; each kind has one writer
  (ADR-0010).

#### The daily transcript

File start, written once when the file is created:

```markdown
---
type: transcript
host: work-laptop
date: 2026-11-23
timezone: Europe/Stockholm
---

# Transcript 2026-11-23, work-laptop
```

Then one line per event, in arrival order:

```
[HH:MM:SS] <emoji> **<tag>** <text> <!-- id:<key> -->
```

| Tag   | Emoji | Source                     | Text                                                                                              | Key                                  |
| ----- | ----- | -------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------ |
| `mic` | 🎤    | Owner (ambient mic)        | Cleaned text                                                                                      | utterance ID                         |
| `sys` | 🔊    | Other side (system audio)  | Cleaned text                                                                                      | utterance ID                         |
| `dic` | ⌨️    | Owner's dictation          | Cleaned or raw text                                                                               | utterance ID                         |
| `nfo` | 📝    | `odsodctl note`            | Note text                                                                                         | `note:<ts>`                          |
| `pin` | 📍    | `odsodctl pin`             | Pin text, or empty                                                                                | `pin:<ts>`                           |
| `mtg` | 🪟    | Meeting start or end       | `started: <title> (<platform> <code>)`, `ended: <platform> <code>`                                | `mtg:<kind>:<ts>`                    |
| `gap` | ⏸️    | Recording gap or lost text | `not recording <HH:MM:SS>–<HH:MM:SS> (<cause>)`, `untranscribed <HH:MM:SS>–<HH:MM:SS> (<reason>)` | `gap:<start>`, `untx:<utterance ID>` |

- The time is local time of the event: the utterance `start`, or the
  event's `ts` (`at` for signals records, when present). `live-transcript`
  AC-2.
- Speech lines have no speaker names. The batch pass adds them
  (ADR-0002, principle 10).
- Lines appear in arrival order, not time order. A dictation line can come
  before an older ambient line (ADR-0005). Each line has its own time.
- The trailing HTML comment holds the line's key. Markdown viewers hide it.
  It makes the file its own checkpoint: a restart reads the keys back and
  writes no line twice (`live-transcript` AC-10). One line is one `write`
  call, so a line and its key commit together.
- Text is one line: newlines become spaces, and `<!--` is escaped.
- The day file holds no finish mark, so the vault copy stays clean.

#### `finished/transcript/` record

| Field      | Seam  | Meaning                            |
| ---------- | ----- | ---------------------------------- |
| `kind`     | yes   | `finished`                         |
| `document` | yes   | File name, `<local-day>-<host>.md` |
| `type`     | yes   | `transcripts`                      |
| `day`      | extra | The local day                      |
| `capped`   | extra | true when the 48 h cap finished it |

- A transcript is finished when its `finished` record exists. transcript
  writes nothing to the day file after it. publishing reads only
  `state/finished/*/` to find work (ADR-0010 decision).

### Reads

| Path                     | Seam fields relied on                                                                                           | Why                              |
| ------------------------ | --------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| `text/`                  | `input`, `outcome`, `channel`, `start`, `end`, `text`                                                           | Speech lines                     |
| `events/signals/`        | `meeting-start` (`platform`, `code`, `title`), `meeting-end`                                                    | Meeting lines                    |
| `events/user/`           | `note`, `pin`, `pause`                                                                                          | Note and pin lines; gap cause    |
| `events/capture/`        | `start` (`channel`, `prev_end`, `audio_start`); `gap` (`channel`, `start`, `end`, `reason`); `stop` (`channel`) | Gap lines and their cause        |
| `utterances/ambient/`    | `utterance` (`id`, `channel`, `start`, `end`)                                                                   | Pending check, echo wait, finish |
| `coverage/`              | `covered` (`channel`, `end`)                                                                                    | Echo wait, finish                |
| `utterances/dictation/`  | `utterance` (`id`, `start`, `end`)                                                                              | Pending check                    |
| `documents/transcripts/` | its own files                                                                                                   | Rebuild keys at start            |
| `finished/transcript/`   | its own records                                                                                                 | Which days are closed            |
| `config/config.json`     | `transcript`, `common.host`                                                                                     |                                  |

- `coverage/` is segmentation's stream (`state/coverage/<day>.jsonl`,
  ADR-0012). Without it the finish and the echo wait have no safe signal.

### Outside dependencies

- None beyond `lib/` and the local time zone (`zoneinfo` from
  `/etc/localtime`).
- `lib/textmatch` for the echo match (ADR-0010).

### Internal design

#### Module layout

```
components/transcript/
├── __init__.py       SUBSYSTEM = "transcript"; run(config)
├── contract.py       Finished record; line format, parse_line(), parse_file()
├── config.py         TranscriptConfig
├── lines.py          records → Line (pure)
├── echo.py           echo hold and drop (pure)
├── gaps.py           recording-off ranges and causes (pure)
├── days.py           day assignment and finish rule (pure)
├── writer.py         the loop: follow inputs, append lines, finish days
├── cli.py            odsodctl transcript
└── tests/
components/note/      __init__.py, contract.py, cli.py, tests/
components/pin/       __init__.py, contract.py, cli.py, tests/
```

#### Main loop

- `lib/streams` follows `text/`, `events/*/`, `utterances/*/` and
  `coverage/` (inotify
  plus a scan every 2 s). Each new record goes to the pure parts.
- A flush step runs on each new record and every 1 s. It appends every line
  that is ready, then checks each open day for its finish.
- All decisions are pure functions of the records seen and the time. The
  writer only does I/O. A restart replays the inputs of each open day and
  gets the same decisions.

#### Day assignment

- A line belongs to the local day of its time, in the host's time zone.
- Open days: every day with no `finished` record, and every day
  with an utterance or event, within the pending window (14 days,
  ADR-0003).
- The file is created at its first line. A day with no line has no file
  and no delivery: a silent day gives no transcript (`live-transcript`
  AC-9).
- A line for a finished day is not written. Its text stays in `text/`, and
  the 48 h cap line already names the range. The transcript never changes
  after the finish (`live-transcript` AC-12).

#### Speech lines

- `text` with outcome `ok` and non-empty `text`: a line with tag `mic`,
  `sys` or `dic` from `channel`.
- `empty`: no line (`live-transcript` AC-9).
- `failed` or `expired`: an `untranscribed` gap line for that utterance,
  with the reason. A reader then sees "lost", not "silent".
- `dic` lines are never held. The speech subsystem drops `mic` speech
  inside a dictation window, so one dictation gives one line
  (`live-transcript` AC-16; ADR-0012).

#### Echo drop

A `mic` line waits until the `sys` text of the same time is known, then is
dropped if it repeats it. `live-transcript` AC-6.

1. Window: the `mic` range widened by `echo_tolerance_s` (2 s) on each side.
2. Wait while either holds:
   - `sys` coverage (`covered` in `coverage/`) ends before the window end, so a
     `sys` utterance in the window may still be cut;
   - a `sys` utterance that overlaps the window has no `text` record yet.
3. Stop waiting at `echo_hold_max_s` (120 s) after the `mic` text arrived.
   Then write the line. A stuck `sys` backlog never holds the owner's words
   for long.
4. Match: the `mic` text against each overlapping `sys` text, and against
   all of them joined in time order (an echo can span two `sys`
   utterances). Overlap ≥ `echo_threshold` (0.6) drops the line.
5. Overlap: `lib.textmatch.overlap(a, b)`, which implements exactly this
   rule (from the Go recorder): lowercase, strip punctuation, split on
   space. 1.0 when one text contains the other. 0.0 when the shorter text
   has fewer than 3 tokens. Else common tokens (multiset) divided by the
   tokens of the shorter text. interactions uses the same function
   (ADR-0016). The threshold stays with each caller.

- The `sys` line always wins. The PRD wants the phrase "once, from the
  other side".
- With the inference host idle, `sys` text comes within seconds, so the
  wait fits in the 10 s of `live-transcript` AC-1.
- A dropped line leaves no trace in the file. After a restart, the same
  inputs drop it again.
- Short `mic` phrases under 3 tokens are never dropped. A short echo can
  then show twice. Bench measures the rate (AC-6, 95% target).

#### Gaps

- Recording-off ranges per channel, from `events/capture/` (seam fields,
  ADR-0010):
  - each `start` record with a non-null `prev_end`: from `prev_end` to its
    `audio_start`. This covers a clean stop and a crash alike: a crash
    writes no `stop`, but the next `start` still names where the old audio
    ended;
  - each `gap` record's `start` to `end`, with its `reason`;
  - a `stop` with no later `start` of that channel: an open range from the
    `stop` time to `now`. It closes when the next `start` arrives.
- `stop` records only name the cause of a range (see `logout` below). They
  never define its start, so a lost `stop` changes nothing.
- Merge `mic` and `sys` ranges that overlap. A range on one channel only
  names that channel: `not recording sys …`.
- A gap line is written for a range longer than `gap_min_s` (60 s), when
  the range closes, at the range start time. `live-transcript` AC-14.
- Cause, first rule that matches:

| Cause     | Rule                                                                             |
| --------- | -------------------------------------------------------------------------------- |
| `pause`   | A `pause` record in `events/user/` from 10 s before to 5 s after the range start |
| capture's | The `gap` record has `reason`, such as `suspend` or `clock`                      |
| `restart` | The range lasts at most `restart_max_s` (300 s): a crash, an upgrade or a deploy |
| `logout`  | A `stop` record lies at the range start (±5 s) and the range lasts longer        |
| `unknown` | All else                                                                         |

- A range that crosses local midnight gives one line in each day, cut at
  midnight.
- Utterances never span a gap: capture leaves the hole, and segmentation
  cuts at it. Transcript only reports it.

#### Finish

A day D is finished when all of these hold (ADR-0003 "Output targets"):

1. `now` is at least `finish_settle_s` (60 s) past the end of D.
2. For `mic` and `sys`, coverage reaches the end of D. Coverage is the
   `covered` end of segmentation (`coverage/`), moved forward across any
   recording-off range that starts at or before it, including an open
   range, which ends at `now`. A stopped capture then counts as covered, so a logout before midnight does not hold the
   day open.
3. No utterance (ambient or dictation) with its start in D lacks a `text`
   record.
4. No `mic` line of D is held for echo.

Then transcript appends the `finished` record to
`state/finished/transcript/`.

- Cap: at 48 h (`finish_cap_h`) after the end of D, transcript writes an
  `untranscribed` line for each utterance of D still pending, with
  adjacent ranges of one channel merged, then the `finished` record with
  `capped: true`.
  `live-transcript` AC-12.
- With the inference host up and no backlog, rule 1 is the last to hold,
  so publishing gets the file a little over 1 min after midnight
  (`live-transcript` AC-12 allows 10 min).

#### Restart

- At start, read `finished/transcript/` for the closed days, then each open
  day's file. Collect the keys of its lines.
  Replay the inputs of the open days through the pure parts. A line whose
  key is in the file is not written again. `live-transcript` AC-10.
- A crash after the last line and before the `finished` record only
  delays the record: the rule still holds at the next check.
- A crash mid-write leaves a partial last line with no `\n`. On start, the
  writer truncates the file to its last `\n` before it appends. It is the
  sole writer, so this is safe.

#### `odsodctl transcript`

- `odsodctl transcript [--day YYYY-MM-DD] [--json]`. Default: today's
  local day, this host.
- Text: prints the file.
- `--json`: one document: `day`, `host`, `finished` (bool), `lines`: list
  of `time` (local, with offset), `tag`, `text`, `key`. Parsed with
  `contract.parse_file()`.
- Reads one file, so it answers well within 1 s (`live-transcript` AC-13).

#### `odsodctl note` and `pin`

- Append one record with `lib/streams` and print the line the transcript
  will show. `--json` prints the record.
- The pipeline follows `events/user/`, so the line appears within the
  2 s scan, faster with inotify (`live-transcript` AC-7).
- The commands work while the pipeline is down. The line appears when it
  starts again.

### Failure modes

| Fault                                    | What transcript does                                                    | Fault code                                    |
| ---------------------------------------- | ----------------------------------------------------------------------- | --------------------------------------------- |
| Inference host down: no `text` records   | Writes nothing new. Lines appear with their own times when text returns | none (speech reports `inference-unreachable`) |
| `text` with `failed` or `expired`        | Writes an `untranscribed` line                                          | none                                          |
| `sys` text stuck behind a backlog        | Holds `mic` lines at most 120 s, then writes them                       | none                                          |
| Segmentation stalled (no `coverage/`)    | The day does not finish until the 48 h cap                              | none (control reports the backlog)            |
| A line for a finished day                | Not written; logged                                                     | none                                          |
| Partial last line after a crash          | Truncates to the last `\n` at start                                     | none                                          |
| Disk full, or the file cannot be written | Exception ends the pipeline. systemd restarts it (ADR-0004)             | none                                          |

- Transcript has no fault code of its own. Its causes show through speech
  (`inference-unreachable`) and control (backlog, `health-and-control`
  AC-9).

### Config

Section `transcript`:

```json
{
  "transcript": {
    "echo_threshold": 0.6,
    "echo_tolerance_s": 2,
    "echo_hold_max_s": 120,
    "gap_min_s": 60,
    "restart_max_s": 300,
    "finish_settle_s": 60,
    "finish_cap_h": 48
  }
}
```

- The host name comes from `common.host`. The time zone is the system's.
- `note` and `pin` have no config.

### Tests

Component tests use a temp state root, a fake clock and JSONL inputs in
`testdata/`. No audio, no inference.

| Test                 | Input                                                                                    | Checks                                                                 |
| -------------------- | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `test_lines.py`      | One record of each kind                                                                  | Line format, tags, local time: `live-transcript` AC-2                  |
| `test_live.py`       | A `text` record after an utterance, fake clock                                           | Line within 10 s: AC-1                                                 |
| `test_note_pin.py`   | `odsodctl note`, `pin`, `note -` with stdin, `--json`                                    | Record, then line within 2 s: AC-7                                     |
| `test_silence.py`    | 1 h of `empty` outcomes and `coverage/` records                                          | No lines, no file: AC-9                                                |
| `test_echo.py`       | Paired `mic` and `sys` texts: exact, partial, split over two `sys`, short                | Drops and keeps: AC-6 (logic; bench measures the rate)                 |
| `test_echo_wait.py`  | `sys` text late, `sys` backlog, no `sys` at all                                          | Hold and the 120 s limit; AC-1 with no `sys`                           |
| `test_restart.py`    | Kill the writer between lines; partial last line                                         | Each utterance has one line: AC-10                                     |
| `test_backlog.py`    | 1 h of utterances, then their `text` records in a burst                                  | All lines, own times, within 30 min: AC-11                             |
| `test_finish.py`     | Day with pending utterances, then text; logout before midnight; 48 h cap                 | One `finished` record; `untranscribed` lines; no change after: AC-12   |
| `test_cli.py`        | A day file                                                                               | Text and `--json`, under 1 s: AC-13; `health-and-control` AC-10        |
| `test_gaps.py`       | Capture `stop`/`start`, `gap`, `pause`, ranges over midnight                             | One line per gap, cause: AC-14                                         |
| `test_gaps_crash.py` | A `start` with `prev_end` and no `stop` before it (crash); an open `stop` at finish time | One `restart` gap line; the open range counts as covered: AC-14, AC-12 |
| `test_dictation.py`  | A `dic` text and no `mic` text for its range                                             | One `dic` line: AC-16                                                  |

- System test (root `tests/`, with speech's fake whisper-server and
  llama-server): audio fixtures through segmentation, transcription,
  cleanup and transcript. Checks AC-1, AC-10 and AC-16 end to end, and
  that publishing delivers the finished file (AC-12).
- AC-3, AC-4 and AC-5 are speech quality. bench checks them
  (ADR-0012, ADR-0019).

### Build without hardware

- All of it. Inputs are JSONL files and a fake clock. The system test uses
  the audio fixtures and the inference fakes of ADR-0010.
- The owner only reads real transcripts and reports format problems, and
  gives bench references for the echo rate (AC-6).

## Alternatives considered

### Write lines in time order

- Easier to read than arrival order.
- Rejected: an append-only file cannot insert, and a rewrite breaks the
  "never changes" rule for readers that tail it. Each line has its time,
  and the batch documents are in time order.

### A separate checkpoint stream for written keys

- Keeps the Markdown clean.
- Rejected: the line and the checkpoint are two writes. A crash between
  them loses or doubles a line. The key in the line commits with the line.

### Echo drop by time alone

- Drop any `mic` line that overlaps `sys` speech.
- Rejected: it drops the owner's own words when both talk. The text match
  keeps them.

### Echo cancellation in audio

- Cleaner text, but lossy when both sides talk. It stays a bench
  experiment (`mic-ec`, ADR-0005).

### Participant lines in the live transcript

- The Go recorder wrote a `ppl` line on each change.
- Left out: no PRD needs it, and documents list the participants. Add it
  later if agents miss it.

### Finish at local midnight

- Simple, but lines of the day can still be pending for hours. Rejected by
  the adversarial review (ADR-0003).

## Consequences

- A transcript reaches the vault about 1 min after midnight on a normal
  day, and up to 48 h later after an outage, with the missing ranges named.
- Line keys show as HTML comments in raw Markdown. Viewers hide them.
- `mic` lines can lag `sys` lines by a few seconds while echo is checked.
- The finish depends on segmentation's `coverage/` stream. Without it,
  every day waits for the 48 h cap.
- Deliberately left out: speaker names, participant lines, idle lines,
  segment markers, merged transcripts across hosts, and live captions.
