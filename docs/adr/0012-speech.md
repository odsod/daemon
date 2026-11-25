# ADR-0012: Speech

## Status

Proposed

## Date

2026-11-23

## Context

- [ADR-0002](0002-high-level-architecture.md) makes the utterance the unit
  (principle 8): one stretch of speech on one channel, sent to Whisper as
  one request. Short requests keep Swedish and English apart (benchmark
  2026-11: 45% mixed WER on long chunks, 5.3% per utterance).
- Raw ASR text is never final. An LLM cleans it with the glossary.
- Dictation and ambient speech share the ASR and cleanup path, but differ:
  dictation is the owner's whole key hold, in English, and must reach the
  clipboard in 2 s (`dictation` AC-3). Dictation goes first on each host
  (ADR-0002, principle 9).
- whisper-server takes one request at a time. llama-server has four slots
  (ADR-0002, [ADR-0023](0023-inference-servers.md)). Both are shared by every host and reached over localhost or
  the tailnet only.
- [ADR-0010](0010-contracts-and-runtime.md) fixes the seam fields of
  `utterances/ambient/`, `asr/<backend>/` and `text/`.
  [ADR-0003](0003-filesystem-interface.md) fixes pending work: input IDs
  with no output record.
- This ADR takes the segmentation, transcription and cleanup sections out
  of [ADR-0005](0005-components-and-implementation.md) and deepens them.

## Decision

### Purpose

- Turn stored audio into clean text, one record per utterance: cut ambient
  audio into utterances, transcribe ambient and dictation utterances, and
  clean the text.
- PRDs: [`live-transcript`](../prd/live-transcript.md) AC-1, AC-3, AC-4,
  AC-5, AC-9, AC-10, AC-11, AC-15, AC-16;
  [`dictation`](../prd/dictation.md) AC-2, AC-3, AC-4, AC-6, AC-7, AC-8,
  AC-21, AC-22, AC-24.
- Speech knows nothing about meetings, interactions or the transcript file.

### Components

| Component       | Service    | Job                                                              |
| --------------- | ---------- | ---------------------------------------------------------------- |
| `segmentation`  | `pipeline` | Silero VAD on `mic` and `sys`; write ambient utterances          |
| `transcription` | `pipeline` | Send each pending utterance to whisper-server; write ASR text    |
| `cleanup`       | `pipeline` | Filter and clean ASR text with llama-server; write `text/`       |
| `parakeet`      | `pipeline` | CPU speech-to-text for dictation, inference host only (ADR-0022) |

- All four have `SUBSYSTEM = "speech"`. They may import each other's
  internals (ADR-0009, rule 2). transcription uses the Silero wrapper of
  segmentation for the dictation presence gate.
- Version 1 runs one ASR backend. Its name is the config value
  `speech.backend` (default `whisper`), so the stream is `asr/whisper/`.
  Dictation records from `parakeet` land in the same stream.
  No live shadow backends; bench runs other setups offline
  ([ADR-0019](0019-bench.md)).

### Writes

| Path                                   | Kind     | Owner           |
| -------------------------------------- | -------- | --------------- |
| `state/utterances/ambient/<day>.jsonl` | Stream   | `segmentation`  |
| `state/coverage/<day>.jsonl`           | Stream   | `segmentation`  |
| `state/asr/<backend>/<day>.jsonl`      | Stream   | `transcription` |
| `state/text/<day>.jsonl`               | Stream   | `cleanup`       |
| `state/models/parakeet-tdt-0.6b-v2/`   | Files    | `parakeet`      |
| `run/health/pipeline.json`             | Document | all four        |

Records and fields beyond the seam:

| Stream                | Kind        | Extra fields                                                                                                                                                                                                           |
| --------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `utterances/ambient/` | `utterance` | `vad`: mean speech probability (2 decimals). `cut`: `pause`, `forced`, `mask` (dictation window) or `end-of-audio`                                                                                                     |
| `coverage/`           | `covered`   | Seam: `channel`, `end`. No utterance of that channel will start before `end`                                                                                                                                           |
| `asr/<backend>/`      | `asr`       | `channel`, `start`, `end` (copied from the utterance), `ms` (request time), `attempts`, `gate` (dictation: peak speech probability)                                                                                    |
| `text/`               | `text`      | `raw_reason` (when `raw`): `timeout`, `llm-empty`, `guard-length`, `guard-number`, `guard-overlap`, `guard-english`. `ms`. `prompt` (hash of the rendered prompt). `heard`: the ASR text, only when cleanup changed it |

- `covered` is written at each utterance (with `end` = the utterance end)
  and at least every 60 s while the channel advances. It has its own
  stream, so `utterances/ambient/` keeps one record kind. transcript,
  interactions and control use it to tell silence from backlog.
  Segmentation uses it as its restart point, so it needs no checkpoint
  file.
- Every input gets exactly one output record with an outcome (ADR-0003).
  cleanup copies `empty`, `expired` and `failed` from `asr/` to `text/`,
  so `text/` alone tells its readers that an utterance is done.
- Fault: `inference-unreachable` in the pipeline health file, with key
  `whisper` (transcription) or `llama` (cleanup), so one server coming back
  never clears the other's fault (ADR-0010).

### Reads

| Path                                                | Seam fields relied on                          | Reader                 |
| --------------------------------------------------- | ---------------------------------------------- | ---------------------- |
| `state/audio/mic/`, `state/audio/sys/`              | Format and coverage by file size (`lib.audio`) | segmentation           |
| `state/audio/mic/`, `state/audio/sys/`              | Same, to cut dictation and ambient slices      | transcription          |
| `state/utterances/dictation/`                       | `id`, `start`, `end`                           | segmentation           |
| `state/utterances/{ambient,dictation}/`             | `id`, `channel`, `start`, `end`                | transcription          |
| `run/status.json`                                   | `mode`, `since`, `audio_start`                 | segmentation           |
| `config/glossary.yaml`                              | Entries, most important last (ADR-0021)        | transcription, cleanup |
| `config/prompts/cleanup.md`, `cleanup-dictation.md` | Optional prompt overrides                      | cleanup                |
| `config/config.json`                                | Section `speech`; `common.inference`           | all                    |

### Outside dependencies

- whisper-server (whisper.cpp) at `common.inference.whisper_url`, through
  `lib.inference`. Speech segments audio itself, so the server needs no
  server-side VAD. The daemon runs it without `--vad`
  ([ADR-0023](0023-inference-servers.md)).
- For dictation, the `parakeet` server at `common.inference.dictation_url`
  when it is set ([ADR-0022](0022-dictation-asr.md)).
- llama-server at `common.inference.llama_url`, OpenAI chat completions,
  with 4 parallel slots and n-gram speculation (the daemon runs it,
  [ADR-0023](0023-inference-servers.md)).
- Silero VAD v5 as an ONNX file, shipped as package data in
  `components/segmentation/models/` (MIT license, about 2 MB). No model
  download.
- `onnxruntime` (CPU, one thread per session), `numpy`, `httpx` (through
  `lib.inference`), `jinja2` for prompt templates.
- `lib.power.on_mains()` for the battery rule.

### Internal design

#### Module layout

```
components/segmentation/
├── __init__.py     SUBSYSTEM = "speech", run(config)
├── contract.py     AmbientUtterance, Covered
├── vad.py          Silero ONNX session; one state and context per channel
├── cutter.py       pure: frame probabilities → utterances (hysteresis, pads, forced cut)
├── mask.py         pure: dictation windows and the open dictation → masked ranges
├── runner.py       per channel: read new audio, run vad and cutter, append records
├── models/silero_vad.onnx
└── tests/          testdata/: Swedish and English speech, silence, zeros, noise
components/transcription/
├── __init__.py, contract.py (AsrRecord)
├── queue.py        pure: pending set and order (dictation first, then oldest)
├── request.py      pure: utterance kind → whisper fields (language, prompt, thresholds)
├── presence.py     dictation presence gate (uses segmentation.vad)
├── worker.py       one request at a time; retries; host state
└── tests/
components/cleanup/
├── __init__.py, contract.py (TextRecord)
├── filters.py      pure: phantom phrases, glossary echo, fillers
├── guard.py        pure: length ratio, numbers, word overlap, English words
├── language.py     pure: whisper language field → ISO 639-1 code
├── prompt.py       render templates with the glossary
├── prompts/        cleanup.md, cleanup-dictation.md (jinja2)
├── worker.py       two lanes: dictation and ambient
└── tests/
```

#### Segmentation

Per channel (`mic`, `sys`) one task reads new audio and runs the cutter.

- **Model:** Silero VAD v5, ONNX, 16 kHz
  (source: `https://github.com/snakers4/silero-vad`, file
  `src/silero_vad/data/silero_vad.onnx`, from a v5 release tag). The repo
  pins the file by its tag and SHA-256, written into `vad.py` when the file is added. Inputs: `input`
  (float32, shape 1 × 576: 64 samples of context from the end of the
  previous frame, then 512 new samples), `state` (float32, 2 × 1 × 128,
  zeros at start) and `sr` (int64, 16000). Outputs: the speech probability
  (1 × 1) and the next `state`. A test runs the model on a fixture and
  checks the shapes.
- **Frames:** 512 samples (32 ms). A frame of all zeros (a capture hole or
  a muted mic) gets probability 0 without the model. A frame whose RMS is
  under `energy_floor_dbfs` also gets 0. RMS is in dBFS with full scale
  32768: `20 · log10(rms / 32768)`. After such a run, the Silero state and
  context are reset. This keeps the CPU cost of silence and holes near
  zero.
- **Cutter** (hysteresis, as Silero's own and Meetily, Handy):
  - Speech starts at the first frame with probability ≥ `threshold`.
  - A candidate end is the first frame under `neg_threshold`. Speech ends
    there when the probability stays under `threshold` for
    `min_silence_ms`.
  - Speech shorter than `min_speech_ms` is dropped.
  - Pads: `pad_start_ms` before, `pad_end_ms` after, clamped so that
    utterances never overlap each other, a masked range or a capture hole.
  - **Forced cut:** when speech reaches `max_s`, the cutter ends it at the
    frame with the lowest probability in its second half, and the next
    utterance starts there with no pad (WhisperX). `max_s` (28 s) keeps
    each request inside Whisper's 30 s window.
  - **End of audio:** when the channel's coverage has not advanced for
    `idle_close_s` (3 s), an open utterance ends at the covered end. So a
    pause or a stop never leaves an utterance open, and an utterance never
    spans a recording gap (`live-transcript` AC-14).
- **Dictation mask** (`mic` only). Dictation speech must give no ambient
  line (`live-transcript` AC-16, `dictation` AC-24):
  - Each record in `utterances/dictation/` is a masked range. Frames in it
    get probability 0, and open speech ends at the mask start (`cut:
    mask`).
  - While `run/status.json` says `dictating`, the `mic` task stops at its
    `audio_start`. Dictation writes the utterance record
    before it sets the mode back to `idle`.
  - **Unmask rule:** when the `mic` task sees the mode leave `dictating`,
    it reads `utterances/dictation/` to its end, synchronously, before it
    reads any `mic` audio past the held `audio_start`. File write order
    alone does not order two reads, so the task never trusts `idle` until
    the stream is read.
  - **Guard:** the `mic` task reads only up to
    `min(newest audio, now − DICTATION_GUARD)`. The status file shows
    `dictating` at most about 850 ms after `audio_start` (300 ms pre-roll,
    350 ms threshold, 150 ms mute, a write). So no `mic` frame is cut
    before segmentation can know of the dictation. When capture stops,
    the wall clock passes the guard and the task reads to the end of the
    audio, so coverage reaches the stop time.
  - A status whose `since` is older than `DICTATION_STALE` (130 s: the
    dictation limit of 120 s plus a margin) is stale (a crash), and
    segmentation ignores it.
  - **Constants, not config** (owner decision, 2026-11-23):
    `DICTATION_GUARD` (1.2 s) and `DICTATION_STALE` (130 s) are constants
    in `components/segmentation/`. Their safety depends on the dictation
    constants of [ADR-0013](0013-dictation.md) (pre-roll, threshold, mute
    limit, maximum hold). A test asserts the budget:
    pre-roll + threshold + mute limit + 200 ms margin ≤ guard, and maximum
    hold + 10 s ≤ stale. A config change can then never leak a dictation
    into ambient text (`dictation` AC-24).
  - A cancelled dictation writes no utterance. Its audio stays ambient.
- **Restart:** per channel, segmentation starts at the newest `covered.end`
  in `coverage/`. It searches back day by day, at most over the
  pending window. With none, it starts at the oldest audio on disk. A new
  utterance never starts before that point, so no ID is written twice.
- **IDs:** `<channel>-<UTC start>` (ADR-0003).

#### Transcription

- **Pending:** all utterance IDs from `utterances/dictation/` and
  `utterances/ambient/` in the pending window, minus the `input` IDs in
  `asr/<backend>/`. Rebuilt from files at start (ADR-0003). New records
  arrive through `lib.streams.follow`, which must wake within 20 ms
  .
- **Order:** dictation first, then ambient, oldest first (ADR-0003). One
  request in flight, because whisper-server serves one at a time. Before
  each request the worker takes the head of the queue again, so a new
  dictation waits for at most one ambient request (about 0.5 s for 28 s of
  audio on the inference GPU) (`dictation` AC-4). With
  `common.inference.dictation_url` set, dictation has a loop of its own
  against that server and waits for no ambient request (ADR-0022).
- **Audio:** `lib.audio` cuts the range from `mic` or `sys` (dictation:
  `mic`) and wraps it as WAV in memory. A range whose hour file is gone gets
  outcome `expired` with no request.
- **Request fields** (POST to `common.inference.whisper_url`, or for
  dictation to `dictation_url` when set, a full
  endpoint URL, such as `.../v1/audio/transcriptions` on the owner's
  server; `response_format = verbose_json`, `temperature = 0`, no previous-text context):

| Field                            | Ambient                     | Dictation             |
| -------------------------------- | --------------------------- | --------------------- |
| `language`                       | `ambient.language` (`auto`) | `en` (owner decision) |
| `prompt`                         | Glossary tail               | Glossary tail         |
| `entropy_thold`, `logprob_thold` | Server defaults             | 2.8, −1.25            |
| Timeout                          | 60 s                        | 8 s                   |

- **Glossary prompt:** terms joined with `, `, taken from the end of
  `glossary.yaml` until `glossary_prompt_chars` (800, about 200 tokens).
  Whisper keeps only the tail of a long prompt, so the most important
  terms go last (`live-transcript` AC-5).
- **Language field:** whisper.cpp may return the language as a name
  (`swedish`) or a code (`sv`). One pure function in `language.py` maps
  both to an ISO 639-1 code. Its test uses the recorded responses in
  `lib/inference/testdata/` (ADR-0010). Every comparison uses the code.
- **Language:** with `auto`, a detected language outside
  `ambient.languages` gets one more request with `fallback_language`
  (`sv`). Whisper often hears Swedish as Norwegian or Danish. Bench data
  picks the default (`live-transcript` AC-4). A separate language-ID model
  is left out.
- **Presence gate** (dictation only, YazSes): Silero runs over the whole
  slice. If fewer than `presence_min_ms` of frames reach
  `presence_threshold` (0.3), the record gets outcome `empty` and no
  request is sent (`dictation` AC-7). No VAD cuts inside a dictation: cut
  pauses make Whisper decode near-silence and recite the glossary
  (OpenWhispr).
- **Empty result:** whitespace-only text gives outcome `empty`.
- **Battery:** while `lib.power.on_mains()` is false and the whisper URL is
  a loopback address, the worker sends no request and work
  waits (`live-transcript` AC-15).

#### Inference faults

The worker tells host faults from input faults:

- **Host fault:** connect refused, DNS failure, connect timeout, a
  connection reset before a response, HTTP 502, 503 or 504, and HTTP 429.
  These say that the host cannot serve now, not that the input is bad. The
  host is down. The worker stops, counts no attempt, and probes again with
  backoff (2 s doubling to 30 s). After 60 s down with work pending, it
  sets `inference-unreachable`. The first success clears it. Work waits in
  files, so one hour down loses nothing (`live-transcript` AC-11).
- **Input fault:** HTTP 500, any other 5xx, or a read timeout after the
  server accepted the request, counts one attempt for that input. After
  `attempts` (3) the record gets outcome `failed`.
- **Input rejection:** HTTP 400, 413 or 422, or a 200 reply that does not
  parse. The input itself is bad, so the record gets `failed` at once.
  `error` holds one line.
- A host that stays reachable but answers 503 for an hour then loses no
  input: the worker waits, as for a host that is down
  (`live-transcript` AC-11).
- The same rules apply to cleanup and llama-server.

#### Cleanup

- **Pending:** `asr/<backend>/` input IDs minus `text/` input IDs.
- **Two lanes**, each with one request in flight: dictation and ambient.
  Dictation never waits behind an ambient request of this host. Across
  hosts, a free llama-server slot serves it (ADR-0002, principle 9).
- **Copy-through:** an `asr` record with outcome `empty`, `expired` or
  `failed` gives a `text` record with the same outcome and empty text.
- **Filters before the LLM** (no request; outcome `empty`):
  - text that is only a known phantom phrase (`phantoms`, such as "Tack
    för att du tittade", "Thanks for watching");
  - glossary echo: three or more glossary terms in glossary order, and
    glossary tokens are at least 70% of all tokens (OpenWhispr, Handy).
- **Fillers, dictation only:** "uh", "um" and "erm" are dropped before the
  request (`filters.fillers`), so the raw text on a timeout has none
  either. Text with nothing else left is `empty`. `heard` keeps the ASR
  text. Parakeet writes fillers that whisper's prompt hid (ADR-0022).
- **Request:** system prompt from `prompts/cleanup.md` (ambient) or
  `prompts/cleanup-dictation.md`, rendered with the glossary and
  `prompt_languages`. The user message wraps the text in
  `<transcript>…</transcript>`. The prompt says that the speaker never
  talks to the model, that questions are never answered, and that the text
  stays in its language (`live-transcript` AC-4, `dictation` AC-8).
  `temperature = 0`, reasoning off,
  `max_tokens = max(64, 2 · len(text) // 3)`, with `len` in characters
  (about twice the input in tokens).
  The reply loses any `<think>` block and zero-width characters.
- **Guard** (YazSes). The reply is replaced by the raw text, with
  `raw: true` and a `raw_reason`, when:
  - its length is outside 0.5 to 2.0 times the input length;
  - it drops a number of the input;
  - fewer than half of the reply's words are in the input
    (`guard-overlap`);
  - in a Swedish line, it drops an English word of 5 or more ASCII letters
    (in the host list `/usr/share/dict/words`) and keeps no word that
    contains it, or of 4 or more letters that it contains (`guard-english`). The model translates English terms in
    Swedish speech ("invoicing" to "fakturering"), and the owner wants them
    kept. Bench on 718 held-out Swedish lines: 17 kept as raw text, 15 of
    them translations. No word list on the host: this check is off.
- A guard for dropped capitalized words in general stays deferred (owner
  decision, 2026-11-23): it undoes valid fixes in mixed-language text.
- **Empty reply:** ambient gives outcome `empty` (the prompt asks for
  empty output on pure hallucination). Dictation passed the presence gate,
  so an empty reply there gives the raw text with `raw_reason: llm-empty`.
- **Dictation time limit:** 1 s (`dictation.cleanup_timeout_ms`). On timeout, or
  with llama-server down, cleanup writes the raw text with `raw: true`
  and `raw_reason: timeout` (ADR-0002, principle 9; `dictation` AC-22).
  Ambient cleanup waits for the host instead.
- Prompt override: `config/prompts/cleanup.md` and
  `config/prompts/cleanup-dictation.md`, as jinja2 templates
  ([ADR-0010](0010-contracts-and-runtime.md)).

#### Drain mode (`--once`)

- `odsodctl run segmentation --once` reads each channel's audio to the end
  of its files, as if capture had stopped there: coverage ends at the last
  sample, and an open utterance closes at that end. Dictation masks from
  existing records apply; it does not wait for the dictation guard.
- `odsodctl run transcription --once` and `odsodctl run cleanup --once`
  drain the pending work of that component, then exit 0
  ([ADR-0010](0010-contracts-and-runtime.md)).
- The pending set, order, request path, guards and record writes are the
  same as in the service. Only the loop differs: no follow, no wait for
  new input.
- A host fault in `--once` gets the same backoff for at most 60 s, then
  the command exits non-zero and leaves the rest pending. It never writes
  `failed` for a host fault.
- The battery rule applies as in the service.
- bench runs these commands in a sandbox root (`ODSOD_DAEMON_ROOT`) with
  the setup's config and prompts, so it scores the live code path
  ([ADR-0019](0019-bench.md); `benchmarking` AC-11). Component and system
  tests use the same mode.

#### Dictation latency budget

For a 15 s dictation (`dictation` AC-3, 2 s from release):

| Step                                      | Typical       |
| ----------------------------------------- | ------------- |
| Coverage of release plus 150 ms post-roll | 250 ms        |
| Utterance append and wake (×3 file hops)  | 60 ms         |
| Wait for an ambient request in flight     | 0 (ADR-0022)  |
| parakeet on the inference CPU, 15 s       | 200 to 600 ms |
| Cleanup (limit 1 s)                       | 300 ms        |
| Paste                                     | 50 ms         |

- The worst case reaches 2.5 s when every step is at its limit. Bench
  measures the real time (`dictation` AC-3). An adaptive cleanup limit is
  left out until bench data shows the need.

### Failure modes

| Fault                                                                | What speech does                                               | Code                                                           |
| -------------------------------------------------------------------- | -------------------------------------------------------------- | -------------------------------------------------------------- |
| whisper-server, parakeet or llama-server down, or 429, 502, 503, 504 | Waits, probes with backoff; dictation cleanup pastes raw text  | `inference-unreachable` (key `whisper`, `parakeet` or `llama`) |
| Rejected request (400, 413, 422, bad reply)                          | `failed` record at once                                        | none                                                           |
| 500 or read timeout                                                  | Up to 3 attempts, then `failed`                                | none                                                           |
| Audio of a pending utterance expired                                 | `expired` record, no request                                   | none                                                           |
| On battery with a loopback whisper or dictation URL                  | No request; work waits                                         | none                                                           |
| Silence hallucination                                                | Filters or the LLM give `empty`                                | none                                                           |
| LLM rewrites too much                                                | Guard writes the raw text                                      | none                                                           |
| Silero model fails to load                                           | Raises; the pipeline exits and systemd restarts it             | none (unit state)                                              |
| Crash at any point                                                   | Restart rebuilds pending sets from files; one record per input | none                                                           |

- Backlog size is control's state, not a speech fault
  ([ADR-0018](0018-control.md)).

### Config

Section `speech`:

```json
{
  "speech": {
    "backend": "whisper",
    "prompt_languages": ["Swedish", "English"],
    "segmentation": {
      "threshold": 0.5,
      "neg_threshold": 0.35,
      "min_silence_ms": 500,
      "min_speech_ms": 250,
      "pad_start_ms": 300,
      "pad_end_ms": 400,
      "max_s": 28,
      "idle_close_s": 3,
      "energy_floor_dbfs": -65
    },
    "ambient": {
      "language": "auto",
      "languages": ["sv", "en"],
      "fallback_language": "sv"
    },
    "dictation": {
      "presence_threshold": 0.3,
      "presence_min_ms": 150,
      "entropy_thold": 2.8,
      "logprob_thold": -1.25,
      "timeout_s": 8,
      "cleanup_timeout_ms": 1000
    },
    "glossary_prompt_chars": 800,
    "attempts": 3,
    "phantoms": ["Thanks for watching", "Tack för att du tittade"]
  }
}
```

- `segmentation` may hold `mic` and `sys` objects that override single
  values per channel. Bench data tunes the values (`live-transcript` AC-3).
- The defaults are the study's starting values (Meetily, Handy, YazSes,
  OpenWhispr).
- The dictation mask timings are constants, not config (see Segmentation).
- `common.inference.whisper_url`, `llama_url` and `dictation_url` are full
  endpoint URLs (ADR-0010). `speech.parakeet` holds the dictation server
  (ADR-0022).

### Tests

Component tests run on the virtual-time event loop of `lib.clock`
(ADR-0010), so backoffs and timeouts take no real time. They use the
shared audio fixtures (public-domain Swedish and English speech, with
provenance; silence, zeros and fan noise; ADR-0010), and the fake
whisper-server and llama-server from `lib.inference`. The fakes replay
recorded request and response pairs, with scripted delays and status
codes. Latency targets are not CI tests: they are bench measures and owner
checks.

| Test                                                                          | Checks                    |
| ----------------------------------------------------------------------------- | ------------------------- |
| Cutter on scripted probabilities: start, end, pads, min speech                | `live-transcript` AC-1    |
| Forced cut lands at the lowest probability in the second half                 | AC-3 (shorter requests)   |
| One hour of zeros and fan noise gives no utterance, and little CPU            | AC-9                      |
| Idle coverage closes an utterance; no utterance spans a hole                  | AC-14                     |
| Dictation record and `dictating` status mask `mic`; cancel does not           | AC-16; `dictation` AC-24  |
| Status goes `idle` before the follow delivers the record: still masked        | AC-16; `dictation` AC-24  |
| Capture stops: coverage reaches the stop time once the guard passes           | AC-12, AC-14              |
| Mask budget: dictation constants fit the guard and stale constants            | `dictation` AC-24         |
| Silero model: input and output shapes on a fixture; pinned SHA-256            | AC-1                      |
| Stale `dictating` status is ignored after the limit                           | AC-16                     |
| Restart from `covered`: no duplicate ID, no lost speech                       | AC-10                     |
| `--once` drains pending work and exits 0; host down → non-zero, no `failed`   | `benchmarking` AC-11      |
| Pending order: a dictation queued behind ambient goes next                    | `dictation` AC-4          |
| Host down 1 h (fake): no attempts counted; fault after 60 s; catch up         | `live-transcript` AC-11   |
| 400 → `failed`; 3 × 500 → `failed`; expired audio → `expired`                 | ADR-0003 outcomes         |
| 503 for 1 h, then 200: no `failed` record; all text arrives                   | `live-transcript` AC-11   |
| Whisper fault set, llama fine: cleanup does not clear it (keyed fault)        | `health-and-control` AC-2 |
| Language names and codes from recorded replies map to ISO codes               | AC-4                      |
| Battery with loopback URL: no request; tailnet URL: requests go on            | AC-15                     |
| Dictation silence: presence gate gives `empty`, no request                    | `dictation` AC-7          |
| Detected `no` language → second request with `sv`                             | AC-4                      |
| Glossary prompt keeps the tail within 800 chars                               | AC-5                      |
| Phantom and glossary echo give `empty`                                        | AC-9; `dictation` AC-7    |
| Guard: length and number rules fall back to raw                               | AC-3                      |
| Dictated question: prompt and fake LLM keep it a question                     | `dictation` AC-8          |
| llama-server slow 2 s: dictation text is raw after the 1 s limit; `raw: true` | `dictation` AC-22         |
| Dictation lane runs while an ambient cleanup is in flight (order, not time)   | `dictation` AC-4, AC-21   |

System tests (root `tests/`): capture fake → segmentation → transcription
→ cleanup with fake servers. One utterance gives one `text` record after a
pipeline kill at any step (`live-transcript` AC-10). System tests run in
real time with small config values and check order and outcomes, never
latency. A dictation with another host's ambient cleanup holding one fake
llama slot gets its text before that request ends (`dictation` AC-21,
order only).

Bench measures and owner checks (not here, [ADR-0019](0019-bench.md)):
WER (`live-transcript` AC-3, `dictation` AC-6), language (AC-4), glossary
spelling (AC-5), dictation latency (`dictation` AC-3, AC-21).

### Build without hardware

- An agent builds and tests all three components with the fixtures and the
  fake servers. Silero runs on the CPU, so the VAD tests need no GPU.
- Initial audio fixtures are public-domain recordings with a
  `PROVENANCE.md` (owner decision, 2026-11-23). After the first day of
  capture, real audio from the owner's host extends them.
- The fakes need recorded whisper-server and llama-server replies. An
  agent records them once against the owner's inference host, over the
  tailnet, before the build (ADR-0010).
- Real WER, language behavior and latency need the owner's inference host
  and the bench. The owner reviews bench references; agents run the rest.

## Alternatives considered

### Server-side VAD (the Go recorder)

- Simple: send RMS-gated chunks, let whisper-server's Silero pick speech.
- Rejected: chunks then span language changes and pauses, and utterances
  have no times of their own for speakers, dictation masks and bench.

### A checkpoint file for segmentation

- Rejected: the `covered` stream does the same, and transcript,
  interactions and control need it too.

### Drop overlapping `mic` utterances in transcript

- Rejected: the words would still reach `utterances/ambient/` and every
  later reader. Masking at the source keeps them out of all of them.

### Raw text for ambient when llama-server is down

- Lines would keep coming during an LLM outage.
- Rejected: raw text has no glossary fixes, and lines would differ by luck
  of timing. Ambient work waits; only dictation, which the owner waits for,
  pastes raw text.

### Config keys for the dictation mask timings

- The owner could tune the guard and the stale limit per host.
- Rejected for v1 (owner decision, 2026-11-23): the mask is safe only
  while these values fit the dictation constants. A config change could
  leak private dictation into ambient text.

### A guard for dropped capitalized words

- Deferred: it can undo valid fixes, and new names outside the glossary
  trigger it. Bench data decides.

### A language-ID model before Whisper

- Rejected for now: one more model. The fallback request covers the common
  Norwegian and Danish mistakes. Bench data can reopen it.

## Consequences

- Live `mic` lines come about 1.2 s later than they could, so a dictation
  never leaks into them.
- Each host sends many short requests. The shared GPU carries more
  requests than with long chunks (ADR-0002).
- Under load, dictation can paste raw ASR text. The text record says why.
- Every utterance gets exactly one `text` record, so readers need no
  second stream to know that an utterance is done.
