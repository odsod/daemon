"""Detailed schematic for ADR-0005 and ADR-0009: subsystems, components, files and flows on one host.

Usage: uv run docs/diagrams/high-level-architecture.py docs/diagrams/high-level-architecture.svg
"""

import sys

from schematic import DASH_DOT, DASHED, HEAVY, THIN, Page

W, H = 2400, 2370
p = Page(W, H)
p.header("OD-ADR-0005", "SUBSYSTEMS, COMPONENTS, FILES AND FLOWS")

BH = 72  # component box height


CH = 50  # command box height


def svc_mark(x, y, svc):
    if svc == "CMD":
        p.text(x + 6, y + 14, "CMD", 9, "bold", anchor="start")
    else:
        p.callout(x + 13, y + 13, svc, 9)


def comp(n, x, y, w, name, svc, ports=(), h=BH):
    p.block(x, y, w, h, name, ports=ports, width=2, size=15 if h == BH else 13)
    p.number(x + w + 16, y - 16, n, leader=(x + w, y))
    svc_mark(x, y, svc)


def cmd(n, x, y, w, name):
    comp(n, x, y, w, name, "CMD", h=CH)


def subsystem(x, y, w, h, name, adr):
    """Boundary of one subsystem: dashed frame, name and its ADR."""
    p.rect(x, y, w, h, width=1.5, dash="9 5")
    p.text(x + 10, y + 19, name, 13, "bold", anchor="start")
    p.text(x + 18 + len(name) * 10, y + 19, adr, 10, anchor="start")


def mid(x, w):
    return x + w / 2


# ------------------------------------------------------------------ odsod-daemon
p.boundary(
    [(255, 245), (2195, 245), (2195, 1510), (255, 1510)],
    "ODSOD-DAEMON",
    262,
    237,
)

# ------------------------------------------------------------------ top band
FT, TY = 255, 310  # frame top, component top
FB = TY + BH + 18  # frame bottom
L1, L2, L3 = 190, 212, 234  # lines to KDE

subsystem(290, FT, 230, FB - FT, "KEYS", "ADR-0007")
comp(
    1,
    320,
    TY,
    160,
    "KEYS",
    "A",
    [("l", 0.5, "EVDEV"), ("t", 0.5, "UINPUT"), ("r", 0.5, "SOCKET")],
)

subsystem(640, FT, 460, FB - FT, "DICTATION", "ADR-0013")
comp(2, 670, TY, 190, "DICTATION", "D", [("l", 0.5, "SOCKET"), ("t", 0.82, "PACTL")])
cmd(3, 900, TY + 11, 160, "UNMUTE-STALE")

subsystem(1140, FT, 240, FB - FT, "SHORTCUTS", "ADR-0008")
comp(4, 1170, TY, 170, "SHORTCUTS", "D", [("t", 0.35, "D-BUS")])

subsystem(1420, FT, 760, FB - FT, "CONTROL", "ADR-0018")
comp(5, 1450, TY, 140, "TRAY", "E")
cmd(6, 1625, TY + 11, 140, "HEALTH")
cmd(7, 1800, TY + 11, 190, "STATUS, PAUSE,\nRESUME")
cmd(8, 2025, TY + 11, 125, "NOTIFY-\nFAILED")

ky = TY + BH / 2
p.flow(
    [(480, ky), (670, ky)],
    "START, STOP,\nPASTE",
    width=HEAVY,
    both=True,
    anchor="middle",
)

p.ext(40, ky - 32, 180, 64, "KEYBOARDS", ["/dev/input"])
p.flow([(220, ky), (320, ky)], width=THIN)

p.ext(
    2215,
    150,
    170,
    200,
    "KDE PLASMA",
    ["APPLICATIONS", "KWIN SCRIPT", "SYSTEM TRAY", "NOTIFICATIONS"],
    size=16,
)
p.flow([(450, TY), (450, L1), (2215, L1)], "REMAPPED KEYS, PASTE CHORD", at=1)
p.flow([(1310, TY), (1310, L2), (2215, L2)], "SHORTCUTS (D-BUS)", at=1, both=True)
p.flow([(1570, TY), (1570, L3), (2215, L3)], "TRAY ICON, NOTIFICATIONS", at=1)
p.flow([(2120, TY + 11), (2120, L3)], arrow=False)
p.dot(2120, L3)

p.flow([(826, TY), (826, 168)], width=THIN)
p.open_end(826, 150, ["MUTE MEETING CAPTURE STREAMS (TO PIPEWIRE)"], size=11)

# ------------------------------------------------------------------ capture, audio, run/
CT = 440
subsystem(290, CT, 230, 230, "CAPTURE", "ADR-0011")
comp(9, 320, CT + 55, 160, "CAPTURE", "B", [("l", 0.5, "PCM")])
cmd(10, 320, CT + 160, 160, "RETENTION")
ay = CT + 55 + BH / 2
p.ext(40, ay - 35, 180, 70, "PIPEWIRE", ["MIC, SYSTEM AUDIO"])
p.flow([(220, ay), (320, ay)], width=HEAVY)

p.store(
    760,
    CT + 55,
    740,
    80,
    "state/audio/<channel>/",
    ["ROLLING RAW AUDIO · TIME = BYTE OFFSET"],
)
p.flow([(480, ay), (760, ay)], "AUDIO BLOCKS", width=HEAVY, anchor="middle")
ry = CT + 185
p.flow([(480, ry), (900, ry), (900, CT + 135)], width=THIN)
p.text(560, ry - 7, "DELETE EXPIRED", 11, anchor="start")

p.store(1620, CT + 55, 260, 80, "run/", ["STATUS, HEALTH/, MUTED, PAUSED"])
p.flow(
    [(845, TY + BH), (845, 420), (1650, 420), (1650, CT + 55)],
    "STATUS, MUTED",
    at=1,
    width=THIN,
)
p.flow([(1740, TY + 11 + CH), (1740, CT + 55)], "HEALTH, PAUSED", width=THIN, both=True)

# ------------------------------------------------------------------ speech
RA = 745
ra = RA + BH / 2
subsystem(300, RA - 55, 1365, BH + 80, "SPEECH", "ADR-0012")
comp(11, 330, RA, 160, "SEGMENTATION", "C")
p.store(560, RA - 5, 160, 80, "utterances/", ["AMBIENT, DICTATION", "+ coverage/"])
comp(12, 790, RA, 160, "TRANSCRIPTION", "C", [("b", 0.5, "HTTP")])
p.store(1020, RA - 5, 160, 80, "asr/", ["RAW TEXT"])
comp(13, 1250, RA, 160, "CLEANUP", "C", [("b", 0.5, "HTTP")])
p.store(1480, RA - 5, 160, 80, "text/", ["CLEANED TEXT"])

p.flow([(490, ra), (560, ra)], width=HEAVY)
p.tag(525, ra, "LIVE")
p.flow([(720, ra), (790, ra)], width=HEAVY)
p.flow([(950, ra), (1020, ra)], width=HEAVY)
p.flow([(1180, ra), (1250, ra)], width=HEAVY)
p.flow([(1410, ra), (1480, ra)], width=HEAVY)

# audio bus to the readers
p.flow([(1010, CT + 135), (1010, 668)], width=HEAVY, arrow=False)
p.flow([(1010, 668), (460, 668), (460, RA)], width=HEAVY)
p.flow([(870, 668), (870, RA)], width=HEAVY)
p.dot(1010, 668)
p.dot(870, 668)

# glossary into cleanup
p.flow([(1380, RA - 28), (1380, RA)], width=THIN)
p.text(1372, RA - 22, "GLOSSARY, PROMPTS (config/)", 10, anchor="end")

# dictation loop
p.flow([(690, TY + BH), (690, RA - 5)], width=HEAVY)
p.tag(690, 470, "DIC", vertical=True)
p.flow(
    [(1560, RA - 5), (1560, 455), (810, 455), (810, TY + BH)],
    "DICTATED TEXT",
    at=1,
    width=HEAVY,
    anchor="middle",
)

# ------------------------------------------------------------------ row B: signals, transcript
RB = 955
rb = RB + BH / 2
subsystem(290, RB - 55, 230, BH + 85, "SIGNALS", "ADR-0014")
comp(14, 320, RB, 160, "SIGNALS", "C", [("l", 0.5, "CDP")])
p.ext(40, rb - 32, 180, 64, "BROWSER", ["MEETING TABS (CDP)"])
p.flow([(220, rb), (320, rb)], width=THIN)
p.store(560, RB - 5, 160, 80, "events/", ["SIGNALS, USER, CAPTURE"])
p.flow([(480, rb), (560, rb)], width=THIN)
# capture events
p.flow([(480, CT + 100), (540, CT + 100), (540, rb + 22), (560, rb + 22)], width=THIN)
p.text(532, 872, "CAPTURE EVENTS", 10, anchor="end")

subsystem(940, RB - 55, 740, BH + 85, "TRANSCRIPT", "ADR-0015")
cmd(16, 970, RB + 11, 160, "NOTE, PIN")
comp(15, 1480, RB, 160, "TRANSCRIPT", "C")
p.flow([(970, rb), (720, rb)], "NOTES, PINS", width=THIN)
p.flow([(1560, RA + 75), (1560, RB)], width=HEAVY)

p.store(
    1820,
    RB - 5,
    180,
    310,
    "documents/",
    ["TRANSCRIPTS/", "INTERACTIONS/", "+ finished/"],
)
p.flow([(1640, rb), (1820, rb)], width=HEAVY)

# events bus to transcript and interactions
EV = 1072
p.flow(
    [(640, RB + 75), (640, EV), (1530, EV), (1530, RB + BH)],
    "MEETINGS, NOTES, PINS, GAPS",
    at=1,
    width=THIN,
)
p.flow([(1500, EV), (1500, 1185)], width=THIN)
p.dot(1500, EV)

# ------------------------------------------------------------------ row C: interactions, publishing
RC = 1185
rc = RC + BH / 2
subsystem(940, RC - 55, 635, BH + 85, "INTERACTIONS", "ADR-0016")
p.store(970, RC - 5, 160, 80, "interactions/", ["OK, SKIPPED"])
comp(17, 1380, RC, 160, "INTERACTIONS", "C", [("b", 0.5, "HTTP")])
p.flow([(1380, rc), (1130, rc)], width=THIN, dash=DASHED)

# batch inputs
p.flow(
    [(640, RA + 75), (640, 870), (1410, 870), (1410, RC)],
    "UTTERANCE TIMES",
    at=1,
    width=THIN,
    dash=DASHED,
)
p.flow(
    [(1640, RA + 50), (1730, RA + 50), (1730, rc - 18), (1540, rc - 18)],
    width=THIN,
    dash=DASHED,
)
p.lines(1738, 1115, ["PASS 1", "TEXT"], 10, anchor="start", lead=12)
p.flow([(1540, rc + 18), (1820, rc + 18)], width=THIN, dash=DASHED)
p.tag(1780, rc + 18, "BATCH")

subsystem(2015, 1020, 170, 170, "PUBLISHING", "")
p.text(2025, 1056, "ADR-0017", 10, anchor="start")
comp(18, 2035, 1090, 120, "PUBLISH", "C")
p.flow([(2000, 1126), (2035, 1126)], width=THIN)
p.flow([(2155, 1126), (2215, 1126)], width=THIN)
p.ext(2215, 1090, 170, BH, "TARGET DIRS", ["VAULT INBOX"])

# ------------------------------------------------------------------ inference host
IB = 1297
p.flow([(870, RA + BH), (870, IB), (1460, IB)], width=THIN, arrow=False)
p.flow([(1330, RA + BH), (1330, IB)], width=THIN, arrow=False)
p.flow([(1460, RC + BH), (1460, IB)], width=THIN, arrow=False)
p.dot(1330, IB)
p.dot(1215, IB)
p.flow(
    [(1215, IB), (1215, 1540)],
    "AUDIO SLICES, TEXT (HTTP, TAILNET)",
    width=THIN,
    both=True,
)
p.ext(1000, 1540, 430, 56, "INFERENCE HOST", ["WHISPER-SERVER, LLAMA-SERVER"], size=15)

# ------------------------------------------------------------------ row D: operations, bench, runtime
RD = 1330
subsystem(290, RD, 430, 110, "OPERATIONS", "ADR-0006")
cmd(19, 320, RD + 45, 160, "INSTALL")
cmd(20, 520, RD + 45, 160, "VERSION")

subsystem(1600, RD, 585, 110, "BENCH", "ADR-0019")
cmd(21, 1630, RD + 45, 160, "BENCH")
p.store(1900, RD + 25, 170, 75, "bench/", ["CASES, RESULTS"])
p.flow([(1790, RD + 70), (1900, RD + 70)], width=THIN)
p.flow([(1760, RD - 22), (1760, RD + 45)], width=THIN)
p.text(1772, RD - 14, "AUDIO, ASR, TEXT", 10, anchor="start")

p.rect(290, 1455, 860, 40, width=1.5, dash="2 4")
p.text(
    720,
    1481,
    "RUNTIME  ADR-0010:  lib/ (STREAMS, PENDING WORK, CONFIG, CLIENTS)  ·  services/  ·  cli.py",
    11,
    "bold",
)

# ------------------------------------------------------------------ keys


def num(n):
    return lambda x, y: p.number(x, y, n, r=10)


def service(ch):
    return lambda x, y: p.callout(x, y, ch, 9)


COMPONENTS = [
    (1, "KEYS", "KEYS", "A", "REMAP; DICTATION KEY; PASTE CHORD"),
    (2, "DICTATION", "DICTATION", "D", "MEETING MUTE, UTTERANCE, PASTE"),
    (3, "UNMUTE-STALE", "DICTATION", "", "UNMUTE STREAMS LEFT MUTED"),
    (4, "SHORTCUTS", "SHORTCUTS", "D", "GLOBAL SHORTCUTS; LAUNCH APPS"),
    (5, "TRAY", "CONTROL", "E", "MODE AND HEALTH; PAUSE"),
    (6, "HEALTH", "CONTROL", "", "STATE FROM UNITS AND HEALTH FILES"),
    (7, "STATUS, PAUSE, RESUME", "CONTROL", "", "HEALTH VIEW; PAUSE FLAG"),
    (8, "NOTIFY-FAILED", "CONTROL", "", "NOTIFY A FAILED UNIT"),
    (9, "CAPTURE", "CAPTURE", "B", "MIC AND SYSTEM AUDIO TO THE BUFFER"),
    (10, "RETENTION", "CAPTURE", "", "DELETE EXPIRED AUDIO (TIMER)"),
    (11, "SEGMENTATION", "SPEECH", "C", "AUDIO TO UTTERANCES"),
    (12, "TRANSCRIPTION", "SPEECH", "C", "UTTERANCES TO TEXT (ASR)"),
    (13, "CLEANUP", "SPEECH", "C", "LLM FIXES WITH THE GLOSSARY"),
    (14, "SIGNALS", "SIGNALS", "C", "MEETING AND SPEAKER EVENTS"),
    (15, "TRANSCRIPT", "TRANSCRIPT", "C", "THE DAILY TRANSCRIPT (LIVE)"),
    (16, "NOTE, PIN", "TRANSCRIPT", "", "OWNER EVENTS"),
    (17, "INTERACTIONS", "INTERACTIONS", "C", "BOUNDARIES, BATCH PASS, DOCUMENTS"),
    (18, "PUBLISH", "PUBLISHING", "C", "COPY TO TARGET DIRS"),
    (19, "INSTALL", "OPERATIONS", "", "UNITS, KEYS BUILD, KWIN SCRIPT"),
    (20, "VERSION", "OPERATIONS", "", "INSTALLED COMMIT"),
    (21, "BENCH", "BENCH", "", "SCORE SETUPS ON CASES"),
]


def comp_row(n, name, subsys, d, job):
    return (num(n), name, subsys, service(d) if d else "CMD", job)


cols = [(20, "middle"), (40, "start"), (215, "start"), (338, "middle"), (360, "start")]
TB = 1640
p.table(
    40,
    TB,
    760,
    "COMPONENTS 1-11",
    [comp_row(*c) for c in COMPONENTS[:11]],
    cols,
    row_h=26,
)
p.table(
    820,
    TB,
    760,
    "COMPONENTS 12-21",
    [comp_row(*c) for c in COMPONENTS[11:]],
    cols,
    row_h=26,
)

SERVICES = [
    (service("A"), "KEYS", "SYSTEM UNIT, ROOT, FROM BOOT"),
    (service("B"), "CAPTURE", "NEVER STOPS"),
    (service("C"), "PIPELINE", "RESTARTS FREELY"),
    (service("D"), "SESSION", "GRAPHICAL SESSION"),
    (service("E"), "TRAY", "GRAPHICAL SESSION"),
    ("CMD", "COMMAND", "ODSODCTL, NO SERVICE"),
]
sh = p.table(
    1600,
    TB,
    760,
    "SERVICES (LIFECYCLE)",
    SERVICES,
    [(30, "middle"), (60, "start"), (200, "start")],
    row_h=26,
)


def sample_line(width, dash=""):
    return lambda x, y: p.flow([(x - 30, y), (x + 30, y)], width=width, dash=dash)


SYMBOLS = [
    (
        lambda x, y: p.rect(x - 30, y - 10, 60, 20, width=1.5, dash="9 5"),
        "SUBSYSTEM: DESIGN UNIT, ONE ADR (DASHED FRAME)",
    ),
    (lambda x, y: p.callout(x, y, "A", 9), "SERVICE OF A COMPONENT (FILLED LETTER)"),
    (lambda x, y: p.number(x, y, 1, r=10), "COMPONENT (HOLLOW NUMBER)"),
    (sample_line(HEAVY), "SPEECH PATH (HEAVY)"),
    (sample_line(THIN), "CONTROL AND EVENTS (THIN)"),
    (sample_line(THIN, DASHED), "BATCH PASS (DASHED)"),
    (
        lambda x, y: (sample_line(THIN)(x, y), p.tag(x, y, "")),
        "MODE TAG: LIVE, DIC, BATCH",
    ),
    (lambda x, y: p.dot(x, y), "JUNCTION"),
    (
        lambda x, y: p.add(
            f'<line x1="{x - 30}" y1="{y}" x2="{x + 30}" y2="{y}" stroke="#1b1b1b" '
            f'stroke-width="1.8" stroke-dasharray="{DASH_DOT}"/>'
        ),
        "ODSOD-DAEMON: THE WHOLE SYSTEM (DASH-DOT)",
    ),
    (
        lambda x, y: p.rect(x - 28, y - 9, 56, 18, width=1.4, dash="6 4"),
        "OUTSIDE SYSTEM (DASHED BOX)",
    ),
]
p.table(
    1600,
    TB + sh + 20,
    760,
    "SYMBOLS",
    SYMBOLS,
    [(60, "middle"), (120, "start")],
    row_h=26,
)

p.footer("OD-5-001", "Figure 1-2.  Subsystems, Components, Files and Flows", "1-2")
with open(sys.argv[1] if len(sys.argv) > 1 else "arch.svg", "w") as f:
    f.write(p.svg())
