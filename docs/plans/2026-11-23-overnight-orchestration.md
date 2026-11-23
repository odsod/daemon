# Plan: overnight orchestration

- Status: Done 2026-11-23
- Depends on: [roadmap](2026-11-23-roadmap.md)
- Design: none (process plan)

## Goal

- The plans in `docs/plans/` (local commit `knypkxzk`) say what to build
  tonight and in what order. This plan says how a team runs them with no
  human: who does which plan, how work merges, how it is checked, and what
  happens when something fails.
- Outcome by morning: the deploy gate plans are Done, as many should and
  stretch plans as time allows, the rehearsal passed, and the morning
  report is in the roadmap's Progress log.
- Everything stays local. No push, no PR.

## Step 0: check this plan in

- Copy this plan to `docs/plans/2026-11-23-overnight-orchestration.md`
  (plan format of `docs/plans/README.md`) and link it from the roadmap.
  Commit it as a new change on top of `knypkxzk`
  (`docs(plans): add overnight orchestration plan`), so the reviewed
  commit stays as it is.

## Team (space `recorder/always-on`, team `recorder-always-on`)

New brief over the closed one: `/tmp/agent-team/recorder-always-on/brief.md`.

| Role         | Kind / model             | Unit                                                                                                            | Why delegate                          |
| ------------ | ------------------------ | --------------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| orchestrator | t38, claude / Opus 5.5   | Schedule, hand out plans, integrate, run every Done when, review gate, whisper-novad, rehearsal, morning report | Holds the plans and ADRs              |
| impl-a       | pi / DeepSeek V4.1 Flash | Lane A: python-scaffold → capture → install-and-control → keys → tray → publishing                              | Grind                                 |
| impl-b       | pi / DeepSeek V4.1 Flash | Lane B: audio-fixtures (steps 2 to 5) → inference-recordings → speech → transcript → dictation                  | Grind, parallel                       |
| impl-c       | pi / DeepSeek V4.1 Flash | Lane C, starts when scaffold is Done: signals → bench → interactions                                            | Live-only signals early               |
| research     | agy / Gemini 4 Hydrogen  | audio-fixtures step 1 report, then closed                                                                       | Web research                          |
| review       | agy / Gemini 4 Neon      | Isolated review of each finished plan's diff against its plan, ADR and PRD ACs                                  | Different frame; keeps diffs out here |

- pi workers and research are vacuum workers: one plan path, one
  workspace, a stop. They never see the brief. review is primed.
- Fallback: a pi worker that is stuck after one resend, or fails a plan
  twice, hands that plan to codex (Sol 6.1) in the same workspace.
- Tabs: `impl` (three pi workers), `research`, `review`.

## Workspaces and integration

- Each pi worker has its own jj workspace:
  `~/Workspaces/github.com/odsod/recorder/impl-{a,b,c}`
  (`jj workspace add <path> -r <tip>`).
- Local bookmark `python-rewrite` in this workspace is the integrated tip.
  It starts at the orchestration-plan commit on top of `knypkxzk`.
- Each plan starts with `jj new python-rewrite` in the worker's workspace,
  so it builds on everything accepted so far.
- Accept a plan: rebase its commits onto `python-rewrite`
  (`jj rebase -s <first> -o python-rewrite`), resolve conflicts (expected
  only in the shared one-line lists), move the bookmark, run the plan's
  Done when and `mise run build` on the tip. Then mark the plan
  `Status: Done <date>`.
- Workers append to their plan's Progress log and Decisions to confirm.
  Only the orchestrator changes `Status`.

## Schedule

| Wave | impl-a              | impl-b                                  | impl-c                                    | orchestrator / others                            |
| ---- | ------------------- | --------------------------------------- | ----------------------------------------- | ------------------------------------------------ |
| 0    | python-scaffold     | waits for research                      | (not started)                             | whisper-novad; research: fixtures report         |
| 1    | capture             | audio-fixtures 2 to 5                   | signals                                   | review scaffold                                  |
| 2    | install-and-control | inference-recordings, then speech       | bench (after speech) or interactions prep | review each Done plan                            |
| 3    | keys                | transcript                              | bench                                     | integrate                                        |
| 4    | tray                | dictation (needs keys, speech, install) | interactions                              | integrate                                        |
| 5    | publishing          | (free: help with a Blocked plan)        |                                           | last steps: Done whens, wheel, rehearsal, report |

- A lane takes its next plan only when that plan's dependencies are
  integrated. If not, it takes the next ready plan in roadmap order.
- impl-c starts bench only after speech is integrated; until then it does
  signals and the pure parts of interactions.

## Per-plan loop (orchestrator)

1. Hand out: `hc send <t> "Implement docs/plans/<plan>.md in
   <workspace>. First run: jj new python-rewrite. Read docs/plans/README.md,
   the plan and every ADR section it links. Pure core and tests first.
   Commit with jj -m (Conventional Commits). Append to the plan's Progress
   log. Stop when its Done when passes, or after 2 failed attempts at the
   same step, and write why in Progress log."`
2. Wait: `hc wait` in the background with a timebox per plan (scaffold,
   speech, keys: 2.5 h; others: 1.5 h). Read the screen if it returns
   early.
3. Check: run the plan's Done when in the worker's workspace. Read the
   diff stat. Reject a diff that touches files outside the plan's scope.
4. Review: send review the plan path and the revset. It writes
   `review-<plan>.md` (blocker, fix, or ok). Deploy gate, speech, keys and
   dictation always get a review; the rest get one if time allows.
5. Fix cycles: at most two (worker fixes the review's blockers). Then mark
   the plan Blocked, keep its commits out of `python-rewrite`, and move on.
6. Integrate (above). Append a Handoff line.

## Context and time

- The orchestrator's state lives in the brief Handoff and the plans'
  Progress logs, so a `/compact` loses nothing. Compact between waves.
- Reset each pi worker (`/new`) between plans, and review (`/clear`)
  between reviews.
- Overrun: a plan past 2× its timebox is Blocked. Deploy gate plans get
  the codex fallback before Blocked.
- Stop new plans at 05:30. Then do the last steps.

## Guardrails (in every worker prompt and in the brief)

- No push, PR or merge, in either repo.
- Never run `mise run deploy`, `odsodctl install` without the fake
  `systemctl` on `PATH`, or `install --system`. Never touch
  `/dev/input`, `/dev/uinput`, `odsod-keys.service`, `llama-server`.
- Only the orchestrator changes the live host: whisper-novad (once) and
  the transient rehearsal units.
- Smoke runs use a temp `ODSOD_DAEMON_ROOT` and delete it after.
- Never run code from the `machine` repo's keys source or from downloads.

## Last steps (orchestrator)

1. Run every Done plan's Done when on `python-rewrite`.
2. Wheel check and the rehearsal under real systemd, per the roadmap.
3. Morning report in the roadmap's Progress log: Done and Blocked plans,
   the `python-rewrite` change ID, rehearsal result, all Decisions to
   confirm, and whether the dictation trial is possible.
4. Clean up: `hc kill` and `hc rm` every worker, close tabs, check each
   workspace's commits are in `python-rewrite` (or Blocked and named in
   the report), `jj workspace forget` and remove the workspace dirs,
   delete temp roots. Append `orchestrator: team closed`.
5. Leave the working copy here on `python-rewrite` so `mise run deploy`
   runs from it.

## Done when

- `jj log -r python-rewrite` shows the deploy gate plans integrated, and
  `mise run build` passes on it.
- Each Done plan's Done when passes on `python-rewrite`.
- The rehearsal gives `active` and `NRestarts=0` for capture and pipeline.
- `/tmp/agent-team/recorder-always-on/config.json` passes
  `odsodctl config check`.
- The morning report exists; `hc ls` shows no `recorder-always-on-`
  terminals; `jj workspace list` shows only this workspace.

## Progress log

## Decisions to confirm
