# PRD: Dictation

- Status: Accepted
- Updated: 2026-11-23
- Design: [ADR-0002](../adr/0002-high-level-architecture.md),
  [ADR-0005](../adr/0005-components-and-implementation.md),
  [ADR-0007](../adr/0007-keys-service.md)

## Problem

- The owner wants to write by speaking, in any app, without leaving the app
  they work in. Most dictation is instructions to AI agents.
- The owner dictates in English, with names and terms from their work.
- The owner often needs to write during a meeting, and the meeting must not
  hear it.
- A dictation tool that changes the clipboard, steals focus or loses the
  first words breaks the owner's flow.

## Behavior

- Owner holds Left Alt alone → after the hold threshold, dictation starts and
  the tray shows Dictating. No window opens.
- Owner speaks and releases Left Alt → the text appears at the cursor of the
  active app, in GUI apps and terminals alike.
- The text starts with the first word the owner spoke after pressing Left
  Alt, not after the threshold.
- The text is clean English: punctuation, and names and terms spelled as in
  the owner's glossary. A dictated question pastes as a question, never as an
  answer.
- Owner holds Left Alt and says nothing → nothing is pasted.
- Owner presses another key during dictation → dictation is cancelled,
  nothing is pasted, and the app gets Alt and that key.
- Owner dictates during a meeting → the meeting hears nothing from the owner
  until the release. The owner's voice is still recorded.
- After the paste → the owner's clipboard holds what it held before. The
  dictated text is not in the clipboard history.
- Dictation goes ahead of all other transcription work on the host.

### When something fails

- The session service is down → Left Alt works as a plain Alt.
- The keys service is down → no dictation, and the tray shows Error.
- Muting the meeting fails → dictation still works, and the tray shows
  Warning.
- A crash during dictation → the meeting hears the owner again once the
  session service restarts.
- The inference host does not answer in 10 s → nothing is pasted, and a
  desktop notification says that dictation failed. Text that arrives later
  never touches the clipboard. The owner or an agent gets it with
  `odsodctl dictation last`, and it appears in the daily transcript.
- The paste fails (a modifier held past 1.5 s) → the text stays on the
  clipboard, and a desktop notification tells the owner to paste it by hand.

## Acceptance criteria

The paste wait (1.5 s) comes from ADR-0007. The owner set the 2 s text
target and the 10 s wait for the inference host. Other numbers are proposed
targets for the owner to confirm.

1. **AC-1** The tray shows Dictating at most 200 ms after the hold
   threshold. _Check: system test._
2. **AC-2** A phrase that starts with the key press loses no words. _Check:
   system test._
3. **AC-3** For an utterance of up to 15 s, the text appears at most 2 s
   after the release, with no other dictation in progress (target; bench
   confirms). _Check: bench._
4. **AC-4** AC-3 holds while ambient transcription has a backlog. _Check:
   system test._
5. **AC-5** Text pastes in a browser, in Obsidian and in Konsole, with the
   Swedish keyboard layout, including å, ä and ö in names. _Check: manual._
6. **AC-6** Word error rate on the owner's English dictations is at most 5%
   (target; bench confirms). _Check: bench._
7. **AC-7** A hold with no speech pastes nothing and leaves the clipboard
   as it was. Silence never gives phantom text. _Check: system test._
8. **AC-8** Dictated questions paste as the questions. _Check: system test._
9. **AC-9** Another key during dictation pastes nothing, and the app gets
   Alt and the key. _Check: system test._
10. **AC-10** In a Meet or Teams call, the other side hears nothing from the
    owner during dictation, and hears the owner again at most 1 s after the
    release. _Check: manual._
11. **AC-11** Ambient recording of the mic has no gap during dictation.
    _Check: system test._
12. **AC-12** At most 1 s after the paste, the clipboard holds its earlier
    content. The KDE clipboard history never shows dictated text. _Check:
    manual._
13. **AC-13** If the owner still holds a modifier after the release, the
    paste waits for it, up to 1.5 s. _Check: system test._
14. **AC-14** With the session service down, Left Alt taps and chords work
    as plain Alt. _Check: system test._
15. **AC-15** With the keys service down, the tray shows Error at most 10 s
    later. _Check: system test._
16. **AC-16** If muting the meeting fails, dictation still pastes and the
    tray shows Warning. _Check: system test._
17. **AC-17** After a crash during dictation, the meeting hears the owner
    again at most 10 s later. _Check: system test._
18. **AC-18** If no text arrives in 10 s, a desktop notification says that
    dictation failed. Text that arrives later is never pasted and never
    touches the clipboard. _Check: system test._
19. **AC-19** `odsodctl dictation last` prints the text of the newest
    dictation, also when it arrived late. _Check: system test._
20. **AC-20** If the paste fails, the text stays on the clipboard and a
    desktop notification says so at most 1 s later. _Check: system test._

## Boundaries

### Covered by other PRDs

- The hold threshold, Left Alt taps and chords, and Right Alt → the
  `keyboard` PRD.
- Dictated text in the daily transcript → the `live-transcript` PRD.
- Tray states in full → the `health-and-control` PRD.
- Recording of the owner's voice → the `ambient-recording` PRD.
- A test of other places to run dictation against today's design → the
  `benchmarking` PRD (owner decision, 2026-11-23):
  - a streaming speech model on the host's own CPU;
  - a cloud speech model on Google Cloud, paid by the owner's employer. If
    adopted, it uses the host's ambient Google Cloud credentials, and
    dictation falls back to the local path when they are missing or the
    cloud fails. Using it needs an ADR: it is an exception to "Local only"
    (ADR-0002).

### Not planned

- Dictation in Swedish. Dictation is English only; ambient
  recording covers both languages (owner decision, 2026-11-23).
- Text that appears while the owner still speaks, for now. Text comes on
  release (ADR-0002). Benchmark data on a streaming model can change this.
- Typing the text key by key. It breaks on the Swedish layout (ADR-0005).
- An overlay window. A window steals focus on Wayland (ADR-0005).

## Open questions

- None.
