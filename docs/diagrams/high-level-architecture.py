"""High-level architecture diagram for ADR-0002. Writes arch.svg."""

import sys
from xml.sax.saxutils import escape

W, H = 2480, 1440
SANS = "Adwaita Sans"
MONO = "Adwaita Mono"

STYLE = {
    "keys": ("#fde4e1", "#b5473a"),
    "capture": ("#d7f0ec", "#2a8c7f"),
    "session": ("#e3f2d9", "#4f8a2b"),
    "pipeline": ("#dde8f7", "#3a6ab0"),
    "cli": ("#ece4f5", "#7a5aa6"),
    "store": ("#fff2cc", "#b38600"),
    "run": ("#fffaf0", "#b38600"),
    "vault": ("#ffe3b3", "#9a6200"),
    "ext": ("#efefef", "#8a8a8a"),
}
FLOW = {
    "shared": "#444444",
    "ambient": "#3a6ab0",
    "dictation": "#4f8a2b",
    "batch": "#d0701a",
    "os": "#8a8a8a",
}

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
            f'<rect x="{bx}" y="{by}" width="50" height="20" rx="10" fill="#f1e6fb" '
            f'stroke="#8a4fc4" stroke-width="1.5"/>'
        )
        text(bx + 25, by + 14, badge, 11, "bold", fill="#6a2fa4")


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
    dash = ' stroke-dasharray="3 4"' if dashed else ""
    # white halo so crossings read as pass-overs
    out.append(f'<path d="{d}" fill="none" stroke="white" stroke-width="7"/>')
    out.append(
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.2"{dash} '
        f'marker-end="url(#a-{flow})"/>'
    )
    if label:
        lx, ly = lpos
        text(lx, ly, label, 12, "bold", fill=color, anchor=lanchor)


# ---------------------------------------------------------------- frame
out.append(f'<rect width="{W}" height="{H}" fill="white"/>')
text(
    40,
    42,
    "odsod-daemon: high-level architecture (ADR-0002 to ADR-0008)",
    24,
    "bold",
    anchor="start",
)
text(
    40,
    66,
    "Arrows show data flow: writer to file, file to reader. Paths and formats: ADR-0003.",
    14,
    anchor="start",
    fill="#555",
)
out.append(
    '<rect x="20" y="90" width="2440" height="1090" rx="16" fill="none" '
    'stroke="#999" stroke-width="2" stroke-dasharray="10 6"/>'
)
text(40, 114, "EACH HOST", 14, "bold", anchor="start", fill="#777")

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
box("indicator", 1450, 210, "session", "tray", ["mode + health;", "pause stops capture"], w=180)
box("shortcuts", 1950, 210, "session", "shortcuts", ["global shortcuts,", "launch apps"], w=180)
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
    ["VAD: utterances;", "interaction ends"],
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
    "reprocessing",
    ["diarize, name speakers,", "summarize (pass 2)"],
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
text(ax0 + 20, ay + 33, "read by segmentation, transcription, reprocessing, bench", 12, anchor="start", fill="#555")

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
    ["transcripts/", "<day>-<host>.md", "daily log, pass 1", "", "interactions/", "<day>-<HHMM>-<host>", "-<slug>.md", "transcript + summary,", "pass 2"],
    path="state/documents/",
    w=200,
    h=250,
)
box("publish", 2330, 960, "pipeline", "publish", ["copy finished docs,", "write once"])
box("targets", 2330, 1100, "ext", "target dirs", ["from config, e.g. a", "vault inbox"], w=200)

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
line(
    [edge("seg", "r"), edge("jobs", "l")], "ambient"
)
line([edge("jobs", "r"), edge("asrw", "l")])
line([edge("asrw", "r"), edge("asr", "l")])
line([edge("asr", "r"), edge("cleanup", "l")])
line([edge("gloss", "b"), edge("cleanup", "t")])
line([edge("cleanup", "r"), edge("text", "l")])
line([edge("text", "r"), edge("transcript", "l")], "ambient")
line([edge("transcript", "r"), edge("docs", "l", -115)], "ambient")
# dictation
line([edge("kbd", "r"), edge("input", "l")], "os", True)
line([edge("input", "r"), edge("session", "l")], "dictation", label="socket", lpos=(900, 202))
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
    [edge("events", "t", 50), edge("seg", "b", -40)],
    label="pins, meetings",
    lpos=(700, 720),
    lanchor="start",
)
line(
    [edge("events", "b", 40), (610, 1130), (2110, 1130), edge("transcript", "b")],
    "ambient",
    label="notes, pins, meetings to the daily log",
    lpos=(2090, 1120),
    lanchor="end",
)
# batch
line(
    [edge("seg", "b", 40), edge("inter", "l")],
    "batch",
    label="interaction ends",
    lpos=(880, 760),
)
line([edge("inter", "r"), edge("reproc", "l")], "batch")
line(
    [edge("events", "b", -40), (530, 1000), (1200, 1000), edge("reproc", "b", -30)],
    "batch",
    label="speaker events",
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
    '<rect x="900" y="1220" width="1100" height="90" rx="12" fill="#f6effc" stroke="#8a4fc4" '
    'stroke-width="2" stroke-dasharray="10 6"/>'
)
text(1450, 1252, "INFERENCE HOST (desktop GPU)", 15, "bold", fill="#6a2fa4")
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
text(1450, 1206, "components with an HTTP badge call these servers", 12, fill="#6a2fa4")

# ---------------------------------------------------------------- legend
lx, ly = 40, 1215
text(lx, ly, "LEGEND", 14, "bold", anchor="start", fill="#777")
items = [
    ("keys", "odsod-daemon-keys.service (system, root, C)"),
    ("capture", "odsod-daemon-capture.service (always on)"),
    ("session", "odsod-daemon-session.service: dictation, tray, shortcuts"),
    ("pipeline", "odsod-daemon-pipeline.service (restartable)"),
    ("cli", "command (on demand)"),
    ("store", "file interface (state/ = $XDG_STATE_HOME/odsod-daemon)"),
    ("run", "runtime file (run/ = $XDG_RUNTIME_DIR/odsod-daemon, tmpfs)"),
    ("ext", "outside odsod-daemon"),
]
for i, (k, label) in enumerate(items):
    col, row = divmod(i, 4)
    x, y = lx + col * 420, ly + 18 + row * 46
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
    dash = ' stroke-dasharray="3 4"' if dashed else ""
    out.append(
        f'<line x1="{x}" y1="{y}" x2="{x + 40}" y2="{y}" stroke="{FLOW[k]}" stroke-width="2.2"{dash} marker-end="url(#a-{k})"/>'
    )
    text(x + 50, y + 4, label, 12, anchor="start")

defs = "".join(
    f'<marker id="a-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
    f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
    for k, c in FLOW.items()
)
svg = (
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
    f"<defs>{defs}</defs>" + "\n".join(out) + "</svg>"
)
open(sys.argv[1] if len(sys.argv) > 1 else "arch.svg", "w").write(svg)
