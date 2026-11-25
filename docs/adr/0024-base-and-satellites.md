# ADR-0024: Base and satellites

## Status

Accepted. Replaces [ADR-0002](0002-high-level-architecture.md) principle 11
("Hosts are independent"). Changes ADR-0002 principle 5,
[ADR-0003](0003-filesystem-interface.md) (paths, sync),
[ADR-0015](0015-transcript.md) and [ADR-0017](0017-publishing.md) (one
inbox).

## Date

2026-11-25

## Context

- Each host ran the full pipeline and published to its own vault inbox.
  Documents of the laptop stayed in the laptop's inbox, and two hosts
  processed audio with two configs.
- Owner decision (2026-11-25): one host, the **base** (the desktop),
  processes all ambient audio. A **satellite** (a laptop) records,
  dictates and sends its audio and events to the base. A 30 s lag in the
  live transcript is fine. The base may hold the raw audio of every host.
  Dictation on a satellite must work as before.
- Names: base and satellite, as a ground station and its satellites. A
  handheld recorder is a satellite that uplinks by USB (later plan).
- Bench (2026-11-25, laptop audio of one conference day):

  | Mic hour while recording | Bytes per hour |
  | ------------------------ | -------------- |
  | Raw PCM                  | 115 MB         |
  | zstd (rsync compression) | 68 to 105 MB   |
  | FLAC                     | 70 MB          |
  | Opus 32 / 24 / 16 kbit/s | 13 / 10 / 7 MB |

  A sys hour compresses to under 0.2 MB (digital silence between sounds).

- Whisper on 30 far-field Swedish mic clips: Opus changed 47% (32 kbit/s)
  to 65% (16 kbit/s) of the words against PCM. The same PCM again changed
  0%, and 1-bit dither changed 1.5%. Clean English fixtures did not
  change. Lossy audio hurts exactly the hard cases.

## Decision

### Roles

- `common.role`: `base` (default) or `satellite`. `common.base`: the SSH
  host of the base, required on a satellite.
- A single host with no config change is a base with no satellites, and
  works as before.

### Host roots on the base

- The base keeps its own files where they are: `state/` and `run/`.
- Each satellite gets `state/hosts/<host>/`, with the same layout as
  `state/` (audio, events, utterances, coverage, asr, text, documents,
  finished, published). Its run root is `state/hosts/<host>/run/`.
- The pipeline on the base runs one set of the host components
  (segmentation, transcription, cleanup, transcript, interactions,
  publish) per host root. A context variable in `lib/paths.py` holds the
  host. The runner sets it before it creates that host's tasks, so
  `paths.roots()` returns the host root and call sites do not change.
- The host name of a document comes from its host root, not from
  `common.host`. Document names stay `<day>-<host>.md` and
  `<stamp>-<host>[-slug].md`, so names do not clash in one inbox.
- Utterance IDs stay unique per host root. They need no host prefix.
- The echo check compares mic and sys of one host, on one clock.
- A satellite host root runs the same components with no special case.
  The base also transcribes the satellite's dictation utterances from the
  synced audio, for the transcript. The satellite's own text is only for
  the paste.
- The runner scans `state/hosts/` every 60 s and starts new host roots.
- Components that are not per host (parakeet, signals) run once, on the
  base's own root.
- Local day: the base's time zone for every host root. A satellite in
  another zone gets day files split at the base's midnight.

### Satellite

- Services: capture, keys, session, tray and pipeline. The pipeline holds
  only transcription and cleanup for dictation, signals (it reads the
  local browser), and **sync**.
- No `publishing.targets`. Signals skips its sys-speech fault check, as it
  has no ambient utterances.
- `odsodctl transcript` runs on the base over SSH, for this host.

### Sync

- Component `sync`, satellite only. Every 15 s it runs `rsync` over SSH
  (`BatchMode=yes`, tailnet host names only) to
  `<base>:.local/state/odsod-daemon/hosts/<host>/`. Order in each pass:
  1. `events/` and `utterances/dictation/`: append only
     (`--append-verify`).
  2. `run/status.json` to `run/status.json` in the host root.
  3. `audio/`: `--append-verify --sparse --compress`. Capture only grows
     hour files, so a pass sends new bytes only.
- The order keeps the dictation mask of segmentation correct: a dictation
  range or hold always arrives before its audio
  ([ADR-0012](0012-speech.md)).
- Lossless audio only: the bench shows that Opus changes whisper output on
  far-field speech.
- Writer per path: on the base, the satellite's sync writes only these
  paths. Base components write only their outputs.
- Offline: the satellite keeps its 14 days of audio. Sync catches up when
  the base answers. Nothing is lost while a gap is under 14 days.
- Retention: each host root keeps 14 days on the base (about 77 GB per
  host), by the same rules as `state/`.

### Health

| Fault                       | Where     | Code                                       |
| --------------------------- | --------- | ------------------------------------------ |
| Sync fails or falls behind  | Satellite | `sync-behind` (Warning 5 min, Error 1 h)   |
| A host root's backlog grows | Base      | backlog codes, with the host in the detail |
| A satellite sends no audio  | Base      | none: a closed laptop is normal            |

- `odsodctl status` on the base shows the faults of each host root, with
  the host name before the message.
- A satellite has no ambient backlog: its pipeline makes no ambient
  utterances.

## Consequences

- One vault inbox gets every document. The laptop inbox gets no new files.
- Mic audio costs about 70 to 105 MB per recorded hour on the network.
  At home this is LAN traffic over the tailnet. On a phone hotspot it is
  real data.
- The live transcript of a satellite lags by the sync interval plus the
  base's queue (target 60 s).
- The base holds about 77 GB per satellite.
- Away from the base, a satellite records and dictates (when it reaches the
  inference servers), but makes no transcript until it syncs.

## Alternatives

### Opus chunks

- 10 times less data, but changes about half of whisper's words on hard
  audio. Rejected by the bench.

### Move the base's own files under `state/hosts/`

- Uniform, but needs a capture stop and a migration, and changes the paths
  in about 40 test files. The base's own root stays as it is.

### A satellite that only sends text

- Today's model: two pipelines and two configs, and the base cannot rerun
  a satellite's audio. Rejected by the owner.
