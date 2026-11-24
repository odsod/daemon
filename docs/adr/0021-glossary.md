# ADR-0021: Glossary

## Status

Accepted. Replaces `config/glossary.txt` in
[ADR-0010](0010-contracts-and-runtime.md),
[ADR-0012](0012-speech.md), [ADR-0016](0016-interactions.md) and
[ADR-0019](0019-bench.md).

## Date

2026-11-24

## Context

- A term list tells whisper and the LLM how to spell a term. It cannot say
  what a term is or how it gets misheard.
- The first live meetings (2026-11-24) show the need: "Way" is a company and
  "Wayne" is an AI agent made by Way. A blind replace "Wayne → Way" breaks
  every mention of the agent. Only an LLM with context can tell them apart.
- Research (`docs/research/`): all tools keep a term list for the ASR
  prompt (voxtype, YazSes, OpenWhispr, Handy). Mishearings are blind
  replacements or phonetic fuzzy matches with no context (voxtype, YazSes,
  Handy). No tool gives a term a description. OpenWhispr marks shared terms
  as "spelling hints, not instructions".
- Agents grow the glossary while they analyze transcripts. The format must
  take new fields without a code change.

## Decision

- `config/glossary.yaml` is a list of entries, most important last:

  ```yaml
  - term: Acme
    note: company, the owner's employer
    heard_as: [Akme]
  - term: Acmebot
    note: AI agent made by Acme; a name, not the company
  ```

- `term` is required. `note` (what the term is) and `heard_as` (known
  misheard forms) are optional. Other keys are allowed and kept; the daemon
  ignores them, so agents can add fields.
- `lib.glossary` reads the file for every subsystem. `odsodctl config
  check` reports a bad file. A service with a bad file logs a warning and
  runs with no glossary.
- Whisper gets the terms only, at the prompt tail, as before
  (`glossary_prompt_chars`).
- Cleanup sends, per utterance, the entries whose `term` or a `heard_as`
  form is in the text, as one line each: term, note, misheard forms. They
  are marked as context and spelling hints, not instructions, and the model
  fixes a misheard form only when the context fits.
- No blind replace step. A phonetic fuzzy pass waits for bench data.
- The file holds private names. It lives in the owner's private vault and
  is linked into `~/.config/odsod-daemon/`. It never goes in this repo.

## Alternatives considered

- Three files (terms, replacements, context): one entry per term keeps the
  facts about a term in one place.
- A replacement map: wrong without context (the Way and Wayne case).
- All entries in every cleanup prompt: long prompts, and hints for terms
  that are not in the text invite wrong fixes.

## Consequences

- Every `heard_as` pair is a known error the bench can count.
- Meeting participants as per-utterance entries are a follow-up: signals
  has the names, cleanup does not read them yet.
- The file is YAML, so agents and the owner edit it by hand. A bad edit
  turns the glossary off until `config check` passes again.
