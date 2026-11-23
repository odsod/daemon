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
  repo `odsod/daemon`. The repo is `odsod/recorder` today and is renamed to
  `odsod/daemon` before the first `daemon:setup`. `uv` and `mise` are on
  every host.
- `main` is always deployable: `mise run build` gates every merge.
- The keys service needs root to install. Everything else installs as the owner.
- v1 has no diarization, so the install needs no model download and no
  secret ([ADR-0002](0002-high-level-architecture.md), owner decision,
  2026-11-23).
- Today the old Go recorder runs on each host, and the `machine` repo
  installs the old keyboard remapper, the KWin script and its D-Bus service.

## Decision

### Install from GitHub with uv

```sh
uv tool install --force \
  "odsod-daemon @ git+https://github.com/odsod/daemon@<ref>"
```

- No releases, no package index, no build pipeline.
- `<ref>` is `main` by default. To roll back, install `@<commit>`.
- uv fetches the Python version that `requires-python` asks for.
- The keys service's C source and unit template ship as package data.
- `odsodctl install` restarts the target right after `uv tool install`. A
  service that restarts in that short window can load a mix of old and new
  files. We accept this: the window is seconds, and a crash-only service
  restarts on the new code. No directory per commit.

### The version is the commit

- uv records the git commit of a VCS install in the package metadata
  (PEP 610 `direct_url.json`). `odsodctl version` prints it.
- No version numbers and no tags.
- `odsodctl install` records the commit it replaces in
  `state/install/previous-commit`. After a failed upgrade, `odsodctl status`
  names the rollback command with that commit.

### The `machine` repo owns install and upgrade

One mise task installs, upgrades and rolls back. Rerun it to upgrade.

```toml
[tasks."daemon:setup"]
usage = 'arg "[ref]" default="main"'
run = """
sudo dnf install -y pipewire-utils pulseaudio-utils wl-clipboard gcc kernel-headers jq
url=https://github.com/odsod/daemon
commit="$(git ls-remote "$url" "${usage_ref}" | cut -f1)"
commit="${commit:-${usage_ref}}"
if [ "$(odsodctl version --json 2>/dev/null | jq -r .commit)" != "$commit" ]; then
  uv tool install --force "odsod-daemon @ git+$url@$commit"
fi
sudo "$(command -v odsodctl)" install --system
odsodctl install
"""
```

- The task resolves `[ref]` to a commit and reinstalls only when the
  installed commit differs.
- `install` and `install --system` compare what they would write with what
  is on disk. They restart a unit only when its files or the installed
  commit changed. A rerun with no change restarts nothing, so it leaves no
  audio gap.
- `install --system` compiles the keys service, installs it as
  `/usr/local/bin/odsod-daemon-keys`, writes its system unit with the owner
  as the socket owner, and restarts it. It is a no-op restart when the
  binary did not change.
- `install` writes the user units, the timers and the D-Bus activation
  file, installs the KWin script, reloads systemd and restarts
  `odsod-daemon.target`
  ([ADR-0004](0004-orchestration-with-systemd.md),
  [ADR-0008](0008-shortcuts-and-kwin-script.md)). A pause survives it.
- The `machine` repo also links the per-host `config.json` into
  `~/.config/odsod-daemon/`, and keeps the platform settings the services
  rely on, such as the WirePlumber Bluetooth profile config.
- The `machine` repo keeps the KWin settings (window rules, focus policy).

### The repo has a dev deploy

```toml
[tasks.deploy]
run = "uv tool install --force . && odsodctl install"
```

- Installs the local working copy as the live system, to test a branch.
- The install is not editable. Services run a copy made at deploy time, so
  an agent's half-written change never loads into capture on a restart. A
  code change needs `mise run deploy` again (owner decision, 2026-11-23).
- `deploy:system` adds `sudo odsodctl install --system` for keys service
  changes.
- `odsodctl version` prints `dev`, the workspace path and the commit, with
  `+dirty` for uncommitted changes.
- A dev install is a mark, not a health state. The tray shows a separate
  dev mark, and `odsodctl status` shows `dev: true`. The state and the exit
  code do not change (owner decision, 2026-11-23).
- The next `daemon:setup` from the `machine` repo puts `main` back.

### No secrets in v1

- The install and the running services read no secret.
- A later diarization extra needs a Hugging Face token for its gated model.
  Its ADR decides how the token gets to the host.

### Migration from the old recorder and the `machine` repo

1. Install the daemon and run capture and pipeline beside the old Go
   recorder. Compare until the new transcript meets `live-transcript` AC-1
   and AC-10.
2. Stop the old recorder. Keep its files read-only. The vault keeps the old
   transcripts and segments as they are. Nothing converts them.
3. Switch the keyboard in one script: stop and disable `odsod-keys.service`,
   then start `odsod-daemon-keys.service`. Two programs cannot grab the same
   keyboard, so the order matters.
4. The `machine` repo commit that removes the old parts (the remapper, the
   KWin script and the `io.github.odsod.kwin` D-Bus service) lands together
   with the daemon commit that replaces them, so no host is left with no
   chords.

## Alternatives considered

### GitHub releases with built artifacts

- Needs a release pipeline and version numbers for one user.
- Rejected: a VCS install of `main` gives the same result with no pipeline.

### Publish to PyPI

- Rejected: public publishing for software only one person runs.

### Pin a commit in the `machine` repo

- Reproducible, but every upgrade needs a commit in two repos.
- Rejected: `main` is gated, and `daemon:setup <commit>` covers rollback.

### Prebuilt keys binary in the repo

- No compiler on the host.
- Rejected: a binary in git, built on one host for all. `gcc` is one package.

### An install directory per commit, switched by a symlink

- Atomic upgrades: no service ever sees a half-installed environment.
- Rejected: crash-only services already recover from the few seconds
  between install and restart.

### Editable dev install

- A Python change is live after one service restart, with no reinstall.
- Rejected: the live services, capture too, would import whatever the
  working copy holds, such as an agent's half-written edit
  (owner decision, 2026-11-23).

### Encrypted token in a repo (fnox with age)

- Not needed in v1: there is no secret. Revisit with the diarization extra.

## Consequences

- Install, upgrade and rollback are one command:
  `mise run daemon:setup [ref]`. It asks for sudo.
- A new host needs no manual step beyond the `machine` repo.
- Hosts can run different commits if one is not upgraded.
  `odsodctl version` shows which.
- An upgrade restarts capture, which leaves an audio gap of a few seconds. A
  keys service restart leaves the keyboard unmapped for about a second. A
  rerun with no change restarts nothing.
- Each dev change needs a deploy of a few seconds.
