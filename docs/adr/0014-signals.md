# ADR-0014: Signals

## Status

Proposed

## Date

2026-11-23

## Context

- The owner's meetings run in the browser: Google Meet first, then
  Microsoft Teams. The meeting page knows who takes part and who speaks now.
  Audio alone does not.
- Interaction documents need meeting speaker names (`interactions` AC-3,
  AC-4) and meeting fields that let the ingest agent match two hosts
  (`interactions` AC-13, AC-14). The live transcript marks each meeting
  start and end (`live-transcript` AC-8). Interaction boundaries split at a
  meeting change (`interactions` AC-2).
- The Go recorder already reads these signals over the Chrome DevTools
  Protocol (CDP). It finds the CSS class of the speaking indicator by
  snapshot diffing, confirms it by toggles, and debounces flicker. This
  works today. This ADR ports it and fixes its output as a stream.
- [ADR-0010](0010-contracts-and-runtime.md) fixes the seam fields of
  `events/signals/`. [ADR-0009](0009-taxonomy-and-code-organization.md)
  rule 3 puts the browser in this subsystem only.

## Decision

### Purpose

- Turn the meeting tabs of the owner's browser into a stream of meeting
  events: meeting start and end, the participant set, and who speaks now.
- PRDs: `live-transcript` (meeting lines, AC-8), `interactions` (boundaries
  AC-2, speaker names AC-3 and AC-4, meeting fields AC-13 and AC-14),
  `health-and-control` (the Warning for a missing speaking indicator).
- Speaker names are best effort. A missing or wrong name never blocks a
  document (`interactions` "Behavior").

### Components

| Component | Service    | Job                                                    |
| --------- | ---------- | ------------------------------------------------------ |
| `signals` | `pipeline` | Poll meeting tabs over CDP and write `events/signals/` |

- No commands. `odsodctl run signals` runs it alone for debugging.
- Signals runs in `pipeline` because it needs no session lifecycle of its
  own and is cheap (ADR-0010 "Services").

### Writes

| Path                                  | Kind     | Owner of the model                      |
| ------------------------------------- | -------- | --------------------------------------- |
| `state/events/signals/<day>.jsonl`    | Stream   | `components/signals/contract.py`        |
| `run/health/pipeline.json` (one code) | Document | the pipeline service (`lib/healthfile`) |

Records, with fields beyond the seam marked _extra_:

| Kind            | Seam fields                 | Extra fields                                                                 |
| --------------- | --------------------------- | ---------------------------------------------------------------------------- |
| `meeting-start` | `platform`, `code`, `title` | `url` (tab URL without query), `at` (time the meeting was seen)              |
| `meeting-end`   | `platform`, `code`          | `at` (time the meeting went away), `cause` (`left`, `tab-closed`, `restart`) |
| `participants`  | `platform`, `code`, `names` | none                                                                         |
| `speaking`      | `platform`, `code`, `names` | `at` (time the change took effect)                                           |

- `ts` is the write time (ADR-0010). `at` is the time of the change. The
  debounce makes `ts` up to 2.5 s later than `at`. Readers that need
  precise overlap use `at`, and fall back to `ts` when it is missing.
- `names` lists are sorted, so equal sets give equal records.
- Signals writes `participants` and `speaking` only when the set changes.
  It writes an empty `speaking` before each `meeting-end`, so the state
  never leaks past the meeting (ADR-0010 notes).
- The owner's own tile is in `names`, under the name the platform shows.
  Signals does not know the owner. interactions maps the owner's names.
- Fault: `no-speaking-indicator` (Warning), see "Failure modes".

### Reads

- Chrome's CDP HTTP endpoint `http://127.0.0.1:<port>/json/list` and the
  tab WebSocket. Only `localhost`.
- Its own stream `events/signals/` for today and yesterday (UTC), at start,
  to rebuild the open meeting. This is its own output, not a seam.
- `config/config.json`, section `signals`.
- It reads no other stream. It needs no audio and no text.

### Outside dependencies

- Chrome or Chromium with `--remote-debugging-port` and a non-default
  `--user-data-dir`. Chrome 136 and later ignore the port on the default
  profile. The `machine` repo owns the launch setup (ADR-0005).
- The DOM of Meet and Teams. It changes without notice. This is the main
  risk of this subsystem.
- Libraries: `httpx` (tab list), `websockets` (CDP), `pydantic`.

### Internal design

#### Module layout

```
components/signals/
├── __init__.py        SUBSYSTEM = "signals"; run(config)
├── contract.py        MeetingStart, MeetingEnd, Participants, Speaking
├── config.py          SignalsConfig
├── cdp.py             tab list over HTTP; Runtime.evaluate over WebSocket
├── platforms/
│   ├── base.py        Platform protocol: match, meeting code, JS, parse
│   ├── meet.py        Meet URL rule, code rule, snapshot and poll JS
│   ├── teams.py       Teams URL rule, code rule, snapshot and poll JS
│   └── js/            *.js expressions, loaded as package data
├── discovery.py       speaking-class discovery (pure, no I/O)
├── debounce.py        speaker debounce (pure, no I/O)
├── meeting.py         meeting state machine (pure, no I/O)
├── collector.py       the loop: poll, feed the pure parts, write records
└── tests/
```

- `discovery`, `debounce` and `meeting` are pure. They take samples and a
  time and return changes. The tests drive them with no browser.
- The JavaScript is in `.js` files, not in Python strings, so a DOM fix is
  a one-file change.

#### Meeting detection

- Every `tab_poll_s` (2 s), list the tabs on each configured port. A tab is
  a candidate when its type is `page` and a platform matches its URL:
  - Meet: host `meet.google.com`, path `/<xxx-xxxx-xxx>`.
  - Teams: host `teams.microsoft.com` or `teams.live.com`.
- More than one candidate: take the first one in port and list order. The
  owner is in one meeting at a time.
- A candidate is a meeting only when the page shows at least one
  participant tile. The lobby and the "you left" page have none. This
  avoids meetings that the owner only opened.
- Meeting code:
  - Meet: the path, such as `abc-defg-hij`. Two hosts in one meeting get
    the same code (`interactions` AC-14).
  - Teams: the thread ID from the URL when the URL has one
    (`19:meeting_…@thread.v2`). Otherwise a slug of the tab title, prefixed
    `title:`. The Teams web client often hides the meeting ID. A title slug
    still matches across hosts when the meeting has a name.
- Title: the tab title, with the platform prefix removed (`Meet – `).
  Falls back to the code.
- States of `meeting.py`:

```
idle ──(tiles seen in a matching tab)──► active ──(no tiles for end_grace_s, or tab gone)──► idle
                                           │
                                           └──(code changes)──► meeting-end, then meeting-start
```

- `end_grace_s` (10 s) stops a reload or a short DOM glitch from splitting
  a meeting. A tab that goes away ends the meeting at once.
- `live-transcript` AC-8 allows 30 s from join or leave to the line.
  Detection takes at most `tab_poll_s` plus `end_grace_s`, so 12 s, plus the
  transcript's own delay.

#### Speaking-class discovery

The Go recorder's method, kept as is:

1. Snapshot: for each participant tile, the name and the set of CSS classes
   of all elements in the tile.
2. Diff two snapshots in a row. Take the shortest class that changed on any
   tile as the candidate.
3. Count the toggles of the candidate: present on some tile, then absent,
   then present. At `toggles_required` (3), the class is confirmed.
4. From then on, poll with the cheap expression: per tile, name and
   whether the tile holds an element with that class.

- A confirmed class is kept in memory per platform, across meetings, until
  it fails (see below) or the process ends. A restart rediscovers it in
  seconds once people speak.
- Name rule (Meet, from the Go code): the first `.notranslate` text in the
  tile that has 3 to 49 characters, starts with a capital letter and has a
  space. Tiles with no name are left out.
- The poll expression checks the class name against `^[A-Za-z0-9_-]+$`
  before it builds JavaScript from it.

#### Speaker debounce

- Poll every `speaking_poll_ms` (250 ms) while a meeting is active.
- A speaker starts when seen speaking in `start_samples` (2) polls within
  `start_window_ms` (1500 ms). `at` is the time of the first of those
  samples.
- A speaker stops when not seen speaking for `stop_grace_ms` (2000 ms).
  `at` is the last time seen speaking plus one poll period.
- After each poll, if the set of active speakers changed, write one
  `speaking` record with the new set.
- These values come from the Go recorder, where they filter Meet's short
  indicator flashes. Bench data on `interactions` AC-4 tunes them.

#### Participants

- The participant set is the names of all tiles in the last poll.
- Write `participants` when the set has differed from the last written set
  for `participants_stable_s` (5 s). Tiles come and go while the grid
  scrolls or loads; the delay stops that churn.
- Meet shows only tiles that fit the grid. Large meetings give a partial
  set. This is accepted: the set holds everyone who was visible, and the
  speaking indicator brings a speaker's tile into view on Meet.

#### Restart

- At start, read today's and yesterday's `events/signals/`. The last
  `meeting-start` with no later `meeting-end` is the open meeting, with its
  last `participants` and `speaking` sets.
- On the first poll:
  - The same meeting is still active: write nothing new. Continue with the
    sets from the file, so a set that did not change gives no record.
  - It is gone: write an empty `speaking` (if the last set was not empty)
    and a `meeting-end` with `cause: restart` and `at` set to the start of
    this process.
- No record is ever written twice for one change, and a meeting never has
  two open starts (`live-transcript` AC-8, `interactions` AC-2).

#### Cost

- Outside a meeting: one HTTP request per port every 2 s.
- In a meeting: one `Runtime.evaluate` every 250 ms on one open WebSocket.
  The poll expression is a few DOM queries. This is below 1% of one core
  in the Go recorder.

### Failure modes

| Fault                                      | What signals does                                                                           | Fault code              |
| ------------------------------------------ | ------------------------------------------------------------------------------------------- | ----------------------- |
| Chrome not running, or port closed         | Treat as "no meeting". If a meeting was active, end it (`cause: tab-closed`). Log once      | none                    |
| WebSocket drops                            | Reconnect on the next tab poll. If the tab is gone, end the meeting                         | none                    |
| `Runtime.evaluate` error or bad JSON       | Skip this poll. After 10 failures in a row, reset discovery for the tab                     | none                    |
| No class confirmed for 5 min in a meeting  | Keep discovery running. Report the fault                                                    | `no-speaking-indicator` |
| Confirmed class shows no speaker for 5 min | Drop the class, go back to discovery, report the fault                                      | `no-speaking-indicator` |
| DOM change hides names                     | Tiles without a name are skipped. If no tile has a name, the meeting looks idle: no records | none                    |
| Unexpected exception                       | Ends the pipeline process. systemd restarts it (crash-only, ADR-0004). Restart rule above   | none                    |

- `no-speaking-indicator` applies only while a meeting is active with at
  least 2 participant tiles, so a meeting where the owner waits alone gives
  no Warning. The fault clears on the next confirmed speaker or at
  `meeting-end`.
- Fault message: "Meeting tab open, no speaking indicator for 5 min
  (`<platform>` UI change?)". `fix` is null: no command fixes a UI change.
- A silent meeting of 5 min with 2 or more people also triggers the
  Warning. This is rare and accepted; the Warning clears when someone
  speaks.
- Speaker names that are wrong do not show as a fault. Bench measures them
  (`interactions` AC-4).

### Config

Section `signals`:

```json
{
  "signals": {
    "cdp_ports": [9222],
    "platforms": ["meet", "teams"],
    "tab_poll_s": 2,
    "speaking_poll_ms": 250,
    "start_samples": 2,
    "start_window_ms": 1500,
    "stop_grace_ms": 2000,
    "toggles_required": 3,
    "end_grace_s": 10,
    "participants_stable_s": 5,
    "no_indicator_after_s": 300
  }
}
```

- An empty `cdp_ports` turns signals off. Then the pipeline writes no
  signals and documents use "Others" for all `sys` lines.
- The host of the CDP endpoint is fixed to `127.0.0.1`. It is not a config
  value, so a typo can never point it at another host.

### Tests

Component tests in `components/signals/tests/`. No browser.

| Test                           | Fixture                                                                                                          | Checks                                            |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| `test_discovery.py`            | Snapshot sequences in `testdata/discovery/*.json`: real Meet and Teams snapshots, layout-only changes, 3 toggles | Confirms the speaking class, never a layout class |
| `test_debounce.py`             | Sample timelines with flashes of one poll, overlaps of two speakers, silence                                     | `interactions` AC-4 (input quality)               |
| `test_meeting.py`              | Tab lists: lobby, join, reload, code change, tab closed                                                          | `live-transcript` AC-8, `interactions` AC-2       |
| `test_codes.py`                | Meet and Teams URLs and titles                                                                                   | `interactions` AC-13, AC-14                       |
| `test_collector.py`            | Fake CDP (below), fake clock, temp state root                                                                    | Record sequence and fields; one write per change  |
| `test_restart.py`              | A signals stream with an open meeting; fake CDP with and without the tab                                         | No double start; `meeting-end` on restart         |
| `test_health.py`               | Fake CDP with tiles and no class change for 5 min                                                                | `health-and-control` (Warning cause)              |
| `test_js.py` (marked `chrome`) | Saved Meet and Teams DOM pages in `testdata/dom/*.html`, loaded in headless Chromium                             | The JS expressions parse the saved DOM            |

- The fake CDP server lives in `components/signals/tests/conftest.py`
  (ADR-0010: a fake for an outside system that one subsystem uses lives in
  that subsystem). It serves `/json/list` and a WebSocket that answers
  `Runtime.evaluate` from a script of snapshots and polls, by time.
- `test_js.py` runs only where Chromium is installed (`pytest -m chrome`).
  `mise run build` skips it when Chromium is missing.
- System test (root `tests/`): signals, transcript and interactions on one
  temp root, with the fake CDP. Checks that a scripted meeting gives meeting
  lines in the transcript and named `sys` lines in the document
  (`live-transcript` AC-8, `interactions` AC-3).

### Build without hardware

- An agent can build and test all of it: the pure parts, the collector
  against the fake CDP, and the JS against saved DOM pages in headless
  Chromium.
- The owner must:
  - save fresh DOM pages of a live Meet and Teams call (a helper,
    `uv run components/signals/tests/save_dom.py --port 9222`, writes them
    to `testdata/dom/`), when the platform UI changes;
  - check AC-8 by hand in a real call (`live-transcript` AC-8 is manual);
  - give the bench the speaker references for `interactions` AC-4.

## Alternatives considered

### Meeting platform APIs (Google Meet REST API, Microsoft Graph)

- Give participants and sometimes the meeting title, with stable IDs.
- Rejected: they need OAuth per employer tenant, give no live speaking
  state, and send meeting data through a cloud API. CDP is local and gives
  the speaking indicator.

### A browser extension

- Reads the DOM with no debug port, and gets events instead of polls.
- Rejected: one more artifact to build, sign and install per browser, and
  it needs a channel to the daemon. The debug port already works in the Go
  recorder.

### Fixed CSS selectors for the speaking indicator

- Simpler than discovery.
- Rejected: Meet uses generated class names that change with each release.
  Discovery adapts with no code change. Teams has a stable `data-tid`
  attribute, and the same discovery handles it.

### Speaker attribution inside signals

- Signals could write "who spoke during utterance X".
- Rejected: it would join with utterances, which signals does not read.
  ADR-0002 puts attribution in the batch pass, which has full context.

### Diarization to name voices outside meetings

- Cut by the owner (ADR-0002, "Diarization in v1"). Not in this subsystem.

## Consequences

- Meeting lines and speaker names depend on the owner's Chrome launch
  setup. Without the debug port, documents still come, with "Others" for
  the other side.
- A Meet or Teams UI change can break names. Discovery adapts to new class
  names. A change of the tile structure or the name element needs a JS fix,
  and the Warning shows it within 5 min of a meeting.
- Teams meeting codes are weaker than Meet codes: a title slug when the URL
  has no ID. Two hosts in one unnamed Teams call can get codes that differ.
- Deliberately left out: per-tab audio, chat messages, screen-share state,
  meeting platforms other than Meet and Teams, and diarization.
