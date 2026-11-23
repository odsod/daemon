# ADR-0009: Taxonomy and code organization

## Status

Proposed

## Date

2026-11-23

## Context

- The repo is `odsod/daemon`: the owner thinks of the system as one daemon.
  Earlier ADRs used "daemon" also for each of its processes. One word with two
  meanings confuses the owner and agents.
- The owner reviews contracts, not code
  ([ADR-0002](0002-high-level-architecture.md), goal "Agent-coded"). The
  owner and agents must find all code for a component from its name alone.
- The list of components will change. The structure must not.
- Components alone are too small a unit to design in isolation. Several
  components share one job, such as segmentation, transcription and cleanup.
  Services group by lifecycle, not by design, so they are the wrong unit
  too. Without a unit between daemon and component, each design question
  touches the whole system, and the code drifts toward a tangle.
- An earlier draft of [ADR-0005](0005-components-and-implementation.md)
  sorted code by layer (`contracts/`, `files/`, `clients/`, `components/`)
  and by language (`keys/`, `kwin/`). One component was then spread over
  four or more folders.

## Decision

This ADR defines the code layout. ADR-0005 refers to it.

### Taxonomy

| Term          | Is                                                                                   | In the repo                                                                    | At runtime                                             |
| ------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------ | ------------------------------------------------------ |
| **daemon**    | The whole system: one repo, one install, one CLI                                     | The repo, the package `odsod_daemon`, the CLI `odsodctl`                       | All services together                                  |
| **subsystem** | Components that are designed together, with one ADR and one seam to the rest         | A column in the component table; `SUBSYSTEM` in each component's `__init__.py` | No runtime form                                        |
| **service**   | One systemd unit, so one process. Runs one or more components that share a lifecycle | `services/<service>.py`                                                        | `odsod-daemon-<service>.service`                       |
| **component** | One job with one contract                                                            | `components/<component>/`                                                      | Inside a service, or alone: `odsodctl run <component>` |
| **command**   | A component that runs on demand and has no service                                   | `components/<command>/`                                                        | `odsodctl <command>`                                   |

- Each component belongs to exactly one subsystem, and runs in exactly one
  service or is a command.
- Subsystems and services are independent groupings. A subsystem can span
  services (control: the tray service and commands). A service can hold
  several subsystems (pipeline: speech, transcript, signals, interactions,
  publishing).
- A service component may also expose read-only `odsodctl` subcommands from
  its own folder, such as `odsodctl transcript`, `odsodctl shortcuts` and
  `odsodctl dictation last`. They read the component's files and never run
  its service loop.
- Services group components by lifecycle (ADR-0002, principle 13). Moving a
  component to another service, or into its own, changes one file in
  `services/` and no component code.
- Names are unique across components and services. The one exception is a
  service that runs a single component of the same name, such as `capture`.

### Subsystems

| Subsystem    | Components                                         | ADR                                           |
| ------------ | -------------------------------------------------- | --------------------------------------------- |
| runtime      | `lib/`, `services/`, `cli.py` (not components)     | [ADR-0010](0010-contracts-and-runtime.md)     |
| keys         | keys                                               | [ADR-0007](0007-keys-service.md)              |
| capture      | capture, retention                                 | [ADR-0011](0011-capture.md)                   |
| speech       | segmentation, transcription, cleanup               | [ADR-0012](0012-speech.md)                    |
| dictation    | dictation, unmute-stale                            | [ADR-0013](0013-dictation.md)                 |
| signals      | signals                                            | [ADR-0014](0014-signals.md)                   |
| transcript   | transcript, note, pin                              | [ADR-0015](0015-transcript.md)                |
| interactions | interactions                                       | [ADR-0016](0016-interactions.md)              |
| publishing   | publish                                            | [ADR-0017](0017-publishing.md)                |
| control      | health, status, pause, resume, tray, notify-failed | [ADR-0018](0018-control.md)                   |
| bench        | bench                                              | [ADR-0019](0019-bench.md)                     |
| shortcuts    | shortcuts                                          | [ADR-0008](0008-shortcuts-and-kwin-script.md) |
| operations   | install, version                                   | [ADR-0006](0006-installation.md)              |

Subsystem rules:

1. **One ADR per subsystem.** It is the design unit. Its ADR names its
   components, what it writes, what it reads, its outside dependencies, its
   failure modes and its tests. Anyone can design or change a subsystem
   from its own ADR plus the contracts it reads.
2. **The seam is the contract.** A component imports another subsystem's
   code only through that component's `contract.py`. Inside one subsystem,
   components may import each other's internals. An architecture test
   checks this in `mise run build` ([ADR-0010](0010-contracts-and-runtime.md)).
3. **Each outside system has one subsystem.** PipeWire is in capture, the
   browser in signals, KWin in shortcuts, the kernel input devices in keys.
   Clients that several subsystems need, such as the inference host, are in
   `lib/` with no business logic.
4. **Admission to `lib/` is by subsystem.** Code that two components of one
   subsystem need stays in that subsystem. It moves to `lib/` only when two
   subsystems need it (rule 7 below).
5. **The detailed architecture diagram draws one frame per subsystem.** A
   new subsystem, its table row, its ADR and its diagram frame go in the
   same commit.

### Tiers

```
<repo>/
├── src/odsod_daemon/
│   ├── cli.py                     ENTRY        odsodctl
│   ├── services/<service>.py      COMPOSITION  which components share a process
│   ├── components/<component>/    BEHAVIOR     one folder per component, flat
│   └── lib/<mechanism>/           MECHANISM    shared code with no business logic
├── tests/                         SYSTEM TESTS across components
└── docs/                          adr/ diagrams/ plan/ prd/ research/
```

- The package root holds only these four entries. Each is one tier.
- A component name can never collide with a tier name.

Each component folder has the same shape:

```
components/<component>/
├── __init__.py      job, SUBSYSTEM, reads, writes, ADR link; exports run(config)
├── contract.py      models of everything this component writes
├── …                internals, free form
├── <non-Python>/    C source, KWin script, prompts, unit templates it owns
└── tests/           test_*.py, conftest.py, testdata/
```

### Rules

1. **Three kinds of code, three places.** Composition goes in `services/`,
   behavior in `components/`, mechanism in `lib/`. Each file is exactly one
   kind. Split a file that mixes two.
2. **Dependencies go one way:** `cli` → `services` → `components` → `lib`.
   Across subsystems, the only link between components is an import of
   another component's `contract.py`, to read what it writes. `lib/`
   imports no component.
   import-linter enforces this rule in `mise run build`.
3. **Folder names are architecture names.** A component folder has the name
   in the ADR-0005 component table and on the diagram. A service file has the
   name of its unit. A new component folder, its table row and its diagram box
   go in the same commit. No other map of the code exists.
   Python folder names use underscores where the architecture name has a
   hyphen: `notify-failed` lives in `components/notify_failed/`.
4. **Same shape everywhere.** The entry point, the contract and the tests are
   always in the same place. Only internals vary.
5. **A component owns all of its parts, in any language.** C, JavaScript,
   prompts, models and unit templates live in their component, never in a
   folder per language. They ship as package data
   ([ADR-0006](0006-installation.md)). `components/install/` owns the user
   unit and timer templates, because it writes them. `components/keys/` owns
   the system unit template.
6. **The writer owns the contract.** Each path has one writer (ADR-0002,
   principle 6), so the writer's `contract.py` holds its model. This also
   covers the keys socket and D-Bus messages. A change to a contract model is
   a change to the interface.
7. **Admission to `lib/`.** Code moves to `lib/` only when two or more
   subsystems need it and it makes no business decision. Until then, it stays
   in its component. Shared code that makes decisions shows a wrong border
   between components.
8. **Two test levels.**
   - Component tests, in `components/<component>/tests/`: files from
     `testdata/` in, output files compared. They are left out of the
     installed package.
   - System tests, in the root `tests/`: several components through their
     files.
   - Fakes for an outside system live next to its client. A client that
     several subsystems use is in `lib/` with its fake, such as the
     inference host and systemd. A system that one subsystem uses keeps its
     fake in that subsystem: PipeWire in capture, the browser in signals,
     the keys socket in dictation, KWin in shortcuts
     ([ADR-0010](0010-contracts-and-runtime.md)).

### Toolchain layers

Each version has one owner:

| Layer | Owns                                                                                 | Pinned in                    |
| ----- | ------------------------------------------------------------------------------------ | ---------------------------- |
| mise  | The uv version and non-Python tools. The tasks that humans, agents and CI run        | `mise.toml`                  |
| uv    | The Python version, the virtual environment, all Python packages, dev tools included | `.python-version`, `uv.lock` |

- Standard workflows are mise tasks (`mise run <task>`). Tasks and ad hoc
  commands call `uv run`, never a bare `python` or `pytest`.
- mise does not install Python. uv does, from `.python-version`.
- Python dev tools (pytest, ruff, pyright, import-linter) are uv dev
  dependencies, not mise tools, so one lock holds every Python package.
- CI installs mise, then runs `mise run build`, the same as a host.

### Python project conventions

The repo follows the standard layout of a packaged uv project
(`uv init --package`):

| Concern      | Convention                                                                                                    |
| ------------ | ------------------------------------------------------------------------------------------------------------- |
| Layout       | `src/odsod_daemon/`, build backend `uv_build`                                                                 |
| Entry point  | `[project.scripts]` `odsodctl = "odsod_daemon.cli:app"`                                                       |
| Dependencies | Runtime in `[project.dependencies]`; extras (`bench`; later `diarize`) in `[project.optional-dependencies]`   |
| Dev tools    | pytest, ruff, pyright and import-linter in `[dependency-groups] dev` (PEP 735). `uv run` installs them        |
| Tool config  | All in `pyproject.toml`: `[tool.pytest]`, `[tool.ruff]`, `[tool.pyright]`, `[tool.importlinter]`              |
| Package data | Non-Python files in a component ship in the wheel. `[tool.uv.build-backend] wheel-exclude` drops `tests` dirs |
| Imports      | Absolute only: `from odsod_daemon.components.capture.contract import AudioBlock`                              |

Tests:

- pytest with `--import-mode=importlib`, the mode pytest recommends for new
  projects. Test folders have no `__init__.py`, and test file names need not
  be unique.
- `testpaths = ["src", "tests"]`: one run finds component and system tests.
- `conftest.py` holds pytest fixtures (setup code). `testdata/` holds files
  (input and expected output). The name avoids a clash with pytest's term
  "fixture".
- Commands:
  - `mise run test`: all tests (`uv run pytest`).
  - `uv run pytest src/odsod_daemon/components/<component>`: one component.
  - `mise run build`: the CI gate. Runs ruff (lint and format check), pyright,
    import-linter, pytest and the keys service compile.

### How the structure absorbs change

| Change                                   | What moves                                                          |
| ---------------------------------------- | ------------------------------------------------------------------- |
| New component                            | New folder, table row and diagram box, in an existing subsystem     |
| New subsystem                            | New ADR, table row and diagram frame                                |
| Component moves to another subsystem     | Its `SUBSYSTEM` value, the two ADRs and the diagram; no path change |
| Component splits or merges               | Its folders; contracts show who reads what                          |
| Component moves to another service       | One line in `services/`                                             |
| A helper is needed by a second component | It moves to `lib/` under rule 7                                     |
| New service                              | One file in `services/`, one unit template in `components/install/` |

The tree stays three levels deep below the package: tier, component, file.
More components make the list in `components/` longer and never add a level.

## Alternatives considered

### Folders by layer (ADR-0005)

- Rejected: one component spreads over `contracts/`, `files/`, `clients/`,
  `components/` and a mirrored `tests/`.

### Component folders at the package root

- One level shorter import paths.
- Rejected: tiers and components mix in one list. The reader must know every
  component name to tell a tier from a component.

### Folders by domain (`input/`, `speech/`, `documents/`, `control/`)

- Rejected: no rule attaches to a domain, so the folders are only labels.
  Domain borders are judgment calls, and a new domain for a component would
  change its path and every import. Subsystems replace domains.

### Folders by subsystem (`components/<subsystem>/<component>/`)

- The code tree would show the subsystems.
- Rejected: most subsystems hold one component, so paths repeat a name
  (`capture/capture/`). A component that moves to another subsystem would
  change its path and every import. The `SUBSYSTEM` value, the component
  table and the import-linter config show the grouping with no extra level.

### Folders by service

- Rejected: moving a component to another service would change its path and
  imports. Rule: services are composition, not structure.

### One central `contracts/` package

- One place to read all interfaces, but far from the code that writes them.
- Rejected: with one writer per path, the writer is the natural owner.

### Folders per language (`keys/`, `kwin/`)

- Rejected: a component then lives in two places.

### One service per component

- Gives per-component restarts, logs and limits.
- Rejected again (ADR-0002): about ten more Python processes, several hundred
  MB on a laptop, and files already decouple the components. Rule 1 keeps it
  a one-file change if a component ever needs its own service.

### Tests only in a root `tests/` tree

- The most common layout, and pytest supports it.
- Rejected: every component then lives in two trees. pytest also documents
  tests inside the package as a standard layout, and `importlib` mode removes
  its pitfalls. Go's `_test.go` files beside the code work the same way.

### Python tools as mise tools

- mise can pin ruff and pyright too.
- Rejected: two version files for Python tools, and pytest and import-linter
  must live in the project environment anyway.

### Other names for `lib/`

- `platform`: reads as a cloud platform, and shadows the stdlib module.
- `common`, `shared`, `utils`, `helpers`: invite a junk drawer.
- `core`: suggests the business core, the opposite of its content.

### "Daemon" for each process

- Rejected: the repo name already uses "daemon" for the whole system.

## Consequences

- Each path tells its tier and its component. Its subsystem is one lookup
  away, in its `__init__.py` or the component table.
- Each subsystem can be designed, reviewed and built from its own ADR and
  the contracts it reads.
- The other ADRs and the diagrams say "service" where they said "daemon" for
  a process.
- The flat list of components gets long. It stays sorted and one level deep.
- Component tests must be excluded from the built package.
- The Go reference code at the repo root moves to `legacy/` when the first
  Python code lands, and goes away when the rewrite replaces it.
