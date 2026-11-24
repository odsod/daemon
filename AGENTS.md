# daemon — Agent Instructions

You, the agent, are the long-term owner of this repo. You are responsible
for code quality and for managing tech debt as part of ongoing development.

The repo is the Python package `odsod_daemon`: one daemon, one CLI
(`odsodctl`), one package.

Read first:

- [ADR-0009](docs/adr/0009-taxonomy-and-code-organization.md): taxonomy,
  four tiers, subsystems, toolchain layers, Python conventions.
- [ADR-0010](docs/adr/0010-contracts-and-runtime.md): seams, config, `lib/`
  mechanisms, services, command surface, import rules, test fixtures.
- [`docs/plans/README.md`](docs/plans/README.md): how work is ordered and
  what a plan holds.
- [`docs/adr/`](docs/adr/) and [`docs/prd/`](docs/prd/): design and
  owner-facing behavior.

## Where things are

| Path                                   | Holds                                                                                    |
| -------------------------------------- | ---------------------------------------------------------------------------------------- |
| `src/odsod_daemon/components/<name>/`  | One component each: `contract.py`, `config.py`, `service.py`, pure core, `tests/`        |
| `src/odsod_daemon/services/`           | The three systemd services (`capture`, `pipeline`, `tray`) and their runner              |
| `src/odsod_daemon/lib/`                | Shared mechanisms: streams, paths, config, glossary, health files, inference             |
| `src/odsod_daemon/cli.py`              | `odsodctl` commands                                                                      |
| `src/odsod_daemon/components/install/` | systemd units and hot deploy (ADR-0020)                                                  |
| `src/odsod_daemon/components/keys/c/`  | The C keys helper (`mise run keys:compile`)                                              |
| `tests/`                               | System tests over the CLI and services; `tests/bin/` fakes `systemctl`                   |
| `docs/adr/`                            | Design decisions, numbered; ADR-0009 and ADR-0010 first                                  |
| `docs/prd/`                            | Owner-facing behavior and acceptance criteria, one per capability                        |
| `docs/plans/`                          | Work plans and their progress logs                                                       |
| `docs/research/`                       | Studies of similar apps (Handy, Voxtype, OpenWhispr, …); `alternatives.md` compares them |
| `docs/diagrams/`                       | Diagram sources (`.py`) and rendered `.svg`                                              |
| `.agents/skills/`                      | Repo skills (`prd`)                                                                      |
| `mise.toml`                            | Tasks: `build` (CI gate), `test`, `lint`, `deploy`                                       |

Live host, outside the repo:

- Config: `~/.config/odsod-daemon/` (`config.json`, `prompts/`, and
  `glossary.yaml`, linked from the brain vault).
- State: `~/.local/state/odsod-daemon/` (audio, streams, `documents/`,
  `install/current`). Health: `$XDG_RUNTIME_DIR/odsod-daemon/health/`.

Work comes from one plan in `docs/plans/`. Run `mise run build` before you
push any change. It is the CI gate. Every change goes through a pull
request; never push to `main`.
