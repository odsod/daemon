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

Work comes from one plan in `docs/plans/`. Run `mise run build` before you
push any change. It is the CI gate.
