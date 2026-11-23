# Decisions triage

## Needs the owner

- **`dictation` + `keys`: omit `session` and `keys` from `install.contract.SERVICES` until keyboard cutover.**
  - Why it matters: `odsodctl install` skips `odsod-daemon-session.service`, and `odsodctl status` and the tray do not monitor `session` or `keys`. Dictation will not run or alert until both join `SERVICES`.
  - Recommendation: Accept until you cut over from `odsod-keys.service`, then add both in one commit.

- **`bench`: count `ambient_per_language` per `(channel, language)` stratum (200 ambient cases total).**
  - Why it matters: 50 Swedish and 50 English cases on each of `mic` and `sys` doubles the references you review by hand.
  - Recommendation: Keep per-stratum sampling and lower `ambient_per_language` to 25 in `config.json` if 200 cases is too many.

- **`bench`: measure live dictation latency as `ready_ms` (text-ready) instead of release-to-paste.**
  - Why it matters: `ready_ms` excludes clipboard copy and paste time, so bench cannot verify full `dictation` latency until it reads dictation's timing log.
  - Recommendation: Accept `ready_ms` for the data day and wire the release-to-paste log in a follow-up plan now that `dictation` exists.

- **`capture`: subtract `capture_latency_ms` in the drift formula (default remains `0`).**
  - Why it matters: ADR-0011's formula omits `capture_latency_ms` and would re-anchor on every block once you set a nonzero value after the capture spike.
  - Recommendation: Keep the code's formula, update ADR-0011 to match, and run the capture spike to set `capture_latency_ms`.

- **`capture`: delete an audio hour file when `now - hour_start >= retention_days`.**
  - Why it matters: The last 59 minutes of that hour are deleted up to 59 minutes before they turn 14 days old.
  - Recommendation: Accept as is; it matches ADR-0011 and keeps retention strictly bounded at 14 days.

- **`transcript`: keep the 3-token echo guard in `transcript`, not in `lib.textmatch.overlap`.**
  - Why it matters: `interactions` calls `lib.textmatch.overlap` directly, so short 1 to 2 word owner replies ("Yes", "No", "Okay") get dropped from interaction documents when those words appear in nearby `sys` text.
  - Recommendation: Move the 3-token guard into `lib.textmatch.overlap` as ADR-0015 specifies.

- **`transcript`: keep an open capture gap open across local midnight and write gap lines only on restart.**
  - Why it matters: If you pause or log out before midnight and stay off past 00:01, the day finishes without the pre-midnight gap line, and the morning restart cannot append to the finished file.
  - Recommendation: Close and write the pre-midnight segment at finish time so the daily transcript records the gap.

- **`interactions`: write interaction document front matter as JSON inside `---`.** Resolved 2026-11-23: plain YAML with PyYAML.
  - Why it matters: JSON is valid YAML, but Obsidian and humans see braced JSON instead of clean YAML keys in every interaction note.
  - Recommendation: Accept for now if your vault ingest agent parses it; switch to plain YAML only if Obsidian Properties rejects it.

- **`publishing`: keep `target-missing` active until a document is delivered to that target.**
  - Why it matters: If no new document is pending or you remove the target from config, the Warning stays in the tray until reboot.
  - Recommendation: Clear `target-missing` when the target directory exists on scan (and reset `pipeline.json` on service start).

- **`keys`: resolve a pending Left Alt on key press only, not on key release or repeat.**
  - Why it matters: Releasing an unrelated key while holding Left Alt stays in dictation-pending instead of emitting Alt, which changes typing feel if you overlap keys.
  - Recommendation: Accept and test during the keyboard trial; change only if chords misfire.

- **`keys`: exit 1 when no keyboard is found, but keep running without a socket if bind fails.**
  - Why it matters: Remaps stay alive if `/run/odsod-daemon-keys` breaks, while dictation fails visibly with `keys-socket-missing`.
  - Recommendation: Accept as is; protecting basic typing beats failing the keyboard service for dictation.

- **`signals`: run Teams through speaking-class discovery and test Meet only against synthetic `meet.html`.**
  - Why it matters: Teams waits for 3 speaker toggles on every restart instead of reading a fixed selector, and Meet selectors have not been checked against a live page yet.
  - Recommendation: Accept for now, then save one live Meet page and one live Teams page on the data day.

- **`install-and-control`: restart all Python services on every dev install.**
  - Why it matters: Running `mise run deploy` restarts `capture` and `pipeline` even when nothing changed, creating short recording gaps.
  - Recommendation: Accept as is; dev deploys always load the latest local working copy.

- **`tray`: use simple placeholder SVG shapes for tray icons (including `unknown`).**
  - Why it matters: You see these icons in the Plasma panel all day; they may be hard to tell apart at 16 px.
  - Recommendation: Accept for the data day and refine the SVGs after seeing them in your panel.

## Accept as is

- `audio-fixtures`: name fixture files `<lang>-<work>.wav`.
- `audio-fixtures`: calibrate synthetic noise levels to RMS (-60 and -45 dBFS), not peak.
- `audio-fixtures`: use the third preamble paragraph (1940s translation) for Swedish clip 2.
- `bench`: merge `settings` as host `speech`, then `asr.settings`, then `cleanup.settings`, and store the result in the manifest.
- `bench`: hash both lane prompts (name and bytes, or `builtin`) into the single `prompt_sha256` manifest field.
- `bench`: space sandbox cases sequentially with a 5 s gap so audio never overlaps inside one hour file.
- `bench`: turn `live.json` into a live result for ambient and dictation cases only, leaving interactions for stage 2.
- `bench`: print `{"rows": [...]}` for `bench report --json`.
- `bench`: run the `odsodctl` script next to the running Python interpreter in the sandbox.
- `bench`: keep `bench accept` without `--draft-by` owner-only; smoke tests accept no reference.
- `bench`: report WER and glossary scores as percents rounded to 2 decimals, use nearest-rank percentiles, and show a row as soon as one result exists.
- `bench`: enforce the cloud adapter rule via `adapters.check_contract(adapter, cloud=True)` until a cloud adapter exists.
- `capture`: reset drift history after a seek or drop so the next ten blocks do not carry the old step.
- `capture`: write no record for dropped blocks; write a `clock` gap only for seek-forward holes of 1 s or more.
- `capture`: trim the front of overlapping blocks and skip blocks before current file size so audio never writes backward.
- `capture`: retry a self-exiting `pw-record` after `stall_restart_s`, and restart stalled processes right after timeout.
- `capture`: write `stop` only on clean shutdown and only for channels that wrote audio in this run.
- `capture`: mark `capture` with `WATCHDOG_OWNER` so `services/runner.py` leaves `WATCHDOG=1` pings to capture.
- `capture`: treat an unknown mute state (broken `pactl`) as not muted so it never hides `mic-silent`.
- `capture`: set `mic-muted` `since` to first mute observation and `mic-silent` `since` to first zero block.
- `capture`: keep fake `pw-record` and `pactl` scripts in `components/capture/tests/bin/` for system tests and in-process fakes for component tests.
- `capture`: accept float seconds in `CaptureConfig` instead of ints so system tests can use sub-second timeouts.
- `capture`: add `capture` to `install.contract.SERVICES` before its unit template landed (template now exists).
- `dictation`: run desktop subprocess tests in real time while hold timers and clipboard restore use virtual time.
- `dictation`: start each hold's text wait immediately while keeping clipboard delivery in hold order.
- `dictation`: give Python `pactl` fakes a 2 s mute budget in system tests while production keeps 150 ms.
- `dictation`: derive expected units in health tests from `install.contract.SERVICES`; defer live hardware trial to the owner.
- `inference-recordings`: store recordings flat in `testdata/*.json` and filter by request path.
- `inference-recordings`: store Whisper multipart bodies as fields plus file metadata (name, content type, SHA-256, bytes) and Llama bodies as JSON.
- `inference-recordings`: use a missing file for the Whisper 400 pair because bogus field values return 200 or 500.
- `inference-recordings`: measure `chunk_chars` against the 2,048 output-token client default.
- `install-and-control`: omit `Restart=always` on oneshot helpers and omit `OnFailure` on the notify unit to prevent recursion.
- `install-and-control`: follow ADR-0006 for target membership and pipeline enablement where ADR-0004 is broader.
- `install-and-control`: start backlog from the oldest present current/previous-hour audio file when no coverage record exists yet.
- `interactions`: fail an attempt when a single transcript line exceeds `chunk_chars` rather than splitting mid-line.
- `interactions`: exit `--once` when power, pending speech, or host availability blocks the gate, while waiting through bounded model-error retries.
- `interactions`: resolve local document timezone from `TZ`, falling back to `/etc/localtime`.
- `interactions`: seed signals and transcript records directly in the interactions system test.
- `keys`: add `repeat` to `out key` in the `.seq` test grammar so forwarded key repeats are tested.
- `keys`: set socket ownership via `ExecStartPre` `chown <uid>:<gid> /run/odsod-daemon-keys` and read directory ownership in `io.c`.
- `keys`: take notify unit `User=` from `SUDO_USER` (else passwd entry of `SUDO_UID`) and gid from `SUDO_GID` (else primary gid).
- `keys`: ignore a second `paste` while one is already waiting.
- `keys`: end an active dictation when a new socket peer connects.
- `keys`: release held output keys in key-code order on escape chord and `SIGTERM`.
- `keys`: open devices without a grab in `--record` mode and tell the owner to stop the keys service first.
- `keys`: keep `system.py` tested directly while CLI wiring lives in install-and-control (now wired).
- `keys`: compile C code in `mise run keys:compile` and replay `.seq` fixtures in `mise run build` without committing binaries.
- `keys`: require `gcc` and Linux input headers for `mise run build` on host and CI.
- `publishing`: write a target's `start` and `since` on the first `publish --once` run.
- `publishing`: treat a finished record with `ts == since` as pending ("at or after").
- `python-scaffold`: add `pytest-asyncio` to the dev group because `looptime` needs it.
- `python-scaffold`: exclude `docs/` and `legacy/` from ruff.
- `python-scaffold`: delete `.github/workflows/release.yaml` and `.goreleaser.yml` as orphans.
- `python-scaffold`: export `CONFIG_MODEL` and `run(config, *, once=False)` from component `__init__.py` modules.
- `python-scaffold`: discover config models for `odsodctl config check` by importing components and reading `CONFIG_MODEL`.
- `python-scaffold`: store inference fake pairs as `{request, response}` JSON (path layout superseded by `inference-recordings`).
- `python-scaffold`: omit `gcc` as a mise tool (system `gcc` is used instead).
- `python-scaffold`: leave `README.md` update for a later plan.
- `signals`: break equal-length discovery ties by lexicographically smallest class name for determinism.
- `signals`: record speaking stop `at` as last seen speaking time plus one poll period (matching ADR-0014).
- `signals`: emit `cause: tab-closed` when a meeting tab navigates to a different meeting code.
- `signals`: resume an open meeting on restart only when the first poll sees the same platform, code, and at least one tile; otherwise emit `cause: restart`.
- `signals`: use process start as `at` for both the restart `meeting-end` and the empty `speaking` record before it.
- `signals`: strip common Meet and Teams prefixes/suffixes from tab titles.
- `signals`: clear stale `no-speaking-indicator` faults at startup.
- `signals`: reload `run/health/pipeline.json` before each mutation so other pipeline faults stay intact.
- `signals`: write `participants` only after the set is stable for `participants_stable_s` (5 s).
- `signals`: run fake CDP on two ephemeral `127.0.0.1` ports (HTTP for `/json/list`, WebSocket for `Runtime.evaluate`).
- `signals`: use a 5 s timeout for `/json/list` from the Go client.
- `signals`: run one tab poll and one speaking poll in `odsodctl run signals --once`.
- `signals`: run Chrome tests in `mise run build` when Chromium is present and skip when absent.
- `speech`: read ambient utterance ends as well as coverage on restart to close the crash window.
- `speech`: ship the Silero ONNX model as package data with its MIT license.
- `speech`: back `lib.clock.monotonic()` with the running event loop clock so virtual backoff works in tests.
- `speech`: exit non-zero after 60 s on battery deferral in `--once` mode, leaving work pending.
- `speech`: drain components sequentially in composition order for `run <service> --once`.
- `speech`: write hourly PCM directly in the speech system test fake.
- `speech`: check restart equivalence via one-to-one interval overlap above 95% with equal counts and no duplicate IDs.
- `transcript`: measure echo hold age from the text record `ts` so restarts do not reset the hold cap.
- `transcript`: order replay records by write `ts` with stable stream order for ties, appending held lines on release and gap lines on closure.
- `transcript`: print empty Markdown and an empty JSON lines list for a missing day.
- `transcript`: parse repeated DST wall-clock hours as the first occurrence.
- `transcript`: test `finished/transcript/` as the seam without starting `publish`.
- `tray`: include an icon for `unknown` so every `StatusReport.state` has a file.
- `tray`: format new tray Error notifications with title `odsod-daemon: <service>`, body `<message> <fix>`, critical urgency, and skip `unit-failed`.
- `tray`: re-evaluate tray state on any `mode` or `keys` change in `run/status.json`.
- `tray`: support `odsodctl run tray --once` to evaluate once and exit.

## Conflicts

- **`transcript` plan vs ADR-0015 (3-token echo guard):** ADR-0015 puts the `< 3` token guard inside `lib.textmatch.overlap(a, b)` so `transcript` and `interactions` share it. The `transcript` plan kept the guard in `transcript/echo.py`, leaving `interactions` without it.
- **`capture` plan vs ADR-0011 (drift formula):** ADR-0011 defines drift as `arrival - expected end` without subtracting `capture_latency_ms`. The `capture` plan subtracts `capture_latency_ms` so nonzero latency does not re-anchor every block.
- **`dictation` + `keys` plans vs `capture` plan, ADR-0006, and ADR-0018 (`SERVICES`):** `capture` and `install/contract.py` require adding each built service to `SERVICES` in the same commit, and ADR-0006/ADR-0018 expect `session` and `keys` to be installed and monitored. `dictation` and `keys` omit both from `SERVICES` until the keyboard cutover.
- **`transcript` plan vs ADR-0015 (open capture gap across midnight):** ADR-0015 says a gap crossing local midnight writes one line in each day. The `transcript` plan writes gap lines only on capture restart, so the pre-midnight line is lost if the day finishes before capture restarts.
- **`interactions` plan vs `transcript` / ADR-0015 (local time zone):** `interactions` reads `TZ` before `/etc/localtime`, while `transcript` reads only `/etc/localtime`. Setting `TZ` splits their local day boundaries.
- **`python-scaffold` plan vs `inference-recordings` plan (`testdata` layout):** `python-scaffold` put recordings in `lib/inference/testdata/{whisper,llama}/`; `inference-recordings` moved them flat into `testdata/*.json` (current code uses flat).
- **`keys` plan vs ADR-0007 (`.seq` grammar):** ADR-0007 allows only `down|up` on `out key`; the `keys` plan added `repeat`.
- **`bench` plan vs ADR-0019 (`prompt_sha256`):** ADR-0019 defines `prompt_sha256` as the hash of the rendered cleanup prompt; the `bench` plan hashes the unrendered bytes (or `builtin`) of both lane prompts.
- **`capture` plan vs ADR-0011 (config types):** ADR-0011 shows integer seconds in `capture` config; the `capture` plan uses floats.
- **`install-and-control` plan vs ADR-0004 (target membership):** ADR-0004 describes units under `default.target`; the plan follows ADR-0006 (`odsod-daemon.target` and `graphical-session.target`).
