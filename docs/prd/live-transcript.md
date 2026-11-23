# PRD: Live transcript

- Status: Accepted
- Updated: 2026-11-23
- Design: [ADR-0002](../adr/0002-high-level-architecture.md),
  [ADR-0003](../adr/0003-filesystem-interface.md),
  [ADR-0005](../adr/0005-components-and-implementation.md)

## Problem

- The owner needs a record of what was said today, while the day runs: to
  look back an hour, and to give AI agents context now, not tomorrow.
- Talks are in Swedish or English. Swedish talk carries English technical
  words, such as PR, pull request and monitoring. The language of a call
  changes when an English speaker joins or leaves, such as in the permanent
  call. The record must keep both languages.
- The record must tell the owner's words from the other side's.
- Some context is not in the audio: what the owner thinks, and where a
  topic starts. The owner and agents must be able to add it.

## Behavior

- Someone speaks → a line appears in today's transcript within seconds: the
  time, the source (the owner or the other side) and clean text.
- Speech in Swedish or English → text in the language spoken. English
  technical words in Swedish speech stay in English.
- An English speaker joins or leaves a call → the lines follow the new
  language.
- Owner dictates → the dictated text appears too, marked as dictation.
- A meeting starts or ends in the browser → a line marks it.
- Owner or an agent runs `odsodctl note "<text>"` → a note line at the
  current time. `odsodctl pin` → a pin line that marks the start of a new
  topic.
- The meeting's voices reach the mic through the speakers → each phrase
  appears once, from the other side.
- Silence → no lines.
- Recording stops for more than 1 min (pause, crash, upgrade, logout) → a
  line shows the gap, its time range, and its cause when known. A reader
  can tell "nothing recorded" from "nothing said".
- One transcript per host per local day. Owner or an agent runs
  `odsodctl transcript` → today's transcript of this host, while the day
  runs.
- The local day ends → the transcript is finished and copied to the
  configured targets, such as the vault inbox. It never changes after that.
- While the host is on mains power, transcription keeps up with all audio
  (owner decision, 2026-11-23).
- On battery, the host runs no speech model itself. Transcription uses the
  inference host, or waits for mains power (owner decision, 2026-11-23).

### When something fails

- The inference host is out of reach → lines stop, and the tray shows
  Warning. When it returns, the missed lines appear, each with its own time.
- The pipeline service crashes → it restarts. No line is lost or doubled.

## Acceptance criteria

All numbers are proposed targets for the owner to confirm.

1. **AC-1** On mains power, with the inference host idle, a line appears at
   most 10 s after its utterance ends. _Check: system test._
2. **AC-2** Each line shows the local time to the second, the source
   (owner, other side, dictation, note, pin or meeting) and the text.
   _Check: system test._
3. **AC-3** Word error rate on the owner's Swedish and English speech is at
   most 15% on the mic and 10% on system audio (target; bench confirms).
   _Check: bench._
4. **AC-4** No line is translated: each line is in the language spoken, and
   English technical words in Swedish lines stay in English. After a
   change of language in a call, the next utterance in the new language
   comes out in that language. _Check: bench._
5. **AC-5** Names and terms in the glossary are spelled as in the glossary.
   _Check: bench._
6. **AC-6** A phrase that is in both the mic and system audio appears once,
   in at least 95% of cases (target; bench confirms). _Check: bench._
7. **AC-7** A note or pin from `odsodctl` appears at most 2 s later.
   _Check: system test._
8. **AC-8** A meeting start or end line appears at most 30 s after the
   owner joins or leaves a Meet or Teams call. _Check: manual._
9. **AC-9** One hour of silence or noise gives no text lines. _Check:
   system test._
10. **AC-10** After a pipeline crash, every utterance has exactly one line.
    _Check: system test._
11. **AC-11** After one hour with the inference host down, the missed lines
    appear at most 30 min after it returns, with their own times. _Check:
    system test._
12. **AC-12** The transcript is in the targets at most 10 min after the
    local day ends, and never changes after that. Transcripts from several
    hosts do not clash. _Check: system test._
13. **AC-13** `odsodctl transcript` prints today's transcript of this host
    in at most 1 s, and as JSON with `--json`. _Check: system test._
14. **AC-14** A recording gap of more than 1 min gives one line with its
    start, end and cause (pause, restart, logout or unknown). Speech before
    and after a gap never joins into one line. _Check: system test._
15. **AC-15** On battery, the host uses no more CPU for transcription than
    for recording alone. _Check: bench._

## Boundaries

### Covered by other PRDs

- Speaker names, interaction documents and summaries → the
  `interactions-and-publishing` PRD.
- Recording, and what is kept when → the `ambient-recording` PRD.
- Dictation itself → the `dictation` PRD.
- The tray Warning for a growing backlog → the `health-and-control` PRD.

### Not planned

- Speaker names in the live transcript. The batch pass adds them with full
  context (ADR-0002).
- Live captions in a window. A window steals focus on Wayland (ADR-0005).
- Merging transcripts of the same day from several hosts. The vault's
  ingest agent does it (owner decision, 2026-11-23).

## Open questions

- None.
