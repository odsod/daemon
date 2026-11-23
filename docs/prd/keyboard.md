# PRD: Keyboard

- Status: Accepted
- Updated: 2026-11-23
- Design: [ADR-0007](../adr/0007-keys-service.md),
  [ADR-0004](../adr/0004-orchestration-with-systemd.md)

## Problem

- The owner drives the window manager from the keyboard: switch windows,
  start apps and raise apps, with quick shortcuts. Space as Meta puts all of
  them under the thumb, which is the most ergonomic layer the owner has.
- The owner presses Esc all the time in Neovim and other modal apps. A tap
  on Caps Lock or Left Ctrl gives Esc without leaving the home row.
- Both must work the same on every keyboard, in every app, from boot.
- Dictation needs a key to hold, without taking a key away from typing. A
  remapper bug must never leave the owner without a working keyboard.

## Behavior

- Space held with another key → Meta and that key. Space tapped → a space.
  Space held alone and released late → nothing.
- The Meta layer never leaves a bare Meta press, so the KDE launcher never
  opens by mistake.
- Caps Lock or Left Ctrl tapped alone → Esc. With another key → Ctrl and
  that key.
- Esc → Caps Lock.
- Left Alt tapped → an Alt tap, as before. Left Alt with another key → the
  Alt chord (`Alt+Tab` works). Left Alt held alone past the hold threshold
  → dictation starts, and no app sees the Alt.
- Left Alt with a mouse click, drag or scroll → the app gets Alt with it
  (Alt+click, Alt+drag). It never starts dictation.
- Another key during dictation → dictation is cancelled, and the app gets
  Alt and that key.
- Right Alt is always AltGr, for Swedish symbols. It never starts
  dictation.
- Owner plugs in a keyboard → it behaves the same, with no action.
- The remaps work from boot, at the login screen too.

### When something fails

- The keys service crashes or stops → the plain keyboard works at once, with
  no stuck key. The remaps come back when the service restarts. The tray
  shows Error while dictation is unavailable.
- The session service is down → Left Alt works as a plain Alt. Remaps still
  work.
- The keys service misbehaves without a crash (keys lost or stuck) → the
  owner holds both Shift keys and Esc for 3 s, and gets the plain keyboard
  back.

## Acceptance criteria

The 350 ms tap window and the 150 ms Space hold come from the current
remapper. The 350 ms dictation hold threshold matches the tap window. It is
above Handy's 300 ms hold threshold, the closest value in the source study.
Other numbers are proposed targets for the owner to confirm.

1. **AC-1** Caps Lock or Left Ctrl, tapped alone and released within
   350 ms, gives one Esc and no Ctrl chord. _Check: system test._
2. **AC-2** Caps Lock or Left Ctrl with another key gives Ctrl and that key,
   and no Esc. _Check: system test._
3. **AC-3** The Esc key gives Caps Lock. _Check: system test._
4. **AC-4** Space tapped and released within 350 ms gives one space. Keys
   pressed during the tap come after it, in order. _Check: system test._
5. **AC-5** Space with a key held past 150 ms gives Meta and that key. No
   bare Meta release reaches KDE. _Check: system test._
6. **AC-6** Recorded fast typing with key rollover, replayed, gives the same
   text and no Meta chord. _Check: system test._
7. **AC-7** Left Alt released within 350 ms gives one Alt tap.
   Left Alt with another key gives the Alt chord. _Check: system test._
8. **AC-8** Left Alt held alone past 350 ms, with the session
   service up, starts dictation. No app gets an Alt event. _Check: system
   test._
9. **AC-9** Another key during dictation cancels it and gives Alt and that
   key. _Check: system test._
10. **AC-10** Right Alt never starts dictation, and AltGr symbols (@, $, {,
    [) type on the Swedish layout. _Check: system test._
11. **AC-11** With the session service down, Left Alt behaves as a plain Alt
    in all cases. _Check: system test._
12. **AC-12** A keyboard plugged in gets the remaps in at most 2 s. _Check:
    manual._
13. **AC-13** The remaps work at the login screen after a boot. _Check:
    manual._
14. **AC-14** When the keys service stops, the plain keyboard works in at
    most 1 s and no key stays down. The remaps return in at most 5 s after
    a crash. _Check: system test._
15. **AC-15** Keys with no remap reach the app at most 1 ms later than
    without the keys service, measured inside the service from read to
    write. _Check: system test._
16. **AC-16** Left Alt held with a mouse button press, drag or scroll gives
    the app Alt with that mouse event, and never starts dictation, also when
    held past 350 ms. _Check: system test._
17. **AC-17** Both Shift keys and Esc held for 3 s give back the plain
    keyboard at most 1 s later, with no key left down. _Check: system
    test._

## Boundaries

### Covered by other PRDs

- What happens after dictation starts, and the paste → the `dictation` PRD.
- What Meta shortcuts do → the `global-shortcuts` PRD.
- Tray states in full → the `health-and-control` PRD.

### Not planned

- Remaps per app. One remap set for all apps (ADR-0007).
- Changing remaps or the dictation key without a rebuild. They are fixed in
  code (ADR-0007).
- Right Alt as a dictation key. Swedish symbols need it (ADR-0007).

## Open questions

- None.
