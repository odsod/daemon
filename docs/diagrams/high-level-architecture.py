"""Detailed schematic for ADR-0005: components, files and flows on one host.

Usage: uv run docs/diagrams/high-level-architecture.py docs/diagrams/high-level-architecture.svg
"""

import sys

from schematic import DASHED, HEAVY, THIN, Page

W, H = 2400, 1680
p = Page(W, H)
p.header("OD-ADR-0005", "COMPONENTS, FILES AND FLOWS")

BH = 72  # component box height


def comp(n, x, y, w, name, ports=()):
    p.block(x, y, w, BH, name, ports=ports, width=2, size=15)
    p.number(x + w + 16, y - 16, n, leader=(x + w, y))


def mid(x, w):
    return x + w / 2


# ------------------------------------------------------------------ A keys, D session
T = 200
p.frame(300, T, 200, 150, "A", "KEYS")
comp(
    1,
    320,
    T + 50,
    160,
    "KEYS",
    [("l", 0.5, "EVDEV"), ("t", 0.5, "UINPUT"), ("r", 0.5, "SOCKET")],
)

p.frame(580, T, 880, 150, "D", "SESSION")
comp(2, 640, T + 50, 200, "DICTATION", [("l", 0.5, "SOCKET"), ("t", 0.5, "PACTL")])
comp(3, 1080, T + 50, 160, "TRAY")
comp(4, 1265, T + 50, 180, "SHORTCUTS", [("r", 0.5, "D-BUS")])

ky = T + 50 + BH / 2
p.flow([(480, ky), (640, ky)], "START, STOP,\nPASTE", width=HEAVY, both=True)

p.ext(40, ky - 32, 180, 64, "KEYBOARDS", ["/dev/input"])
p.flow([(220, ky), (320, ky)], width=THIN)

p.ext(
    1570,
    140,
    240,
    180,
    "KDE PLASMA",
    ["APPLICATIONS", "KWIN SCRIPT", "SYSTEM TRAY"],
    size=16,
)
p.flow([(400, T + 50), (400, 160), (1570, 160)], "REMAPPED KEYS, PASTE CHORD", at=1)

p.flow([(740, T + 50), (740, 175)], width=THIN)
p.open_end(740, 140, ["MUTE MEETING CAPTURE STREAMS (TO PIPEWIRE)"], size=11)

p.flow([(1160, T + 50), (1160, 175)], width=THIN)
p.open_end(1160, 140, ["TO KDE PLASMA (SYSTEM TRAY)"], size=11)

p.flow([(1445, ky), (1570, ky)], "SHORTCUTS", width=THIN, both=True)

# run/ files
p.store(890, 365, 150, 70, "run/", ["status.json, muted.json"])
p.flow([(840, ky + 18), (965, ky + 18), (965, 365)], width=THIN)
p.flow([(1040, 400), (1160, 400), (1160, T + 50 + BH)], width=THIN)

# ------------------------------------------------------------------ B capture, audio buffer
p.frame(300, 470, 200, 140, "B", "CAPTURE")
comp(5, 320, 515, 160, "CAPTURE", [("l", 0.5, "PCM")])
ay = 515 + BH / 2
p.ext(40, ay - 35, 180, 70, "PIPEWIRE", ["MIC, SYSTEM AUDIO"])
p.flow([(220, ay), (320, ay)], width=HEAVY)

p.store(
    760,
    500,
    700,
    80,
    "state/audio/<channel>/",
    ["ROLLING RAW AUDIO · TIME = BYTE OFFSET"],
)
p.flow([(480, ay), (760, ay)], "AUDIO BLOCKS", width=HEAVY)

# ------------------------------------------------------------------ C pipeline
p.frame(300, 660, 1860, 440, "C", "PIPELINE")
RA, RB = 700, 900  # row tops
ra, rb = RA + BH / 2, RB + BH / 2

comp(6, 330, RA, 160, "SEGMENTATION")
p.store(560, RA - 5, 160, 80, "utterances/", ["AMBIENT, DICTATION"])
comp(7, 790, RA, 160, "TRANSCRIPTION", [("b", 0.5, "HTTP")])
p.store(1020, RA - 5, 160, 80, "asr/", ["RAW TEXT"])
comp(8, 1250, RA, 160, "CLEANUP", [("b", 0.5, "HTTP")])
p.store(1480, RA - 5, 160, 80, "text/", ["CLEANED TEXT"])
comp(10, 1710, RA, 160, "TRANSCRIPT")
p.store(1950, RA - 5, 170, 295, "documents/", ["TRANSCRIPTS/", "INTERACTIONS/"])

comp(9, 330, RB, 160, "SIGNALS", [("l", 0.5, "CDP")])
p.store(560, RB - 5, 160, 80, "events/", ["SIGNALS, USER"])
p.store(1020, RB - 5, 160, 80, "interactions/", ["BOUNDARIES"])
comp(11, 1480, RB, 160, "INTERACTIONS", [("b", 0.5, "HTTP")])
comp(12, 1950, 1015, 170, "PUBLISH", [("r", 0.5, "COPY")])

# speech path (live pass)
p.flow([(490, ra), (560, ra)], width=HEAVY)
p.tag(525, ra, "LIVE")
p.flow([(720, ra), (790, ra)], width=HEAVY)
p.flow([(950, ra), (1020, ra)], width=HEAVY)
p.flow([(1180, ra), (1250, ra)], width=HEAVY)
p.flow([(1410, ra), (1480, ra)], width=HEAVY)
p.flow([(1640, ra), (1664, ra)], width=HEAVY, arrow=False)
p.merge(1675, ra)
p.flow([(1686, ra), (1710, ra)], width=HEAVY)
p.flow([(1870, ra), (1950, ra)], width=HEAVY)

# audio bus to the readers
p.flow([(1010, 580), (1010, 640)], width=HEAVY, arrow=False)
p.flow([(1010, 640), (410, 640), (410, RA)], width=HEAVY)
p.flow([(870, 640), (870, RA)], width=HEAVY)
p.flow([(1010, 640), (1445, 640), (1445, rb), (1480, rb)], width=THIN)
p.dot(1010, 640)
p.dot(870, 640)

# dictation loop
p.flow([(690, T + 50 + BH), (690, RA - 5)], "DICTATION\nUTTERANCES", width=HEAVY)
p.tag(690, 470, "DIC", vertical=True)
p.flow(
    [(1560, RA - 5), (1560, 455), (790, 455), (790, T + 50 + BH)],
    "DICTATED TEXT",
    at=1,
    width=HEAVY,
    anchor="middle",
)

# glossary into cleanup
p.flow([(1330, 668), (1330, RA)], width=THIN)
p.text(1322, 686, "GLOSSARY, PROMPTS (config/)", 10, anchor="end")

# events
p.flow([(490, rb), (560, rb)], width=THIN)
p.ext(40, rb - 32, 180, 64, "BROWSER", ["MEETING TABS (CDP)"])
p.flow([(220, rb), (330, rb)], width=THIN)
p.flow(
    [(640, RB + 75), (640, 1050), (1675, 1050), (1675, ra + 11)],
    "NOTES, PINS, MEETINGS",
    at=1,
    width=THIN,
)
p.flow([(1560, 1050), (1560, RB + BH)], width=THIN)
p.dot(1560, 1050)

# batch pass
p.flow(
    [(700, RA + 75), (700, 830), (1520, 830), (1520, RB)],
    "UTTERANCE TIMES",
    at=1,
    width=THIN,
    dash=DASHED,
)
p.flow([(1480, RB + 20), (1180, RB + 20)], width=THIN, dash=DASHED)
p.flow([(1640, rb), (1950, rb)], "SPEAKERS, SUMMARY", width=THIN, dash=DASHED)
p.tag(1900, rb, "BATCH")

# documents out
p.flow([(2035, RA + 290), (2035, 1015)], width=THIN)
p.flow([(2120, 1015 + BH / 2), (2210, 1015 + BH / 2)], width=THIN)
p.ext(2210, 1015, 160, BH, "TARGET DIRS", ["VAULT INBOX"])

# inference host
p.flow([(870, RA + BH), (870, 1080), (1600, 1080)], width=THIN, arrow=False)
p.flow([(1330, RA + BH), (1330, 1080)], width=THIN, arrow=False)
p.flow([(1600, RB + BH), (1600, 1080)], width=THIN, arrow=False)
p.dot(1330, 1080)
p.flow([(1215, 1080), (1215, 1150)], "AUDIO SLICES, TEXT (HTTP)", width=THIN, both=True)
p.dot(1215, 1080)
p.ext(1000, 1150, 430, 56, "INFERENCE HOST", ["WHISPER-SERVER, LLAMA-SERVER"], size=15)

# ------------------------------------------------------------------ commands
comp(13, 100, 990, 160, "NOTE, PIN")
p.flow([(260, 1026), (600, 1026), (600, RB + 75)], width=THIN)

comp(16, 1700, 1130, 170, "DIARIZE")
p.flow([(1625, RB + BH), (1625, 1166), (1700, 1166)], width=THIN, dash=DASHED)

comp(15, 2200, RA, 160, "BENCH")
p.flow([(2280, 640), (2280, RA)], width=THIN)
p.text(2290, 650, "AUDIO, ASR TEXT", 10, anchor="start")
p.store(2200, 830, 160, 80, "bench/", ["CASES, REFERENCES"])
p.flow([(2280, RA + BH), (2280, 830)], width=THIN)

# ------------------------------------------------------------------ keys


def num(n):
    return lambda x, y: p.number(x, y, n, r=10)


def service(ch):
    return lambda x, y: p.callout(x, y, ch, 9)


COMPONENTS = [
    (1, "KEYS", "INPUT", "A", "REMAP; DICTATION KEY; PASTE CHORD"),
    (2, "DICTATION", "SPEECH", "D", "MEETING MUTE, UTTERANCE, CLIPBOARD"),
    (3, "TRAY", "CONTROL", "D", "MODE AND HEALTH; PAUSE"),
    (4, "SHORTCUTS", "INPUT", "D", "GLOBAL SHORTCUTS; LAUNCH APPS"),
    (5, "CAPTURE", "SPEECH", "B", "MIC AND SYSTEM AUDIO TO THE BUFFER"),
    (6, "SEGMENTATION", "SPEECH", "C", "AUDIO TO UTTERANCES"),
    (7, "TRANSCRIPTION", "SPEECH", "C", "UTTERANCES TO TEXT (ASR)"),
    (8, "CLEANUP", "SPEECH", "C", "LLM FIXES WITH THE GLOSSARY"),
    (9, "SIGNALS", "DOCUMENTS", "C", "MEETING AND SPEAKER EVENTS"),
    (10, "TRANSCRIPT", "DOCUMENTS", "C", "THE DAILY TRANSCRIPT (LIVE)"),
    (11, "INTERACTIONS", "DOCUMENTS", "C", "BOUNDARIES, BATCH PASS, DOCUMENTS"),
    (12, "PUBLISH", "DOCUMENTS", "C", "COPY TO TARGET DIRS"),
    (13, "NOTE, PIN", "CONTROL", "", "OWNER EVENTS"),
    (14, "STATUS", "CONTROL", "", "HEALTH VIEW (NOT DRAWN)"),
    (15, "BENCH", "CONTROL", "", "WER PER BACKEND AND STRATEGY"),
    (16, "DIARIZE", "CONTROL", "", "SPEAKER TURNS, ONE-SHOT"),
    (17, "INSTALL, MODELS", "CONTROL", "", "SETUP (NOT DRAWN)"),
]


def comp_row(n, name, domain, d, job):
    return (num(n), name, domain, service(d) if d else "CMD", job)


cols = [(20, "middle"), (42, "start"), (200, "start"), (318, "middle"), (345, "start")]
TY = 1230
p.table(
    40,
    TY,
    760,
    "COMPONENTS 1-9",
    [comp_row(*c) for c in COMPONENTS[:9]],
    cols,
    row_h=26,
)
p.table(
    820,
    TY,
    760,
    "COMPONENTS 10-17",
    [comp_row(*c) for c in COMPONENTS[9:]],
    cols,
    row_h=26,
)


def sample_line(width, dash=""):
    return lambda x, y: p.flow([(x - 30, y), (x + 30, y)], width=width, dash=dash)


SYMBOLS = [
    (sample_line(HEAVY), "SPEECH PATH (HEAVY)"),
    (sample_line(THIN), "CONTROL AND EVENTS (THIN)"),
    (sample_line(THIN, DASHED), "BATCH PASS (DASHED)"),
    (
        lambda x, y: (sample_line(THIN)(x, y), p.tag(x, y, "")),
        "MODE TAG: LIVE, DIC, BATCH",
    ),
    (lambda x, y: p.dot(x, y), "JUNCTION"),
    (lambda x, y: p.merge(x, y, 9), "MERGE"),
    (lambda x, y: p.callout(x, y, "A", 9), "SERVICE (FILLED LETTER)"),
    (lambda x, y: p.number(x, y, 1, r=10), "COMPONENT (HOLLOW NUMBER)"),
    (
        lambda x, y: p.rect(x - 28, y - 9, 56, 18, width=1.4, dash="6 4"),
        "OUTSIDE SYSTEM (DASHED BOX)",
    ),
    (
        lambda x, y: p.text(x, y + 4, "BOLD TEXT", 10, "bold"),
        "REFERENCE TO A BOX ELSEWHERE (OPEN END)",
    ),
]
p.table(1600, TY, 760, "SYMBOLS", SYMBOLS, [(60, "middle"), (120, "start")], row_h=26)

p.footer("OD-5-001", "Figure 1-2.  Components, Files and Flows", "1-2")
with open(sys.argv[1] if len(sys.argv) > 1 else "arch.svg", "w") as f:
    f.write(p.svg())
