# Plan: Dictation speech-to-text on CPU

- Status: Active
- Depends on: [dictation](2026-11-23-dictation.md)
- Design: [ADR-0022](../adr/0022-dictation-asr.md),
  [PRD dictation](../prd/dictation.md) AC-3, AC-23, AC-27

## Goal

- Dictation speech-to-text runs on the inference host's CPU and never
  waits for ambient whisper work.
- Every host sends dictation there. With the inference host out of reach,
  dictation is off.

## Scope

- In: the `parakeet` component, `common.inference.dictation_url`, a
  dictation loop of its own in transcription, the session probe on
  `dictation_url`, health code `parakeet-unavailable`.
- Out: a local fallback, streaming, whisper-server and llama-server units
  (they stay in the `machine` repo).

## Steps

1. Config: `speech.parakeet`, `common.inference.dictation_url`.
2. `parakeet`: model pin and fetch, endpoint, service; tests with a fake
   recognizer and a local file server.
3. Transcription: two loops when `dictation_url` is set.
4. Session: probe `dictation_url` when set.
5. Desktop: enable the server, set `dictation_url`, deploy, measure.
6. Laptop: set `dictation_url` to the desktop, reinstall, measure.

## Done when

- `mise run build` passes.
- On the desktop, `odsodctl dictation last` shows text, and the
  `dictation timing` journal line shows text within 2 s of release while
  ambient work runs.

## Progress log

- 2026-11-24: steps 1 to 4 built; `mise run build` passes (887 tests).
  Smoke with the real model through the endpoint: warm load 0.9 s,
  `en-chinese-feet` gives the reference text, silence gives no text.

## Decisions to confirm

- Port 8180 and 8 threads.
- The server runs in the `pipeline` service, not a service of its own:
  a pipeline restart takes dictation down for the model load (about 1 s
  warm).
