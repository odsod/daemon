# Plan: shortcuts (built with fakes, not shipped)

- Status: Draft
- Depends on: [python-scaffold](2026-11-23-python-scaffold.md)
- Design: [ADR-0008](../adr/0008-shortcuts-and-kwin-script.md),
  [ADR-0009](../adr/0009-taxonomy-and-code-organization.md),
  [ADR-0010](../adr/0010-contracts-and-runtime.md) (services, command
  surface, test fixtures), PRD
  [global-shortcuts](../prd/global-shortcuts.md)

## Goal

- `components/shortcuts/` holds every part in ADR-0008 "Module layout":
  the list, key parsing, Configure, Run, the KWin package and its install,
  the D-Bus interface and `odsodctl shortcuts`.
- Every row of the ADR-0008 "Tests" table passes with fakes for
  KGlobalAccel, `systemd-run`, the KWin tools and KWin itself.
- Nothing ships: the session service and `install.contract.SERVICES` do
  not run it yet.

## Scope

- In:
  - `shortcuts.json`, ported from `machine/kwin/contents/code/main.js`
    (ADR-0008 "The shortcut list"). The `recorder-note` entry changes to
    an `odsodctl note` command.
  - `keys.py`, `kglobalaccel.py`, `launcher.py`, `kwin_install.py`,
    `service.py`, `cli.py`, `kwin/` and `run(config)` in `__init__.py`.
  - The `odsodctl shortcuts [--json]` line in the root `cli.py`. It is
    read-only and needs no session (ADR-0008 "`odsodctl shortcuts`").
  - In-process fakes for KGlobalAccel, the process spawner, the KWin tools
    and the KWin reload, next to their clients (ADR-0010 "Test
    fixtures").
- Out:
  - Adding `shortcuts` to the session service `COMPONENTS`, to
    `install.contract.SERVICES`, or the D-Bus activation file in install
    (ADR-0006). That is the ship step and the owner's call.
  - Loading the KWin script, calling `kpackagetool6`, `kwriteconfig6`,
    KGlobalAccel or KWin on the live session bus. Tests never connect to
    the real session bus.
  - The `machine` repo migration (old package and service removal).
  - Owner checks on Plasma: `global-shortcuts` AC-1 to AC-5, AC-8, AC-9.

## Steps

1. Port the list to `shortcuts.json` and fix the contract to match it.
   `test_contract.py`: the file validates, names are unique, every own
   action starts with `[odsod]`, and `app` entries have a window match.
2. `keys.py` and table tests: modifiers, named keys, letters in both
   cases, digits, punctuation, and an unknown key that raises. Every key
   in the list parses (AC-6).
3. `kglobalaccel.py`: a client protocol, the pure stale diff, and
   `configure()` that binds, clears conflicts and goes on after a failed
   call. A `FakeKGlobalAccel` records calls. Tests for AC-6, AC-7 and the
   failure row. Then the thin dbus-fast client.
4. `launcher.py`: the scope unit name, the `systemd-run` argv, and the
   2 s start check through `lib.clock`. A fake spawner gives exit codes,
   stderr and slow starts. Tests for AC-5 (argv) and AC-11 (one log line).
5. `kwin/` package data: `metadata.json` (Id `odsod-daemon`) and the
   `main.js` template with the new D-Bus names and the `debug` kind.
   `kwin_install.py`: `render()`, the file-by-file compare, and the
   install and reload steps with three tries and backoff, through an
   injected command runner and reload call. Tests: placeholder replaced
   and the list equals the file; same package gives no tool call and no
   reload; a changed package runs the toggle in order; three failures give
   one log line. A `node` test runs the rendered script against a fake
   KWin API, if `node` is on `PATH`.
6. `service.py`: the dbus-fast interface with `Configure`, `Run` and
   `Log`. `Run` refuses a name not in the list. Tests call the methods in
   process with the fakes.
7. `run(config)`: connect to the session bus, install the script, export
   the interface, take the bus name, then wait. No test connects to a bus.
8. `cli.py` and the root mount. Test that `--json` holds every chord and
   action, and the text form has one line per shortcut (AC-10).

## Done when

```sh
mise run build
uv run pytest src/odsod_daemon/components/shortcuts
uv run odsodctl shortcuts --json | jq -e '.shortcuts | length > 0'
uv run python -c "from odsod_daemon.services.session import COMPONENTS; from odsod_daemon.components.install.contract import SERVICES; assert all(c.SUBSYSTEM != 'shortcuts' for c in COMPONENTS); assert 'session' not in SERVICES"
```

## Progress log

## Decisions to confirm
