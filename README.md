# daemon

My personal daemon: one system of long-running services on my hosts that
handle input, audio and text. Built for one setup: Fedora, KDE Plasma on
Wayland, PipeWire and systemd.

![odsod-daemon system configuration](docs/diagrams/overview.svg)

## Services

| Service  | Unit                            | Job                                                     |
| -------- | ------------------------------- | ------------------------------------------------------- |
| keys     | `odsod-daemon-keys.service`     | Remap keys; hold Left Alt to dictate; paste the text    |
| capture  | `odsod-daemon-capture.service`  | Record mic and system audio, always on                  |
| pipeline | `odsod-daemon-pipeline.service` | Transcribe, clean up, summarize, publish to target dirs |
| session  | `odsod-daemon-session.service`  | Dictation, the tray icon and global shortcuts           |

All speech and language models run locally. The owner uses one CLI,
`odsodctl`.

## Status

- The architecture is in [`docs/adr/`](docs/adr/), with the research behind
  it in [`docs/research/`](docs/research/alternatives.md).
- The code in this repo is still the Go recorder. It is the reference for the
  Python rewrite and stays in use until the rewrite replaces it.

## Development

```sh
mise run build   # the CI gate
```
