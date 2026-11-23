"""Shared drawing style for the diagrams: a monochrome engineering schematic.

After Apollo-era block diagrams: square boxes with port labels on their inner
edges, signal names written on the lines, open-ended arrows for systems
outside the sheet, line weight for importance, mode tags, junction dots,
framed key tables, and a header and footer form.
"""

from xml.sax.saxutils import escape

PAPER = "#f7f5ee"
INK = "#1b1b1b"
GRAY = "#6b6b6b"
LETTER = "Futura, 'Century Gothic', 'Avenir Next Condensed', 'Arial Narrow', Arial, sans-serif"
MONO = "'Courier New', Courier, monospace"

TITLE = "ODSOD-DAEMON SCHEMATIC"
BASIC_DATE = "23 Nov 2026"

# Line weights: the main signal path is heavy, everything else thin.
HEAVY = 3.4
THIN = 1.6
DASHED = "11 6"
DASH_DOT = "18 5 3 5"


class Page:
    def __init__(self, width, height):
        self.w = width
        self.h = height
        self.out = []

    # ------------------------------------------------------------ primitives

    def add(self, s):
        self.out.append(s)

    def text(
        self,
        x,
        y,
        s,
        size=14,
        weight="normal",
        family=LETTER,
        anchor="middle",
        fill=INK,
    ):
        self.add(
            f'<text x="{x}" y="{y}" font-family="{escape(family)}" font-size="{size}" '
            f'font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">{escape(s)}</text>'
        )

    def lines(
        self,
        x,
        y,
        rows,
        size=14,
        weight="normal",
        anchor="middle",
        family=LETTER,
        lead=None,
    ):
        lead = lead or size * 1.2
        for i, row in enumerate(rows):
            self.text(x, y + i * lead, row, size, weight, family, anchor)

    def rect(self, x, y, w, h, width=THIN, fill="none", dash=""):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" '
            f'stroke="{INK}" stroke-width="{width}"{d}/>'
        )

    def hline(self, x1, x2, y, width=THIN):
        self.add(
            f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{INK}" stroke-width="{width}"/>'
        )

    # ------------------------------------------------------------ blocks

    def block(self, x, y, w, h, title, ports=(), width=2.2, size=16):
        """Square box. ports: (side, offset 0..1, label), drawn on the inner edge."""
        self.rect(x, y, w, h, width=width, fill=PAPER)
        rows = title.split("\n")
        self.lines(
            x + w / 2,
            y + h / 2 - (len(rows) - 1) * size * 0.6 + size * 0.35,
            rows,
            size,
            "bold",
        )
        for side, at, label in ports:
            self.port(x, y, w, h, side, at, label)

    def ext(self, x, y, w, h, title, rows=(), size=14):
        """A system outside odsod-daemon: thin dashed box."""
        self.rect(x, y, w, h, width=1.4, fill=PAPER, dash="6 4")
        n = len(rows)
        ty = y + h / 2 - n * 7 + size * 0.35
        self.text(x + w / 2, ty, title, size, "bold")
        self.lines(x + w / 2, ty + 17, rows, 11, lead=14)

    def port(self, x, y, w, h, side, at, label, size=10):
        if side == "l":
            self.text(x + 5, y + h * at + 4, label, size, anchor="start")
        elif side == "r":
            self.text(x + w - 5, y + h * at + 4, label, size, anchor="end")
        elif side == "t":
            self.text(x + w * at, y + 14, label, size)
        else:
            self.text(x + w * at, y + h - 6, label, size)

    def store(self, x, y, w, h, path, rows=()):
        """A file in state/: folder outline with the path in typewriter."""
        t = 12
        self.add(
            f'<path d="M{x},{y + t} L{x},{y + h} L{x + w},{y + h} L{x + w},{y + t} '
            f'L{x + 58},{y + t} L{x + 50},{y} L{x},{y} Z" fill="{PAPER}" stroke="{INK}" '
            f'stroke-width="{THIN}"/>'
        )
        self.text(x + w / 2, y + t + 20, path, 13, "bold", MONO)
        self.lines(x + w / 2, y + t + 38, rows, 11)

    def drum(self, x, y, w, h, title, rows=()):
        ry = 11
        self.add(
            f'<path d="M{x},{y + ry} L{x},{y + h - ry} A{w / 2},{ry} 0 0 0 {x + w},{y + h - ry} '
            f'L{x + w},{y + ry}" fill="{PAPER}" stroke="{INK}" stroke-width="2.2"/>'
        )
        self.add(
            f'<ellipse cx="{x + w / 2}" cy="{y + ry}" rx="{w / 2}" ry="{ry}" fill="{PAPER}" '
            f'stroke="{INK}" stroke-width="2.2"/>'
        )
        # title centered on the drum, so a flow at y + h / 2 meets it
        self.text(x + w / 2, y + h / 2 + 6, title, 17, "bold", MONO)
        self.lines(x + w / 2, y + h / 2 + 30, rows, 13)

    def boundary(self, points, label, lx, ly):
        """Boundary of odsod-daemon, the whole system: dash-dot outline."""
        d = " ".join(f"{x},{y}" for x, y in points)
        self.add(
            f'<polygon points="{d}" fill="none" stroke="{INK}" stroke-width="1.8" '
            f'stroke-dasharray="{DASH_DOT}"/>'
        )
        self.text(lx, ly, label, 13, "bold", anchor="start")

    def frame(self, x, y, w, h, letter, name):
        """Boundary of one service: thin dashed frame with a filled letter."""
        self.rect(x, y, w, h, width=1.2, dash="4 4")
        self.callout(x + 2, y + 2, letter, 13)
        self.text(x + 22, y + 18, name, 12, "bold", anchor="start")

    # ------------------------------------------------------------ flows

    def flow(
        self,
        points,
        label=None,
        at=0,
        width=THIN,
        dash="",
        arrow=True,
        both=False,
        above=True,
        anchor="start",
    ):
        """A signal line. The label sits on segment `at`, above the line."""
        d = " ".join(
            f"{'M' if i == 0 else 'L'}{x},{y}" for i, (x, y) in enumerate(points)
        )
        self.add(
            f'<path d="{d}" fill="none" stroke="{PAPER}" stroke-width="{width + 6}"/>'
        )
        dd = f' stroke-dasharray="{dash}"' if dash else ""
        end = ' marker-end="url(#arrow)"' if arrow else ""
        start = ' marker-start="url(#arrow)"' if both else ""
        self.add(
            f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{width}"{dd}{end}{start}/>'
        )
        if label:
            (x1, y1), (x2, y2) = points[at], points[at + 1]
            rows = label.split("\n")
            if y1 == y2:
                lx = min(x1, x2) + 12 if anchor == "start" else (x1 + x2) / 2
                ly = y1 - 7 - (len(rows) - 1) * 12 if above else y1 + 16
                self.lines(lx, ly, rows, 11, anchor=anchor, lead=12)
            else:
                lx = x1 + 8
                ly = (y1 + y2) / 2 - (len(rows) - 1) * 6 + 4
                self.lines(lx, ly, rows, 11, anchor="start", lead=12)

    def open_end(self, x, y, rows, anchor="middle", size=12):
        """Label at the open end of a line to or from a system off the sheet."""
        self.lines(x, y, rows, size, "bold", anchor=anchor, lead=size * 1.2)

    def tag(self, x, y, label, vertical=False):
        """Mode tag: a break in the line with two bars, like the PF/CF/AF tags."""
        g = 5
        if vertical:
            self.add(
                f'<rect x="{x - 8}" y="{y - g}" width="16" height="{2 * g}" fill="{PAPER}"/>'
            )
            for dy in (-g, g):
                self.add(
                    f'<line x1="{x - 9}" y1="{y + dy}" x2="{x + 9}" y2="{y + dy}" stroke="{INK}" stroke-width="2"/>'
                )
            self.text(x + 14, y + 4, label, 10, "bold", anchor="start")
        else:
            self.add(
                f'<rect x="{x - g}" y="{y - 8}" width="{2 * g}" height="16" fill="{PAPER}"/>'
            )
            for dx in (-g, g):
                self.add(
                    f'<line x1="{x + dx}" y1="{y - 9}" x2="{x + dx}" y2="{y + 9}" stroke="{INK}" stroke-width="2"/>'
                )
            self.text(x, y - 13, label, 10, "bold")

    def dot(self, x, y, r=4):
        self.add(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{INK}"/>')

    def merge(self, x, y, r=11):
        """Summing junction: a circle with a cross."""
        self.add(
            f'<circle cx="{x}" cy="{y}" r="{r}" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>'
        )
        k = r * 0.7
        for a, b in (((-k, -k), (k, k)), ((-k, k), (k, -k))):
            self.add(
                f'<line x1="{x + a[0]}" y1="{y + a[1]}" x2="{x + b[0]}" y2="{y + b[1]}" '
                f'stroke="{INK}" stroke-width="2"/>'
            )

    # ------------------------------------------------------------ callouts and keys

    def callout(self, x, y, letter, r=15):
        """Filled letter: a service."""
        self.add(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{INK}"/>')
        self.text(x, y + r * 0.4, letter, int(r * 1.15), "bold", fill=PAPER)

    def number(self, x, y, n, leader=None, r=12):
        """Hollow number: a component. leader: point the leader line goes to."""
        if leader:
            self.add(
                f'<line x1="{x}" y1="{y}" x2="{leader[0]}" y2="{leader[1]}" stroke="{INK}" '
                f'stroke-width="1.2"/>'
            )
        self.add(
            f'<circle cx="{x}" cy="{y}" r="{r}" fill="{PAPER}" stroke="{INK}" stroke-width="1.6"/>'
        )
        self.text(x, y + 4.5, str(n), 13, "bold")

    def table(self, x, y, w, title, rows, cols, row_h=24):
        """Framed key table with a title band. cols: (x offset, anchor) per cell."""
        band = 30
        h = band + 10 + row_h * len(rows)
        self.rect(x, y, w, h, width=2, fill=PAPER)
        self.hline(x, x + w, y + band, width=2)
        self.text(x + w / 2, y + 21, title, 14, "bold")
        for i, row in enumerate(rows):
            ry = y + band + 4 + row_h * (i + 1) - 7
            for (dx, anchor), cell in zip(cols, row, strict=False):
                if callable(cell):
                    cell(x + dx, ry - 5)
                else:
                    self.text(x + dx, ry, cell, 12, anchor=anchor)
        return h

    # ------------------------------------------------------------ sheet

    def header(self, doc, section):
        cx = self.w / 2
        self.text(cx, 36, doc, 17, family=MONO)
        self.text(cx, 62, TITLE, 19, family=MONO)
        self.text(cx, 96, section, 17, family=MONO)
        self.hline(cx - 260, cx + 260, 104, width=1.2)
        self.hline(40, self.w - 40, 116, width=2)

    def footer(self, drawing, caption, page):
        cx, h = self.w / 2, self.h
        self.text(self.w - 40, h - 132, drawing, 13, "bold", anchor="end")
        self.text(cx, h - 104, caption, 19, family=MONO)
        self.hline(40, self.w - 40, h - 88, width=3)
        self.text(cx, h - 60, "HOST CONFIGURATION", 18, family=MONO)
        y = h - 22

        def field(x, label, value, width, anchor="start"):
            self.text(x, y, label, 16, family=MONO, anchor="start")
            vx = x + len(label) * 9.6 + 8
            self.hline(vx, vx + width, y + 4, width=1.2)
            if value:
                self.text(vx + width / 2, y - 2, value, 16, family=MONO)

        field(40, "Host", "", 170)
        field(cx - 250, "Basic Date", BASIC_DATE, 160)
        field(cx + 140, "Change Date", "", 160)
        field(self.w - 210, "Page", page, 110)

    def svg(self):
        defs = (
            '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="13" '
            'markerHeight="11" markerUnits="userSpaceOnUse" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{INK}"/></marker>'
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}"><defs>{defs}</defs>'
            f'<rect width="{self.w}" height="{self.h}" fill="{PAPER}"/>'
            + "\n".join(self.out)
            + "</svg>"
        )
