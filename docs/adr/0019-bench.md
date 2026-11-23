# ADR-0019: Bench

## Status

Proposed

## Date

2026-11-23

## Context

- Many targets in the PRDs carry "bench confirms". The owner picks models,
  prompts and settings from data on their own speech
  ([PRD benchmarking](../prd/benchmarking.md)).
- Capture keeps 14 days of audio, and speech keeps every ASR and cleanup
  result ([ADR-0003](0003-filesystem-interface.md)). Real use gives the raw
  material for cases with no extra recording.
- The owner's review time is short: at most 3 h per quarter
  (`benchmarking` AC-3). Agents do the work; the owner accepts references.
- The owner cut live shadow backends: setups run offline on saved cases
  (`benchmarking` AC-6 removed). Measures come in stages: word error rate
  and dictation latency first.
- [ADR-0005](0005-components-and-implementation.md) held the first design of
  bench. This ADR replaces that section.

## Decision

### Purpose

- Turn stored audio and its text into self-contained test cases that the
  owner reviews with a player and an editor.
- Run a setup (a model, a prompt or a setting) offline on all cases, and
  report scores per setup next to the PRD criterion each score checks.
- Give the data that an ADR needs to adopt a new model, prompt or backend
  (ADR-0002, "Cloud ASR"; ADR-0005).

PRD: [benchmarking](../prd/benchmarking.md). Measures in stage 1 check
`live-transcript` AC-3, AC-4 and AC-5, and `dictation` AC-3 and AC-6.

### Components

| Component | Service or command                                                        | Job                                 |
| --------- | ------------------------------------------------------------------------- | ----------------------------------- |
| `bench`   | `odsodctl bench cases\|list\|accept\|run\|report\|delete` (extra `bench`) | Build cases, run setups, score them |

- One component, one command group. It has no service and holds no state in
  memory between commands.
- It needs the optional extra `bench` (`jiwer`). Without the extra,
  `odsodctl bench` prints the install command and exits 1. The `machine`
  repo installs the extra ([ADR-0006](0006-installation.md)).

### Writes

All writes are under `state/bench/<case-id>/` (ADR-0003). Each file is a
document: written to a temp name, then renamed.

| File                         | Content                                                                                                                               |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `case.json`                  | `id`, `kind` (`ambient`, `dictation`, `interaction`), `host`, `channel`, `start`, `end`, `language`, `source_id`, `created`, `commit` |
| `audio.wav`                  | The audio slice, 16 kHz mono 16-bit WAV (ambient and dictation cases)                                                                 |
| `mic.wav`, `sys.wav`         | Both channels of the interaction range (interaction cases)                                                                            |
| `live.json`                  | What the live pass gave: ASR text per backend with its `setup`, cleaned text, `raw`, live latency                                     |
| `reference.txt`              | The reference text (ambient, dictation). Starts as a draft                                                                            |
| `reference.md`               | The reference decisions and next steps (interaction). Starts as a draft                                                               |
| `document.md`                | A copy of the interaction document (interaction cases)                                                                                |
| `review.json`                | `state` (`draft`, `accepted`), `drafted_by`, `accepted_by`, `accepted_at`, `reference_sha256`                                         |
| `results/<fingerprint>.json` | One result per setup: the setup manifest, `outcome`, `output`, `latency_ms`, `error`, `ts`                                            |

- Case IDs: `<source id>` for ambient and dictation cases (for example
  `mic-20261122T143005.120Z`), and `int-<interaction id>` for interaction
  cases. A case ID names where the case came from.
- WAV, not raw PCM, so the owner plays a case in any player
  (`benchmarking` AC-2).
- A case directory is self-contained: audio, text, reference, review state
  and source (`benchmarking` AC-7). Retention never reads `state/bench/`
  (ADR-0003), so case audio stays until `bench delete`.
- Results sit inside their case. Deleting a case deletes its results, and
  no index needs an update.
- `outcome` uses the ADR-0010 values: `ok`, `empty` or `failed` (with
  `error`).

The setup manifest, in each result:

| Field             | Content                                                                                  |
| ----------------- | ---------------------------------------------------------------------------------------- |
| `name`            | Setup name from config                                                                   |
| `kind`            | `asr` or `pipeline`                                                                      |
| `model`           | ASR model name and `revision`; for `pipeline` also the LLM `model` and `revision`        |
| `prompt_sha256`   | Hash of the rendered cleanup prompt (`pipeline`), or null                                |
| `glossary_sha256` | Hash of `config/glossary.txt` as used                                                    |
| `settings`        | The full ASR and cleanup settings, as JSON                                               |
| `commit`          | The daemon commit (`odsodctl version`)                                                   |
| `fingerprint`     | SHA-256 of the canonical JSON of all fields above except `name`, first 16 hex characters |

- The fingerprint names the setup. A changed model, prompt, glossary,
  setting or commit gives a new fingerprint, so results never mix
  (`benchmarking` AC-11).

### Reads

| Path                            | Seam fields relied on                                                          | Used for                           |
| ------------------------------- | ------------------------------------------------------------------------------ | ---------------------------------- |
| Audio buffer                    | Cut by channel and time (`lib.audio`)                                          | Case audio                         |
| `state/text/`                   | `input`, `outcome`, `channel`, `start`, `end`, `text`, `language`, `raw`, `ts` | Candidates; live text and latency  |
| `state/asr/<backend>/`          | `input`, `outcome`, `text`, `language`, `setup`                                | Live ASR text per backend          |
| `state/interactions/`           | `id`, `start`, `end`, `outcome`, `document`                                    | Interaction candidates             |
| `state/documents/interactions/` | The document by name                                                           | `document.md` of interaction cases |
| `config/glossary.txt`           | One term per line                                                              | Setups; glossary measure           |
| `config/prompts/<name>.md`      | A prompt file that a setup names                                               | `pipeline` setups                  |
| `config/config.json`            | Sections `bench` and `common` (`host`, `inference`)                            | Setups; case source                |
| `state/install/current`         | `commit` ([ADR-0006](0006-installation.md))                                    | Manifest                           |

- `text/` carries channel and time, so bench never joins with `utterances/`
  (ADR-0010).
- A setup runs the real speech components in a sandbox root (see "Sandbox
  run" below): the same WAV wrapping, glossary prompt, presence gate,
  decoder settings, cleanup prompt and reply guards as the live pass
  ([ADR-0012](0012-speech.md)). bench imports no speech code and never
  reimplements it. A setup differs from live only in its config.
- In the sandbox, bench writes `audio/`, `utterances/ambient/` and
  `utterances/dictation/` (seam fields `id`, `channel`, `start`, `end`),
  and reads back `asr/<backend>/` (`input`, `outcome`, `text`, `ms`) and
  `text/` (`input`, `outcome`, `text`, `raw`, `ms`). These files live only
  in the temp root; bench never writes the host's own streams.

### Outside dependencies

| System or library                                                  | For                                                                        |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------- |
| `odsodctl run transcription --once`, `odsodctl run cleanup --once` | The speech components in drain mode, in the sandbox (ADR-0012)             |
| whisper-server, llama-server                                       | Reached by the sandboxed speech components; URL from the setup or `common` |
| `jiwer` (extra `bench`)                                            | Word error rate                                                            |

- The sandboxed components send every request through `lib.inference`,
  which accepts only localhost and tailnet URLs. bench also checks the setup
  URLs before it starts. Ambient audio then never leaves the owner's hosts and
  the inference host (`benchmarking` AC-8).
- Not in this version: a streaming model on the host CPU and a cloud model.
  Each needs its own library, and so an ADR (ADR-0005, "A new runtime
  dependency needs an ADR"). The setup interface below is ready for them.
  A local CPU model behind a whisper-server on `localhost` works today as
  an `asr` setup.

### Internal design

#### Module layout

```
components/bench/
├── __init__.py      SUBSYSTEM = "bench"; no run()
├── contract.py      Case, Review, Live, Result, Manifest, ReportRow
├── cli.py           typer group: cases, list, accept, run, report, delete
├── cases.py         Candidate selection and case writing
├── setups.py        Setup config models, manifest, fingerprint
├── adapters.py      Adapter protocol; sandbox adapter (asr, pipeline)
├── sandbox.py       Build the temp root; run the --once commands; read back
├── runner.py        Run a setup over cases; resume; failures
├── score.py         Normalization, WER, glossary hits, latency percentiles
├── report.py        Group results into rows; text and JSON
└── tests/           conftest.py, testdata/ (short sv and en speech, silence)
```

#### `bench cases`

`odsodctl bench cases [--ambient N] [--dictation N] [--interactions N] [--json]`
tops the case set up to the targets in config.

1. Read `text/` and `interactions/` for the last 14 days.
2. Candidates:
   - ambient: `text` records with `outcome: ok`, channel `mic` or `sys`,
     length from `min_s` to `max_s`, language `sv` or `en`;
   - dictation: `text` records with channel `dic` and `outcome: ok`;
   - interaction: `interactions` records with `outcome: ok`, at most
     `max_interaction_min` long.
3. Drop candidates that are a case already, or whose audio is gone.
4. Strata: ambient by channel and language, dictation, interaction. For each
   stratum below its target, draw at random with the config seed, at most
   `max_per_hour` from one UTC hour, so one long call does not fill a
   stratum.
5. For each pick, write the case: audio, `live.json`, `case.json`, and the
   draft reference. The draft is the live cleaned text (ambient and
   dictation), or an empty outline with the labels Decided and Next
   (interaction). `review.json` starts as `draft`, `drafted_by: bench`.

- The targets default to `benchmarking` AC-1: 50 ambient cases per
  language, 50 dictation cases and 10 interactions.
- An agent then improves each draft: it listens to the audio through a
  speech model of its choice, or reads the document, and edits the
  reference file. It records itself with `bench accept --draft-by <name>`
  (below), which leaves the state `draft`.

#### `bench list` and `bench delete`

- `bench list [--kind] [--state] [--json]` prints one line per case: ID,
  kind, language, length, review state.
- `bench delete <case>...` removes case directories.

#### `bench accept`

- `bench accept <case>... [--by owner] [--json]` sets `state: accepted`,
  `accepted_by`, `accepted_at` and the SHA-256 of the reference file.
- `bench accept <case> --draft-by <name>` only sets `drafted_by`.
- A reference edited after acceptance no longer matches its hash. The
  report then counts the case as a draft until the next accept
  (`benchmarking` AC-10).
- Owner decision (2026-11-23): only the owner accepts. Agents never run
  `bench accept` without `--draft-by`. The code cannot tell an agent from
  the owner; the rule lives in the repo's `AGENTS.md`.

#### Setups and adapters

A setup in config:

```json
{
  "name": "large-v3-turbo-glossary",
  "kind": "pipeline",
  "cases": ["ambient", "dictation"],
  "asr": {
    "whisper_url": null,
    "model": "ggml-large-v3-turbo",
    "revision": "2024-10",
    "settings": {}
  },
  "cleanup": {
    "llama_url": null,
    "model": "qwen3-30b-a3b",
    "revision": "q4_k_m",
    "prompt": null,
    "settings": {}
  }
}
```

- `kind: asr` runs ASR only; `pipeline` runs ASR and cleanup.
- Null URLs take `common.inference`. A null prompt takes the live prompt of
  speech.
- `settings` override the host's `speech` config section key by key. The
  manifest holds the merged section.
- `model` and `revision` are what the setup states. whisper-server and
  llama-server serve one model each, so the URL picks the model. Another
  model means another server on another port, set up by the `machine` repo.
- An adapter has `accepts(case_kind) -> bool` and
  `run(cases) -> [(outcome, output, latency_ms)]`. The sandbox adapter accepts
  `ambient` and `dictation`. A later cloud adapter must accept only
  `dictation` (`benchmarking` AC-8, ADR-0002).
- Interaction setups (summary prompts) come with the stage 2 measures.

#### Sandbox run

One sandbox per case, so cases never share a queue and latency stays clean.

1. Make a temp dir with `state/`, `run/` and `config/`.
2. `config/config.json`: the host's config, with `common.inference` set to
   the setup URLs and the `speech` section merged with the setup
   `settings`. `config/glossary.txt`: a copy of the host's glossary. The
   setup prompt, if any, goes to its name under `config/prompts/`.
3. Write the case audio into `state/audio/<channel>/<hour>Z.pcm` at the
   offset of its original time ([ADR-0003](0003-filesystem-interface.md)).
   The rest of the hour stays a hole. Dictation case audio goes to the
   `mic` channel.
4. Append one utterance record with the case's source ID, channel, start
   and end to `utterances/ambient/` or `utterances/dictation/`. Its audio
   is complete, so no coverage wait applies.
5. Run `odsodctl run transcription --once` with `ODSOD_DAEMON_ROOT` set to
   the temp dir. For a `pipeline` setup, then run
   `odsodctl run cleanup --once` the same way.
6. Read the `asr` record (and the `text` record) for the case's ID. Output
   is the ASR text (`asr`) or the cleaned text (`pipeline`).
7. Delete the temp dir.

- A non-zero exit of a `--once` command (for example the inference host
  stays out of reach for 60 s) leaves the case with no record. bench then
  writes the case result as `failed` with the command's last error line.
- The sandbox never reads or writes the host's `state/` or `run/`. The
  live services never see sandbox work.

#### `bench run`

`odsodctl bench run <setup> [--kind K] [--limit N] [--retry-failed] [--json]`:

1. Load the setup and build its manifest and fingerprint.
2. Select cases that the adapter accepts and that have a reference (draft
   or accepted).
3. Skip cases with a result for this fingerprint, except `failed` ones
   with `--retry-failed`. An interrupted run resumes where it stopped.
4. Run one case at a time, oldest first. One request at a time keeps the
   shared inference host free for live dictation (ADR-0002, principle 9).
5. Write the result file. A failure writes `outcome: failed` and `error`,
   and the run goes on (`benchmarking` AC-9).
6. Print a summary: cases run, ok, empty, failed.

- `latency_ms` is the request time that speech records: `ms` of the `asr`
  record, plus `ms` of the `text` record for a `pipeline` setup. Process
  start of the `--once` commands is left out. For dictation cases it is the offline part of
  "release to text". The live part comes from `live.json`.

#### Live results

- `bench cases` turns `live.json` into one result per case with the setup
  name `live` and the fingerprint `live-<asr setup>`. Its `commit` is null,
  because the live pass ran under an unknown commit.
- Live latency for dictation is the `ts` of the `text` record minus its
  `end`: the real time from release to text (`dictation` AC-3).

#### Scoring and report

`odsodctl bench report [--setup S] [--json]` scores at report time, from the
saved outputs and the references. It never calls a model, so the same saved
outputs give the same scores (`benchmarking` AC-4).

Normalization before WER and glossary hits:

1. Unicode NFC, lower case.
2. Every character that is not a letter, a digit, `'` or `-` becomes a
   space. Letters include å, ä and ö.
3. Collapse spaces.

Measures in stage 1:

| Measure    | Group                         | Score                                                                | Target   | Checks                       |
| ---------- | ----------------------------- | -------------------------------------------------------------------- | -------- | ---------------------------- |
| `wer`      | ambient, `mic`, `sv` and `en` | Corpus WER (errors / reference words)                                | 15%      | `live-transcript` AC-3, AC-4 |
| `wer`      | ambient, `sys`, `sv` and `en` | Corpus WER                                                           | 10%      | `live-transcript` AC-3, AC-4 |
| `wer`      | dictation, `en`               | Corpus WER                                                           | 5%       | `dictation` AC-6             |
| `glossary` | ambient and dictation         | Glossary terms in the reference spelled the same in the output, in % | none     | `live-transcript` AC-5       |
| `latency`  | dictation                     | p50 and p95, ms                                                      | 2,000 ms | `dictation` AC-3             |

- One row per measure, group and fingerprint: setup name, fingerprint,
  accepted case count, draft count, failed count, score, target and
  criterion (`benchmarking` AC-5).
- Only accepted cases with a matching hash count in the score. Drafts show
  as a count only (`benchmarking` AC-10).
- A failed case shows in the failed count and never in the score
  (`benchmarking` AC-9).
- Rows never merge two fingerprints (`benchmarking` AC-11).
- `--json` prints the rows as one JSON document.

#### What this ADR leaves out

- Stage 2 measures: speaker names (`interactions` AC-4), summary points
  (`interactions` AC-9, AC-10) and echo removal (`live-transcript` AC-6).
  They wait for the timed review pilot of `benchmarking` AC-3. Interaction
  cases are built now, so references can grow before the pilot.
- A streaming CPU model and a cloud model for dictation. Each needs a
  dependency ADR. The adapter rule for the cloud (dictation cases only) is
  fixed here.
- Live shadow backends, a review UI and public datasets (PRD "Not
  planned").

### Failure modes

| Fault                                        | What bench does                                                                     | Code           |
| -------------------------------------------- | ----------------------------------------------------------------------------------- | -------------- |
| Inference host out of reach in `run`         | Bounded retries (`lib.pending` policy), then `failed` for the case; the run goes on | none (command) |
| A setup URL that is not localhost or tailnet | Refuse the setup at load; exit 1 with the reason                                    | none           |
| Audio of a candidate is gone                 | Skip the candidate in `cases`                                                       | none           |
| Unknown setup name                           | Exit 1 with the list of setup names                                                 | none           |
| Extra `bench` not installed                  | Exit 1 with the install command                                                     | none           |
| Reference edited after accept                | Count as draft in the report                                                        | none           |
| Run interrupted                              | Finished results stay; the next run resumes                                         | none           |

- bench is a command. It writes no health file and never changes the tray
  state.

### Config

Section `bench`:

```json
{
  "bench": {
    "cases": {
      "ambient_per_language": 50,
      "dictation": 50,
      "interactions": 10,
      "min_s": 2,
      "max_s": 30,
      "max_interaction_min": 60,
      "max_per_hour": 3,
      "seed": 0
    },
    "setups": []
  }
}
```

- `setups` is a list of setup objects (above). An empty list still allows
  `cases`, `accept`, `list`, `delete`, and `report` on the `live` results.

### Tests

Component tests use the runtime fixtures (ADR-0010): a temp root, a fake
clock, the fake whisper-server and llama-server, and audio fixtures in
`components/bench/tests/testdata/`.

| Test                                                                                                              | Checks                           |
| ----------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| `cases` on synthetic `text/` and `interactions/` streams fills each stratum to its target, with `max_per_hour`    | `benchmarking` AC-1 (logic)      |
| A case directory holds audio, text, reference, review state and source                                            | `benchmarking` AC-7              |
| `odsodctl retention` on the temp root leaves case audio in place                                                  | `benchmarking` AC-7              |
| `report` twice on the same results gives equal output                                                             | `benchmarking` AC-4              |
| Each row names setup, case count, score and criterion                                                             | `benchmarking` AC-5              |
| A setup with a public URL is refused; requests go only to the fake localhost servers                              | `benchmarking` AC-8              |
| A cloud-like test adapter that accepts ambient cases fails the adapter contract test                              | `benchmarking` AC-8              |
| The fake server fails one case; the run finishes the others; the report shows one failed                          | `benchmarking` AC-9              |
| Drafts and hash mismatches count apart from accepted cases                                                        | `benchmarking` AC-10             |
| A changed prompt, setting or commit gives a new fingerprint and a new row                                         | `benchmarking` AC-11             |
| WER and normalization on known pairs, with å, ä and ö                                                             | `live-transcript` AC-3 (measure) |
| Live latency from `text` `ts` minus `end`                                                                         | `dictation` AC-3 (measure)       |
| `bench list --json` and `bench report --json` hold all text fields                                                | `health-and-control` AC-10       |
| Sandbox run with the fake servers: one `asr` and one `text` record per case read back; the host root is unchanged | `benchmarking` AC-11             |
| A `--once` command that exits non-zero gives a `failed` result for its case                                       | `benchmarking` AC-9              |

### Build without hardware

- An agent builds and tests all of bench with no owner hardware: streams,
  audio and the inference servers are fixtures and fakes.
- An agent can also run bench for real on a host with 14 days of audio:
  build cases, draft references and run setups.
- The owner is needed for:
  - accepting references (owner decision, 2026-11-23);
  - the manual checks `benchmarking` AC-1 (case counts from real use),
    AC-2 (30 s per review) and AC-3 (review time per quarter).

## Alternatives considered

### Cases as references into the audio buffer

- No copy of the audio.
- Rejected: retention deletes the buffer after 14 days, and a case keeps its
  audio with no end date (`benchmarking` AC-7).

### A results stream per setup

- One file to read for a report.
- Rejected: deleting a case would need a rewrite of every stream. Results in
  the case directory go with the case.

### Score during `bench run`

- One step fewer.
- Rejected: a reference edited after the run would leave stale scores.
  Scoring at report time from saved outputs is cheap and repeatable.

### Reimplement the speech requests in bench

- No code seam with speech.
- Rejected: bench would score a pipeline that differs from the live one.

### Call speech functions exported from its contract

- One process, no sandbox.
- Rejected by the orchestrator: `contract.py` holds models only (ADR-0009,
  rule 6). The sandbox keeps one pipeline and file seams only, and the
  same `--once` mode serves the tests.

### Fingerprint without the commit

- Results stay comparable across deploys.
- Rejected: a code change in cleanup or its guards changes the output with
  the same settings. A rerun on a new commit takes minutes.

## Consequences

- A case costs about 1 MB for 30 s of audio; an interaction case up to
  about 230 MB for 60 min of two channels. 10 interactions use up to
  about 2.3 GB, kept until deleted.
- A model change needs a server on another port. The `machine` repo sets it
  up; bench only names the URL.
- bench depends on the `--once` mode of transcription and cleanup, and on
  `ODSOD_DAEMON_ROOT`. A change to the `speech` config section changes the
  manifest and starts new rows.
- Each sandbox case costs two process starts, about 1 s each. 200 cases
  take a few minutes beyond the inference time.
- Seam decisions (orchestrator, 2026-11-23): bench reads `text/`,
  `interactions/`, `documents/interactions/` and the glossary; it runs speech
  in a sandbox with `--once`; `bench list` and `bench delete` are in the
  command surface.
