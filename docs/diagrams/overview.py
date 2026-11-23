"""Overview diagram: the four daemons on one host. Hero image of the README.

Usage: uv run docs/diagrams/overview.py docs/diagrams/overview.svg
"""

import sys

from schematic import DASH, GRAY, INK, MONO, PAPER, Page

W, H = 1400, 1000
p = Page(W, H)
p.header("SYSTEM CONFIGURATION")


def block(x, y, w, h, title, lines=(), kind="daemon", letter=None, title_size=21):
    """kind: daemon (heavy outline), part (thin), ext (dashed, outside the system)."""
    if kind == "daemon":
        p.rect(x, y, w, h, width=3, fill=PAPER)
    elif kind == "part":
        p.rect(x, y, w, h, width=1.5, fill=PAPER)
    else:
        p.rect(x, y, w, h, width=1.5, fill=PAPER, dash="7 5")
    n = len(lines)
    ty = y + h / 2 - (n * 20) / 2 + (6 if n else 7)
    p.text(x + w / 2, ty, title, title_size if kind != "part" else 15, "bold")
    for i, line in enumerate(lines):
        p.text(
            x + w / 2, ty + 22 * (i + 1), line, 15, fill=GRAY if kind == "ext" else INK
        )
    if letter:
        p.callout(x, y, letter, 17)


def store(x, y, w, h, title, lines=()):
    """Storage drum: the file system interface."""
    ry = 12
    p.add(
        f'<path d="M{x},{y + ry} L{x},{y + h - ry} A{w / 2},{ry} 0 0 0 {x + w},{y + h - ry} '
        f'L{x + w},{y + ry}" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>'
    )
    p.add(
        f'<ellipse cx="{x + w / 2}" cy="{y + ry}" rx="{w / 2}" ry="{ry}" fill="{PAPER}" '
        f'stroke="{INK}" stroke-width="2"/>'
    )
    p.text(x + w / 2, y + 48, title, 18, "bold", family=MONO)
    for i, line in enumerate(lines):
        p.text(x + w / 2, y + 48 + 22 * (i + 1), line, 15)


def label(x, y, s, anchor="middle", size=14):
    p.text(x, y, s, size, "bold", anchor=anchor, extra='letter-spacing="0.5"')


# ------------------------------------------------------------------ row 1: keys, session
block(40, 205, 170, 90, "KEYBOARDS", ["/dev/input"], kind="ext")
block(300, 195, 210, 110, "KEYS", ["DEVICE LEVEL"], letter="A")
block(620, 185, 340, 130, "SESSION", ["DICTATION · TRAY · SHORTCUTS"], letter="D")
block(1110, 205, 250, 90, "KDE PLASMA", ["APPLICATIONS"], kind="ext")

p.path([(210, 250), (300, 250)], dash=DASH["dotted"])
label(255, 240, "EVDEV")
p.path([(510, 250), (620, 250)], width=2, both=True)
label(565, 240, "SOCKET")
p.path([(960, 250), (1110, 250)], both=True, dash=DASH["dotted"])
label(1035, 240, "D-BUS")
p.path([(405, 195), (405, 135), (1235, 135), (1235, 205)], dash=DASH["dotted"])
label(820, 128, "UINPUT: REMAPPED KEYS, PASTE")

# ------------------------------------------------------------------ row 2: capture, state
block(40, 360, 170, 100, "PIPEWIRE", ["MIC, SYSTEM", "AUDIO"], kind="ext")
block(300, 360, 210, 100, "CAPTURE", ["ALWAYS ON"], letter="B")
store(620, 345, 340, 140, "STATE/", ["AUDIO BUFFER · STREAMS", "DOCUMENTS"])

p.path([(210, 410), (300, 410)], dash=DASH["dotted"])
label(255, 400, "PCM")
p.path([(510, 410), (620, 410)])
label(565, 400, "AUDIO")
p.path([(790, 315), (790, 345)], both=True)
label(800, 336, "UTTERANCES, TEXT", anchor="start", size=12)

# ------------------------------------------------------------------ row 3: pipeline
px, py, pw, ph = 300, 530, 660, 190
block(px, py, pw, ph, "", kind="daemon", letter="C")
label(px + 26, py + 28, "PIPELINE", anchor="start", size=18)
bw, bh, gap = 145, 46, 18
x0 = px + 20
row_a = ["SEGMENTATION", "TRANSCRIPTION", "CLEANUP", "TRANSCRIPT"]
row_b = ["SIGNALS", "INTERACTIONS", "PUBLISH"]
ya, yb = py + 48, py + 122
for i, name in enumerate(row_a):
    block(x0 + i * (bw + gap), ya, bw, bh, name, kind="part")
    if i:
        p.path(
            [
                (x0 + i * (bw + gap) - gap, ya + bh / 2),
                (x0 + i * (bw + gap), ya + bh / 2),
            ],
            width=1.5,
        )
for i, name in enumerate(row_b):
    block(x0 + i * (bw + gap), yb, bw, bh, name, kind="part")
    if i:
        p.path(
            [
                (x0 + i * (bw + gap) - gap, yb + bh / 2),
                (x0 + i * (bw + gap), yb + bh / 2),
            ],
            width=1.5,
        )

p.path([(790, 485), (790, 530)], both=True)
label(800, 512, "READ, WRITE", anchor="start", size=12)

block(40, 640, 170, 90, "BROWSER", ["MEETINGS (CDP)"], kind="ext")
p.path([(210, 685), (x0, 685)], dash=DASH["dotted"])

block(1110, 640, 250, 90, "TARGET DIRS", ["VAULT INBOX"], kind="ext")
p.path([(x0 + 2 * (bw + gap) + bw, 685), (1110, 685)], dash=DASH["dotted"])
label(1035, 675, "COPY")

# ------------------------------------------------------------------ inference host
block(
    300,
    780,
    660,
    64,
    "INFERENCE HOST",
    ["WHISPER-SERVER · LLAMA-SERVER"],
    kind="ext",
    title_size=17,
)
p.path([(630, 720), (630, 780)], dash=DASH["dotted"], both=True)
label(640, 756, "HTTP", anchor="start")

# ------------------------------------------------------------------ key
kx, ky = 1110, 345
label(kx, ky, "DAEMONS", anchor="start", size=15)
p.add(
    f'<line x1="{kx}" y1="{ky + 8}" x2="{kx + 250}" y2="{ky + 8}" stroke="{INK}" stroke-width="1.5"/>'
)
keys = [
    ("A", "KEYS", "ROOT, FROM BOOT"),
    ("B", "CAPTURE", "NEVER STOPS"),
    ("C", "PIPELINE", "RESTARTS FREELY"),
    ("D", "SESSION", "GRAPHICAL SESSION"),
]
for i, (letter, name, note) in enumerate(keys):
    y = ky + 40 + i * 54
    p.callout(kx + 14, y - 5, letter, 13)
    p.text(kx + 40, y, name, 15, "bold", anchor="start")
    p.text(kx + 40, y + 19, note, 13, anchor="start", fill=GRAY)

p.footer("Figure 1-1.  Daemon Configuration", "1-1")
with open(sys.argv[1] if len(sys.argv) > 1 else "overview.svg", "w") as f:
    f.write(p.svg())
