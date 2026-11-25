# PRD: Benchmarking

- Status: Accepted
- Updated: 2026-11-25
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
  cancellation, speaker diarization.
- The owner's time to check results by hand is short. Agents do the work;
  the owner supervises and accepts.

## Behavior

- Owner or an agent runs `odsodctl bench cases` → new test cases from the
  stored audio and its text: ambient utterances in Swedish and English,
  dictations, and finished interactions.
- Each case is a folder the owner can open. An agent writes a draft
  reference in it: the corrected text, or for a summary, the decisions and
  next steps it must hold.
- Owner plays the case audio in any player, fixes the draft in any editor,
  and runs `odsodctl bench accept <case>`. There is no review window. Only
  accepted references count in a report.
- Agents can do every bench step: build cases, draft references, run setups
  and read reports. The owner accepts references and decides on adoption
  (owner decision, 2026-11-23).
- Owner or an agent runs `odsodctl bench run <setup>` → the setup runs on all
  cases with a reference, offline, on the saved audio. A setup is a model,
  a prompt or a setting.
- Each result names its full setup: model and revision, prompt, settings
  and daemon commit. Results from a changed setup never mix with old ones.
- Owner or an agent runs `odsodctl bench report` → a table per measure and
  setup, with the PRD criterion each measure checks. `--json` for agents.
- Measures come in stages. First: word error rate and dictation latency.
  Then, after a timed pilot of their review: speaker names.
- A case keeps its audio with no end date, so new setups can run on it
  later (owner decision, 2026-11-23). Each case is one self-contained unit:
  its audio, its text, its reference, who wrote and accepted the reference,
  and where it came from (host, time, channel). The owner or an agent can
  list, read and delete cases with `odsodctl bench`.
- The cloud model for dictation gets only dictation audio, never ambient
  audio (ADR-0002).

### Measures

| Measure                                   | For                    | Checks                       |
| ----------------------------------------- | ---------------------- | ---------------------------- |
| Word error rate, Swedish and English      | Ambient speech-to-text | `live-transcript` AC-3, AC-4 |
| Glossary terms spelled right              | Ambient and dictation  | `live-transcript` AC-5       |
| Echo lines removed                        | Live transcript        | `live-transcript` AC-6       |
| Word error rate, English                  | Dictation              | `dictation` AC-6             |
| Time from release to text, CPU load, cost | Dictation backends     | `dictation` AC-3             |
| Speech time with the right speaker name   | Interaction documents  | `interactions` AC-4          |

### When something fails

- A setup fails on a case → the report shows the failure for that case. The
  run goes on with the other cases.
- The cloud model has no credentials → its setup reports "no credentials"
  and runs on no case.

## Acceptance criteria

The 3 h of owner review time per quarter and the case counts are targets.

1. **AC-1** `odsodctl bench cases` gives at least 50 ambient cases in each
   language, 50 dictation cases and 10 interactions from 14 days of normal
   use. _Check: manual._
2. **AC-2** Review of one 15 s case with an agent draft takes at most 30 s,
   from audio start to accepted reference. _Check: manual._
3. **AC-3** All measures in the table can be reported from at most 3 h of
   owner review per quarter. A timed pilot confirms this before the speaker
   measure is added. _Check: manual._
4. **AC-4** Scoring the same saved output twice gives the same scores. A new
   inference run may differ. _Check: system test._
5. **AC-5** Each report row names the setup, the case count, the score and
   the PRD criterion it checks. _Check: system test._
6. **AC-6** Removed: live shadow backends are deferred. Setups run offline
   on saved cases.
7. **AC-7** A case's audio stays after the audio around it is deleted, until
   the owner or an agent deletes the case. Each case holds its audio, text,
   reference, review state and source in one place. _Check: system test._
8. **AC-8** No ambient audio leaves the owner's hosts and the inference host
   during a bench run. _Check: system test._
9. **AC-9** A failed case shows in the report, and the run finishes the
   other cases. _Check: system test._
10. **AC-10** A report counts only references the owner accepted. Drafts
    show as a separate count. _Check: system test._
11. **AC-11** Each result records the model and its revision, the prompt,
    the settings and the daemon commit. A report never puts results from
    two different setups in one row. _Check: system test._

## Boundaries

### Covered by other PRDs

- The targets that the measures check → the PRD named in each row.
- Recording CPU and disk use → the `ambient-recording` PRD.
- Delay of unmapped keys → the `keyboard` PRD.
- Choosing a new backend → an ADR, on bench data (ADR-0002, ADR-0005).

### Not planned

- Public datasets. The bench uses only the owner's own audio.
- Automatic switch to the best setup. A person decides, in an ADR.
- Benchmarks of the inference host itself, such as GPU load.
- A review window or app. A folder, a player and an editor do the job.
- Live shadow backends next to the main one, for now. Add them only with a
  measured need and a resource limit (owner decision, 2026-11-23).
- Recorded key timing to tune the Left Alt hold threshold, for now. The
  owner tunes it from use. Add it later only if the threshold is a real
  problem (owner decision, 2026-11-23).

## Open questions

- None.
