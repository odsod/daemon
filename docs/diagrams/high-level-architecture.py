"""Detailed architecture diagram for ADR-0005, in the schematic style.

Usage: uv run docs/diagrams/high-level-architecture.py docs/diagrams/high-level-architecture.svg
"""

import sys
from xml.sax.saxutils import escape

import schematic
from schematic import GRAY, INK, PAPER, Page

W, H = 2480, 1440
SANS = schematic.SANS
MONO = schematic.MONO

STYLE = {
    "keys": ("#d9d6cc", INK),
    "capture": ("#e4e1d8", INK),
    "session": ("#eeebe3", INK),
    "pipeline": (PAPER, INK),
    "cli": (PAPER, GRAY),
    "store": (PAPER, INK),
    "run": (PAPER, INK),
    "vault": (PAPER, INK),
    "ext": (PAPER, GRAY),
}
FLOW = {
    "shared": INK,
    "ambient": INK,
    "dictation": INK,
    "batch": INK,
    "os": INK,
}
FLOW_DASH = {
    "shared": "",
    "ambient": "",
    "dictation": "",
    "batch": schematic.DASH["dashed"],
    "os": "",
}
FLOW_WIDTH = {"shared": 1.6, "ambient": 2.4, "dictation": 3.6, "batch": 2.4, "os": 1.8}

out = []
boxes = {}


def text(
    x,
    y,
    s,
    size=14,
    weight="normal",
    family=SANS,
    anchor="middle",
    fill="#222",
    style="",
):
    if family == SANS and not any(c in s for c in "/<$"):
        s = s.upper()
    out.append(
        f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
        f'font-weight="{weight}" text-anchor="{anchor}" fill="{fill}" {style}>{escape(s)}</text>'
    )


def box(key, cx, cy, kind, title, lines=(), path=None, w=190, h=None, badge=None):
    fill, stroke = STYLE[kind]
    n = len(lines) + (1 if path else 0)
    h = h or 40 + 17 * n
    x, y = cx - w / 2, cy - h / 2
    boxes[key] = (cx, cy, w, h)
    dash = ' stroke-dasharray="6 4"' if kind in ("ext", "run") else ""
    if kind in ("store", "run", "vault"):
        # folder shape: tab on the top-left
        t = 14
        out.append(
            f'<path d="M{x},{y + t} L{x},{y + h} L{x + w},{y + h} L{x + w},{y + t} '
            f'L{x + 70},{y + t} L{x + 60},{y} L{x},{y} Z" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="2"{dash}/>'
        )
        ty = y + t + 22
    else:
        out.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="2"{dash}/>'
        )
        ty = y + 24
    if path:
        text(cx, ty, path, 14, "bold", MONO)
    else:
        text(cx, ty, title, 15, "bold")
    for i, line in enumerate(lines):
        text(cx, ty + 18 * (i + 1), line, 12, fill="#333")
    if badge:
        bx, by = x + w - 44, y - 10
        out.append(
            f'<rect x="{bx}" y="{by}" width="50" height="20" rx="10" fill="{PAPER}" '
            f'stroke="{INK}" stroke-width="1.5"/>'
        )
        text(bx + 25, by + 14, badge, 11, "bold", fill=INK)


def edge(key, side, offset=0):
    cx, cy, w, h = boxes[key]
    if side == "l":
        return (cx - w / 2, cy + offset)
    if side == "r":
        return (cx + w / 2, cy + offset)
    if side == "t":
        return (cx + offset, cy - h / 2)
    return (cx + offset, cy + h / 2)


def line(points, flow="shared", dashed=False, label=None, lpos=None, lanchor="middle"):
    color = FLOW[flow]
    d = " ".join(f"{'M' if i == 0 else 'L'}{x},{y}" for i, (x, y) in enumerate(points))
    pattern = schematic.DASH["dotted"] if dashed else FLOW_DASH[flow]
    dash = f' stroke-dasharray="{pattern}"' if pattern else ""
    # paper halo so crossings read as pass-overs
    out.append(f'<path d="{d}" fill="none" stroke="{PAPER}" stroke-width="8"/>')
    out.append(
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{FLOW_WIDTH[flow]}"{dash} '
        f'marker-end="url(#a-{flow})"/>'
    )
    if label:
        lx, ly = lpos
        text(lx, ly, label, 12, "bold", fill=color, anchor=lanchor)


# ---------------------------------------------------------------- frame
out.append(
    '<rect x="20" y="90" width="2440" height="1090" rx="16" fill="none" '
    'stroke="#6b6b6b" stroke-width="2" stroke-dasharray="10 6"/>'
)
text(40, 114, "EACH HOST", 14, "bold", anchor="start", fill=GRAY)

# ---------------------------------------------------------------- external
box("pw", 130, 420, "ext", "PipeWire", ["mics, outputs,", "meeting capture streams"])
box("kbd", 560, 210, "ext", "keyboards", ["/dev/input,", "grabbed"], w=150)
box("input", 790, 210, "keys", "keys", ["remap; hold Alt;", "Shift+Insert"], w=170)
box(
    "wayland",
    1680,
    210,
    "ext",
    "KDE Plasma",
    ["KWin script, tray,", "clipboard, apps"],
    w=180,
)
box("chrome", 130, 760, "ext", "Chrome", ["Meet / Teams tabs", "(DevTools Protocol)"])
box("user", 130, 920, "ext", "Owner", ["odsodctl note,", "odsodctl pin"])

# ---------------------------------------------------------------- components
box(
    "capture",
    350,
    420,
    "capture",
    "capture",
    ["record mic + system", "audio, never stops"],
)
box(
    "session",
    1010,
    210,
    "session",
    "dictation",
    ["mute meeting streams,", "clipboard, utterance"],
)
box(
    "indicator",
    1450,
    210,
    "session",
    "tray",
    ["mode + health;", "pause stops capture"],
    w=180,
)
box(
    "shortcuts",
    1950,
    210,
    "session",
    "shortcuts",
    ["global shortcuts,", "launch apps"],
    w=180,
)
box(
    "signals",
    350,
    760,
    "pipeline",
    "signals",
    ["meeting + speaker", "events from browser"],
)
box("note", 350, 920, "cli", "note / pin CLI", ["append user events"])
box(
    "seg",
    790,
    600,
    "pipeline",
    "segmentation",
    ["VAD: audio to", "utterances"],
)
box(
    "asrw",
    1230,
    600,
    "pipeline",
    "transcription",
    ["one worker per", "ASR backend"],
    badge="HTTP",
)
box("cleanup", 1670, 600, "pipeline", "cleanup", ["LLM + glossary"], badge="HTTP")
box(
    "transcript",
    2110,
    600,
    "pipeline",
    "transcript",
    ["sole writer of", "the daily log"],
)
box(
    "reproc",
    1230,
    840,
    "pipeline",
    "interactions",
    ["boundaries; diarize,", "names, summary (pass 2)"],
    badge="HTTP",
)
box("bench", 1560, 1060, "cli", "bench", ["score backends", "vs references"])

# ---------------------------------------------------------------- stores
# audio buffer: wide bar that all audio readers tap
fill, stroke = STYLE["store"]
ax0, ax1, ay, ah = 480, 1380, 420, 84
out.append(
    f'<path d="M{ax0},{ay - ah / 2 + 12} L{ax0},{ay + ah / 2} L{ax1},{ay + ah / 2} '
    f"L{ax1},{ay - ah / 2 + 12} L{ax0 + 70},{ay - ah / 2 + 12} L{ax0 + 60},{ay - ah / 2} "
    f'L{ax0},{ay - ah / 2} Z" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
)
text(ax0 + 20, ay - 2, "state/audio/<channel>/", 15, "bold", MONO, anchor="start")
text(ax0 + 20, ay + 16, "rolling raw audio, time = byte offset", 13, anchor="start")
text(
    ax0 + 20,
    ay + 33,
    "read by segmentation, transcription, interactions, bench",
    12,
    anchor="start",
    fill="#555",
)

box(
    "jobs",
    1010,
    600,
    "store",
    "",
    ["ambient/ + dictation/;", "pending = no text yet"],
    path="state/utterances/",
    w=200,
)
box("asr", 1450, 600, "store", "", ["raw ASR text", "per utterance"], path="state/asr/")
box(
    "text",
    1890,
    600,
    "store",
    "",
    ["cleaned text", "per utterance"],
    path="state/text/",
)
box(
    "events",
    570,
    840,
    "store",
    "",
    ["append-only event", "streams per source"],
    path="state/events/",
)
box(
    "inter",
    1010,
    840,
    "store",
    "",
    ["finished", "interactions"],
    path="state/interactions/",
    w=200,
)
box(
    "benchs",
    1890,
    1060,
    "store",
    "",
    ["cases: audio slice,", "hypotheses, reference"],
    path="state/bench/",
)
box("gloss", 1670, 420, "store", "", ["glossary, prompts"], path="config/")
box(
    "state",
    1230,
    210,
    "run",
    "",
    ["dictation mode;", "read by tray and", "odsodctl status"],
    path="run/status.json",
    w=180,
)
box(
    "docs",
    2330,
    715,
    "store",
    "",
    [
        "transcripts/",
        "<day>-<host>.md",
        "daily log, pass 1",
        "",
        "interactions/",
        "<day>-<HHMM>-<host>",
        "-<slug>.md",
        "transcript + summary,",
        "pass 2",
    ],
    path="state/documents/",
    w=200,
    h=250,
)
box("publish", 2330, 960, "pipeline", "publish", ["copy finished docs,", "write once"])
box(
    "targets",
    2330,
    1100,
    "ext",
    "target dirs",
    ["from config, e.g. a", "vault inbox"],
    w=200,
)

# ---------------------------------------------------------------- edges
# capture
line([edge("pw", "r"), edge("capture", "l")], "os", True)
line([edge("capture", "r"), (ax0, 420)])
# audio readers
line([(790, ay + ah / 2), edge("seg", "t")])
line([(1230, ay + ah / 2), edge("asrw", "t")])
line([(1340, ay + ah / 2), (1340, 740), (1250, 740), edge("reproc", "t", 20)], "batch")
line([(1340, 740), (1340, 1060), edge("bench", "l")])
out.append('<circle cx="1340" cy="740" r="4" fill="#444"/>')
# ambient spine
line([edge("seg", "r"), edge("jobs", "l")], "ambient")
line([edge("jobs", "r"), edge("asrw", "l")])
line([edge("asrw", "r"), edge("asr", "l")])
line([edge("asr", "r"), edge("cleanup", "l")])
line([edge("gloss", "b"), edge("cleanup", "t")])
line([edge("cleanup", "r"), edge("text", "l")])
line([edge("text", "r"), edge("transcript", "l")], "ambient")
line([edge("transcript", "r"), edge("docs", "l", -115)], "ambient")
# dictation
line([edge("kbd", "r"), edge("input", "l")], "os", True)
line(
    [edge("input", "r"), edge("session", "l")],
    "dictation",
    label="socket",
    lpos=(895, 188),
)
line(
    [edge("session", "b", -30), (980, 557)],
    "dictation",
    label="dictation utterances",
    lpos=(972, 520),
    lanchor="end",
)
line([edge("session", "r"), edge("state", "l")], "dictation")
line([edge("state", "r"), edge("indicator", "l")], "dictation")
line([edge("indicator", "r"), edge("wayland", "l")], "os", True)
line([edge("wayland", "r"), edge("shortcuts", "l")], "os", True, "D-Bus", (1815, 202))
line(
    [edge("session", "t", -40), (970, 120), (110, 120), edge("pw", "t", -20)],
    "os",
    True,
    "mute meeting capture streams while dictating",
    (500, 112),
)
line(
    [edge("text", "t"), (1890, 300), (1040, 300), edge("session", "b", 30)],
    "dictation",
    label="dictated text",
    lpos=(1880, 292),
    lanchor="end",
)
line(
    [edge("input", "t", 40), (830, 150), (1680, 150), edge("wayland", "t")],
    "os",
    True,
    "remapped keys + paste chord (uinput)",
    (1300, 142),
)
# events
line([edge("chrome", "r"), edge("signals", "l")], "os", True)
line([edge("signals", "r"), edge("events", "l", -20)])
line([edge("note", "r"), edge("events", "l", 20)])
line(
    [edge("events", "b", 40), (610, 1130), (2110, 1130), edge("transcript", "b")],
    "ambient",
    label="notes, pins, meetings to the daily log",
    lpos=(2090, 1120),
    lanchor="end",
)
# batch
line(
    [edge("jobs", "b", 60), (1070, 760), (1200, 760), edge("reproc", "t", -30)],
    "batch",
)
line([edge("reproc", "l"), edge("inter", "r")], "batch")
line(
    [edge("events", "b", -40), (530, 1000), (1200, 1000), edge("reproc", "b", -30)],
    "batch",
    label="meetings, pins, speakers",
    lpos=(1180, 990),
    lanchor="end",
)
line([edge("reproc", "r"), (2230, 840)], "batch")
line([edge("docs", "b"), edge("publish", "t")])
line([edge("publish", "b"), edge("targets", "t")], "os", True)
# bench
line([edge("asr", "b"), (1450, 1000), (1530, 1000), edge("bench", "t", -30)])
line([edge("bench", "r"), edge("benchs", "l")])

# ---------------------------------------------------------------- inference host
out.append(
    '<rect x="900" y="1220" width="1100" height="90" rx="0" fill="none" stroke="#1b1b1b" '
    'stroke-width="2" stroke-dasharray="10 6"/>'
)
text(1450, 1252, "INFERENCE HOST (desktop GPU)", 15, "bold")
text(
    1450,
    1276,
    "whisper-server (ASR) and llama-server (LLM), reached over HTTP via Tailscale",
    13,
)
text(
    1450,
    1296,
    "no broker: each host serves its own dictation first; across hosts, first come first served",
    12,
    fill="#555",
)
text(1450, 1206, "components with an HTTP badge call these servers", 12)

# ---------------------------------------------------------------- legend
lx, ly = 40, 1215
text(lx, ly, "LEGEND", 14, "bold", anchor="start", fill="#777")
items = [
    ("keys", "keys daemon (system, root, C)"),
    ("capture", "capture daemon (always on)"),
    ("session", "session daemon: dictation, tray, shortcuts"),
    ("pipeline", "pipeline daemon (restartable)"),
    ("cli", "command (on demand)"),
    ("store", "file interface (state/ = $XDG_STATE_HOME/odsod-daemon)"),
    ("run", "runtime file (run/ = $XDG_RUNTIME_DIR/odsod-daemon, tmpfs)"),
    ("ext", "outside odsod-daemon"),
]
for i, (k, label) in enumerate(items):
    col, row = divmod(i, 4)
    x, y = lx + col * 470, ly + 18 + row * 46
    f, s = STYLE[k]
    dash = ' stroke-dasharray="5 3"' if k in ("ext", "run") else ""
    out.append(
        f'<rect x="{x}" y="{y}" width="34" height="22" rx="5" fill="{f}" stroke="{s}" stroke-width="2"{dash}/>'
    )
    text(x + 44, y + 16, label, 12, anchor="start")
flows = [
    ("shared", False, "data flow, shared"),
    ("ambient", False, "ambient (pass 1)"),
    ("dictation", False, "dictation"),
    ("batch", False, "batch (pass 2)"),
    ("os", True, "OS / device interface"),
]
for i, (k, dashed, label) in enumerate(flows):
    x, y = lx + 2010 + (i // 3) * 220, ly + 30 + (i % 3) * 30
    pattern = schematic.DASH["dotted"] if dashed else FLOW_DASH[k]
    dash = f' stroke-dasharray="{pattern}"' if pattern else ""
    out.append(
        f'<line x1="{x}" y1="{y}" x2="{x + 40}" y2="{y}" stroke="{FLOW[k]}" stroke-width="{FLOW_WIDTH[k]}"{dash} marker-end="url(#a-{k})"/>'
    )
    text(x + 50, y + 4, label, 12, anchor="start")

defs = "".join(
    f'<marker id="a-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
    f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
    for k, c in FLOW.items()
)
page = Page(W, H + 220)
page.header("DETAILED ARCHITECTURE", doc="OD-ADR-0005")
page.add(f"<defs>{defs}</defs>")
page.add('<g transform="translate(0, 100)">' + "\n".join(out) + "</g>")
page.footer("Figure 1-2.  Components, Files and Flows", "1-2")
with open(sys.argv[1] if len(sys.argv) > 1 else "arch.svg", "w") as f:
    f.write(page.svg())
