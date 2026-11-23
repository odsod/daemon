# PRD: Install and upgrade

- Status: Accepted
- Updated: 2026-11-23
- Design: [ADR-0006](../adr/0006-installation.md),
  [ADR-0004](../adr/0004-orchestration-with-systemd.md)

## Problem

- The owner runs the system on a few hosts: a desktop and laptops. A new
  host must get the whole system with one command, not a page of steps.
- The owner and agents change the system often. A change on `main` must
  reach every host with no risk to the keyboard or to recordings.
- A bad upgrade must be easy to undo, in minutes, without knowing how the
  system is built.
- The owner must always be able to tell which version runs on a host.

## Behavior

- New host → the owner pastes the Hugging Face token once (the only manual
  step), then runs `mise run daemon:setup` from the `machine` repo → all
  services run, recording starts, the remaps and shortcuts work.
- The `machine` repo runs `daemon:setup` again, today when the owner runs it
  → the host runs the newest `main`. Services restart; recording has a short gap and the keyboard is
  plain for a moment.
- An upgrade changes nothing else: config, transcripts, documents, audio
  and bench cases stay.
- Owner or an agent runs `odsodctl version` → the commit that runs.
- Bad upgrade → the owner installs an earlier commit with the same command
  and a commit id. The host runs that commit.
- Owner or an agent develops on a host → `mise run deploy` in the repo
  switches the live system to the local work. After that, a code change is
  live after a restart of the changed service, with no reinstall. The next
  `daemon:setup` from the `machine` repo puts `main` back.
- A host runs local work → `odsodctl version` says so, with the workspace
  and commit, and the tray shows a Warning. A host is never left on local
  work without a sign.
- The first `daemon:setup` replaces the old remapper, KWin script and D-Bus
  service from the `machine` repo, with no step by the owner.

### When something fails

- The install fails halfway → the services that ran before still run, or
  the command says which step failed and how to rerun it.
- No network → the install stops before it changes anything.
- The Hugging Face token is missing → the install says so and names the
  command to fix it. Everything works except speaker names.
- A service fails to start after an upgrade → the tray and
  `odsodctl status` show Error, with the command to roll back.

## Acceptance criteria

The commands come from ADR-0006. The timings are proposed targets for the
owner to confirm. The recording gap during an upgrade is `ambient-recording`
AC-4.

1. **AC-1** On a host that the `machine` repo provisions, one
   `daemon:setup` after the token step gives all services running, with no
   other step. _Check: manual._
2. **AC-2** An upgrade takes at most 5 min on a host with a cached Python
   and network access. _Check: manual._
3. **AC-3** During an upgrade, the keyboard is plain for at most 2 s, and
   no key stays down. _Check: manual._
4. **AC-4** An upgrade keeps config, transcripts, documents, audio and bench
   cases unchanged. _Check: system test._
5. **AC-5** `odsodctl version` prints the full commit id that runs, also
   over SSH. _Check: system test._
6. **AC-6** Rolling back to a named commit takes one command and at most
   5 min. _Check: manual._
7. **AC-7** Running `daemon:setup` twice in a row changes nothing the second
   time, and keeps the keys service running if its code did not change.
   _Check: manual._
8. **AC-8** After the first `daemon:setup`, the old remapper, KWin script and
   D-Bus service from the `machine` repo are gone, and no key event is
   handled twice. _Check: manual._
9. **AC-9** An install with no network changes no installed file. _Check:
   manual._
10. **AC-10** A failed step prints which step failed and the command to rerun
    it. _Check: manual._
11. **AC-11** No running service reads the Hugging Face token. _Check: system
    test._
12. **AC-12** After the first `deploy`, a Python change is live in the
    changed service at most 5 s after one restart command. _Check: manual._
13. **AC-13** While a host runs local work, `odsodctl version` prints the
    workspace path and commit, and `odsodctl status` shows Warning.
    `daemon:setup` clears both. _Check: system test._

## Boundaries

### Covered by other PRDs

- The recording gap during an upgrade → the `ambient-recording` PRD.
- Error states after a failed start → the `health-and-control` PRD.
- The keyboard during a keys service restart → the `keyboard` PRD.

### Not planned

- Releases, version numbers or a package index. The commit is the version
  (ADR-0006).
- Upgrades started by the daemon, such as a timer that follows `main`. The
  `machine` repo decides when a host upgrades (owner decision, 2026-11-23).
- Hosts that the `machine` repo does not provision, or other Linux
  distributions.
- Secrets read by running services. The token is used only at install
  (ADR-0006).

## Open questions

- None.
