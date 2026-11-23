# PRD: Benchmarking

- Status: Accepted
- Updated: 2026-11-23
- Design: [ADR-0002](../adr/0002-high-level-architecture.md),
  [ADR-0003](../adr/0003-filesystem-interface.md),
  [ADR-0005](../adr/0005-components-and-implementation.md)

## Problem

- Speech-to-text and language models change every month. The owner needs to
  pick models, prompts and settings from data on their own speech, their
  own meetings and their own words, not from public leaderboards.
- Many targets in the other PRDs carry "bench confirms". Without a bench,
  they stay guesses.
- Some choices need data before an ADR can adopt them: a dictation model on
  the local CPU or in the cloud, a second speech-to-text pass, echo
  cancellation.
- The owner's time to check results by hand is short. Agents do the work;
  the owner supervises and accepts.

## Behavior

- Owner or an agent runs `odsodctl bench cases` → new test cases from the
  stored audio and its text: ambient utterances in Swedish and English,
  dictations, and finished interactions.
- An agent writes a draft reference for a case: the corrected text, or for
  a summary, the decisions and next steps it must hold.
- Owner runs `odsodctl bench review` → sees the draft next to the audio,
  fixes it if needed, and accepts it. Only accepted references count in a
  report.
- Agents can do every bench step: build cases, draft references, run setups
  and read reports. The owner accepts references and decides on adoption
  (owner decision, 2026-11-23).
- Owner or an agent runs `odsodctl bench run <setup>` → the setup runs on all
  cases with a reference. A setup is a model, a prompt or a setting.
- Owner or an agent runs `odsodctl bench report` → a table per measure and
  setup, with the PRD criterion each measure checks. `--json` for agents.
- Shadow backends: config adds a second speech-to-text backend that runs on
  live audio next to the main one. Its text is stored but never shown in the
  transcript.
- A case keeps its audio with no end date, so new setups can run on it
  later (owner decision, 2026-11-23). Each case is one self-contained unit:
  its audio, its text, its reference, who wrote and accepted the reference,
  and where it came from (host, time, channel). The owner or an agent can
  list, read and delete cases with `odsodctl bench`.
- The cloud model for dictation gets only dictation audio, never ambient
  audio (ADR-0002).

### Measures

| Measure                                     | For                    | Checks                              |
| ------------------------------------------- | ---------------------- | ----------------------------------- |
| Word error rate, Swedish and English        | Ambient speech-to-text | `live-transcript` AC-3, AC-4        |
| Glossary terms spelled right                | Ambient and dictation  | `live-transcript` AC-5              |
| Echo lines removed                          | Live transcript        | `live-transcript` AC-6              |
| Word error rate, English                    | Dictation              | `dictation` AC-6                    |
| Time from release to text, CPU load, cost   | Dictation backends     | `dictation` AC-3                    |
| Speech time with the right speaker name     | Interaction documents  | `interactions-and-publishing` AC-4  |
| Summary points that trace to the transcript | Summaries              | `interactions-and-publishing` AC-12 |
| Decisions and next steps found              | Summaries              | `interactions-and-publishing` AC-13 |
| CPU and disk use of recording               | Recording              | `ambient-recording` AC-11           |
| Delay of unmapped keys                      | Keys service           | `keyboard` AC-15                    |

### When something fails

- A setup fails on a case → the report shows the failure for that case. The
  run goes on with the other cases.
- The cloud model has no credentials → its setup reports "no credentials"
  and runs on no case.
- A shadow backend is down → the main transcript is not affected. The tray
  shows nothing.

## Acceptance criteria

The 3 h of owner review time per quarter and the case counts are proposed
targets for the owner to confirm.

1. **AC-1** `odsodctl bench cases` gives at least 50 ambient cases in each
   language, 50 dictation cases and 10 interactions from 14 days of normal
   use. _Check: manual._
2. **AC-2** Review of one 15 s case with an agent draft takes at most 30 s,
   from audio start to accepted reference. _Check: manual._
3. **AC-3** All measures in the table can be reported from at most 3 h of
   owner review per quarter. _Check: manual._
4. **AC-4** Two runs of the same setup on the same cases give the same
   scores, except for time measures. _Check: system test._
5. **AC-5** Each report row names the setup, the case count, the score and
   the PRD criterion it checks. _Check: system test._
6. **AC-6** A shadow backend adds no delay to the live transcript, measured
   as `live-transcript` AC-1 with and without it. _Check: bench._
7. **AC-7** A case's audio stays after the audio around it is deleted, until
   the owner or an agent deletes the case. Each case holds its audio, text,
   reference, review state and source in one place. _Check: system test._
8. **AC-8** No ambient audio leaves the owner's hosts and the inference host
   during a bench run. _Check: system test._
9. **AC-9** A failed case shows in the report, and the run finishes the
   other cases. _Check: system test._
10. **AC-10** A report counts only references the owner accepted. Drafts
    show as a separate count. _Check: system test._

## Boundaries

### Covered by other PRDs

- The targets that the measures check → the PRD named in each row.
- Choosing a new backend → an ADR, on bench data (ADR-0002, ADR-0005).

### Not planned

- Public datasets. The bench uses only the owner's own audio.
- Automatic switch to the best setup. A person decides, in an ADR.
- Benchmarks of the inference host itself, such as GPU load.
- Recorded key timing to tune the Left Alt hold threshold, for now. The
  owner tunes it from use. Add it later only if the threshold is a real
  problem (owner decision, 2026-11-23).

## Open questions

- None.
