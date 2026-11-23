# Plans

A plan holds the order of work for one unit. An ADR holds the design. A PRD
holds what the owner sees.

## Files

- One file per plan: `YYYY-MM-DD-<slug>.md`. The date is the day the plan
  was made.
- [`2026-11-23-roadmap.md`](2026-11-23-roadmap.md) orders the plans in
  phases and names their dependencies.

## Header

```markdown
# Plan: <title>

- Status: Draft | Active | Done YYYY-MM-DD | Dropped YYYY-MM-DD
- Depends on: <plan links, or none>
- Design: <ADR and PRD links>
```

## Sections

- **Goal:** what is true when the plan is done. One to three bullets.
- **Scope:** in and out. "Out" stops a worker from building the next
  obvious thing.
- **Steps:** the order of work. Pure core and its table tests first, then
  the I/O shell.
- **Done when:** exact commands that the orchestrator runs alone.
- **Progress log:** append-only, one line per event, newest last.
- **Decisions to confirm:** gaps the worker filled with the simplest
  reading. The owner confirms or changes each one.

## Rules

- A plan never holds design that its ADR lacks. A design change goes to
  the ADR first, and the plan links it.
- Link ADR and PRD sections. Do not copy them.
- One plan is one unit for one worker. The worker gets the plan path as
  its task.
- Guardrails for every plan, unless the plan says otherwise:
  - Tests and smoke runs use a temp root through `ODSOD_DAEMON_ROOT`.
  - No daemon units in the real `HOME`. Only the owner deploys.
  - No push, PR or merge. Local `jj` commits only.
  - Never stop or restart a service the plan does not own.
- Retention: delete a plan 60 days after it is Done or Dropped. Git
  history keeps it.
