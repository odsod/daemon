# PRD: Health and control

- Status: Accepted
- Updated: 2026-11-23
- Design: [ADR-0004](../adr/0004-orchestration-with-systemd.md),
  [ADR-0005](../adr/0005-components-and-implementation.md)

## Problem

- The owner relies on the system without watching it. A recorder that fails
  without a sign looks fine and records nothing, and the loss shows only
  when the owner needs the record.
- One glance must tell the owner: is it recording, can I dictate, is
  something wrong?
- When something is wrong, the owner needs to know what, and what to do. Not
  a log.
- The owner hands work to AI agents. Agents must check and control the
  system as the owner does, from a terminal.

## Behavior

- The tray icon shows one state: Running, Paused, Dictating, Mic muted,
  Warning or Error. Each state has its own icon. When several apply, the
  first in this order wins: Error, Dictating, Warning, Paused, Mic muted,
  Running. Dictating is the owner's own action and lasts seconds, so it
  shows over a Warning.
- Owner opens the tray → sees the reason for a Warning or an Error in plain
  words, since when, and the command that fixes it. The menu has Pause or
  Resume.
- Owner or an agent runs `odsodctl status` → the same state and reasons as
  the tray, plus each service, the time of the newest audio, and the
  transcription backlog. It works with no graphical session, such as over
  SSH.
- Every tray action has an `odsodctl` command: `pause`, `resume`. Other
  PRDs add commands, such as `dictation last`, `transcript`, `note`, `pin`,
  `shortcuts`, `bench` and `version`. Each command takes `--json` for
  agents.
- `odsodctl status` exits with 0 for OK, 1 for Warning, 2 for Error and 3
  when it cannot tell.
- Generic service control stays with systemd: an agent restarts a service
  with `systemctl --user restart odsod-daemon-<service>`. Each Warning and
  Error names that command when it is the fix.
- Desktop notifications come only for events that need the owner now: a
  failed dictation, a failed paste, and a new Error. An Error notifies once
  per cause, never again while it lasts.
- Untranscribed audio older than 10 min → Warning, with the backlog size.

### When something fails

- A service crashes again and again until systemd gives up → Error that
  names the service.
- The session service is down → no tray icon. `odsodctl status` reports
  the session service as down.
- The inference host is out of reach → the backlog grows, and the tray shows
  Warning. Recording goes on.

## Acceptance criteria

The 10 min backlog limit and the timings are proposed targets for the owner
to confirm. Detection times for silent mics and stalls are in the
`ambient-recording` PRD.

1. **AC-1** The tray state changes at most 2 s after its condition is
   detected. _Check: system test._
2. **AC-2** Each Warning and Error shows one sentence that names the cause,
   and the time it started. _Check: system test._
3. **AC-3** `odsodctl status` and the tray show the same state at the same
   moment, in every state. _Check: system test._
4. **AC-4** `odsodctl status` answers in at most 1 s, also over SSH with no
   graphical session. _Check: system test._
5. **AC-5** Each tray action has an `odsodctl` command with the same effect.
   _Check: system test._
6. **AC-6** The only desktop notifications are failed dictations, failed
   pastes and new Errors. An Error that lasts 1 h gives one notification.
   _Check: system test._
7. **AC-7** A service that reaches its restart limit shows Error naming that
   service at most 10 s later. _Check: system test._
8. **AC-8** With the session service down, `odsodctl status` says so at most
   10 s later. _Check: system test._
9. **AC-9** Untranscribed audio older than 10 min shows Warning with the
   backlog size. _Check: system test._
10. **AC-10** Every `odsodctl` command with `--json` prints one JSON
    document that holds all fields of its text output. _Check: system
    test._
11. **AC-11** `odsodctl status` exits with 0 (OK), 1 (Warning), 2 (Error)
    or 3 (unknown), in the convention of Nagios plugins. _Check: system
    test._
12. **AC-12** When several states apply, the tray and `odsodctl status`
    show the first in the order Error, Dictating, Warning, Paused, Mic
    muted, Running. _Check: system test._
13. **AC-13** Each Warning and Error that a service restart fixes names the
    `systemctl --user restart` command for that service. _Check: system
    test._

## Boundaries

### Covered by other PRDs

- What each recording problem is, and when it is detected → the
  `ambient-recording` PRD.
- Other Warning causes: a failed meeting mute (`dictation`), the inference
  host out of reach (`live-transcript`), a missing target
  (`interactions-and-publishing`), a dev install (`install-and-upgrade`).
- Dictation failures and their notifications → the `dictation` PRD.
- The keys service and Left Alt without a session → the `keyboard` PRD.
- `odsodctl note` and `odsodctl pin` → the `live-transcript` PRD.

### Not planned

- An overlay window or a status window. A window steals focus on Wayland
  (ADR-0005).
- `odsodctl` commands that wrap systemd, such as restart or reload. Agents
  use `systemctl` (owner decision, 2026-11-23).
- A command to run the batch pass now. It runs on its own.

## Open questions

- None.
