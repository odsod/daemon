# Plan: Inference servers in the daemon

- Status: Active
- Depends on: [dictation-asr](2026-11-24-dictation-asr.md)
- Design: [ADR-0023](../adr/0023-inference-servers.md),
  [PRD install-and-upgrade](../prd/install-and-upgrade.md) AC-17,
  [PRD health-and-control](../prd/health-and-control.md) AC-17

## Goal

- The daemon pins, builds and runs whisper-server and llama-server on the
  inference host. The `machine` repo keeps only the OS packages.
- llama-server runs with n-gram speculation and an explicit
  `--parallel 4`.
- A deploy that changes no server restarts no server.

## Scope

- In: component `servers` (subsystem `inference`), `lib.download` shared
  with parakeet, `odsodctl inference setup [--check]`, the two unit
  templates, install rendering, restarts and the double-owner refusal,
  control's expected units, docs.
- Out: an automatic version bump, moving parakeet into `inference`,
  binding the servers to loopback and tailnet only, the `machine` repo
  change (its own pull request after the cutover).

## Steps

1. `lib.download` from parakeet's fetch; parakeet uses it.
2. `servers`: pins, contract, step core with table tests, setup shell with
   a local file server and fake `cmake`, `hipcc` and `g++`.
3. Install: unit templates, rendering on the inference host only, one
   digest per server binary, restart only on change, refusal while a
   `machine` server unit runs.
4. Control: the server units are expected only with `inference.enabled`.
5. Docs: ADR-0023; edits to ADR-0002 to 0006, 0009, 0010, 0012, 0016;
   PRDs; diagram frame.
6. Cutover on the desktop (owner told first; about 1 min without
   inference):
   1. `mise run deploy` (servers off: `inference.enabled` still false).
   2. `odsodctl inference setup` (adopts the models, builds; the old
      servers keep serving).
   3. `systemctl --user disable --now llama-server whisper-server`.
   4. Set `inference.enabled: true`, then `odsodctl install`.
   5. Rollback: `systemctl --user disable --now odsod-daemon-llama
      odsod-daemon-whisper && systemctl --user enable --now llama-server
      whisper-server`.
7. `machine` pull request: remove `llama/`, `whisper/` and their mise
   tasks; keep the dnf packages.

## Done when

- `mise run build` passes.
- On the desktop after the cutover:
  - `systemctl --user is-active odsod-daemon-llama odsod-daemon-whisper`
    prints `active` twice; `odsodctl status` lists both.
  - The llama startup log shows n-gram speculation.
  - A second `mise run deploy` restarts no server.
  - The speculation bench gives a cleanup p50 near 300 ms and no case
    over 1 s.

## Progress log

- 2026-11-24: steps 1 to 5 built; `mise run build` passes (939 tests).
  No real build, no cutover.

## Decisions to confirm

- Install renders the two server units together: only when both binaries
  and both models exist. One missing file renders neither, and status
  shows both down.
- A server unit that no longer renders gets `systemctl --user disable
  --now` before install removes it, so no server runs without its unit.
- A host with no config file counts as `inference.enabled: false`, in
  install and in control.
- Setup checks the build tools only when a build is due, and before any
  download.
- Setup deletes a source tarball after it unpacks it.
- The server units are not in the target's `Wants=`. `WantedBy=` and the
  enable step pull them in.
- The four llama-server slots share one 32,768-token KV cache. The
  default `chunk_chars` of 37,000 (about 12,000 tokens) fits while two
  summaries share it, not four. Check whether interactions needs a lower
  default.
