# ADR-0008: Shortcuts component and KWin script

## Status

Proposed

## Date

2026-11-23

## Context

- The `machine` repo has two parts that give the owner global shortcuts in
  KDE Plasma:
  - A KWin script (`main.js`, JavaScript) lists the shortcuts. It binds
    `Meta+<key>` to KWin actions, focuses or launches app windows by window
    class, and sets window flags such as `noBorder`.
  - A user D-Bus service (`odsod-kwin-dbus-service.py`, `dbus-python` and
    GLib, started by D-Bus activation) does what a KWin script cannot do: it
    registers the shortcuts in KGlobalAccel, launches commands and writes the
    script's logs to the journal.
- The script and the service talk over D-Bus (`io.github.odsod.kwin`). That
  interface is a contract between two files, with no tests.
- The service handles input for the owner's session, so it is in the scope
  of `odsod-daemon` ([ADR-0002](0002-high-level-architecture.md)).
- A process that launches apps from inside a systemd service puts the apps
  in that service's cgroup. A restart of the service then kills the apps.

## Decision

### Move both parts into this repo

- The service becomes the **`shortcuts`** component, in the session daemon.
  It has the same lifecycle as `dictation` and `tray`: it needs the graphical
  session and is idle otherwise.
- The KWin script moves to `kwin/` and ships as package data.
  `odsodctl install` installs or upgrades it with `kpackagetool6` and reloads
  it.
- The script stays JavaScript, because KWin scripts must be JavaScript.
- The port uses `dbus-fast` on the asyncio loop
  ([ADR-0005](0005-components-and-implementation.md)), not `dbus-python` and
  GLib.

### D-Bus interface

The names follow the repo's terms: the bus name is the daemon, the interface
is the component.

| Item        | Name                                |
| ----------- | ----------------------------------- |
| Bus name    | `io.github.odsod.daemon.session`    |
| Object path | `/io/github/odsod/daemon/shortcuts` |
| Interface   | `io.github.odsod.daemon.Shortcuts`  |

| Method      | Argument           | Does                                                                                                |
| ----------- | ------------------ | --------------------------------------------------------------------------------------------------- |
| `Configure` | JSON shortcut list | Registers each shortcut in KGlobalAccel; removes stale `[odsod]` shortcuts and conflicting bindings |
| `Run`       | JSON shortcut      | Launches the shortcut's command                                                                     |
| `Log`       | JSON values        | Writes a script log line to the session daemon's log                                                |

- `contracts/` holds the pydantic model of the shortcut JSON. Tests check the
  script's shortcut list against it.
- A D-Bus activation file names `odsod-daemon-session.service` as its
  `SystemdService`. A call from the script before the daemon is up waits for
  the daemon to start, as it does today.
- Another session component that needs D-Bus adds its own interface on the
  same bus name.

### Launch apps in their own scope

- `Run` starts each command with `systemd-run --user --scope`, so the app
  lives in its own unit. A restart of the session daemon never kills a
  launched app.

### What stays in the `machine` repo

- KWin settings: window rules (`kwinrulesrc`) and the focus policy.
- Chrome app `.desktop` files and icons. Their `Exec=` lines must match the
  launch commands in the script.

## Alternatives considered

### Move only the D-Bus service

- Rejected: the D-Bus contract would cross two repos, the problem
  [ADR-0007](0007-keys-daemon.md) solved for keys.

### Keep the name `io.github.odsod.kwin`

- No change to the script's calls.
- Rejected: the script moves and changes in the same commit anyway, and the
  old name does not say which daemon owns it.

### A fifth daemon for shortcuts

- Rejected: same lifecycle as the session daemon. Principle 13 splits daemons
  by lifecycle, not by module.

### Keep D-Bus activation of a separate script

- Rejected: a second Python environment (system `dbus-python`) outside the
  repo's toolchain, with no tests and no supervision.

## Consequences

- Shortcut code gets tests: key sequence parsing, the stale shortcut diff and
  the shortcut contract.
- Shortcuts that launch apps need the session daemon. Shortcuts for KWin
  actions work without it once registered.
- A session daemon crash stops app launching until systemd restarts it. Apps
  that are already open are not affected.
- The Chrome `.desktop` files in the `machine` repo stay coupled to the
  script's launch commands.
- Script logs move from the syslog tag `odsod-kwin-dbus-service` to
  `journalctl --user -u odsod-daemon-session`.
