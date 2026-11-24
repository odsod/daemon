# PRD: Install and upgrade

- Status: Accepted
- Updated: 2026-11-24
- Design: [ADR-0006](../adr/0006-installation.md),
  [ADR-0020](../adr/0020-hot-deploy.md),
  [ADR-0023](../adr/0023-inference-servers.md),
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

- New host → the owner runs `mise run daemon:setup` from the `machine`
  repo, with no other step → all services run, recording starts, the
  remaps and shortcuts work. No token or secret is needed (owner decision,
  2026-11-23).
- The `machine` repo runs `daemon:setup` again, today when the owner runs it
  → the host runs the newest `main`. Services restart; recording has a short
  gap and the keyboard is plain for a moment.
- `daemon:setup` with no new commit → nothing is reinstalled and nothing
  restarts.
- An upgrade changes nothing else: config, transcripts, documents, audio
  and bench cases stay.
- An install or upgrade during a pause → the pause stays.
- Owner or an agent runs `odsodctl version` → the commit that runs.
- Bad upgrade → the owner runs `daemon:setup` with an earlier commit id.
  The host runs that commit.
- Owner or an agent develops on a host → `mise run deploy` in the repo
  installs the local work as the live system. Each code change needs
  `deploy` again. Only the services whose code changed restart. A change
  outside capture leaves no recording gap, also during a meeting. The
  deploy says when capture restarts. The next `daemon:setup` from the `machine` repo puts
  `main` back.
- A host runs local work → `odsodctl version` says so, with the workspace
  and commit. The tray shows a dev mark and `odsodctl status` shows `dev`.
  This is not a Warning (owner decision, 2026-11-23).
- Inference host → the owner runs `odsodctl inference setup` once, with
  no root. It builds whisper-server and llama-server and gets their
  models. A second run changes nothing. Then the owner sets
  `inference.enabled` in the config, and the next install starts both
  servers. A deploy that changes neither server restarts neither, so no
  model reloads.
- The first `daemon:setup` replaces the old remapper, KWin script and D-Bus
  service from the `machine` repo in one step, with no step by the owner.
- Move from the old Go recorder → the new system records next to the old
  one until the new transcript is good. Then the old recorder stops. Its
  old transcripts stay where they are.

### When something fails

- The install fails halfway → the services that ran before still run, or
  the command says which step failed and how to rerun it.
- No network → the install stops before it changes anything.
- A service fails to start after an upgrade → the tray and
  `odsodctl status` show Error, with the `daemon:setup` command and the
  commit id to roll back to.

## Acceptance criteria

The commands come from ADR-0006. The timings are targets. The recording gap
during an upgrade is `ambient-recording` AC-4.

1. **AC-1** On a host that the `machine` repo provisions, one
   `daemon:setup` gives all services running, with no other step. _Check:
   manual._
2. **AC-2** An upgrade takes at most 5 min on a host with a cached Python
   and network access. _Check: manual._
3. **AC-3** During an upgrade, the keyboard is plain for at most 2 s, and
   no key stays down. _Check: manual._
4. **AC-4** An upgrade keeps config, transcripts, documents, audio and bench
   cases unchanged. _Check: system test._
5. **AC-5** `odsodctl version` prints the full commit id that runs, also
   over SSH. _Check: system test._
6. **AC-6** Rolling back to a named commit takes one `daemon:setup` command
   and at most 5 min. _Check: manual._
7. **AC-7** Running `daemon:setup` with no new commit reinstalls nothing and
   restarts no service, so recording has no gap. _Check: manual._
8. **AC-8** After the first `daemon:setup`, the old remapper, KWin script and
   D-Bus service from the `machine` repo are gone, and no key event is
   handled twice. _Check: manual._
9. **AC-9** An install with no network changes no installed file. _Check:
   manual._
10. **AC-10** A failed step prints which step failed and the command to rerun
    it. _Check: manual._
11. **AC-11** No running service reads a secret. _Check: system test._
12. **AC-12** `mise run deploy` makes a code change live in at most 60 s
    (target). _Check: manual._
13. **AC-13** While a host runs local work, `odsodctl version` prints the
    workspace path and commit, the tray shows a dev mark, and
    `odsodctl status` shows `dev`. The dev install alone does not make the
    state Warning. `daemon:setup` clears all of these. _Check: system test._
14. **AC-14** An install or upgrade during a pause keeps the pause. _Check:
    system test._
15. **AC-15** After a failed upgrade, `odsodctl status` names the
    `daemon:setup` command and the commit id that ran before. _Check:
    system test._

16. **AC-16** A deploy or upgrade that changes no capture code restarts
    no capture service, so recording has no gap. The output names the
    services that restarted. _Check: system test._
17. **AC-17** On the inference host, a deploy or upgrade that changes no
    server binary and no server unit restarts no inference server. _Check:
    system test._

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
- Secrets read by running services.
- Conversion of the old recorder's transcripts and segments. They stay as
  they are.
- A live link from the workspace to the running system. Each change goes
  through `deploy` (owner decision, 2026-11-23).

## Open questions

- None.
