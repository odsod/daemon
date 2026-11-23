# PRD: Global shortcuts

- Status: Accepted
- Updated: 2026-11-23
- Design: [ADR-0008](../adr/0008-shortcuts-and-kwin-script.md),
  [ADR-0007](../adr/0007-keys-service.md)

## Problem

- The owner works across a few apps all day: terminal, browser, calendar,
  chat. Finding a window with the mouse or Alt+Tab breaks focus.
- The owner wants one thumb chord per app: press it, and that app is in
  front, wherever it was and whether it ran or not.
- Window layout must also be one chord away: tile, maximize, close, show all
  windows.
- The same chords must work on every host and after every upgrade, with no
  clicks in system settings.

## Behavior

- Owner presses Meta and an app's key:
  - app not running → it starts and comes to the front;
  - app running, not in front → its window comes to the front. With several
    windows, the one used last comes to the front;
  - app minimized → it is restored and comes to the front;
  - app already in front → it is minimized.
- Owner presses Meta and a window key → KWin does the action on the active
  window: close, maximize, tile left, right, top or bottom, or show all
  windows.
- Owner presses Meta+R → the KDE launcher opens.
- An app started from a shortcut keeps running when the daemon restarts or
  upgrades.
- Windows of some apps have no border, as the shortcut list says.
- After an install or upgrade, the chords in the shortcut list are the only
  bindings for those keys. Old shortcuts from earlier lists are gone. A KDE
  default bound to the same key is removed.
- Owner or an agent runs `odsodctl shortcuts` → the list of chords and what
  each does.

### When something fails

- The session service is down → window actions still work. App chords do
  nothing until the session service restarts. The tray icon is gone, as
  for all session failures.
- The session service crashes → apps already open stay open.
- An app command fails to start → a line in the session service log names
  the app and the error. No desktop notification: notifications are only
  for failed dictations, failed pastes and new Errors
  (`health-and-control`).

## Acceptance criteria

The chord set and the toggle behavior come from the current KWin script in
the `machine` repo. Timings are proposed targets for the owner to confirm.

1. **AC-1** Meta and an app's key brings a running app's window to the
   front in at most 200 ms. With several windows, it is the one used last.
   _Check: manual._
2. **AC-2** Meta and an app's key starts an app that does not run. Its window
   is in front when it opens. _Check: manual._
3. **AC-3** Meta and the app's key on the app in front minimizes it. The
   same chord again restores it. _Check: manual._
4. **AC-4** Each window chord does its KWin action on the active window.
   _Check: manual._
5. **AC-5** A restart of the session service closes no app that a shortcut
   started. _Check: system test._
6. **AC-6** After an install, KDE shows each chord in the list bound to its
   action, and to no other action. _Check: system test._
7. **AC-7** A shortcut removed from the list has no binding after the next
   install. _Check: system test._
8. **AC-8** With the session service stopped, window chords work. _Check:
   manual._
9. **AC-9** Every chord in the list works with Space as Meta, held from the
   keys service. _Check: manual._
10. **AC-10** `odsodctl shortcuts` prints every chord with its action, also
    as JSON with `--json`. _Check: system test._
11. **AC-11** A failed app start writes one log line with the app and the
    error. _Check: system test._

## Boundaries

### Covered by other PRDs

- Space as Meta and the keyboard remaps → the `keyboard` PRD.
- Install and upgrade of the KWin script → the `install-and-upgrade` PRD.
- Tray states → the `health-and-control` PRD.

### Not planned

- Changing chords without an upgrade. The list is code in the KWin script
  (ADR-0008).
- Window rules beyond the border, and the KWin focus policy. They stay in
  the `machine` repo (ADR-0008).
- Shortcuts outside KDE Plasma.
- Cycling through an app's windows with repeated presses. KWin's own window
  switcher does that.

## Open questions

- None.
