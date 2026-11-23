"""Shared drawing style for the diagrams: a monochrome engineering schematic sheet.

Black line art on paper, uppercase lettering, circled callout letters, a
header with the document number and a footer form with dates and page.
"""

from xml.sax.saxutils import escape

PAPER = "#f7f5ee"
INK = "#1b1b1b"
GRAY = "#6b6b6b"
SANS = "Helvetica Neue, Helvetica, Arial, sans-serif"
MONO = "Courier New, Courier, monospace"

# Line styles replace colors: one dash pattern per kind of flow.
DASH = {
    "solid": "",
    "dashed": "10 6",
    "dotted": "2 5",
}

DOC_NUMBER = "OD-ADR-0002"
TITLE = "ODSOD-DAEMON SCHEMATIC"
BASIC_DATE = "23 Nov 2026"


class Page:
    def __init__(self, width, height):
        self.w = width
        self.h = height
        self.out = []

    def add(self, s):
        self.out.append(s)

    def text(
        self,
        x,
        y,
        s,
        size=16,
        weight="normal",
        family=SANS,
        anchor="middle",
        fill=INK,
        extra="",
    ):
        self.add(
            f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" text-anchor="{anchor}" fill="{fill}" {extra}>{escape(s)}</text>'
        )

    def rect(self, x, y, w, h, stroke=INK, width=2, fill="none", dash="", rx=0):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{width}"{d}/>'
        )

    def path(
        self, points, width=2, dash="", arrow=True, both=False, stroke=INK, halo=True
    ):
        d = " ".join(
            f"{'M' if i == 0 else 'L'}{x},{y}" for i, (x, y) in enumerate(points)
        )
        if halo:
            self.add(
                f'<path d="{d}" fill="none" stroke="{PAPER}" stroke-width="{width + 5}"/>'
            )
        dd = f' stroke-dasharray="{dash}"' if dash else ""
        end = ' marker-end="url(#arrow)"' if arrow else ""
        start = ' marker-start="url(#arrow)"' if both else ""
        self.add(
            f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{width}"{dd}{end}{start}/>'
        )

    def callout(self, x, y, letter, r=15):
        self.add(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{INK}"/>')
        self.text(x, y + r * 0.4, letter, int(r * 1.15), "bold", fill=PAPER)

    def header(self, section, doc=DOC_NUMBER):
        cx = self.w / 2
        self.text(cx, 38, doc, 18, family=MONO)
        self.text(cx, 64, TITLE, 20, family=MONO)
        self.text(cx, 100, section, 18, family=MONO)
        self.add(
            f'<line x1="40" y1="116" x2="{self.w - 40}" y2="116" stroke="{INK}" stroke-width="2"/>'
        )

    def footer(self, caption, page):
        cx, h = self.w / 2, self.h
        self.text(cx, h - 108, caption, 19, family=MONO)
        self.add(
            f'<line x1="40" y1="{h - 90}" x2="{self.w - 40}" y2="{h - 90}" stroke="{INK}" stroke-width="2"/>'
        )
        self.text(cx, h - 62, "HOST CONFIGURATION", 18, family=MONO)
        y = h - 24
        self.text(40, y, "Host ____________", 17, family=MONO, anchor="start")
        self.text(cx - 40, y, f"Basic Date {BASIC_DATE}", 17, family=MONO)
        self.text(cx + 260, y, "Change Date ________", 17, family=MONO)
        self.text(self.w - 40, y, f"Page {page}", 17, family=MONO, anchor="end")

    def svg(self):
        defs = (
            '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            'markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{INK}"/></marker>'
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}"><defs>{defs}</defs>'
            f'<rect width="{self.w}" height="{self.h}" fill="{PAPER}"/>'
            + "\n".join(self.out)
            + "</svg>"
        )
