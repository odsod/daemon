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
    GLib, started by D-Bus activation) does what a KWin script cannot do:
    it binds the keys in KGlobalAccel, launches commands and writes the
    script's logs to the journal.
- The script and the service talk over D-Bus (`io.github.odsod.kwin`). That
  interface is a contract between two files, with no tests.
- The old service runs any command that the script sends. Any process on
  the session bus can call it.
- The service handles input for the owner's session, so it is in the scope
  of `odsod-daemon` ([ADR-0002](0002-high-level-architecture.md)).
- A process that launches apps from inside a systemd service puts the apps
  in that service's cgroup. A restart of the service then kills the apps.
- KWin belongs to the shortcuts subsystem only
  ([ADR-0009](0009-taxonomy-and-code-organization.md), subsystem rule 3).

## Decision

### Purpose

- One chord per app brings the app to the front, starts it, or minimizes
  it. Window chords run KWin actions on the active window
  ([PRD global-shortcuts](../prd/global-shortcuts.md)).
- The same chords work on every host after every install, with no clicks in
  system settings (`global-shortcuts` AC-6, AC-7).
- `odsodctl shortcuts` lists the chords (`global-shortcuts` AC-10).

### Components

| Component   | Service or command            | Job                                                                                  |
| ----------- | ----------------------------- | ------------------------------------------------------------------------------------ |
| `shortcuts` | `session` service             | Install the KWin script; serve the D-Bus interface; bind keys; launch apps in scopes |
| `shortcuts` | `odsodctl shortcuts [--json]` | Print the shortcut list (read-only subcommand, ADR-0009)                             |
| KWin script | Inside KWin (package data)    | Register the chords; focus, restore or minimize windows; call the service            |

- The session service runs `shortcuts` next to `dictation`. Both need the
  graphical session and are idle otherwise (ADR-0002, principle 13).
- The script stays JavaScript, because KWin scripts must be JavaScript
  (ADR-0002, principle 14).

### Writes

| Target                                               | Kind           | Content                                                             |
| ---------------------------------------------------- | -------------- | ------------------------------------------------------------------- |
| `$XDG_DATA_HOME/kwin/scripts/odsod-daemon/`          | KWin package   | The rendered script, installed with `kpackagetool6`                 |
| `kwinrc`, group `Plugins`, key `odsod-daemonEnabled` | KDE config     | `true`, with `kwriteconfig6`                                        |
| KGlobalAccel                                         | D-Bus state    | Key bindings of the listed actions; stale `[odsod]` actions removed |
| D-Bus interface `io.github.odsod.daemon.Shortcuts`   | D-Bus contract | Methods below                                                       |
| Transient scopes `app-odsod-<name>-<n>.scope`        | systemd        | One per launched app                                                |
| Journal of the session service                       | Log            | Script log lines; failed app starts                                 |

- shortcuts writes nothing under `state/` or `run/`, and no health file.
  ADR-0010 has no shortcuts fault code: a broken chord is visible to the
  owner at once, and a failed start is a log line (`global-shortcuts`
  "When something fails").
- `components/shortcuts/contract.py` holds the `Shortcut` model and the
  D-Bus names (ADR-0009, rule 6).

### Reads

| Source                                            | Used for                                           |
| ------------------------------------------------- | -------------------------------------------------- |
| `components/shortcuts/shortcuts.json`             | The shortcut list (package data, the one source)   |
| `components/shortcuts/kwin/`                      | Script template and `metadata.json` (package data) |
| `$XDG_DATA_HOME/kwin/scripts/odsod-daemon/`       | Compare before install                             |
| KGlobalAccel (`/kglobalaccel`, `/component/kwin`) | Current bindings and action names                  |

- shortcuts reads no config section. The chord list is code: changing it
  needs an upgrade (`global-shortcuts` "Not planned").

### Outside dependencies

| System or tool                   | For                                                           |
| -------------------------------- | ------------------------------------------------------------- |
| KWin scripting (JavaScript API)  | `registerShortcut`, `workspace`, `callDBus`                   |
| KGlobalAccel over D-Bus          | `action`, `setForeignShortcut`, `unregister`, `shortcutNames` |
| `kpackagetool6`, `kwriteconfig6` | Install the script; enable the plugin                         |
| `org.kde.KWin` over D-Bus        | `reconfigure` to load the plugin                              |
| `systemd-run --user --scope`     | Launch apps outside the session service's cgroup              |
| `dbus-fast` (asyncio)            | Session bus client and server                                 |

### Internal design

#### Module layout

```
components/shortcuts/
├── __init__.py       SUBSYSTEM = "shortcuts"; run(config)
├── contract.py       Shortcut, ShortcutList; BUS_NAME, OBJECT_PATH, INTERFACE
├── shortcuts.json    The shortcut list
├── keys.py           Key sequence to Qt key code
├── kglobalaccel.py   Configure: stale diff, conflict removal, bindings
├── launcher.py       Run: systemd-run scope, start failure detection
├── kwin_install.py   Render the package; compare; install; reload
├── service.py        dbus-fast interface object
├── cli.py            typer: shortcuts [--json]
├── kwin/
│   ├── metadata.json            KPlugin Id "odsod-daemon"
│   └── contents/code/main.js    Script template
└── tests/
```

#### The shortcut list

`shortcuts.json` is the one list. The script, the service and
`odsodctl shortcuts` all use it.

| Field                                                    | Content                                                      |
| -------------------------------------------------------- | ------------------------------------------------------------ |
| `actionId`                                               | KGlobalAccel ID: `["kwin", <name>, "KWin", <friendly name>]` |
| `key`                                                    | Key sequence, such as `Meta+C`                               |
| `kind`                                                   | `builtin` (a KWin action), `app`, `command` or `debug`       |
| `command`                                                | argv list (`app`, `command`)                                 |
| `resourceClass`, `resourceClassIncludes`, `resourceName` | Window match (`app`)                                         |
| `noBorder`                                               | Remove the border of matching windows                        |

- Names of own actions start with `[odsod]`. `builtin` actions keep their
  KWin names, such as `Window Close`.
- `debug` replaces the old inline callback: the script logs the window
  classes of all windows. The list holds no JavaScript.
- Keys stay camelCase, as in the script. The pydantic model uses aliases.
- The ported list is the one in the `machine` repo today. Entries that call
  the old recorder change to `odsodctl` commands in the same commit.

#### KWin script

- `main.js` holds the logic of today's script and one placeholder line:
  `const shortcuts = /*@shortcuts@*/ [];`.
- `kwin_install.render()` replaces the placeholder with the JSON of the
  list. JSON is valid JavaScript, so the rendered script needs no other
  step.
- On load, the script:
  1. registers each non-`builtin` shortcut with `registerShortcut`;
  2. calls `Configure()` on the service;
  3. applies `noBorder` to open and new windows.
- On an `app` chord: find the window by its match (in stacking order, so
  the one used last comes first). Minimized: restore and activate. Not
  active: activate. Active: minimize. No window: call `Run(name)`
  (`global-shortcuts` AC-1 to AC-3).
- On a `command` chord: call `Run(name)`.
- Window focus and minimize run inside KWin and need no service. Only
  `Run` and `Configure` need the session service (`global-shortcuts` AC-8).

#### Installing the script at session start

KWin is the shortcuts subsystem's outside system, so shortcuts installs its
own script. `odsodctl install` does not
([ADR-0006](0006-installation.md)).

1. At start, render the package into a temp dir.
2. Compare it, file by file, with `$XDG_DATA_HOME/kwin/scripts/odsod-daemon/`.
3. Equal: do nothing. KWin keeps the loaded script, and no chord drops.
4. Different or missing: `kpackagetool6 --type=KWin/Script --upgrade <tmp>`
   (or `--install`), set `odsod-daemonEnabled=false`, call
   `org.kde.KWin /KWin reconfigure`, then set it `true` and call
   `reconfigure` again. KWin unloads the old script and loads the new one.
   This is the toggle that the `machine` repo uses today.
5. A failed step gets three tries with backoff, then one log line. The
   session service keeps running; dictation does not depend on it.

- An upgrade restarts the session service (ADR-0006), so a new list reaches
  KWin with each install that changes it.

#### D-Bus interface

The names follow the repo's terms: the bus name is the service, the
interface is the component.

| Item        | Name                                |
| ----------- | ----------------------------------- |
| Bus name    | `io.github.odsod.daemon.session`    |
| Object path | `/io/github/odsod/daemon/shortcuts` |
| Interface   | `io.github.odsod.daemon.Shortcuts`  |

| Method      | Argument         | Does                                                                                            |
| ----------- | ---------------- | ----------------------------------------------------------------------------------------------- |
| `Configure` | (none)           | Binds each listed key in KGlobalAccel; removes stale `[odsod]` actions and conflicting bindings |
| `Run`       | `s`: action name | Launches the command of the listed shortcut with that name                                      |
| `Log`       | `s`: JSON values | Writes a script log line to the session service's log                                           |

- `Configure` and `Run` use the service's own copy of the list. `Run`
  refuses a name that is not in the list. No caller on the session bus can
  make the service run an arbitrary command.
- The script and the service come from the same package and the same list,
  so the names always match.
- A D-Bus activation file names `odsod-daemon-session.service` as its
  `SystemdService`. A call from the script before the service is up waits
  for the service to start, as it does today.
- Another session component that needs D-Bus adds its own interface on the
  same bus name.

#### Configure

1. List the actions of component `kwin` (`shortcutNames`). Each name that
   starts with `[odsod]` or `odsod` and is not in the list: `unregister`
   (`global-shortcuts` AC-7).
2. For each listed shortcut: parse its key to a Qt key code. If KGlobalAccel
   has another action on that code, clear that action's keys with
   `setForeignShortcut(other, [])`. Then
   `setForeignShortcut(actionId, [code])` (`global-shortcuts` AC-6).
3. Log one summary line: bound, removed, conflicts cleared.

- Key parsing (`keys.py`) maps `Meta`, `Ctrl`, `Alt`, `Shift` and the named
  and printable keys to Qt codes, as the old service does. An unknown key
  fails the test of the list, not the running service.
- `builtin` actions get bound too, so `Meta+Backspace` closes a window with
  no service running once it is bound.

#### Run: launch apps in their own scope

- `Run` starts `systemd-run --user --scope --unit=app-odsod-<name>-<n>
  --collect -- <command>` as a child. The app then lives in its own unit,
  and a restart of the session service never kills it
  (`global-shortcuts` AC-5).
- A task waits for the child. If it exits non-zero within 2 s, the start
  failed: one log line with the app name, the exit code and the first line
  of stderr. No desktop notification (`global-shortcuts` AC-11).
- An app that runs longer than 2 s is not watched further.

#### `odsodctl shortcuts`

- Reads `shortcuts.json` through the contract model and prints one line per
  shortcut: chord, kind, name and command. `--json` prints the list
  (`global-shortcuts` AC-10).
- It reads no D-Bus and needs no session.

### Failure modes

| Fault                                  | What happens                                                                                                 | Code                        |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------ | --------------------------- |
| Session service down                   | Window chords and focus of open apps work; launches do nothing until restart. control shows Error (ADR-0018) | none (control: `unit-down`) |
| Session service restarts               | Apps in their scopes stay open                                                                               | none                        |
| App command fails to start             | One log line with app and error                                                                              | none                        |
| `Run` with an unknown name             | D-Bus error reply; one log line                                                                              | none                        |
| KGlobalAccel call fails in `Configure` | Log the shortcut and the error; go on with the rest                                                          | none                        |
| Script install or reload fails         | Three tries, then one log line; old script stays loaded                                                      | none                        |
| KWin not running at session start      | Install retries; the next session start tries again                                                          | none                        |

### Config

- No config section. The list is code (`global-shortcuts` "Not planned").

### Tests

Component tests use a fake KGlobalAccel and a fake `systemd-run`, both on a
test session bus or as in-process doubles.

| Test                                                                                           | Checks                    |
| ---------------------------------------------------------------------------------------------- | ------------------------- |
| `shortcuts.json` validates against the contract; every key parses; names are unique            | `global-shortcuts` AC-6   |
| `Configure` binds each chord to its action and clears a conflicting KDE default                | `global-shortcuts` AC-6   |
| `Configure` unregisters an `[odsod]` action missing from the list                              | `global-shortcuts` AC-7   |
| `Run` calls `systemd-run --user --scope` with the listed argv                                  | `global-shortcuts` AC-5   |
| `Run` with an unknown name is refused                                                          | security of the interface |
| A command that fails at once gives exactly one log line with the app and the error             | `global-shortcuts` AC-11  |
| `odsodctl shortcuts --json` holds every chord and action                                       | `global-shortcuts` AC-10  |
| Rendered `main.js`: placeholder replaced; the embedded list parses as JSON and equals the file | `global-shortcuts` AC-6   |
| Same package on disk: no `kpackagetool6` call, no reconfigure                                  | no chord drop on restart  |

### Build without hardware

- An agent builds and tests all Python parts with no KDE: KGlobalAccel,
  `systemd-run` and the KWin tools are fakes.
- The owner checks on Plasma: the script logic in KWin (`global-shortcuts`
  AC-1 to AC-4, AC-8, AC-9), and a real session restart with an app open
  (AC-5 on a real host).

## Alternatives considered

### Move only the D-Bus service

- Rejected: the D-Bus contract would cross two repos, the problem
  [ADR-0007](0007-keys-service.md) solved for keys.

### Keep the name `io.github.odsod.kwin`

- No change to the script's calls.
- Rejected: the script moves and changes in the same commit anyway, and the
  old name does not say which service owns it.

### `Run` takes the command from the caller

- As today: no list in the service.
- Rejected: any process on the session bus could run any command through
  the service. With the list in the package, the service needs no input
  from the caller beyond a name.

### The list only in `main.js`

- As today: one file.
- Rejected: Python cannot read a JavaScript literal with callbacks.
  `odsodctl shortcuts` and `Run` need the list, so it moves to JSON and the
  script gets it rendered in.

### `odsodctl install` installs the script

- One place for all install steps.
- Rejected: KWin belongs to shortcuts (ADR-0009, subsystem rule 3), and an
  install over SSH has no KWin to reload.

### A service of its own for shortcuts

- Rejected: same lifecycle as the session service. Principle 13 splits
  services by lifecycle, not by module.

### Keep D-Bus activation of a separate script

- Rejected: a second Python environment (system `dbus-python`) outside the
  repo's toolchain, with no tests and no supervision.

## Consequences

- Shortcut code gets tests: key parsing, the stale diff, the conflict
  removal and the list contract.
- Shortcuts that launch apps need the session service. Window chords and
  focus work without it once bound.
- A session service crash stops app launching until systemd restarts it.
  Apps that are already open are not affected.
- The Chrome `.desktop` files in the `machine` repo stay coupled to the
  launch commands in the list.
- Script logs move from the syslog tag `odsod-kwin-dbus-service` to
  `journalctl --user -u odsod-daemon-session`.
- The KWin plugin ID changes from `odsod` to `odsod-daemon`. The `machine`
  repo removes the old package in the migration commit (ADR-0006).
