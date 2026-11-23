# ADR-0006: Installation

## Status

Proposed

## Date

2026-11-23

## Context

- One person installs the system, on a few hosts that the `machine` repo
  provisions. Installation must be practical for that person only.
- The system is a Python package ([ADR-0005](0005-components-and-implementation.md))
  plus one C service ([ADR-0007](0007-keys-service.md)), in the public GitHub
  repo `odsod/daemon`. `uv` and `mise` are on every host.
- `main` is always deployable: `mise run build` gates every merge.
- The keys service needs root to install. Everything else installs as the owner.
- The pyannote model is gated on Hugging Face and needs a token to download.

## Decision

### Install from GitHub `main` with uv

```sh
uv tool install --force --reinstall \
  "odsod-daemon[diarize] @ git+https://github.com/odsod/daemon@main"
```

- No releases, no package index, no build pipeline.
- To roll back, install `@<commit>` instead of `@main`.
- uv fetches the Python version that `requires-python` asks for.
- The keys service's C source and unit template ship as package data.

### The version is the commit

- uv records the git commit of a VCS install in the package metadata
  (PEP 610 `direct_url.json`). `odsodctl version` prints it.
- No version numbers and no tags.

### The `machine` repo owns install and upgrade

One mise task installs and upgrades. Rerun it to upgrade.

```toml
[tasks."daemon:setup"]
run = """
sudo dnf install -y pipewire-utils pulseaudio-utils wl-clipboard gcc kernel-headers
uv tool install --force --reinstall "odsod-daemon[diarize] @ git+https://github.com/odsod/daemon@main"
sudo "$(command -v odsodctl)" install --system
odsodctl models fetch
odsodctl install
"""
```

- `install --system` compiles the keys service, installs it as
  `/usr/local/bin/odsod-daemon-keys`, writes its system unit with the owner
  as the socket owner, and restarts it. It is a no-op restart when the
  binary did not change.
- `models fetch` downloads the pyannote model once. The Silero model ships
  in the package.
- `install` writes the user units and the D-Bus activation file, installs
  the KWin script, reloads systemd and restarts `odsod-daemon.target`
  ([ADR-0004](0004-orchestration-with-systemd.md),
  [ADR-0008](0008-shortcuts-and-kwin-script.md)).
- The `machine` repo also links the per-host `config.json` into
  `~/.config/odsod-daemon/`, and keeps the platform settings the services
  rely on, such as the WirePlumber Bluetooth profile config.
- The `machine` repo no longer builds `odsod-keys`. The first `daemon:setup`
  disables and removes `odsod-keys.service`, which the keys service replaces.
- The `machine` repo no longer installs the KWin script or the
  `io.github.odsod.kwin` D-Bus service. It keeps the KWin settings (window
  rules, focus policy).

### The repo has a dev deploy

```toml
[tasks.deploy]
run = "uv tool install --force --editable '.[diarize]' && odsodctl install"
```

- Runs the local workspace as the live system, to test a branch.
- The install is editable: the live services import the workspace source.
  After the first deploy, a Python change needs only a restart of the
  affected service (`mise run restart -- <service>`). Rerun `deploy` only
  when dependencies, units or the KWin script change.
- `deploy:system` adds `sudo odsodctl install --system` for keys service
  changes.
- `odsodctl version` prints `dev`, the workspace path and the commit, with
  `+dirty` for uncommitted changes. `odsodctl status` shows a Warning while a
  host runs a dev install, so it is never left on one by mistake.
- The next `daemon:setup` from the `machine` repo puts `main` back.
- Moving or deleting the workspace breaks the live services. Run
  `daemon:setup` before you remove it.

### Secrets only at install time

- The Hugging Face token is needed only by `odsodctl models fetch`.
  Running services never read a secret.
- The owner runs `uvx hf auth login` once per host and pastes the token from
  KeePass. The Hugging Face client stores it in its own cache.
- Use a fine-grained read-only token.

## Alternatives considered

### GitHub releases with built artifacts

- Needs a release pipeline and version numbers for one user.
- Rejected: a VCS install of `main` gives the same result with no pipeline.

### Publish to PyPI

- Rejected: public publishing for software only one person runs.

### Pin a commit in the `machine` repo

- Reproducible, but every upgrade needs a commit in two repos.
- Rejected: `main` is gated, and `@<commit>` covers rollback.

### Prebuilt keys binary in the repo

- No compiler on the host.
- Rejected: a binary in git, built on one host for all. `gcc` is one package.

### Encrypted token in a repo (fnox with age)

- `machine` could hold the token as age ciphertext, with the age key in KDE
  Wallet. Both repos are public, so the ciphertext would be published, and a
  leaked age key would expose it through git history.
- Rejected for now: the token is used once per host, so pasting it is as much
  work as bootstrapping an age key. Revisit when a secret is needed more than
  once per host.

## Consequences

- Upgrade is one command: `mise run daemon:setup`. It asks for sudo.
- Hosts can run different commits if one is not upgraded.
  `odsodctl version` shows which.
- An upgrade restarts capture, which leaves an audio gap of a few seconds. A
  keys service restart leaves the keyboard unmapped for about a second.
- A new host needs one manual step: `uvx hf auth login`.
