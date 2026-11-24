# ADR-0022: Dictation speech-to-text on CPU

## Status

Accepted. Changes [ADR-0002](0002-high-level-architecture.md) principle 9
and [ADR-0012](0012-speech.md) for dictation.

## Date

2026-11-24

## Context

- Dictation shares one whisper-server with ambient work from every host.
  whisper-server takes one request at a time, and a GPU cannot preempt a
  request in flight. A dictation waits for the ambient request ahead of it.
- Live data (2026-11-24): ambient requests take 3.4 to 7.1 s while ambient
  work saturates the server. Dictation took 3.8 to 5.6 s from release to
  paste, against the 2 s target (`dictation` AC-3).
- 155 of 2334 ambient utterances in one day were longer than 10 s, up to
  27.7 s.
- ADR-0002 rejected a priority broker, and named a second inference server
  just for dictation as the next step. The GPU has no room for a second
  whisper model (14.7 of 17 GB in use).
- Bench (2026-11-24, English, 15 clips and fixtures, scratch study):

  | Engine                         | Fixture WER | p50    | Max     |
  | ------------------------------ | ----------- | ------ | ------- |
  | Parakeet TDT 0.6B v2 INT8, CPU | 5.1%        | 174 ms | 1051 ms |
  | Parakeet TDT 0.6B v3 INT8, CPU | 7.2%        | 172 ms | 928 ms  |
  | faster-whisper small.en, CPU   | 5.2%        | 645 ms | 1464 ms |
  | whisper large-v3, GPU (shared) | 3.1%        | 976 ms | 7200 ms |
  | Chirp 3, Google cloud          | 3.1%        | 721 ms | 1278 ms |

  The CPU runs used 8 threads of the desktop's i9-14900. The laptop CPU
  (Ultra 7 155U) gave a p50 of 931 ms. Parakeet gave no text on noise or
  silence, and lost no words after a 2 s pause. Its errors are mostly in
  names. It keeps fillers, which cleanup removes.

- Research (`docs/research/`): YazSes, hyprwhspr, OpenWhispr, Meetily and
  Voxtype run Parakeet on CPU through ONNX Runtime.
- Dictation is English only (owner decision, 2026-11-24).

## Decision

### One CPU speech-to-text server on the inference host

- New component `parakeet` in the speech subsystem. It runs in the
  `pipeline` service on the inference host only.
- It loads Parakeet TDT 0.6B v2 (INT8 ONNX) once and keeps it in memory.
  It runs one request at a time on `threads` CPU threads. It never uses the
  GPU, so ambient work on the GPU never delays it.
- It serves the whisper-server API: `POST /v1/audio/transcriptions`,
  multipart, field `file` (16 kHz mono 16-bit WAV). It ignores other
  fields. Reply: `{"text", "language": "en", "model"}`. Errors: 400 for bad
  audio, 503 while the model loads.
- It listens on each address in `listen`. Each address must be loopback or
  tailnet (ADR-0002 principle 5). A bind that fails retries every 5 s, so
  the server comes up when tailscaled does.
- Library: `onnx-asr` (MIT, depends only on `numpy`) on the `onnxruntime`
  the daemon already ships. Imported only when the server is enabled.

### The model is pinned

- Source: Hugging Face `istupakov/parakeet-tdt-0.6b-v2-onnx`, revision
  `0bbb45a3365852604aef28b538a8f066f4ccaa85`. Model license CC-BY-4.0.
- The component downloads four files on first start (about 660 MB) into
  `state/models/parakeet-tdt-0.6b-v2/`, checks each SHA-256 against the
  pin in code, and renames into place. A file with a wrong hash is
  deleted, and the download retries with backoff.

| File                            | SHA-256 (start)    | Bytes       |
| ------------------------------- | ------------------ | ----------- |
| `config.json`                   | `666903c76b9798ca` | 97          |
| `vocab.txt`                     | `ec182b70dd42113a` | 9 384       |
| `decoder_joint-model.int8.onnx` | `a449f49acd68979d` | 8 998 286   |
| `encoder-model.int8.onnx`       | `3e0581fda6ab8438` | 652 184 014 |

### Dictation uses it on every host

- New `common.inference.dictation_url`. Unset: dictation uses
  `whisper_url`, as before.
- The inference host sets it to `127.0.0.1`. Other hosts set it to the
  inference host's tailnet address.
- Transcription runs dictation in its own loop, against `dictation_url`.
  It never waits for an ambient request in flight. Ambient stays on
  whisper-server.
- Dictation requests keep the whisper fields. The server ignores them.
- Cleanup stays on llama-server with its 1 s limit (ADR-0012).

### No local fallback

- Hosts other than the inference host load no speech model.
- With the inference host out of reach, dictation is off: Left Alt is a
  plain Alt and the tray says why (ADR-0013, `keys: no-inference`). The
  session checks `dictation_url` when it is set.
- Ambient recording goes on. Its utterances stay pending until the
  inference host answers again (ADR-0012).

### Config

```json
{
  "common": { "inference": { "dictation_url": "http://127.0.0.1:8180/v1/audio/transcriptions" } },
  "speech": {
    "parakeet": {
      "enabled": true,
      "listen": ["127.0.0.1", "100.79.24.22"],
      "port": 8180,
      "threads": 8
    }
  }
}
```

- Defaults: `enabled: false`, `listen: ["127.0.0.1"]`, `port: 8180`,
  `threads: 8`.

### Failure modes

| Fault                                | What happens                                                     | Code / signal                           |
| ------------------------------------ | ---------------------------------------------------------------- | --------------------------------------- |
| Model download fails or hash differs | Retry with backoff; server answers 503                           | `parakeet-model` (Warning)              |
| Bind fails (address not up yet)      | Retry every 5 s                                                  | `parakeet-listen` (Warning) after 60 s  |
| Model fails to load                  | Component raises; the pipeline restarts                          | unit failure                            |
| Server unreachable from a host       | Dictation off on that host                                       | `keys: no-inference`                    |
| Server answers 5xx or times out      | Same retries and `timeout_s` as whisper for dictation (ADR-0012) | `inference-unreachable`, key `parakeet` |

## Consequences

- Dictation transcription drops from about 1 s typical, and up to 7 s
  under ambient load, to about 0.2 s on the inference host.
- About 1 GB of RAM on the inference host, and 8 CPU threads for a few
  hundred ms per dictation.
- A model download of about 660 MB on first start of the inference host.
- Parakeet has no prompt, so the glossary does not reach dictation
  speech-to-text. Cleanup spells the terms.
- The daemon now owns one inference server. whisper-server and
  llama-server stay in the `machine` repo. Moving them into the daemon is a
  separate decision.

## Alternatives

### A priority gate in front of whisper-server and llama-server

- Gives dictation priority across hosts, but a request in flight still
  blocks it. One more service, and a single point of failure.

### Shorter ambient requests

- A 10 s cap bounds the wait to about 1.5 s, but cuts monologues. Not
  needed once dictation has its own server.

### Chirp 3 in the cloud

- Same accuracy as whisper and 721 ms p50, but audio leaves the owner's
  hosts, and every dictation costs money. Its custom prompt does not remove
  fillers and makes up text on silence.

### Streaming speech-to-text

- Not needed at about 0.2 s per dictation. YazSes found that a final
  decode after streaming makes latency worse.

### A local fallback on each host

- Parakeet on the laptop takes about 1 s, but cleanup needs llama-server on
  the inference host. Offline text would be raw. About 1 GB RAM and more
  code for a worse result.
