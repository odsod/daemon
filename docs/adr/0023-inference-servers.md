# ADR-0023: Inference servers

## Status

Accepted. Changes [ADR-0002](0002-high-level-architecture.md) principle 4,
[ADR-0006](0006-installation.md), [ADR-0012](0012-speech.md) and
[ADR-0016](0016-interactions.md) where they say that the `machine` repo
runs whisper-server and llama-server.

## Date

2026-11-24

## Context

- The daemon tunes the inference servers for its own work. It runs Parakeet
  for dictation ([ADR-0022](0022-dictation-asr.md)). Cleanup is the only
  user of llama-server, and its 1 s dictation limit depends on the server
  flags.
- Bench (2026-11-24, n-gram speculation in llama-server, cleanup cases):

  | llama-server flags         | Cleanup p50 | Cleanup max |
  | -------------------------- | ----------- | ----------- |
  | Today's flags              | 576 ms      | 1542 ms     |
  | `--spec-type ngram-simple` | 303 ms      | 632 ms      |

  With speculation, no dictation case went over the 1 s limit.

- Until now the `machine` repo owned both servers end to end: ROCm
  packages, source tarball, cmake build, model download, unit file and
  flags. Each tuning change needed a pull request in a second repo, and
  the daemon's ADRs could not state the setup they depend on.
- The `machine` repo pulled the LLM from `resolve/main`, so the model was
  not pinned.
- The live llama-server runs 4 slots over one unified KV cache of 32,768
  tokens (`/slots`, 2026-11-24). ADR-0002, ADR-0012 and ADR-0016 said 2.
- Owner decision (2026-11-24): the daemon owns everything except OS
  packages. The `machine` repo keeps only the dnf packages for ROCm and
  cmake.

## Decision

### Purpose

- The daemon builds, configures and runs whisper-server and llama-server on
  the inference host. One pull request in this repo changes a server
  version, a model or a flag.
- Clients do not change: the ports, the paths and the host binding stay as
  they were. Other hosts reach the servers through `common.inference`.
- PRDs: [install-and-upgrade](../prd/install-and-upgrade.md) (AC-17),
  [health-and-control](../prd/health-and-control.md) (AC-17).

### Components

| Component | Service or command                                                             | Job                                                    |
| --------- | ------------------------------------------------------------------------------ | ------------------------------------------------------ |
| `servers` | `odsodctl inference setup`; units `odsod-daemon-whisper`, `odsod-daemon-llama` | Pin sources, flags and models; get and build them once |

- `servers/pins.py` holds the pins. A version bump is a pull request that
  edits it. No task discovers or bumps a version.
- `servers/contract.py` holds the `inference` config model and the facts
  that install and control read: unit names, binary and model paths, and
  the fixed flags.
- The servers are C++ programs from upstream. The daemon runs them as user
  units, not as Python services.

### Pins

| Item                     | Version or revision                     | SHA-256 (start)    | Bytes         |
| ------------------------ | --------------------------------------- | ------------------ | ------------- |
| whisper.cpp source       | tag `v1.9.5`                            | `ff1a9053feb509ff` | 9 626 464     |
| llama.cpp source         | tag `v1.0.0-b12359-b1b770d`             | `79465cbc4d52f8d9` | 38 899 849    |
| `ggml-large-v3.bin`      | `ggerganov/whisper.cpp` at `5359861c`   | `64d182b440b98d52` | 3 095 033 483 |
| `Qwen3.5-9B-Q5_K_M.gguf` | `unsloth/Qwen3.5-9B-GGUF` at `3885219b` | `dc2a39aef291f91a` | 6 577 841 376 |

- The Silero VAD ggml model is gone: whisper-server runs without `--vad`
  (ADR-0012).

### Writes

| Path                                 | Holds                                                        |
| ------------------------------------ | ------------------------------------------------------------ |
| `state/servers/<project>-<version>/` | Source tree and `build/`; one tree per version               |
| `state/models/<file>`                | The two models (ADR-0003 already lists `state/models/`)      |
| User units (through install)         | `odsod-daemon-whisper.service`, `odsod-daemon-llama.service` |

### Reads

- Config section `inference`.
- `$XDG_DATA_HOME/odsod/machine/data/{whisper,llama}/`: models that the
  `machine` repo downloaded, adopted once.

### Outside dependencies

- OS packages from the `machine` repo: `cmake`, `gcc-c++`, `hipblas-devel`,
  `hipcc`, `rocblas-devel`, `rocm-hip`.
- The AMD GPU of the inference host (gfx1200).
- GitHub for the tarballs and Hugging Face for the models, at setup only.
- `lib.download` (stream, SHA-256 check, rename), shared with parakeet.

### Internal design

#### `odsodctl inference setup [--check]`

Runs as the owner, with no root. Each run:

1. Inspect each server: model present at its pinned size, model in the
   `machine` data dir, source tree present, binary present. A pure core
   turns this into steps: `adopt`, `download-model`, `download-source`,
   `build`.
2. Print one state line per server. `--check` stops here.
3. If a build is due and `cmake`, `hipcc` or `g++` is missing, exit 1
   before any change. The message names the packages and says that the
   `machine` repo installs them.
4. Adopt: hash the old model file. On a match, move it into
   `state/models/`, so the host never downloads 9 GB again. On a
   mismatch, download.
5. Download a missing model or tarball with `lib.download`. Unpack the
   tarball into a staging folder (`tarfile`, filter `data`), then rename
   its top folder into place and delete the tarball.
6. Build only the server target, and only when its binary is missing:

   ```sh
   cmake -B build <flags>
   cmake --build build --target <whisper-server|llama-server> -j<nproc>
   ```

   - Flags for both: `-DGGML_HIP=ON -DCMAKE_HIP_ARCHITECTURES=gfx1200
     -DGGML_NATIVE=ON -DCMAKE_BUILD_TYPE=Release`.
   - whisper adds `-DWHISPER_BUILD_SERVER=ON`.
   - llama adds `-DLLAMA_BUILD_NUMBER=12359`. A tarball has no Git
     history; without the number, llama.cpp asks for web UI assets of
     build 0, which do not exist.

7. Print what changed, or "nothing to do".

- A second run changes nothing. A new pin gives a new tree, so the old
  binary keeps serving until the next install.

#### Units

Rendered by `odsodctl install` (ADR-0006) only when `inference.enabled` is
true and both binaries and both models exist.

```ini
[Unit]
OnFailure=odsod-daemon-notify@%n.service

[Service]
Type=simple
ExecStart=<binary> --model <model> --port <port> <flags> <extra_args>
Restart=on-failure
RestartSec=5

[Install]
WantedBy=odsod-daemon.target
```

| Server  | Port | Flags                                                                                                                                                                                                                        |
| ------- | ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| whisper | 8178 | `--host 0.0.0.0 --language auto --suppress-nst --convert --inference-path /v1/audio/transcriptions`                                                                                                                          |
| llama   | 8179 | `--host 0.0.0.0 --ctx-size 32768 --n-gpu-layers 99 --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 --reasoning off --parallel 4 --kv-unified --spec-type ngram-simple --spec-ngram-simple-size-n 2 --spec-ngram-simple-size-m 32` |

- `--parallel 4` keeps the slot count the server ran with before. It is
  now explicit.
- `--kv-unified` keeps one shared cache for the 4 slots. llama-server
  shares the cache only when the slot count is automatic. With an explicit
  count, each slot gets 8,192 tokens. Cleanup is the only user now
  (interactions call no LLM, ADR-0016), and no cleanup request needs more
  than one slot's share. The shared cache is a safe default.
- `--host 0.0.0.0` stays as before. Binding to loopback and the tailnet
  only is a later change.

#### Restarts

- `install/current` gets one digest per server: the SHA-256 of its binary
  ([ADR-0020](0020-hot-deploy.md)).
- A server restarts only when its digest or its unit file changed. The
  unit file holds the port and `extra_args`, so a config change restarts
  that server.
- A daemon code change restarts no server, so a deploy never reloads a
  model.

#### One owner

- With `inference.enabled` true, `odsodctl install` refuses while the
  `machine` repo's `llama-server.service` or `whisper-server.service` is
  active. It changes nothing and prints:
  - cutover: `systemctl --user disable --now llama-server whisper-server`,
    then `odsodctl install`;
  - rollback: `systemctl --user disable --now odsod-daemon-llama
    odsod-daemon-whisper`, then `systemctl --user enable --now
    llama-server whisper-server`.
- With `inference.enabled` false, or the files missing, install renders no
  server unit. It removes one that exists, after `disable --now`.

#### Health

- control expects `odsod-daemon-whisper` and `odsod-daemon-llama` only on a
  host with `inference.enabled` (`components/health/units.py`). A failed or
  down unit is Error, with `systemctl --user restart odsod-daemon-<name>`
  as the fix.
- The servers write no health file. Clients keep reporting
  `inference-unreachable` (ADR-0012).

### Failure modes

| Fault                                | What happens                                                  | Code / signal                     |
| ------------------------------------ | ------------------------------------------------------------- | --------------------------------- |
| Build tools missing                  | `setup` exits 1 before any change; names the packages         | exit 1                            |
| Download fails or hash differs       | `setup` deletes the partial file and exits 1; a rerun resumes | exit 1                            |
| Old model in the machine dir differs | `setup` keeps it and downloads the pinned file                | message                           |
| Build fails                          | `setup` exits 1; the next run builds again, with no download  | exit 1                            |
| Machine server unit still active     | `install` refuses and prints cutover and rollback             | exit 1                            |
| Inference on, setup not done         | No server unit; `install` says to run `setup`                 | control: unit missing (Error)     |
| Server crashes                       | systemd restarts it after 5 s                                 | `OnFailure` notify; control Error |
| Server up but not answering          | Clients wait and retry                                        | `inference-unreachable` (Warning) |

### Config

```json
{
  "inference": {
    "enabled": true,
    "whisper": { "port": 8178, "extra_args": [] },
    "llama": { "port": 8179, "extra_args": [] }
  }
}
```

- Defaults: `enabled: false`, ports 8178 and 8179, no extra arguments.
- Only the inference host sets `enabled: true`. Laptops stay clients.
- `extra_args` go last on the command line, for a trial without a code
  change. A flag that stays belongs in `contract.py`.

### Tests

| Test                                                                                   | Checks                      |
| -------------------------------------------------------------------------------------- | --------------------------- |
| Table tests of the step core, the state lines and the tool check                       | Setup logic                 |
| Fresh host: setup downloads from a local file server, builds with a fake `cmake`, once | Idempotent setup            |
| A matching old model is moved, a different one is kept and the pin is downloaded       | Adoption                    |
| `--check` downloads, builds and writes nothing                                         | `--check`                   |
| Missing tools stop setup before any download                                           | Failure modes               |
| A bad tarball hash leaves no tree; a failed build reruns the build only                | Failure modes               |
| Server units render only with inference on and setup done                              | Units                       |
| A deploy with no server change restarts no server; a new binary restarts that one      | `install-and-upgrade` AC-17 |
| An active machine unit makes install refuse and print the commands                     | One owner                   |
| control expects the server units only with inference on; a failed one is Error         | `health-and-control` AC-17  |

### Build without hardware

- Everything above runs in CI: a local HTTP file server serves small fake
  tarballs and models, and fake `cmake`, `hipcc` and `g++` sit on `PATH`.
- A real build, the GPU, the model load and the speed gain need the owner's
  inference host: the cutover in
  [the plan](../plans/2026-11-24-inference-servers.md) and the bench rerun.

## Consequences

- One pull request in this repo changes a server version, a model or a
  flag. The ADRs state the server setup they depend on.
- The model download is pinned and hash-checked. A bump of a model is a
  code change.
- The inference host needs one manual step: `odsodctl inference setup`.
  A build takes several minutes; a new pin needs it again.
- A normal deploy restarts no server, so it never reloads 9 GB of models.
- The `machine` repo loses its `llama/` and `whisper/` folders. It keeps
  the OS packages.
- `state/` on the inference host grows by about 10 GB of models and the
  build trees.

## Alternatives considered

### Keep the servers in the `machine` repo

- No change.
- Rejected: two repos for one tuning change, and an unpinned LLM.

### Download prebuilt binaries

- No compiler on the host, faster setup.
- Rejected: a prebuilt HIP binary must match the host's ROCm version and
  GPU. The `machine` repo already built from source with the host's ROCm,
  and that build works today.

### Containers (llama.cpp ROCm images)

- Rejected: one more runtime to install, GPU device passthrough, and images
  of several GB. The servers are single binaries.

### Run the servers from a Python service

- One more process level that restarts with daemon code.
- Rejected: a server restart reloads its model. A unit that runs the binary
  restarts only when the binary or the unit changes.

### Discover and bump versions automatically

- Out of scope. A bump is a pull request that edits `servers/pins.py`.
