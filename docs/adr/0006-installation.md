# ADR-0006: Install and operations

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
- The keys service needs root to install. Everything else installs as the
  owner.
- v1 has no diarization, so the install needs no model download and no
  secret ([ADR-0002](0002-high-level-architecture.md), owner decision,
  2026-11-23).
- [ADR-0004](0004-orchestration-with-systemd.md) fixes the units, the pause
  flag and the notify unit. This ADR designs the code that writes them.
- Today the old Go recorder runs on each host, and the `machine` repo
  installs the old keyboard remapper, the KWin script and its D-Bus service.

## Decision

### Purpose

- One command installs, upgrades or rolls back a host
  ([PRD install-and-upgrade](../prd/install-and-upgrade.md) AC-1, AC-6).
- A rerun with no new commit changes nothing and restarts nothing
  (`install-and-upgrade` AC-7).
- `odsodctl version` tells which commit runs, and whether it is local work
  (`install-and-upgrade` AC-5, AC-13).
- A dev deploy runs local work as the live system (`install-and-upgrade`
  AC-12).

### Components

| Component | Service or command            | Job                                                                                       |
| --------- | ----------------------------- | ----------------------------------------------------------------------------------------- |
| `install` | `odsodctl install [--system]` | Write and enable the user units, timers and D-Bus activation file; build and install keys |
| `version` | `odsodctl version [--json]`   | Print the installed commit, or `dev` with the workspace and commit                        |

- The mise task `daemon:setup` in the `machine` repo and the mise task
  `deploy` in this repo call these commands. They are part of the design
  but not components.

### Writes

| Path                                                                    | Component          | Kind     | Content                                                                           |
| ----------------------------------------------------------------------- | ------------------ | -------- | --------------------------------------------------------------------------------- |
| `~/.config/systemd/user/odsod-daemon-*.{service,timer,target}`          | `install`          | Document | User units, rendered from templates                                               |
| `~/.local/share/dbus-1/services/io.github.odsod.daemon.session.service` | `install`          | Document | D-Bus activation file ([ADR-0008](0008-shortcuts-and-kwin-script.md))             |
| `state/install/current`                                                 | `install`          | Document | JSON: `source` (`git`, `dev`), `commit`, `workspace`, `dirty`, `installed_at`     |
| `state/install/previous-commit`                                         | `install`          | Document | JSON: `commit`, `source`, `replaced_at` (seam: the commit before the last change) |
| `/usr/local/bin/odsod-daemon-keys`                                      | `install --system` | Binary   | The compiled keys service                                                         |
| `/etc/systemd/system/odsod-daemon-keys.service`                         | `install --system` | Document | System unit, with the owner as socket owner                                       |
| `/etc/systemd/system/odsod-daemon-keys.service.d/notify.conf`           | `install --system` | Document | `OnFailure=` drop-in                                                              |
| `/etc/systemd/system/odsod-daemon-notify-system@.service`               | `install --system` | Document | Runs `notify-failed` as the owner                                                 |

- `install` writes `previous-commit` only when the commit changes. It holds
  the commit that ran before, so `odsodctl status` can name the rollback
  command ([ADR-0018](0018-control.md), `install-and-upgrade` AC-15).
- `install` writes nothing else under `state/` and never touches `config/`,
  audio, streams, documents or bench cases (`install-and-upgrade` AC-4).
- `install --system` runs as root and writes nothing under the owner's
  roots.

### Reads

| Path or source                                      | Used for                                                  |
| --------------------------------------------------- | --------------------------------------------------------- |
| Package metadata `direct_url.json` (PEP 610)        | Source and commit of the install                          |
| The workspace named in `direct_url.json` (dev only) | Commit and dirty flag, with `git -C <path>`               |
| Unit templates in `components/install/units/`       | Package data owned by `install` (ADR-0009, rule 5)        |
| Keys source and system unit template                | Package data of `components/keys/`, named in its contract |
| Files on disk that `install` would write            | Compare before write                                      |
| `state/install/current`                             | Commit change detection; `version` for dev installs       |
| systemd user manager                                | Unit states for restarts                                  |

- `install` reads no config section and no secret (`install-and-upgrade`
  AC-11).

### Outside dependencies

| Tool                            | Used by              | For                                                                                              |
| ------------------------------- | -------------------- | ------------------------------------------------------------------------------------------------ |
| `uv tool install`               | mise tasks           | Install the package from GitHub or the working copy                                              |
| `git`                           | `install`, mise task | Resolve a ref; read a dev workspace's commit and dirty state                                     |
| `systemctl --user`, `systemctl` | `install`            | `daemon-reload`, enable, restart                                                                 |
| `gcc`, kernel headers           | `install --system`   | Build the keys service                                                                           |
| `sudo`                          | `daemon:setup`       | Run `install --system`                                                                           |
| dnf packages                    | `daemon:setup`       | `pipewire-utils`, `pulseaudio-utils`, `wl-clipboard`, `gcc`, `kernel-headers`, `jq`, `libnotify` |

### Internal design

#### Module layout

```
components/install/
├── __init__.py       SUBSYSTEM = "operations"
├── contract.py       InstallRecord, PreviousCommit
├── cli.py            typer: install [--system]
├── source.py         Read direct_url.json; dev commit and dirty from git
├── render.py         Render templates with the odsodctl path and the owner
├── apply.py          Compare, write, reload, enable, restart (user)
├── system.py         Build keys, write system units, restart (root)
├── units/            Unit, timer, target and D-Bus templates
└── tests/
components/version/
├── __init__.py       SUBSYSTEM = "operations"
├── cli.py            typer: version [--json]
└── tests/
```

#### Install from GitHub with uv

```sh
uv tool install --force \
  "odsod-daemon[bench] @ git+https://github.com/odsod/daemon@<ref>"
```

- No releases, no package index, no build pipeline.
- `<ref>` is `main` by default. To roll back, install `@<commit>`.
- uv fetches the Python version that `requires-python` asks for.
- The extra `bench` (`jiwer`, small) is on every host, so agents can run
  bench where the audio is ([ADR-0019](0019-bench.md)).
- The keys service's C source and unit template ship as package data.
- `odsodctl install` restarts the services right after `uv tool install`. A
  service that restarts in that short window can load a mix of old and new
  files. We accept this: the window is seconds, and a crash-only service
  restarts on the new code. No directory per commit.

#### The version is the commit

- uv records the git commit of a VCS install in the package metadata
  (PEP 610 `direct_url.json`, `vcs_info.commit_id`). `odsodctl version`
  prints it.
- No version numbers and no tags.
- A dev install comes from a local directory, and its metadata has no
  commit. `install` reads the commit with `git -C <workspace> rev-parse
  HEAD` and the dirty state with `git status --porcelain`, and records them
  in `state/install/current`. In a colocated jj workspace, git sees the
  working-copy change as uncommitted, so the dirty flag holds there too.
- `odsodctl version` prints, for a git install, the full commit; for a dev
  install, `dev`, the workspace path and the commit with `+dirty` when
  dirty. `--json` prints `source`, `commit`, `workspace`, `dirty`
  (`install-and-upgrade` AC-5, AC-13).

#### `odsodctl install` (user scope)

Steps, each printed as `[n/7] <step>`:

1. **Source.** Read the install source and commit: the candidate. Compare
   it with `state/install/current`, the last install that applied fully.
   Keep the candidate in memory. Write nothing yet.
2. **Render.** Render each template in `units/` with the absolute path of
   the installed `odsodctl` (`sys.argv[0]`, resolved) and `%t` paths.
3. **Write.** Compare each rendered file with the file on disk. Write only
   the changed ones (atomic). Remove `odsod-daemon-*` units on disk that no
   template renders any more.
4. **Reload.** If any unit file changed, run `systemctl --user daemon-reload`.
5. **Enable.** `systemctl --user enable odsod-daemon.target
   odsod-daemon-resume.timer odsod-daemon-retention.timer
   odsod-daemon-capture.service odsod-daemon-session.service
   odsod-daemon-tray.service odsod-daemon-login.service`. This is
   idempotent. Capture, session, tray and the login one-shot are
   `WantedBy=graphical-session.target`, not part of `odsod-daemon.target`,
   so they need their own enable (`install-and-upgrade` AC-1).
6. **Restart.** Only what changed:
   - the candidate differs from `current` in source or commit, or the
     install is a dev deploy: all Python services;
   - else: each service whose own unit file changed;
   - pipeline: `restart`;
   - capture, session and tray: `restart` when `graphical-session.target`
     is active, else `try-restart`, so an install over SSH with no
     graphical session starts none of them. A pause holds: capture's
     `ExecCondition=` blocks its start (`install-and-upgrade` AC-14);
   - then `systemctl --user start odsod-daemon.target`, and, when
     `graphical-session.target` is active, `systemctl --user start` for
     capture, session and tray, to start what is missing. Starting a
     running unit does nothing.
   - On a new host with a graphical session, step 6 starts capture, session
     and tray at once. Over SSH they start at the next login.
7. **Record.** Only after steps 2 to 6 succeed: if the candidate differs
   from `current`, write `previous-commit` from the old `current`, then
   write the candidate as the new `current`. A failure in steps 2 to 6
   leaves the old `current`, so the next run sees a change and repeats every
   restart. Restarts are idempotent, so a repeat does no harm.

- No change at all: no write, no reload, no restart, so no audio gap
  (`install-and-upgrade` AC-7).
- A failed step prints `failed at step <n> (<step>): <error>` and the
  rerun command, `mise run daemon:setup` in the `machine` repo or
  `mise run deploy` for a dev install, then exits 1
  (`install-and-upgrade` AC-10). Steps 1 to 5 stop no service, so the old
  services still run.
- `current` always names the last install that applied fully. Writing it
  last keeps a rerun after a failure from skipping the restarts the failed
  run did not reach (`install-and-upgrade` AC-10, AC-15).

#### Unit templates

Rendered into `~/.config/systemd/user/`. The values below are the
design; ADR-0004 fixes the unit set.

| Unit                            | Key settings                                                                                                                                                                                                                                   |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `odsod-daemon-capture.service`  | `Type=notify`, `WatchdogSec=30`, `ExecCondition=/bin/sh -c '! test -e %t/odsod-daemon/paused'`, `After=pipewire.service wireplumber.service graphical-session.target`, `PartOf=graphical-session.target`, `WantedBy=graphical-session.target`  |
| `odsod-daemon-pipeline.service` | `Type=notify`, `WatchdogSec=120`, `WantedBy=odsod-daemon.target`                                                                                                                                                                               |
| `odsod-daemon-session.service`  | `Type=notify`, `BusName=io.github.odsod.daemon.session`, `ExecStopPost=<odsodctl> unmute-stale`, `After=pipewire.service wireplumber.service graphical-session.target`, `PartOf=graphical-session.target`, `WantedBy=graphical-session.target` |
| `odsod-daemon-tray.service`     | `Type=simple`, `After=graphical-session.target`, `PartOf=graphical-session.target`, `WantedBy=graphical-session.target`                                                                                                                        |
| `odsod-daemon.target`           | `Wants=` pipeline and the timers; `WantedBy=default.target`                                                                                                                                                                                    |
| `odsod-daemon-login.service`    | `Type=oneshot`, `ExecStart=<odsodctl> resume --by login`, `After=graphical-session.target`, `WantedBy=graphical-session.target`. A login ends a pause (ADR-0004)                                                                               |
| `odsod-daemon-resume.timer`     | `OnCalendar=*-*-* 00:00:00`; its service runs `<odsodctl> resume --by timer`                                                                                                                                                                   |
| `odsod-daemon-retention.timer`  | `OnCalendar=hourly`, `OnStartupSec=1min`, `Persistent=true`; its service runs `<odsodctl> retention`                                                                                                                                           |
| `odsod-daemon-notify@.service`  | `Type=oneshot`, `ExecStart=<odsodctl> notify-failed %i`                                                                                                                                                                                        |

- All services: `ExecStart=<odsodctl> run <service>`, `Restart=always`,
  `RestartSec=1`, `StartLimitIntervalSec=60`, `StartLimitBurst=5`,
  `OnFailure=odsod-daemon-notify@%n.service`.
- `WatchdogSec=30` lets capture restart in at most 60 s after audio stops
  (`ambient-recording` AC-13).
- The D-Bus activation file names `SystemdService=odsod-daemon-session.service`
  (ADR-0008).
- The KWin script is not installed here. The shortcuts component installs
  it when the session starts, because KWin belongs to shortcuts
  (ADR-0009, subsystem rule 3; [ADR-0008](0008-shortcuts-and-kwin-script.md)).

#### `odsodctl install --system` (root)

1. Find the owner: `SUDO_UID`. Refuse to run without it.
2. Copy the keys source from package data to a temp dir and compile it
   with `gcc -O2 -Wall -Wextra -Werror`.
3. Compare the binary with `/usr/local/bin/odsod-daemon-keys`. Install it
   (temp name, rename) only if it differs.
4. Render the system unit with the owner's UID as socket owner, the
   `OnFailure=` drop-in and `odsod-daemon-notify-system@.service`. The
   notify unit runs `<odsodctl> notify-failed %i` with `User=<owner>` and
   `Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<uid>/bus`
   (ADR-0004).
5. Write changed files; `systemctl daemon-reload` if any changed;
   `systemctl enable odsod-daemon-keys`.
6. Restart keys only if the binary or its unit changed. A restart leaves
   the keyboard plain for about 1 s (`install-and-upgrade` AC-3).

#### The `machine` repo owns install and upgrade

One mise task installs, upgrades and rolls back. Rerun it to upgrade.

```toml
[tasks."daemon:setup"]
usage = 'arg "[ref]" default="main"'
run = """
set -eu
step() { echo "[daemon:setup] $1"; }
fail() { echo "[daemon:setup] failed: $1. Rerun: mise run daemon:setup ${usage_ref}" >&2; exit 1; }
step "packages"
sudo dnf install -y pipewire-utils pulseaudio-utils wl-clipboard gcc kernel-headers jq libnotify || fail "dnf install"
url=https://github.com/odsod/daemon
step "resolve ${usage_ref}"
if echo "${usage_ref}" | grep -Eq '^[0-9a-f]{40}$'; then
  commit="${usage_ref}"
else
  commit="$(git ls-remote "$url" "${usage_ref}" | cut -f1)" || fail "git ls-remote (network?)"
  [ -n "$commit" ] || fail "unknown ref ${usage_ref}"
fi
installed="$(odsodctl version --json 2>/dev/null | jq -r '"\(.source) \(.commit)"' || true)"
if [ "$installed" != "git $commit" ]; then
  step "uv tool install ${commit}"
  uv tool install --force "odsod-daemon[bench] @ git+$url@$commit" || fail "uv tool install"
fi
step "linger"
loginctl enable-linger "$USER" || fail "loginctl enable-linger"
step "install --system"
sudo "$(command -v odsodctl)" install --system || fail "odsodctl install --system"
step "install"
odsodctl install || fail "odsodctl install"
"""
```

- The task resolves `[ref]` to a commit. It reinstalls when the installed
  source is not `git` or the installed commit differs. A dev deploy at the
  same commit as `main` is then still replaced (`install-and-upgrade`
  AC-13).
- `loginctl enable-linger` keeps the owner's user manager running while the
  owner is logged out. The retention timer then deletes old audio also
  after a logout (`ambient-recording` AC-7; owner decision, 2026-11-23). It
  is idempotent.
- With linger, the user manager and `odsod-daemon.target` (pipeline and
  the timers) keep running after a logout, so pending work and retention
  go on. Capture is `PartOf=graphical-session.target`, so a logout still
  stops recording, and the gap gets the cause `logout`
  (`live-transcript` AC-14). The login one-shot ends a pause at the next
  login ([ADR-0004](0004-orchestration-with-systemd.md)).
- With no network, `git ls-remote` fails before anything changes
  (`install-and-upgrade` AC-9). A full commit id skips the lookup, but
  `uv tool install` still needs the network and fails before it replaces
  the old environment.
- The `machine` repo also links the per-host `config.json` into
  `~/.config/odsod-daemon/`, and keeps the platform settings the services
  rely on, such as the WirePlumber Bluetooth profile config.
- The `machine` repo keeps the KWin settings (window rules, focus policy).

#### The repo has a dev deploy

```toml
[tasks.deploy]
run = "uv tool install --force '.[bench]' && odsodctl install"

[tasks."deploy:system"]
depends = ["deploy"]
run = 'sudo "$(command -v odsodctl)" install --system'
```

- Installs the local working copy as the live system, to test a branch.
- Every deploy restarts all Python services, also when the commit did not
  change: two deploys of a dirty working copy at one commit hold different
  code (`install-and-upgrade` AC-12). A pause still holds through
  capture's `ExecCondition=`.
- The install is not editable. Services run a copy made at deploy time, so
  an agent's half-written change never loads into capture on a restart. A
  code change needs `mise run deploy` again (owner decision, 2026-11-23).
- `deploy:system` adds the keys service for C changes.
- `odsodctl version` prints `dev`, the workspace path and the commit, with
  `+dirty` for uncommitted changes.
- A dev install is a mark, not a health state. The tray shows a separate
  dev mark, and `odsodctl status` shows `dev: true`. The state and the exit
  code do not change (owner decision, 2026-11-23; [ADR-0018](0018-control.md)).
- The next `daemon:setup` from the `machine` repo puts `main` back. It
  sees the `dev` source (or a different commit) and reinstalls.

#### No secrets in v1

- The install and the running services read no secret. No unit has
  `EnvironmentFile=` or `LoadCredential=` (`install-and-upgrade` AC-11).
- A later diarization extra needs a Hugging Face token for its gated model.
  Its ADR decides how the token gets to the host.

#### Migration from the old recorder and the `machine` repo

1. Install the daemon and run capture and pipeline beside the old Go
   recorder. Compare until the new transcript meets `live-transcript` AC-1
   and AC-10.
   - The Go recorder needs whisper-server with server-side VAD (`--vad`).
     The daemon needs it without (ADR-0012). Until the Go recorder stops,
     the `machine` repo runs a second whisper-server without `--vad` on
     another port, and the daemon's `whisper_url` points at it. The second
     unit goes away with the Go recorder.
   - Both inference servers listen on the tailnet address only, not
     `0.0.0.0` (ADR-0002). llama-server runs with `--parallel 2`, so
     dictation cleanup never waits behind a batch summary (ADR-0002,
     principle 9). The `machine` repo owns these server settings
     (owner decision, 2026-11-23).
2. Stop the old recorder. Keep its files read-only. The vault keeps the old
   transcripts and segments as they are. Nothing converts them.
3. Switch the keyboard in one script: stop and disable `odsod-keys.service`,
   then start `odsod-daemon-keys.service`. Two programs cannot grab the
   same keyboard, so the order matters.
4. The `machine` repo commit that removes the old parts (the remapper, the
   KWin script `odsod` and the `io.github.odsod.kwin` D-Bus service) lands
   together with the daemon commit that replaces them, so no host is left
   with no chords (`install-and-upgrade` AC-8).

### Failure modes

| Fault                                     | What happens                                                                                  |
| ----------------------------------------- | --------------------------------------------------------------------------------------------- |
| No network                                | `daemon:setup` stops at the ref lookup or `uv tool install`; nothing changed                  |
| `uv tool install` fails                   | The old environment stays; the task names the step                                            |
| A unit file write fails (disk full)       | `install` stops at step 3; running services keep running; `current` stays old                 |
| A restart fails partway in step 6         | `install` stops; `current` stays old, so the rerun repeats all restarts                       |
| `daemon-reload` or `enable` fails         | `install` stops and names the step; no restart happened                                       |
| A service fails to start after an upgrade | systemd retries; at the start limit, control shows Error with the rollback command (ADR-0018) |
| `gcc` fails                               | `install --system` stops before it replaces the binary; keys keeps running                    |
| `install --system` without `sudo`         | Refuses: no `SUDO_UID`                                                                        |
| Dev workspace has no git                  | `current.commit` is `unknown`; `version` says so                                              |

- install and version are commands. They write no health file.

### Config

- No config section. Install has no tunable; everything comes from the
  package, the templates and the mise tasks.

### Tests

Component tests run on a temp home and a temp root, with a fake
`systemctl` and a fake `gcc` that record their calls.

| Test                                                                                                                  | Checks                      |
| --------------------------------------------------------------------------------------------------------------------- | --------------------------- |
| Second `install` with no change writes nothing and calls no restart                                                   | `install-and-upgrade` AC-7  |
| A commit change restarts all services, then writes `previous-commit` and `current`                                    | `install-and-upgrade` AC-15 |
| Session and tray get `try-restart` with no graphical session, `restart` with one                                      | `install-and-upgrade` AC-14 |
| A first install enables capture, session, tray and the login one-shot, and starts the services in a graphical session | `install-and-upgrade` AC-1  |
| With no graphical session, install starts no capture, session or tray                                                 | `install-and-upgrade` AC-14 |
| A failure at step 3 or partway through step 6 leaves `current` old; the rerun restarts all services                   | `install-and-upgrade` AC-10 |
| A dev deploy at an unchanged commit restarts all Python services                                                      | `install-and-upgrade` AC-12 |
| `daemon:setup` logic: installed `dev` at the same commit as the target reinstalls                                     | `install-and-upgrade` AC-13 |
| Rendered capture unit has `ExecCondition=` on the pause flag                                                          | `ambient-recording` AC-19   |
| `install` writes no file under `state/` except `state/install/`, none under `config/`                                 | `install-and-upgrade` AC-4  |
| No rendered unit has `EnvironmentFile=` or `LoadCredential=`                                                          | `install-and-upgrade` AC-11 |
| A failing step prints the step and the rerun command, exit 1                                                          | `install-and-upgrade` AC-10 |
| `version --json` for a VCS install prints the full commit from `direct_url.json`                                      | `install-and-upgrade` AC-5  |
| `version` for a dev install prints `dev`, workspace, commit and `+dirty`                                              | `install-and-upgrade` AC-13 |
| Every unit has `OnFailure=odsod-daemon-notify@%n.service`                                                             | `health-and-control` AC-14  |
| `install --system` with an unchanged binary does not restart keys                                                     | `install-and-upgrade` AC-7  |

System test in `tests/`: install into a temp home, then `status` reads the
install record and shows the dev mark (`health-and-control` AC-15).

### Build without hardware

- An agent builds and tests `install` and `version` with no owner hardware:
  systemd, `gcc` and the home directory are fakes or temp dirs. The real
  keys compile runs in `mise run build` (ADR-0009).
- The owner checks on a real host: `daemon:setup` on a new host
  (`install-and-upgrade` AC-1), upgrade and rollback time (AC-2, AC-6), the
  plain-keyboard time (AC-3), no network (AC-9), the migration (AC-8) and
  the deploy time (AC-12).

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
- Rejected: a binary in git, built on one host for all. `gcc` is one
  package.

### An install directory per commit, switched by a symlink

- Atomic upgrades: no service ever sees a half-installed environment.
- Rejected: crash-only services already recover from the few seconds
  between install and restart.

### Editable dev install

- A Python change is live after one service restart, with no reinstall.
- Rejected: the live services, capture too, would import whatever the
  working copy holds, such as an agent's half-written edit
  (owner decision, 2026-11-23).

### Restart the whole target on every install

- Simpler restart logic.
- Rejected: a rerun with no change must leave no audio gap
  (`install-and-upgrade` AC-7), and a start of session over SSH would fail
  with no display.

### Read the dev commit at query time

- No install record for dev installs.
- Rejected: the workspace moves on after the deploy. `version` must show
  what runs, not what the workspace holds now.

### Install the KWin script from `install`

- One place for every install step.
- Rejected: KWin belongs to shortcuts (ADR-0009, subsystem rule 3), and the
  script needs a running KWin, which an install over SSH does not have.

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
- Each dev change needs a deploy of a few seconds, and each deploy restarts
  the Python services, with a short audio gap.
- The owner's user manager lingers after logout, so user timers run while
  the owner is logged out.
- `state/install/current` is a new path (orchestrator decision,
  2026-11-23); control and bench read it.
