# Plan: Python scaffold and runtime

- Status: Draft
- Depends on: none
- Design: [ADR-0009](../adr/0009-taxonomy-and-code-organization.md)
  (Rules, Toolchain layers, Python project conventions),
  [ADR-0010](../adr/0010-contracts-and-runtime.md) (Seam fields, Config,
  `lib/` mechanisms, Time in tests, Services, Command surface, Import
  rules, Test fixtures)

## Goal

- The repo is a uv package `odsod_daemon` on Python 3.14, and
  `mise run build` is the Python gate.
- `lib/` gives every mechanism in the ADR-0010 table, with fakes.
- The shared files that later plans would all edit exist in their final
  shape, so parallel plans do not collide.

## Scope

- In: `pyproject.toml`, `.python-version`, `uv.lock`, `mise.toml`, the Go
  code to `legacy/`, `src/odsod_daemon/{cli.py,lib/,services/,components/}`,
  `tests/test_architecture.py`, import-linter contracts, root
  `conftest.py`.
- In: a folder with `__init__.py` (`SUBSYSTEM`) and `contract.py` for
  every component in the ADR-0009 table. Each `contract.py` holds the
  models of what that component writes, from ADR-0010 "Seam fields" and
  the writer's ADR "Writes". A reader plan imports these, even when the
  writer is not built yet.
- Out: component behavior. The recorded inference pairs
  ([inference-recordings](2026-11-23-inference-recordings.md)); this plan
  builds the fake server that replays them.

## Steps

1. Wheel check (spike S0): `uv init --package`, Python 3.14.
   - `[project.dependencies]`: numpy, onnxruntime, httpx, pydantic, typer,
     jinja2, watchfiles, websockets, dbus-fast, PySide6.
   - `[project.optional-dependencies] bench`: jiwer.
   - `[dependency-groups] dev`: pytest, looptime, ruff, pyright,
     import-linter.
   - `uv sync --extra bench` must pass. A missing 3.14 wheel for numpy,
     onnxruntime, httpx, pydantic, typer, jinja2, watchfiles or dbus-fast
     stops the plan. For PySide6 or websockets: leave it out, write it in
     Progress log and Decisions to confirm, and go on.
2. Move the Go code to `legacy/` with plain `mv` (jj tracks it):
   `main.go`, `*.go`, `internal/`, `go.mod`, `go.sum`,
   `config.example.json`. Delete `.golangci.yml` and `.goreleaser.yml` if
   present. Replace the Go content of the root `AGENTS.md`, `CLAUDE.md`
   and `GEMINI.md` with a short pointer to ADR-0009 and `docs/plans/`.
3. `mise.toml`: tool `uv` (and `gcc` if the keys compile needs it).
   Tasks: `build` (ruff check, ruff format check, pyright, import-linter,
   `pytest -m 'not timing'`), `test`, `test:timing` (`pytest -m timing`),
   `lint`, and `deploy` and `deploy:system` from
   [ADR-0006](../adr/0006-installation.md) "The repo has a dev deploy".
   This plan is the only one that writes `mise.toml` tonight. Drop the Go
   tasks and tools.
4. `lib/` in this order, each with table tests on the virtual-time loop:
   `paths`, `clock`, `documents`, `streams`, `config`, `healthfile`,
   `pending`, `audio`, `textmatch`, `power`, `cli`, `systemd` (with fake),
   `inference` (clients, URL check, `reachable`, `is_loopback`, replaying
   fake on `127.0.0.1:0`).
   - `power` table (ADR-0010): no supplies → True; `wacom_battery_1`
     (Battery, Device, Discharging) → True; `BAT0` (Battery, System,
     Discharging) → False; `BAT0` Discharging and `AC` online → True.
5. `streams.follow` timing test, marked `timing`. Run
   `mise run test:timing` and write p50 and p95 in Progress log.
6. Service runner in `services/`: starts the components of a service in
   one `asyncio.TaskGroup`, sends `READY=1` through `lib.systemd` when all
   have started, and sends `WATCHDOG=1` every `WATCHDOG_USEC / 2` from a
   task in the main loop. Test: a datagram socket as `NOTIFY_SOCKET` in
   the temp root gets `READY=1`, then pings. No `NOTIFY_SOCKET` → no
   error.
7. Shared lists, written once here:
   - `services/capture.py`, `services/pipeline.py`, `services/session.py`,
     `services/tray.py`: each lists all its components from ADR-0010
     "Services", one per line, each line commented out. A component plan
     enables only its own line.
   - Root `cli.py`: mounts `run` and `config check`, and lists the
     `cli.py` app of every component in the ADR-0010 "Command surface",
     one per line, commented out. A component plan enables its own line.
   - `components/install/contract.py`: `SERVICES`, empty. A plan that
     makes a service work adds its name (ADR-0006 "Unit templates").
8. Root `conftest.py` with the ADR-0010 "Test fixtures": temp root,
   virtual-time loop, fake inference servers, fake systemd.
9. Architecture test and import-linter per ADR-0010 "Import rules".

## Done when

```sh
uv sync --extra bench && mise run build
uv run pytest src/odsod_daemon/lib
mise run test:timing
uv run odsodctl --help
t=$(mktemp -d); mkdir -p $t/config && echo '{"common":{"inference":{"whisper_url":"http://127.0.0.1:8178/v1/audio/transcriptions","llama_url":"http://127.0.0.1:8179/v1/chat/completions"}}}' > $t/config/config.json
ODSOD_DAEMON_ROOT=$t uv run odsodctl config check   # exit 0
```

## Progress log

- 2026-11-23: Step 1 wheel check: `uv sync --extra bench` passes on
  CPython 3.14.10. Every listed wheel exists, PySide6 and websockets
  included, so nothing is left out.
- 2026-11-23: Step 2: Go code moved to `legacy/` with `mv`. Deleted
  `.golangci.yml`, `.goreleaser.yml` and the goreleaser release workflow.
  Root `AGENTS.md` replaced with a short pointer; `CLAUDE.md` and
  `GEMINI.md` are symlinks to it.
- 2026-11-23: Steps 3 to 9: `pyproject.toml`, `.python-version`,
  `uv.lock`, `mise.toml`, all 24 component folders with `SUBSYSTEM` and
  `contract.py`, the 12 `lib/` mechanisms with tests, the service runner,
  the four service files, the root `cli.py`, `conftest.py`, the
  architecture test and the import-linter contract.
- 2026-11-23: Step 5 timing: `streams.follow` p50 21.1 ms, p95 21.9 ms
  over 1,000 appends (`mise run test:timing`).
- 2026-11-23: Done when passes: `uv sync --extra bench`; `mise run build`
  (117 passed, 1 deselected); `uv run pytest src/odsod_daemon/lib`
  (104 passed); `mise run test:timing` (1 passed); `uv run odsodctl
  --help`; `odsodctl config check` on a temp root exits 0.

## Decisions to confirm

- `pytest-asyncio` joined the dev group. `looptime` needs it to run async
  tests; ADR-0010 names only `looptime`.
- ruff excludes `docs/` and `legacy/`. The research notes hold Python code
  blocks and the diagram scripts predate the gate; formatting them would
  change review documents outside this plan.
- Deleted `.github/workflows/release.yaml` together with `.goreleaser.yml`.
  It called the removed `mise run release`, so it was an orphan.
- Component run convention: `__init__.py` may export `CONFIG_MODEL` and
  exports `run(config, *, once=False)`. The root `run` command loads
  `config.section(SUBSYSTEM, CONFIG_MODEL)` and passes `once`.
- `config check` finds section models by importing every component and
  reading its `CONFIG_MODEL`. A section with no model is not checked. This
  avoids another shared list for component plans to edit.
- The inference fake reads one recorded pair per JSON file in
  `lib/inference/testdata/{whisper,llama}/`, with `request` and `response`
  keys and an optional `delay_ms`. The recordings plan must write that
  shape.
- No `gcc` mise tool yet. This plan has no keys source to compile.
- `README.md` still describes the Go recorder. The plan named only the
  agent files for rewrite; a later plan should update the README.
