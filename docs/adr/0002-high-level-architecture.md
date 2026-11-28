# ADR-0002: High-level architecture

## Status

Proposed

## Date

2026-11-23

## Context

### Scope

`odsod-daemon` is the owner's personal daemon: one system of long-running
services on the owner's hosts that handle input, audio and text. A daemon is a
program
that runs as a background process, not under the direct control of a user.
The name follows the Unix term
([Daemon (computing)](<https://en.wikipedia.org/wiki/Daemon_(computing)>)).

### Goals

- **Keyboard:** remap keys at the lowest level, for every application.
- **Always-on recording:** every host records ambient audio (mic and system)
  in the background, and survives restarts and upgrades.
- **Dictation:** hold a key to speak, see an indicator while speaking, and get
  the text in the active application on release.
- **Quality from real data:** real use produces the data to compare models,
  prompts and segmentation.
- **Local only:** ambient audio is too sensitive to leave the owner's machines.
- **Agent-coded:** the owner understands each component through its contract,
  without reading the code.

### Forces

- Speech is Swedish or English. Swedish speech carries English technical
  words, and the language of a call changes when an English speaker joins or
  leaves. Whisper-family models detect one language per request and lose the
  other language in long chunks that span a change. Short requests,
  one utterance each, avoid most of that loss (benchmark 2026-11: mixed WER
  45% on long chunks, 5.3% split per utterance, as an upper bound).
- Local inference runs on one shared GPU host. Whisper-server handles one
  request at a time, so dictation competes with ambient work. Ambient
  cleanup from other hosts holds llama-server slots too.
- Raw ASR output is never final text. It needs LLM cleanup with a glossary.
- Recording and dictation need the same audio, cut in different ways.
- The keys service grabs every physical keyboard. No other process can read key
  events from them, so dictation keys must come from the keys service.
- A source study of nine dictation and meeting tools
  ([docs/research/](../research/alternatives.md)) found no tool that records
  always-on, and none that mutes the meeting while the owner dictates.

## Decision

### Terms

| Term          | Meaning                                                                      | Example                                |
| ------------- | ---------------------------------------------------------------------------- | -------------------------------------- |
| **daemon**    | The whole system: one repo, one install, one CLI                             | `odsod-daemon`                         |
| **service**   | One systemd unit and its process. Runs the components that share a lifecycle | the keys service, the pipeline service |
| **component** | A module with one job, inside a service or run as a command                  | `segmentation`, `cleanup`              |
| **command**   | A component that runs on demand, with no service                             | `odsodctl note`, `odsodctl bench`      |
| **owner**     | The one person who uses and runs the system                                  |                                        |

### Principles

1. **Simple over complete.** Prefer the 80/20 design. Accept measured
   trade-offs rather than add services or mechanisms.
2. **Local only.** No cloud services for ambient audio or its text.
   Dictation is the one candidate for an exception (see "Cloud ASR").
3. **Built for one system.** Fedora, KDE Plasma on Wayland, PipeWire and
   systemd. No portability layers.
4. **Self-contained.** The repo ships everything it runs: code, units, models,
   defaults. It also builds and runs whisper-server and llama-server on the
   inference host ([ADR-0023](0023-inference-servers.md)). The `machine`
   repo installs the OS packages and configures the daemon.
5. **Six ways to communicate, each in its place.**
   - **Files** between components on one host. Paths and formats are
     documented contracts.
   - **Memory** inside a component: control loops and stream state. A
     component rebuilds its state from files on restart.
   - **One Unix socket** between the keys service and the session service, for
     key events and paste requests that must arrive within milliseconds
     ([ADR-0007](0007-keys-service.md)).
   - **D-Bus** between KWin and the session service, because a KWin script can
     reach other processes only through D-Bus
     ([ADR-0008](0008-shortcuts-and-kwin-script.md)).
   - **rsync over SSH** from a satellite to the base: append-only copies of
     its audio and events, on the tailnet only
     ([ADR-0024](0024-base-and-satellites.md)).
   - **HTTP** from each host to the shared inference servers. No broker in
     between. Inference URLs must be `localhost` or a tailnet address. The
     clients refuse any other host, and the servers listen only on the
     tailnet, so ambient audio never crosses an open network (owner
     decision, 2026-11-23).
6. **Rules for files.**
   - One writer per path.
   - Streams are append-only. Readers consume only complete lines. Single
     files are written to a temporary name and renamed into place.
   - Change notifications wake readers. A directory scan is the source of truth.
   - Each path has an owner that deletes old data.
   - Pending work is derived: input IDs with no output ID yet. No job files.
   - [ADR-0003](0003-filesystem-interface.md) defines roots, paths and formats.
7. **Keep the audio.** Capture writes a rolling audio buffer to disk. All
   consumers read from it. Any stage can run again on stored audio, which also
   gives benchmark data from real use. The stream never closes, so dictation
   never loses its first words to a waking device.
8. **The utterance is the unit.** One utterance is one stretch of speech on one
   channel. Its ID joins all artifacts about it.
9. **Dictation goes first on each host.** Each host queues its work by urgency:
   dictation, then live transcription, then batch work. Across hosts there is
   no priority queue:
   - Dictation speech-to-text runs on its own CPU server on the inference
     host, so it never waits for an ambient whisper request
     ([ADR-0022](0022-dictation-asr.md)).
   - The inference host runs llama-server with 4 parallel slots, so dictation
     cleanup never waits behind the ambient cleanup of other hosts
     ([ADR-0023](0023-inference-servers.md)).
   - Dictation cleanup has a 1 s limit. After it, dictation uses the raw ASR
     text (owner decision, 2026-11-23).
10. **Fast first, accurate later.** A live pass gives text only, within
    seconds. A batch pass reprocesses a finished interaction with full context:
    speaker names from the meeting. It calls no LLM; the brain vault agent
    writes summaries (owner decision, 2026-11-25). Diarization is a later
    per-host extra, not part of v1 (owner decision, 2026-11-23).
11. **One base, many satellites.** The base processes the audio of every
    host. A satellite records, dictates, and sends its audio and events to
    its host root on the base. No locks: each file has one writer
    ([ADR-0024](0024-base-and-satellites.md), replaces "Hosts are
    independent").
12. **Consumers are third parties.** The daemon keeps its own documents and
    copies finished ones to configured target directories, such as a vault
    inbox. It never reads from a target. What syncs a target is outside this
    system.
13. **Split services by lifecycle, not by module.** The keys service runs as root
    from boot, so the keyboard works before login. Capture runs alone, so
    changes elsewhere never cause audio gaps. Session-bound parts (dictation,
    shortcuts) run in the graphical session. The tray icon runs in its own
    unit, so Qt can never delay a mute or a paste. All else can restart
    freely.
    systemd supervises every service
    ([ADR-0004](0004-orchestration-with-systemd.md)).
14. **Python, with two exceptions.** The best speech and audio tools are
    Python libraries. The keys service is C: it is small, runs as root and
    handles key timing ([ADR-0007](0007-keys-service.md)). The KWin script is
    JavaScript, because KWin requires it
    ([ADR-0008](0008-shortcuts-and-kwin-script.md)). Another language needs an
    ADR.

### Services

| Service  | Runs as                  | Job                                                     |
| -------- | ------------------------ | ------------------------------------------------------- |
| keys     | root, from boot          | Remap keys; detect the dictation key; inject paste keys |
| capture  | owner                    | Record mic and system audio to the audio buffer         |
| pipeline | owner                    | Turn audio into transcripts and interaction documents   |
| session  | owner, graphical session | Dictation and global shortcuts                          |
| tray     | owner, graphical session | The tray icon: mode, health, pause and resume           |

### Capabilities

| Capability          | What the owner gets                                                                                          |
| ------------------- | ------------------------------------------------------------------------------------------------------------ |
| Keyboard remapping  | Custom key behavior in every application, from boot.                                                         |
| Ambient recording   | Every host records mic and system audio in the background. Audio is kept for a rolling period.               |
| Live transcript     | A daily log of what was said, within seconds, with notes, pins and meeting changes.                          |
| Dictation           | Hold a key, speak, release: the text appears in the active application. Meetings do not hear the dictation.  |
| Interactions        | Each finished meeting or conversation gets a transcript with meeting speaker names, titled by the meeting.   |
| Publishing          | Finished documents go to configured directories, such as a vault inbox.                                      |
| Benchmarking        | Stored cases compare models, prompts and strategies on real speech, offline.                                 |
| Global shortcuts    | One key chord focuses or launches an app, or runs a window action.                                           |
| Health and control  | A tray icon shows the mode and any problem. Pause stops recording. `odsodctl` can do all that the tray does. |
| Install and upgrade | One command installs or upgrades a host from `main`; a dev deploy runs local work live.                      |

### Flow

```
keyboards ──► keys service ──► remapped keys ──► applications
                  │  ▲
     dictation key│  │paste
                  ▼  │
mic + system audio   │
        │            │
        ▼            │
  audio buffer ──┬──►│dictation ────► active application
                 ├──► live pass ────► daily transcript ───────┐
                 └──► batch pass ───► interaction documents ──┴──► publish ──► targets
                          ▲
                          └── meeting context

benchmark: reads stored audio and results
```

### Detailed ADRs

- [ADR-0003](0003-filesystem-interface.md): files, paths and formats.
- [ADR-0004](0004-orchestration-with-systemd.md): services, units and
  supervision.
- [ADR-0005](0005-components-and-implementation.md): the index of
  components, languages and tools, with the architecture diagram.
- [ADR-0006](0006-installation.md): install.
- [ADR-0007](0007-keys-service.md): the keys service and the dictation socket.
- [ADR-0008](0008-shortcuts-and-kwin-script.md): the shortcuts component and
  the KWin script.
- [ADR-0009](0009-taxonomy-and-code-organization.md): terms, subsystems and
  code organization.
- [ADR-0010](0010-contracts-and-runtime.md): contracts and runtime.
- Subsystem ADRs: [0011 capture](0011-capture.md),
  [0012 speech](0012-speech.md), [0013 dictation](0013-dictation.md),
  [0014 signals](0014-signals.md), [0015 transcript](0015-transcript.md),
  [0016 interactions](0016-interactions.md),
  [0017 publishing](0017-publishing.md), [0018 control](0018-control.md),
  [0019 bench](0019-bench.md).

## Alternatives considered

### Separate repos for the keys service and the daemon

- The keyboard daemon `odsod-keys` lived in the `machine` repo.
- Rejected: dictation depends on it. The socket contract, both of its ends
  and the units must change in one commit.

### Separate tools for recording and dictation

- Two audio feeds and two pipelines. No shared data, no common benchmark set.

### One process with an in-memory audio buffer

- Fast, but audio is lost on restart, nothing can be replayed, and benchmark
  data needs a separate path.

### Local ASR on each laptop

- A local whisper-server on each laptop would work away from the inference
  host.
- Rejected: a model good enough for Swedish and English does not keep up
  with two always-on channels on a laptop CPU. The tailnet reaches the
  inference host from anywhere. With no inference host reachable, ambient
  work waits in files and dictation is off: Left Alt is plain Alt, and the
  tray shows a Warning (owner decision, 2026-11-23).

### Cloud ASR

- Cloud services claim better mixed-language accuracy. Rejected because
  ambient audio must stay local.
- Reopened for dictation only. Dictation is English speech that the owner
  chooses to send, mostly about work. `bench` evaluates a cloud model on
  dictation audio, through the host's ambient Google Cloud credentials. An
  ADR adopts it only if bench data supports it. Dictation then falls back
  to the local path when the credentials are missing or the cloud fails.

### One service per component

- More services to run, with no benefit. Files already give the decoupling.

### Priority broker on the inference host

- An in-memory queue in front of the inference servers would give dictation
  priority across hosts.
- Rejected: one more service. Short whisper requests, 4 llama-server slots
  and the 1 s cleanup limit keep dictation inside its target. If that wait
  still hurts, a second inference server just for dictation is the next
  step. That step is taken: [ADR-0022](0022-dictation-asr.md).

### Diarization in v1

- pyannote on each host would split voices that no meeting names, such as a
  talk in the room.
- Deferred: it brings torch, a Hugging Face token, a model download step and
  hours of CPU on laptops. Meetings already name speakers through their
  speaking indicator. Talks outside a meeting show the owner and "Others"
  until a later per-host extra adds diarization (owner decision,
  2026-11-23).

### Speaker attribution in the live pass

- It needs the live pass to join text with browser events by time, and to wait
  until those events exist.
- Rejected: the batch pass does it better with full context, and the live
  pass stays independent of the browser.

### A language per component

- Lets each part use its best ecosystem, but costs several toolchains and
  duplicated file helpers. For this system, Python is the best ecosystem for
  the hard parts and good enough for the rest. The two exceptions are the
  keys service in C (ADR-0007) and the KWin script in JavaScript
  (ADR-0008).

## Consequences

- Benchmark data builds up as soon as capture runs.
- A component can be rewritten without changes to its neighbors, because
  files and one socket are the only interfaces.
- Raw audio on disk costs space and is sensitive. Retention is a privacy
  decision.
- More moving parts. The filesystem rules must hold, or the design turns into
  a broken message queue.
- More requests per hour of audio than long chunks, so the shared GPU carries
  more load.
- Dictation has its own CPU speech-to-text server, so another host's
  transcription does not delay it (ADR-0022). Under load, dictation can
  paste raw ASR text without cleanup.
- Away from the tailnet, or with the inference host down, there is no
  transcription and no dictation.
- Live text has no speaker names. Names appear when the batch pass finishes.
- Two toolchains: Python and C. The C part stays one small service.
