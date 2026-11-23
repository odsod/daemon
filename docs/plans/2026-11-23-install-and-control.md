# Plan: install, version and the control commands

- Status: Draft
- Depends on: [python-scaffold](2026-11-23-python-scaffold.md),
  [capture](2026-11-23-capture.md) (pause and resume stop and start it);
  step 8 also needs [whisper-novad](2026-11-23-whisper-novad.md) and
  [inference-recordings](2026-11-23-inference-recordings.md)
- Design: [ADR-0006](../adr/0006-installation.md),
  [ADR-0004](../adr/0004-orchestration-with-systemd.md),
  [ADR-0018](../adr/0018-control.md),
  PRD [install-and-upgrade](../prd/install-and-upgrade.md),
  PRD [health-and-control](../prd/health-and-control.md)

## Goal

- `mise run deploy` installs the working copy as the live system, and
  `odsodctl install` is idempotent.
- `odsodctl status`, `pause`, `resume` and `notify-failed` work, and
  status is OK for a build that ships only capture and pipeline.
- A validated config for this host is ready for the owner to copy.

## Scope

- In: `install` (user scope, 7 steps), `version`, the unit templates of
  ADR-0004, `health`, `status`, `pause`, `resume`, `notify-failed`, and
  the ADR-0006 and ADR-0018 "Tests" for these components, both control
  system tests included.
- In: shipped services per ADR-0006 "Unit templates" and ADR-0018
  "Expected units". Add `capture` and `pipeline` to
  `install.contract.SERVICES`.
- Out: `install --system` ([keys](2026-11-23-keys.md) plan). The tray.
  The `machine` repo task `daemon:setup`. Tests that need keys, session
  or tray code.

## Steps

1. `version`: commit, `dev`, workspace path, `+dirty`.
2. `install` pure parts with tests: `source`, `render`, the compare in
   `apply` (ADR-0006 "`odsodctl install` (user scope)").
3. Unit templates in `components/install/units/` for every unit in the
   ADR-0004 table. Render, enable and restart only the units of
   `SERVICES`, plus the target, timers, login and notify units.
4. `apply` against a fake `systemctl` on `PATH`
   (`tests/bin/systemctl`, a script that logs its arguments). Temp `HOME`
   and temp `ODSOD_DAEMON_ROOT` for files.
5. `health` snapshot and `evaluate()` table (ADR-0018 "Snapshot and
   evaluation", "Backlog", "Audio freshness"). The backlog reads only the
   fields it needs with `json.loads`, no model per line. Table row: a
   build that ships capture and pipeline, graphical session active, no
   session, tray or keys unit → `running`, exit 0. A missing capture or
   pipeline unit → Error, exit 2.
6. `status` (`--json`, exit codes 0 to 3), `pause`, `resume` (`--by`),
   `notify-failed`, with fake `systemctl` and `notify-send`.
7. System tests on temp `HOME` and root with fake systemd:
   - a capture stub writes; pause stops it; status is Paused; resume
     starts it again;
   - install while `run/paused` exists never starts capture;
   - a failed apply at step 3 and partway through step 6 leaves
     `current` old; the rerun restarts all services;
   - install writes nothing under `config/` and no other `state/` file.
8. Data-day config: write `/tmp/agent-team/recorder-always-on/config.json`
   and copy it into Progress log. Full endpoint URLs under
   `common.inference`: `whisper_url`
   `http://127.0.0.1:8178/v1/audio/transcriptions`, `llama_url`
   `http://127.0.0.1:8179/v1/chat/completions`; `chunk_chars` from
   inference-recordings under `interactions`; other sections at their
   defaults. Check it:
   `t=$(mktemp -d); install -Dm600 <file> $t/config/config.json;
   ODSOD_DAEMON_ROOT=$t uv run odsodctl config check`. Install and deploy
   never write `config/` (ADR-0006).
9. Never run `mise run deploy`, or `odsodctl install` without the fake
   `systemctl` on `PATH`. Only the owner deploys.

## Done when

```sh
uv run pytest src/odsod_daemon/components/{install,version,health,status,pause,resume,notify_failed}
uv run pytest tests -k 'install or control'
h=$(mktemp -d); for i in 1 2; do HOME=$h XDG_CONFIG_HOME=$h/.config ODSOD_DAEMON_ROOT=$h/root \
  PATH="$PWD/tests/bin:$PATH" uv run odsodctl install; done   # second run: no write, no restart in the log
XDG_CONFIG_HOME=$h/.config systemd-analyze --user verify --recursive-errors=no \
  $h/.config/systemd/user/odsod-daemon-{capture,pipeline,login}.service $h/.config/systemd/user/*.timer
mise run build
```

## Progress log

- 2026-11-23: Step 1 complete. Version reads VCS metadata and the recorded
  dev deployment. Three component tests pass. Started with `jj new
  python-rewrite` and `uv sync --extra bench`.

- 2026-11-23: Step 2 complete. Added source parsing, template substitution,
  shipped-unit selection and file comparison. Four pure tests pass.

- 2026-11-23: Step 3 complete. Added all user unit templates, timers,
  target and D-Bus activation. Two render tests pass; only capture and
  pipeline service units render in this build.

- 2026-11-23: Step 4 complete. Seven-step user apply and CLI use a bounded
  systemctl wrapper. Four fake-systemctl tests cover idempotence, dev
  restarts, logged-out capture and retry after partial restart failure.

- 2026-11-23: Step 5 complete. Snapshot reads active-service faults, unit
  states, current/previous-hour audio sizes and install records. Pure
  evaluation and incremental backlog pass 17 tests, including partial
  builds, ten-day pending work, incomplete lines and day-window rollover.

## Decisions to confirm

- One-shot helpers use no automatic restart. `Restart=always` is invalid
  for `Type=oneshot`. The notify unit has no `OnFailure` to itself, which
  avoids recursive failure notifications.
- ADR-0006 supplies the detailed target membership and pipeline enable
  settings where ADR-0004 uses the broader `default.target` description.

- With audio but no coverage record, backlog starts at the oldest present
  current/previous-hour audio file. This exposes stalled segmentation
  before it has emitted its first coverage record.
