"""Detailed schematic for ADR-0005 and ADR-0009: the filesystem as the backplane of the subsystems.

The state/ folders run left to right in data-flow order. Subsystems sit above
and below them. Each subsystem frame lists the paths it writes (WRITES) and the
folders it reads (READS). The seam table in ADR-0010 has the field detail.

Usage: uv run docs/diagrams/high-level-architecture.py docs/diagrams/high-level-architecture.svg
"""

import sys
import textwrap

from schematic import DASH_DOT, HEAVY, LETTER, MONO, PAPER, THIN, Page

W, H = 2720, 1690
p = Page(W, H)
p.header("OD-ADR-0005", "SUBSYSTEMS ON THE FILESYSTEM BACKPLANE")

# ------------------------------------------------------------------ data

# state/ folders in data-flow order: (name, description rows)
FOLDERS = [
    ("audio", ["mic/", "sys/"]),
    ("utterances", ["ambient/", "dictation/"]),
    ("coverage", ["AUDIO CUT", "UNTIL"]),
    ("asr", ["<backend>/"]),
    ("text", ["CLEANED TEXT"]),
    ("events", ["capture/", "signals/", "user/"]),
    ("interactions", ["RANGES"]),
    ("documents", ["transcripts/", "interactions/"]),
    ("finished", ["transcript/", "interactions/"]),
    ("published", ["<target>/"]),
    ("bench", ["<case-id>/"]),
    ("install", ["current", "previous-commit"]),
]
RUNCFG = [
    ("run/status.json", "status"),
    ("run/health/", "health"),
    ("run/muted.json", "muted"),
    ("run/paused", "paused"),
    ("config/config.json", "config.json"),
    ("config/glossary.txt", "glossary"),
    ("config/prompts/", "prompts"),
]

# Paths each subsystem writes, from ADR-0003 (layout) and ADR-0010 (seams).
# Every service also writes run/health/<service>.json.
WRITES = {
    "keys": [],
    "capture": ["audio/mic/, audio/sys/", "events/capture/"],
    "dictation": ["utterances/dictation/", "run/status.json, muted.json"],
    "signals": ["events/signals/"],
    "speech": ["utterances/ambient/, coverage/, asr/<backend>/, text/"],
    "control": ["run/paused, events/user/"],
    "transcript": ["documents/transcripts/, events/user/", "finished/transcript/"],
    "interactions": [
        "interactions/, documents/interactions/,",
        "finished/interactions/",
    ],
    "publishing": ["published/<target>/"],
    "bench": ["bench/<case-id>/"],
    "install": ["install/current, previous-commit"],
}

# One sentence per subsystem: what it does (from the Purpose of its ADR).
SUMMARY = {
    "keys": "REMAPS KEYS FROM BOOT, DETECTS THE DICTATION KEY AND SENDS THE PASTE CHORD.",
    "dictation": "RECORDS WHILE THE KEY IS HELD AND PASTES THE CLEANED TEXT.",
    "capture": "RECORDS MIC AND SYSTEM AUDIO TO DISK, ALL DAY.",
    "signals": "TURNS MEETING TABS INTO MEETING AND SPEAKER EVENTS.",
    "speech": "CUTS AUDIO INTO UTTERANCES, THEN TRANSCRIBES AND CLEANS EACH ONE ON THE INFERENCE HOST.",
    "shortcuts": "ONE CHORD PER APP: FRONT, START OR MINIMIZE, ON EVERY HOST.",
    "control": "SHOWS IF THE DAEMON RECORDS AND WHAT IS WRONG; PAUSE AND RESUME.",
    "transcript": "WRITES THE DAILY TRANSCRIPT OF ALL SPEECH, NOTES AND EVENTS.",
    "interactions": "FINDS EACH MEETING OR TALK AND WRITES ONE DOCUMENT WITH A SUMMARY.",
    "publishing": "COPIES FINISHED DOCUMENTS TO THE TARGET FOLDERS.",
    "bench": "SCORES MODELS AND PROMPTS ON TEST CASES CUT FROM REAL AUDIO.",
    "install": "INSTALLS, UPGRADES AND ROLLS BACK A HOST; TELLS WHICH COMMIT RUNS.",
}

# Folders each subsystem reads, at folder level. Not listed: config/ (all
# subsystems read it) and reads of a subsystem's own output.
READS = {
    "capture": ["run/paused"],
    "dictation": ["audio/, text/"],
    "speech": ["audio/, utterances/dictation/, run/status.json"],
    "transcript": ["utterances/, coverage/, text/, events/"],
    "interactions": ["utterances/, coverage/, text/, events/"],
    "publishing": ["documents/, finished/"],
    "control": [
        "audio/, utterances/,",
        "coverage/, text/,",
        "install/, run/",
    ],
    "bench": ["audio/, asr/, text/, interactions/,", "documents/, install/"],
}

# ------------------------------------------------------------------ geometry

X0, CW = 520, 160  # band left edge, column width
FW = 140  # folder width
BT, BB = 560, 700  # band top, bottom
FY, FH = 594, 100  # folder top, height
UF = (290, 478)  # upper frames: top, bottom
LF = (862, 1080)  # lower frames: top, bottom
LANE = 18

col = {name: i for i, (name, _) in enumerate(FOLDERS)}


def fx(name):
    return X0 + col[name] * CW + (CW - FW) / 2


# subsystem: (x, width, side, ADR, components as (service, name))
FRAMES = {
    "keys": (230, 240, "up", "ADR-0007", [("A", "KEYS")]),
    "dictation": (
        520,
        260,
        "up",
        "ADR-0013",
        [("D", "DICTATION"), ("CMD", "UNMUTE-STALE")],
    ),
    "capture": (820, 240, "up", "ADR-0011", [("B", "CAPTURE"), ("CMD", "RETENTION")]),
    "signals": (1100, 200, "up", "ADR-0014", [("C", "SIGNALS")]),
    "speech": (
        1340,
        560,
        "up",
        "ADR-0012",
        [("C", "SEGMENTATION"), ("C", "TRANSCRIPTION"), ("C", "CLEANUP")],
    ),
    "control": (
        230,
        250,
        "down",
        "ADR-0018",
        [
            ("E", "TRAY"),
            ("CMD", "HEALTH"),
            ("CMD", "STATUS, PAUSE, RESUME"),
            ("CMD", "NOTIFY-FAILED"),
        ],
    ),
    "transcript": (
        520,
        340,
        "down",
        "ADR-0015",
        [("C", "TRANSCRIPT"), ("CMD", "NOTE, PIN")],
    ),
    "interactions": (900, 460, "down", "ADR-0016", [("C", "INTERACTIONS")]),
    "publishing": (1400, 300, "down", "ADR-0017", [("C", "PUBLISH")]),
    "bench": (1740, 320, "down", "ADR-0019", [("CMD", "BENCH")]),
    "install": (
        2100,
        340,
        "down",
        "ADR-0006",
        [("CMD", "INSTALL"), ("CMD", "VERSION")],
    ),
}


def chip(x, y, svc, name):
    """One component: service letter (or CMD) and name. Returns its width."""
    if svc == "CMD":
        p.text(x, y + 4, "CMD", 9, "bold", anchor="start")
        tx = x + 28
    else:
        p.callout(x + 9, y, svc, 9)
        tx = x + 24
    p.text(tx, y + 5, name, 12, "bold", anchor="start")
    return tx - x + len(name) * 8.2 + 18


def frame(name, x, y, w, h, adr, comps):
    p.rect(x, y, w, h, width=1.5, dash="9 5", fill=PAPER)
    label = name.upper()
    p.text(x + 10, y + 21, label, 14, "bold", anchor="start")
    p.text(x + 20 + len(label) * 11, y + 21, adr, 10, anchor="start")
    rows = textwrap.wrap(SUMMARY[name], int((w - 28) / 6.6))
    p.lines(x + 14, y + 40, rows, 10, anchor="start", lead=13)
    cx, cy = x + 14, y + 40 + len(rows) * 13 + 14
    for svc, cname in comps:
        cw = len(cname) * 8.2 + (52 if svc == "CMD" else 42)
        if cx + cw > x + w and cx > x + 14:
            cx, cy = x + 14, cy + 22
        cx += chip(cx, cy, svc, cname)
    wy = cy + 30
    for label, rows in (("WRITES", WRITES.get(name, [])), ("READS", READS.get(name, []))):
        if rows:
            p.text(x + 14, wy, label, 9, "bold", anchor="start")
            p.lines(x + 64, wy, rows, 11, family=MONO, anchor="start", lead=15)
            wy += len(rows) * 15 + 4


# ------------------------------------------------------------------ boundary and band

p.boundary(
    [(215, 280), (2460, 280), (2460, 1128), (215, 1128)],
    "ODSOD-DAEMON",
    222,
    272,
)

p.rect(X0 - 10, BT, len(FOLDERS) * CW + 20, BB - BT, width=2.4)
for name, rows in FOLDERS:
    sub = any(r.endswith("/") or r.startswith("<") or r.islower() for r in rows)
    p.store(fx(name), FY, FW, FH, name + "/", rows, family=MONO if sub else LETTER)

p.text(240, 502, "state/ →", 18, "bold", "'Courier New', Courier, monospace", anchor="start")
p.lines(
    240,
    520,
    ["FILESYSTEM BACKPLANE (ADR-0003)", "state/<kind>/<writer>/:", "ONE WRITER PER SUBFOLDER,", "ANY NUMBER OF READERS.", "ALL SUBSYSTEMS READ config/;", "OWN-OUTPUT READS NOT SHOWN"],
    11,
    "bold",
    anchor="start",
    lead=14,
)

# ------------------------------------------------------------------ frames

for sub, (x, w, side, adr, comps) in FRAMES.items():
    top, bottom = UF if side == "up" else LF
    frame(sub, x, top, w, bottom - top, adr, comps)

frame("shortcuts", 230, 604, 250, 112, "ADR-0008", [("D", "SHORTCUTS")])

# ------------------------------------------------------------------ outside systems

# KDE Plasma: left strip
p.ext(
    30,
    320,
    150,
    700,
    "KDE PLASMA",
    ["APPLICATIONS", "KWIN SCRIPT", "SYSTEM TRAY", "NOTIFICATIONS"],
    size=15,
)
p.flow([(230, 400), (180, 400)], width=THIN)
p.text(205, 392, "UINPUT", 10, "bold")
p.flow([(230, 640), (180, 640)], width=THIN, both=True)
p.text(205, 632, "D-BUS", 10, "bold")
p.flow([(230, 990), (180, 990)], width=THIN)
p.text(205, 982, "TRAY", 10, "bold")

# keys and dictation
p.ext(230, 150, 240, 70, "KEYBOARDS", ["/dev/input (EVDEV)"])
p.flow([(350, 220), (350, UF[0])], width=THIN)
p.flow([(470, 380), (520, 380)], width=HEAVY, both=True)
p.text(495, 366, "SOCKET", 10, "bold")

# capture and dictation to PipeWire
p.ext(820, 150, 240, 70, "PIPEWIRE", ["MIC, SYSTEM AUDIO"])
p.flow([(900, 220), (900, UF[0])], "PCM", width=HEAVY)
p.flow(
    [(700, UF[0]), (700, 185), (820, 185)], "MUTE", at=1, width=THIN, anchor="middle"
)

# signals to the browser
p.ext(1100, 150, 200, 70, "BROWSER", ["MEETING TABS"])
p.flow([(1200, 220), (1200, UF[0])], "CDP", width=THIN)

# inference host: right strip
p.ext(
    2490,
    320,
    200,
    700,
    "INFERENCE HOST",
    ["WHISPER-SERVER", "LLAMA-SERVER", "(TAILNET)"],
    size=15,
)
p.flow(
    [(1900, 370), (2490, 370)],
    "AUDIO SLICES, TEXT (HTTP)",
    width=THIN,
    both=True,
    anchor="middle",
)
p.flow(
    [(1330, LF[1]), (1330, 1106), (2590, 1106), (2590, 1020)],
    "TEXT (HTTP)",
    at=1,
    width=THIN,
)
p.flow([(2590, 1106), (2590, 1020)], width=THIN, both=True)

# publishing to the target dirs
p.flow([(1550, LF[1]), (1550, 1200)], "COPY", width=THIN)
p.ext(1440, 1200, 220, 60, "TARGET DIRS", ["VAULT INBOX"])

# run/ and config/: listed, not drawn
RX, RY, RWD, RH = 520, 755, 157, 62
p.text(
    RX,
    RY - 10,
    "run/ AND config/",
    11,
    "bold",
    anchor="start",
)
RUNROWS = {
    "run/status.json": ["W DICTATION"],
    "run/health/": ["W EACH SERVICE"],
    "run/muted.json": ["W DICTATION"],
    "run/paused": ["W CONTROL"],
    "config/config.json": ["W OWNER"],
    "config/glossary.txt": ["W OWNER"],
    "config/prompts/": ["W OWNER"],
}
for i, (path, _) in enumerate(RUNCFG):
    p.rect(RX + i * (RWD + 5), RY, RWD, RH, width=THIN, fill=PAPER)
    p.text(
        RX + i * (RWD + 5) + RWD / 2,
        RY + 20,
        path,
        11,
        "bold",
        "'Courier New', Courier, monospace",
    )
    p.lines(RX + i * (RWD + 5) + RWD / 2, RY + 39, RUNROWS[path], 10, lead=13)

MX, MY = 40, 1300


# ------------------------------------------------------------------ services and symbols


SX = MX
SWD = 900


SYMBOLS = [
    (
        lambda x, y: p.rect(x - 30, y - 10, 60, 20, width=1.5, dash="9 5"),
        "SUBSYSTEM, ONE ADR",
    ),
    (
        lambda x, y: p.callout(x, y, "A", 9),
        "SERVICE (SYSTEMD UNIT) THAT RUNS THE COMPONENT: A KEYS (SYSTEM, ROOT), B CAPTURE (LOGIN SESSION),",
    ),
    (
        lambda x, y: None,
        "C PIPELINE (RESTARTS FREELY), D SESSION AND E TRAY (GRAPHICAL SESSION)",
    ),
    (
        lambda x, y: p.text(x, y + 4, "CMD", 9, "bold"),
        "ODSODCTL COMMAND, NO SERVICE",
    ),
    (
        lambda x, y: p.rect(x - 28, y - 9, 56, 18, width=1.4, dash="6 4"),
        "OUTSIDE SYSTEM",
    ),
    (
        lambda x, y: p.add(
            f'<line x1="{x - 30}" y1="{y}" x2="{x + 30}" y2="{y}" stroke="#1b1b1b" '
            f'stroke-width="1.8" stroke-dasharray="{DASH_DOT}"/>'
        ),
        "ODSOD-DAEMON",
    ),
]
sh = p.table(
    SX, MY, 1300, "SYMBOLS", SYMBOLS, [(46, "middle"), (90, "start")], row_h=26
)

p.text(
    MX,
    MY + sh + 30,
    "RUNTIME (ADR-0010): lib/, services/ AND cli.py SERVE ALL SUBSYSTEMS AND OWN NO FILES. RETENTION (CAPTURE) DELETES OLD AUDIO.",
    11,
    anchor="start",
)

p.footer("OD-5-001", "Figure 1-2.  Subsystems on the Filesystem Backplane", "1-2")
with open(sys.argv[1] if len(sys.argv) > 1 else "arch.svg", "w") as f:
    f.write(p.svg())
