# Plan: inference recordings and measures

- Status: Done 2026-11-23
- Depends on: [python-scaffold](2026-11-23-python-scaffold.md),
  [whisper-novad](2026-11-23-whisper-novad.md),
  [audio-fixtures](2026-11-23-audio-fixtures.md)
- Design: [ADR-0010](../adr/0010-contracts-and-runtime.md) (Test
  fixtures), [ADR-0012](../adr/0012-speech.md) (Transcription, Cleanup,
  Inference faults), [ADR-0016](../adr/0016-interactions.md) (Summary,
  Config)

## Goal

- The `lib.inference` fake replays real request and response pairs from
  this host's servers, so no fake is built from ADR text alone.
- `interactions.chunk_chars` has a measured default.

## Scope

- In: recordings in `src/odsod_daemon/lib/inference/testdata/`, a small
  script that makes them, and the token measure.
- Out: changes to the servers. Bench runs.

## Steps

1. A recorder script (kept in `lib/inference/testdata/record.py`, run with
   `uv run`) sends these and saves each request and response as JSON
   (headers that matter, body, status, elapsed time):
   - whisper 8178 (no `--vad`): a Swedish clip,
     an English clip, the silence clip, a request with a bad field (4xx),
     and the request shapes of ADR-0012 "Transcription" (language,
     prompt, `verbose_json`);
   - llama 8179: one ambient cleanup and one dictation cleanup with
     minimal prompts written from the rules in ADR-0012 "Cleanup" (the
     prompt files do not exist yet), one summary request with the JSON
     schema of ADR-0016 "Summary", and one 4xx. The speech plan
     re-records them with its final prompts.
   - A timeout is scripted in the fake, not recorded.
2. Write in Progress log the form of the whisper language field (name or
   code). `cleanup/language.py` tests use these replies.
3. Token measure (spike S3): send a 35,000-character Swedish text with the
   summary prompt; read `usage.prompt_tokens`. Set the default
   `chunk_chars` so the prompt, the chunk and the output fit the per-slot
   context with 25% headroom. With today's single slot the context is
   32,768 tokens; write the value for 2 slots (16,384) too.
4. No owner text, names or meeting content in the recordings: use the
   public-domain fixtures and a generated Swedish text.

## Done when

```sh
ls src/odsod_daemon/lib/inference/testdata/*.json | wc -l   # 9 or more
uv run pytest src/odsod_daemon/lib/inference                # fake replays every recording
```

- Progress log has the language field form and the measured
  `chunk_chars` for 1 and 2 slots.

## Progress log

- 2026-11-23: Converted `lib/inference.py` to `lib/inference/__init__.py`; added `**/testdata/**` to the wheel exclude; `conftest.py` loads the flat testdata directory for both fakes.
- 2026-11-23: Recorded 9 pairs with `record.py`: 5 whisper, 4 llama. The whisper language field is a name (`swedish`, `english`), not a code.
- 2026-11-23: Token measure: 35,000 Swedish characters gave 9,680 prompt tokens (135 for the fixed prompt), or 0.273 tokens per character. With 2,048 output tokens, 1 slot (32,768) fits 82,000 characters and 2 slots (16,384) fit 37,000. Set the ADR-0016 default to 37,000.
- 2026-11-23: Done when passes: 9 JSON recordings; `uv run pytest src/odsod_daemon/lib/inference` (23 passed).

## Decisions to confirm

- Recordings are flat in `testdata/*.json` to match this plan's Done when and the current `load_pairs`. This supersedes the scaffold decision that put them in `{whisper,llama}/`; both fakes now load the flat directory and filter by request path.
- Whisper multipart bodies are stored as fields plus file metadata (name, content type, SHA-256, bytes), not as raw bytes. Llama bodies are the JSON request. This keeps the recordings small and readable.
- The whisper 4xx pair is a missing file, which the server rejects with 400. Bad field values such as `response_format=bogus` return 200 or 500, not 4xx.
- The chunk measure uses 2,048 output tokens (the client default). A larger summary reply budget needs a lower `chunk_chars`.
