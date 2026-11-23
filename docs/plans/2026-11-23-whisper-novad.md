# Plan: whisper-server without server-side VAD

- Status: Done 2026-11-23
- Depends on: none
- Design: [ADR-0006](../adr/0006-installation.md) (Migration from the old
  recorder), [ADR-0012](../adr/0012-speech.md) (Outside dependencies,
  Server-side VAD)
- Repo: `~/Code/github.com/odsod/machine`

## Goal

- The one whisper-server on `odsod-desktop` (8178, large-v3) runs without
  `--vad`, so the daemon gets the requests ADR-0012 designs for.
- llama-server (8179) sees no change.

## Scope

- In: `whisper/whisper-server.service`, `whisper/AGENTS.md`. One run of
  `mise run whisper:setup`.
- Out: a second server (it does not fit in VRAM). `--parallel 2` and
  tailnet-only binding (phase 3 plan `inference-host`).

## Facts (2026-11-23)

- VRAM: 14.5 GB of 17.1 GB used with both servers up.
- The Go recorder does not run on this host. A client on another host
  that uses 8178 loses server-side VAD. The owner accepts this for the
  data day (owner decision, 2026-11-23).

## Steps

1. Remove `--vad` and `--vad-model` and their comment from
   `whisper-server.service`. Keep `--suppress-nst`, `--language auto`
   and `--convert`.
2. Update `whisper/AGENTS.md` "Server Flags": hallucination defense moves
   to the client (the daemon's VAD and cleanup filters, ADR-0012). Keep
   the VAD model download, so a revert needs no network.
3. Note `ActiveEnterTimestamp` of `llama-server`, then run
   `mise run whisper:setup`. Its restart-on-change logic restarts only
   `whisper-server`.
4. One local `jj` commit in the machine repo:
   `feat(whisper): drop server-side VAD`. No push.
5. Revert path, if the server does not come back: `jj abandon <change
   id>` of the commit in the machine repo, run `mise run whisper:setup` again, and write in Progress log that the
   data day runs with `--vad`.

## Done when

```sh
! systemctl --user cat whisper-server | rg -q -- '^\s+--vad'
sox -n -r 16000 -c 1 /tmp/whisper-probe.wav synth 1 sine 440
curl -sf -F file=@/tmp/whisper-probe.wav -F response_format=json \
  http://127.0.0.1:8178/v1/audio/transcriptions | jq -e 'has("text")'
rm -f /tmp/whisper-probe.wav
systemctl --user show -p ActiveEnterTimestamp llama-server  # same as before
```

## Progress log

- 2026-11-23 20:14: machine repo change `xwmopkzv` (`feat(whisper): drop server-side VAD`), local. `whisper:setup` restarted only whisper-server (20:13:54); llama-server unchanged (started 2026-11-22 12:27:28). Probe returns `{"text":""}`.

## Decisions to confirm
