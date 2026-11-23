---
name: prd
description: "Write or update a PRD in docs/prd/: the owner-facing behavior of one odsod-daemon capability, with measurable acceptance criteria. Use when the user asks for a PRD, a feature spec, user-facing behavior or acceptance criteria, or when a change alters what the owner sees or does. Not for software design: that goes in an ADR (docs/adr/)."
---

# PRD

A PRD says what the owner experiences and why. An ADR says how the software
does it and why that design. Keep them apart.

|            | PRD                                         | ADR                                        |
| ---------- | ------------------------------------------- | ------------------------------------------ |
| Answers    | What does the owner do, see and get? Why?   | How is it built? Why this design?          |
| Lifetime   | Living: edit in place when behavior changes | Fixed: superseded by a new ADR, not edited |
| Path       | `docs/prd/<capability>.md`                  | `docs/adr/NNNN-<slug>.md`                  |
| Checked by | Acceptance criteria, as tests               | Code review, import rules                  |

**The test:** can the owner observe it without reading code or state files?
Yes: PRD. No: ADR. The owner sees documents in a target dir, so their content
is PRD. Their exact file format is a contract, so it is ADR.

## Scope

- One PRD per capability in the "Capabilities" table of
  [ADR-0002](../../../docs/adr/0002-high-level-architecture.md). Two small
  capabilities can share one PRD. Say so in its title.
- File name: the capability in lowercase kebab case, such as
  `dictation.md`. No number: a PRD is the living description of one
  capability, and its name is its stable key. ADRs are numbered because they
  are an ordered, append-only log.
- Use the terms of ADR-0002 and
  [ADR-0009](../../../docs/adr/0009-taxonomy-and-code-organization.md):
  owner, daemon, service, command, utterance, interaction.

## Process

1. Read ADR-0002, the ADRs that touch the capability, and the existing PRDs.
2. Draft from the conversation and the ADRs. Do not interview the owner
   first.
3. Put each gap in "Open questions". Ask the owner only the questions that
   block an acceptance criterion.
4. The owner reviews. Status goes from `Draft` to `Accepted` when no open
   questions are left.
5. A change in behavior edits the PRD in the same commit as the code and the
   tests.

## Template

```markdown
# PRD: <Capability>

- Status: Draft | Accepted
- Updated: YYYY-MM-DD
- Design: [ADR-NNNN](../adr/NNNN-<slug>.md), …

## Problem

- 2 to 4 bullets: what the owner needs, and why it matters to them.

## Behavior

- <Trigger> → <what the owner sees, hears or gets>.
- …

### When something fails

- <Failure> → <what the owner sees, and what still works>.

## Acceptance criteria

1. **AC-1** <Observable, measurable statement>. _Check: system test |
   manual | bench._
2. …

## Boundaries

### Covered by other PRDs

- <Topic a reader might expect here> → the `<capability>` PRD.

### Not planned

- <What the whole product will not do>. <The ADR or owner decision behind
  it.>

## Open questions

- <Question>. Blocks AC-n (or a boundary item).
```

## Rules

- **Stay grounded.** Each statement must trace to an ADR, the owner's words or
  measured data. Check it against the decided design: for example, a benefit
  of kept audio holds only for the retention period. Put anything unknown in
  "Open questions", never in a confident sentence.
- **The problem is the owner's need, not a tool.** Describe it at the level
  of the owner's work and life: to remember, to focus, to give AI agents
  context. Never describe the current implementation, an old tool or a
  workaround. Those change; the need does not.
- **Short.** About 120 lines. A longer PRD covers two capabilities: split
  it.
- **Behavior lines are cause and effect:** a trigger, then an observable
  result. Cover timing, feedback and failure. Failure behavior is required:
  the owner must know what they see when a service, the inference host or a
  device is down.
- **Acceptance criteria are measurable.** Each one has a number with a unit
  or a yes/no check, and says how it is checked.
  - Banned words: fast, quickly, seamless, intuitive, reliable, robust,
    user-friendly, should, appropriate.
  - A number that needs data: write the target and add "(target; bench
    confirms)".
  - Say which numbers are proposals. A number is grounded only if it comes
    from an ADR, the owner, or a calculation shown in the PRD.
  - IDs are stable. Never renumber. A dropped criterion stays as
    `**AC-n** Removed: <reason>.`
  - Tests name the criterion they check, such as `test_dictation_ac3_...`
    or a docstring `PRD dictation AC-3`.
- **No design.** No file paths, code, libraries, protocols, file formats or
  component internals. Link the ADR instead. Name a service, a command or a
  unit only where the owner sees it (tray, `odsodctl`, `systemctl`).
- **Boundaries are required, in two kinds.** They stop agents from building
  the obvious next feature.
  - "Covered by other PRDs": the topic belongs to the product, in another
    PRD.
  - "Not planned": the whole product will not do it. Each item names the ADR
    or the owner decision behind it. An undecided item is an open question.
- **Style:** ASD-STE100 Simplified Technical English. Short sentences, active
  voice, plain verbs. Bullets over prose. No em dashes.

## Done when

- Every template heading is present, and "Open questions" is empty or each
  question names the criterion or boundary item it blocks.
- Every criterion has an ID, a measure and a check method.
- No sentence describes design. Each design reference is an ADR link.
