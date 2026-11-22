# ADR-0001: Record architecture decisions

## Status

Proposed

## Date

2026-11-23

## Context

- Agents write all code in this repo. The owner reviews designs and interfaces,
  not every line of code.
- Without a written reason, agents argue settled decisions again or undo them
  by accident.
- The system is built from decoupled components
  ([ADR-0002](0002-high-level-architecture.md)). That creates many decisions
  with real alternatives, and some of them rest on benchmark data.

## Decision

Record each significant decision as an Architecture Decision Record (ADR) in
`docs/adr/`.

### When to write an ADR

- A decision that is expensive to reverse.
- A change to a contract between components: a filesystem path, a file format,
  a queue, a process boundary.
- A choice of runtime, dependency, model or external service.
- A plausible alternative that we reject on purpose.

Do not write an ADR for implementation details inside one component.

### Keep ADRs strategic

- Record the decision, the forces behind it and the trade-offs.
- Do not describe the current code or the current setup. That goes out of
  date, and the code is the record of it.
- Prefer lasting facts over details that change often (versions, hardware,
  flags). Name a detail only when it is part of a contract.

### Format

- File: `docs/adr/NNNN-<slug>.md`, four-digit sequence, lowercase slug.
- One decision per ADR. At most about one page.
- Write in ASD-STE100 Simplified Technical English: short sentences, active
  voice, plain verbs. Bullets over prose. No em dashes.
- Record the evidence: benchmark numbers, measurements, links.
- Use this template:

```markdown
# ADR-NNNN: <Title>

## Status

Proposed | Accepted | Superseded by ADR-NNNN | Deprecated

## Date

YYYY-MM-DD

## Context

<Forces, constraints, evidence.>

## Decision

<What we do.>

## Alternatives considered

### <Alternative>

- <Why we rejected it.>

## Consequences

- <What gets easier, what gets harder, what is still open.>
```

### Lifecycle

```
Proposed → Accepted → Superseded | Deprecated
```

- **Proposed:** open for discussion. Edit it freely. An ADR can stay Proposed
  to hold an open question.
- **Accepted:** the owner approved it. After that, change only the Status line.
- **Superseded:** a new ADR replaces it. Set `Superseded by ADR-NNNN` in the old
  one and link back from the new one. Never delete an ADR.

### Hierarchy

- [ADR-0002](0002-high-level-architecture.md) defines the high-level
  architecture.
- Component ADRs refine ADR-0002 and link to it. A component ADR that
  contradicts ADR-0002 must supersede it first.

### Rules for agents

- Before you change a component, read the Accepted ADRs for it.
- A change that contradicts an Accepted ADR needs a new ADR first. Propose the
  ADR and stop for the owner's approval.
- Change the ADR and the code that implements it in the same commit.

## Alternatives considered

### No design docs, code only

- The code shows what the system does, not why, and not what we rejected.
- The owner would have to read code to understand interfaces.

### One living architecture document

- It shows the current state, but it loses the reasons and rejected options
  each time someone edits it.
- We can add one later as an index if the ADR set grows hard to follow.

### Adopt a generic documentation skill as-is

- `addyosmani/agent-skills/documentation-and-adrs` has a good ADR template.
  Most of the skill (README, changelog and comment advice) does not apply here.
- We take its template and lifecycle only.

## Consequences

- The current architecture is the set of Accepted ADRs that are not superseded.
- Every interface change costs a short ADR. That is the point: the owner sees
  each contract change.
- Open questions get a home as Proposed ADRs, so design work does not block on
  them.
