# PRD: Interactions and publishing

- Status: Accepted
- Updated: 2026-11-23
- Design: [ADR-0002](../adr/0002-high-level-architecture.md),
  [ADR-0003](../adr/0003-filesystem-interface.md),
  [ADR-0005](../adr/0005-components-and-implementation.md)

## Problem

- A day of transcript is too long to read again. The owner needs each
  meeting or talk as its own short record: who took part, who said what,
  and what came out of it.
- The owner's second brain lives in the vault. Records must arrive there
  with no action, and the owner must be free to move, edit or delete them.
- Long calls hold many topics, such as a permanent call that stays open all
  day. Each topic needs its own record.
- Records come from several hosts, and two hosts can record the same talk.
  The vault will be version controlled. An ingest agent with a strong model
  takes each record from the inbox, finds duplicates from other hosts and
  merges them. Records must not clash, and must give that agent what it
  needs to match them.

## Behavior

- An interaction ends when no one speaks for 5 min, the meeting changes, or
  the owner pins → it becomes one document.
- Each document has a title, the time range, the participants, and the
  transcript with a speaker name on each line.
- Each document has a summary in English, also for Swedish talks (owner
  decision, 2026-11-23). The
  transcript stays in the language spoken. The summary has:
  - an overview of 1 to 3 sentences;
  - labeled points: decisions, insights, problems, context and next steps.
    A next step names its owner when the transcript names one. Labels with
    nothing to say are left out;
  - for interactions longer than 30 min, chapters with start times.
- The summary holds only what the transcript says. If the model is unsure,
  it leaves the point out.
- An interaction with only greetings or noise → no document.
- A meeting profile sets its own silence cutoff. Example: the permanent call
  gets a short cutoff, so each topic becomes its own document.
- A talk outside a meeting, such as at the desk → a document too. Voices
  are told apart, but nothing gives their names, so they are "Speaker 1",
  "Speaker 2" and so on. The same holds for a voice in a meeting that the
  meeting does not name.
- Notes the owner or an agent added during the interaction → in the
  transcript at their time, marked as notes. The summary uses them: they are
  the owner's own context.
- Quality comes before speed: the batch pass uses the best model and the
  full context, even if the document comes hours later (owner decision,
  2026-11-23). The live transcript covers the need for text now.
- The document is finished → it is copied to each configured target, such as
  the vault inbox. The daemon never changes or reads the copy afterwards.
- The ingest agent moves or deletes a copy from the inbox → the daemon never
  writes it again.
- Each document states, in a form an agent reads without guessing: the host
  that recorded it, the exact start and end time with the time zone, the
  meeting (platform and meeting code) if any, and the participants. Two
  hosts that record the same talk give documents that these fields match.
- On battery → documents wait, and are made once the host is on mains power.

### When something fails

- The inference host or the language model is down → documents wait, and
  are made when it returns. The live transcript is not affected.
- A target directory is missing or full → the document waits and is copied
  later. The tray shows Warning.
- A crash during the batch pass → the interaction is done again from the
  start. No document is lost or doubled.

## Acceptance criteria

The 5 min cutoff comes from ADR-0005. The summary labels, title length and
greeting rule come from the old recorder's config. The overview, the owners
of next steps, chapters and English summaries follow the studied tools
([alternatives](../research/alternatives.md)): Meetily, YazSes and Voxtype.
Other numbers are proposed targets for the owner to confirm.

1. **AC-1** The document is in the targets at most 24 h after the
   interaction ends, if the host had mains power and an idle inference host
   for at least 1 h in that time. _Check: system test._
2. **AC-2** 5 min of silence, a meeting change or a pin ends an interaction.
   A meeting profile cutoff wins over the default. _Check: system test._
3. **AC-3** Each document has a title of at most 8 words, the start and end
   time, the participants, the transcript with notes inline, and a summary.
   Unnamed voices are "Speaker 1", "Speaker 2" and so on, the same in the
   whole document. _Check: system test._
4. **AC-4** In Meet and Teams, at least 90% of the speech time has the
   right speaker name (target; bench confirms). _Check: bench._
5. **AC-5** The summary is in English. It starts with an overview of at most
   3 sentences, then uses only the labels Decided, Insight, Problem, Context
   and Next. _Check: system test._
6. **AC-6** An interaction of at most 3 lines of greetings or noise gives
   no document. _Check: system test._
7. **AC-7** Each document reaches each target exactly once. The daemon
   never changes, reads or deletes a copy in a target. _Check: system test._
8. **AC-8** Documents from two hosts in one synced target have different
   names. _Check: system test._
9. **AC-9** On battery, no document is made. On mains power, waiting
   documents start at most 5 min later. _Check: system test._
10. **AC-10** After a crash in the batch pass, each interaction has exactly
    one document. _Check: system test._
11. **AC-11** A missing target shows Warning at most 1 min later. The
    document reaches it at most 5 min after it returns. _Check: system
    test._
12. **AC-12** At least 95% of summary points trace to a line in the
    transcript (target; bench confirms). _Check: bench._
13. **AC-13** The summary has at least 80% of the decisions and next steps
    in a reference summary that the owner wrote (target; bench confirms).
    A next step has an owner when the transcript names one. _Check: bench._
14. **AC-14** An interaction longer than 30 min has chapters. Each chapter
    start time matches a transcript line. _Check: system test._
15. **AC-15** A copy that is moved or deleted from a target is never written
    again, also after a restart. _Check: system test._
16. **AC-16** Each document holds the host, the start and end time with the
    time zone, the meeting platform and code (if any), and the participants,
    as fields that an agent reads without parsing prose. _Check: system
    test._
17. **AC-17** One meeting recorded on two hosts gives two documents with the
    same meeting code and overlapping time ranges. _Check: manual._

## Boundaries

### Covered by other PRDs

- The live transcript and its daily copy to targets → the `live-transcript`
  PRD.
- Pins and notes → the `live-transcript` PRD.
- Speaker accuracy and summary quality measured over time, per model and
  prompt → the `benchmarking` PRD.

### Not planned

- Sync between hosts or to the cloud. A target is a directory; what syncs it
  is outside the daemon (ADR-0003).
- Merging duplicates across hosts. Each host delivers its own document; the
  vault's ingest agent merges them (owner decision, 2026-11-23).
- Version control of targets. The daemon writes files; the vault's tools
  commit them.
- Edits that flow back from the vault. The daemon never reads a target
  (ADR-0003).
- Speaker names by voice alone, with no meeting to name them, for now. A
  later feature can name voices from enrolled voice samples, as YazSes does
  ([research](../research/yazses.md)).

## Open questions

- None.
