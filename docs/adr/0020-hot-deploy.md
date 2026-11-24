# ADR-0020: Hot deploy

## Status

Accepted. Amends step 6 of "Install steps" in
[ADR-0006](0006-installation.md).

## Date

2026-11-24

## Context

- The owner develops the daemon during the work day, while it records. Some
  meetings never end, so "deploy after the meeting" is no rule.
- ADR-0006 restarts all Python services on a new commit and on every dev
  deploy. Each capture restart leaves an audio gap
  (`ambient-recording` AC-4).
- Only capture records. The pipeline derives its pending work from files
  ([ADR-0003](0003-filesystem-interface.md)), and signals reloads the open
  meeting from its event stream ([ADR-0014](0014-signals.md)). A pipeline or
  tray restart loses no data.
- The CLI imports every component at start, so the import graph of a
  service is the whole package. The code a service runs is much smaller.

## Decision

- `install.contract.CAPTURE_ROOTS` names where capture's code starts:
  `components/capture/`, `services/capture.py` and `services/runner.py`.
  Install follows their `odsod_daemon` imports (static, with `ast`) to find
  the rest, such as the `lib/` modules capture uses.
- At install, `odsodctl install` hashes the installed package: `capture`
  over those files, `all` over every file. It skips `tests/`, `testdata/`
  and `__pycache__`, as the wheel does, so `src/` and the installed package
  hash the same. It writes both in `install/current` as `digests`.
- Step 6 restarts:
  - capture, when its digest or its unit file changed;
  - every other service, when the `all` digest or its unit file changed;
  - all services, when `current` has no digests (records from before this
    ADR).
- A new commit with no code change restarts nothing. A dev deploy follows
  the same rule; it no longer restarts all.
- The install prints which services restarted, and says so when capture
  restarted: "recording has a gap of about 2 s".
- Step 7 writes `current` also when only the digests changed, so a dirty
  dev deploy is recorded.

## Alternatives considered

- Restart nothing and let services reload code: Python cannot swap loaded
  modules safely.
- Runtime import graph of each service: the CLI imports all components,
  so every change would restart capture. The static graph from capture's
  own files is small.
- Diff commits with Git: Git installs have no workspace, and a dev deploy
  can be dirty. Digests of the installed files work for both.

## Consequences

- A change to cleanup, transcript, signals, interactions or the tray goes
  live with no audio gap.
- A capture process that a deploy skips keeps the old code of other
  components in memory. It never runs that code. After start it imports
  only the standard library, so it never loads the new files.
- A dependency change in `uv.lock` alone does not restart capture. Capture
  keeps the loaded versions until its next restart.
- A new or changed `lib/` module that capture does not import leaves
  capture running.
- An import that capture adds at runtime with `importlib` is not followed.
  Capture has none.
- After a pipeline restart, signals finds the speaking class again when
  people speak; a few seconds of speaking events can be lost.
