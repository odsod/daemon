"""Overview schematic: the five services on one host. Hero image of the README.

Usage: uv run docs/diagrams/overview.py docs/diagrams/overview.svg
"""

import sys

from schematic import DASHED, GRAY, HEAVY, THIN, Page

W, H = 1400, 1000
p = Page(W, H)
p.header("OD-ADR-0002", "SYSTEM CONFIGURATION")

# ------------------------------------------------------------------ blocks
KX, KY, KW, KH = 250, 205, 210, 100  # keys
SX, SY, SW, SH = 600, 195, 250, 120  # session
TX, TY, TW, TH = 885, 195, 150, 50  # tray
CX, CY, CW, CH = 250, 380, 210, 100  # capture
DX, DY, DW, DH = 600, 360, 360, 140  # centered on the capture flow  # state drum
PX, PY, PW, PH = 250, 570, 710, 190  # pipeline

p.block(
    KX,
    KY,
    KW,
    KH,
    "KEYS",
    ports=[("l", 0.5, "EVDEV"), ("t", 0.5, "UINPUT"), ("r", 0.5, "SOCKET")],
    size=20,
)
p.callout(KX, KY, "A", 17)

# ------------------------------------------------------------------ odsod-daemon
p.boundary(
    [(215, 165), (1060, 165), (1060, 775), (215, 775)], "ODSOD-DAEMON", 220, 158
)

p.rect(SX, SY, SW, SH, width=2.2)
p.callout(SX, SY, "D", 17)
p.text(SX + 26, SY + 26, "SESSION", 20, "bold", anchor="start")
p.port(SX, SY, SW, SH, "b", 0.5, "FILES")
sw, sg = 94, 17
sx0 = SX + 22
sy = KY + KH / 2 - 22  # centered on the keys socket line
for i, name in enumerate(["DICTATION", "SHORTCUTS"]):
    p.block(sx0 + i * (sw + sg), sy, sw, 44, name, width=1.4, size=12)
sx_last = sx0 + 1 * (sw + sg) + sw

p.block(TX, TY, TW, TH, "TRAY", size=16)
p.callout(TX, TY, "E", 17)
FX = DX + DW / 2  # vertical flows through the state drum

p.block(
    CX, CY, CW, CH, "CAPTURE", ports=[("l", 0.5, "PCM"), ("r", 0.5, "AUDIO")], size=20
)
p.callout(CX, CY, "B", 17)

p.drum(DX, DY, DW, DH, "STATE/", ["AUDIO BUFFER · STREAMS · DOCUMENTS"])

p.rect(PX, PY, PW, PH, width=2.2)
p.callout(PX, PY, "C", 17)
p.text(PX + 26, PY + 26, "PIPELINE", 20, "bold", anchor="start")
p.port(PX, PY, PW, PH, "b", 0.47, "HTTP")
p.port(PX, PY, PW, PH, "t", 0.76, "FILES")

bw, bh, gap = 150, 44, 22
x0 = PX + 22
ya, yb = PY + 50, PY + 120
row_a = ["SEGMENTATION", "TRANSCRIPTION", "CLEANUP", "TRANSCRIPT"]
row_b = ["SIGNALS", "INTERACTIONS", "PUBLISH"]
for row, y, weight in ((row_a, ya, HEAVY), (row_b, yb, THIN)):
    for i, name in enumerate(row):
        bx = x0 + i * (bw + gap)
        p.block(bx, y, bw, bh, name, width=1.4, size=13)
        if i:
            p.flow([(bx - gap, y + bh / 2), (bx, y + bh / 2)], width=weight)
p.flow(
    [
        (x0 + 3 * (bw + gap) + bw / 2, ya + bh),
        (x0 + 3 * (bw + gap) + bw / 2, yb + 13),
        (x0 + 2 * (bw + gap) + bw, yb + 13),
    ],
    width=THIN,
)

# ------------------------------------------------------------------ flows between blocks
p.flow(
    [(KX + KW, KY + KH / 2), (sx0, KY + KH / 2)],
    "START, STOP,\nPASTE",
    width=HEAVY,
    both=True,
)
p.flow([(CX + CW, CY + CH / 2), (DX, CY + CH / 2)], "AUDIO BLOCKS", width=HEAVY)
p.flow(
    [(SX + SW / 2, SY + SH), (SX + SW / 2, DY)],
    "UTTERANCES, TEXT",
    width=HEAVY,
    both=True,
)
p.flow(
    [(FX, DY + DH), (FX, PY)], "READ, WRITE", width=HEAVY, both=True
)

# ------------------------------------------------------------------ outside systems
p.ext(40, KY + 15, 150, KH - 30, "KEYBOARDS", ["/dev/input"])
p.flow([(190, KY + KH / 2), (KX, KY + KH / 2)], width=THIN)

p.ext(40, CY + 10, 150, CH - 20, "PIPEWIRE", ["MIC, SYSTEM AUDIO"])
p.flow([(190, CY + CH / 2), (CX, CY + CH / 2)], width=HEAVY)

p.ext(40, yb - 13, 150, bh + 26, "BROWSER", ["MEETING TABS (CDP)"])
p.flow([(190, yb + bh / 2), (x0, yb + bh / 2)], width=THIN)

p.ext(
    1110,
    130,
    250,
    160,
    "KDE PLASMA",
    ["APPLICATIONS", "KWIN SCRIPT", "SYSTEM TRAY"],
    size=17,
)
p.flow(
    [(KX + KW / 2, KY), (KX + KW / 2, 150), (1110, 150)],
    "REMAPPED KEYS, PASTE CHORD",
    at=1,
    width=THIN,
)
p.flow(
    [(sx_last, KY + KH / 2), (1110, KY + KH / 2)],
    width=THIN,
    both=True,
)
p.lines(862, KY + KH / 2 + 16, ["SHORTCUTS,", "APP LAUNCH"], 11, anchor="start", lead=12)
p.flow([(TX + TW, TY + TH / 2), (1110, TY + TH / 2)], width=THIN)
p.flow([(TX + 57, TY + TH), (TX + 57, DY + 10)], "STATUS,\nHEALTH", width=THIN)

p.ext(1110, 690, 250, 76, "TARGET DIRS", ["VAULT INBOX"], size=17)
p.flow(
    [(x0 + 2 * (bw + gap) + bw, yb + bh - 12), (1110, yb + bh - 12)],
    width=THIN,
    dash=DASHED,
)
p.lines(975, yb + bh - 31, ["FINISHED", "DOCUMENTS"], 11, anchor="start", lead=12)

ix = PX + PW * 0.47
p.ext(
    ix - 230, 815, 460, 52, "INFERENCE HOST", ["WHISPER-SERVER · LLAMA-SERVER"], size=17
)
p.flow([(ix, PY + PH), (ix, 815)], "TAILNET: AUDIO SLICES, TEXT", width=THIN, both=True)

# ------------------------------------------------------------------ key
kx, ky, kw = 1100, 335, 260


def letter(ch):
    return lambda x, y: p.callout(x, y, ch, 11)


p.table(
    kx,
    ky,
    kw,
    "SERVICES",
    [
        (letter("A"), "KEYS", "ROOT, FROM BOOT"),
        (letter("B"), "CAPTURE", "LOGIN SESSION"),
        (letter("C"), "PIPELINE", "RESTARTS FREELY"),
        (letter("D"), "SESSION", "GRAPHICAL SESSION"),
        (letter("E"), "TRAY", "GRAPHICAL SESSION"),
    ],
    [(22, "middle"), (44, "start"), (126, "start")],
    row_h=30,
)
p.text(kx, ky + 230, "HEAVY LINE: SPEECH PATH", 11, anchor="start", fill=GRAY)
p.text(kx, ky + 246, "DASHED LINE: BATCH PASS", 11, anchor="start", fill=GRAY)
p.text(kx, ky + 262, "DASHED BOX: OUTSIDE SYSTEM", 11, anchor="start", fill=GRAY)
p.text(kx, ky + 278, "DASH-DOT LINE: ODSOD-DAEMON", 11, anchor="start", fill=GRAY)

p.footer("OD-2-001", "Figure 1-1.  Service Configuration", "1-1")
with open(sys.argv[1] if len(sys.argv) > 1 else "overview.svg", "w") as f:
    f.write(p.svg())
