# PRD: Interactions

- Status: Accepted
- Updated: 2026-11-25
- Design: [ADR-0002](../adr/0002-high-level-architecture.md),
  [ADR-0003](../adr/0003-filesystem-interface.md),
  [ADR-0005](../adr/0005-components-and-implementation.md),
  [ADR-0016](../adr/0016-interactions.md)

## Problem

- A day of transcript is too long to read again. The owner needs each
  meeting or talk as its own record: who took part and who said what. The
  vault's ingest agent turns that record into what came out of it.
- Long calls hold many topics, such as a permanent call that stays open all
  day. Each topic needs its own record.
- Two hosts can record the same talk. The vault's ingest agent merges such
  records, so each record must give that agent what it needs to match them.

## Behavior

- An interaction ends when no one speaks for 5 min, the meeting changes, or
  the owner pins → it becomes one document.
- Each document has the time range, the participants, and the transcript
  with a speaker name on each line.
- Title (owner decision, 2026-11-25):
  - in a meeting, the title and the heading are the calendar meeting
    title;
  - outside a meeting, the document has no title, and the heading is
    "Interaction" and the local start time, such as "Interaction 15:00".
- File name: the local start day and time, the host, and the meeting title
  in short form, such as `2026-11-22-1500-work-laptop-weekly-sync.md`.
  With no meeting title, or a title of only emoji, the name ends at the
  host. A second document with the same name gets `-2`.
- Speaker names (owner decision, 2026-11-23):
  - the owner's lines are the owner;
  - in a meeting, the other lines get names from the meeting's own
    speaking indicator, on Meet first, then Teams;
  - a voice with no name, outside a meeting or not named by the meeting,
    is "Others".
- A missing or wrong name never stops a document.
- The document has no summary (owner decision, 2026-11-25). The vault's
  ingest agent reads every document and writes its own title and summary.
  The transcript stays in the language spoken.
- Dictations are not part of the interaction. They never appear in a
  document.
- An interaction with at most 3 speech lines and no note → no document.
  All other interactions → a document.
- A meeting profile sets its own silence cutoff, and nothing else. Example:
  the permanent call gets a short cutoff, so each topic becomes its own
  document.
- Notes the owner or an agent added during the interaction → in the
  transcript at their time, marked as notes. They are the owner's own
  context for the ingest agent.
- A document is made once the interaction ends and all its speech has
  text. It needs no language model.
- Each document states, in a form an agent reads without guessing: the host
  that recorded it, the exact start and end time with the time zone, the
  meeting (platform and meeting code) if any, and the participants. Two
  hosts that record the same talk give documents that these fields match.
- A document is finished → `publishing` delivers it.
- On battery → documents wait only while the live transcript waits.

### When something fails

- The inference host is down → speech waits, so documents wait too. They
  are made when the speech of the interaction has text.
- Documents wait more than 24 h → the tray shows Warning.
- A crash during the batch pass → the interaction is done again from the
  start. No document is lost or doubled.

## Acceptance criteria

The 5 min cutoff comes from ADR-0005. Other numbers are targets.

1. **AC-1** The document is finished at most 24 h after the interaction
   ends, if all speech of the host had text for at least 1 h in that time.
   _Check: system test._
2. **AC-2** 5 min of silence, a meeting change or a pin ends an interaction.
   A meeting profile cutoff wins over the default. _Check: system test._
3. **AC-3** Each document has the start and end time, the participants and
   the transcript with notes inline. Each line names the owner, a meeting
   participant, or "Others". _Check: system test._
4. **AC-4** In Meet and Teams, at least 90% of the speech time has the
   right speaker name (target; bench confirms). This is a bench target, not
   a ship gate. _Check: bench._
5. **AC-5** Removed: the daemon writes no summary; the vault's ingest agent
   does (owner decision, 2026-11-25).
6. **AC-6** Removed: no model judges greetings or noise. AC-17 replaces it
   with a fixed rule (owner decision, 2026-11-25).
7. **AC-7** Removed: documents need no language model, so battery does not
   hold them back. They wait only for speech (owner decision, 2026-11-25).
8. **AC-8** After a crash in the batch pass, each interaction has exactly
   one document. _Check: system test._
9. **AC-9** Removed: no daemon summary to trace (owner decision,
   2026-11-25).
10. **AC-10** Removed: no daemon summary to compare with a reference
    (owner decision, 2026-11-25).
11. **AC-11** No dictation text appears in a document. _Check: system
    test._
12. **AC-12** A document that waits more than 24 h shows Warning. _Check:
    system test._
13. **AC-13** Each document holds the host, the start and end time with the
    time zone, the meeting platform and code (if any), and the participants,
    as fields that an agent reads without parsing prose. _Check: system
    test._
14. **AC-14** One meeting recorded on two hosts gives two documents with the
    same meeting code and overlapping time ranges. _Check: manual._
15. **AC-15** Each speech line names its utterance, so the owner can play it
    again (`ambient-recording` AC-21). A line that cleanup changed also
    holds what speech recognition heard, so an agent can find misheard
    terms. Both are hidden when the document is rendered. _Check: system
    test._
16. **AC-16** In a meeting, the title, the heading and the end of the file
    name come from the meeting title. Outside a meeting, the title is
    empty, the heading is "Interaction HH:MM" and the file name ends at the
    host. A title with no letter or digit left counts as none. A taken name
    gets `-2`. _Check: system test._
17. **AC-17** An interaction with at most 3 speech lines and no note gives
    no document. One note or 4 speech lines give a document. _Check:
    system test._

## Boundaries

### Covered by other PRDs

- Delivery of documents to targets → the `publishing` PRD.
- Pins and notes → the `live-transcript` PRD.
- Speaker accuracy measured over time → the `benchmarking` PRD.

### Not planned

- Merging duplicates across hosts. Each host makes its own document; the
  vault's ingest agent merges them (owner decision, 2026-11-23).
- Telling voices apart with no meeting to name them, for now (owner
  decision, 2026-11-23). A later feature can add speaker diarization per
  host, where bench data shows the host keeps up, and then names from
  enrolled voice samples, as YazSes does
  ([research](../research/yazses.md)).
- A summary, a title outside a meeting, or chapters in the document. The
  vault's ingest agent writes them (owner decision, 2026-11-25).
- Meeting profile settings other than the silence cutoff.

## Open questions

- None.
