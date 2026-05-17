# Copyright 2026 David Wies
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Generator for geometry-app-ui-ux.drawio.

Run from the repository root:

    python spec/design/_generate_drawio.py

Produces spec/design/geometry-app-ui-ux.drawio with 15 pages of
wireframes. Re-run after editing this file to regenerate the diagrams.
"""

from __future__ import annotations

import html
import uuid
from dataclasses import dataclass, field
from pathlib import Path

# ─────────────────────────── style strings ────────────────────────────────
WIN = "rounded=0;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#666666;"
TIT = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#4D7EAF;"
    "fontColor=#FFFFFF;fontStyle=1;align=left;spacingLeft=12;strokeColor=none;fontSize=13;"
)
LBL = "text;html=1;align=left;verticalAlign=middle;"
LBLR = "text;html=1;align=right;verticalAlign=middle;"
INP = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#FFFFFF;"
    "strokeColor=#999999;align=left;spacingLeft=6;"
)
PLA = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#999999;"
    "align=left;spacingLeft=6;fontColor=#999999;fontStyle=2;"
)
RDO = (  # readonly look
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#FFFFFF;"
    "strokeColor=#999999;align=left;spacingLeft=6;"
)
BTN = "rounded=1;whiteSpace=wrap;html=1;fillColor=#E8E8E8;strokeColor=#999999;align=center;"
PBT = (
    "rounded=1;whiteSpace=wrap;html=1;fillColor=#4D7EAF;"
    "strokeColor=#4D7EAF;fontColor=#FFFFFF;fontStyle=1;align=center;"
)
DBT = (
    "rounded=1;whiteSpace=wrap;html=1;fillColor=#C0392B;"
    "strokeColor=#C0392B;fontColor=#FFFFFF;fontStyle=1;align=center;"
)
PNL = "rounded=0;whiteSpace=wrap;html=1;fillColor=#FAFAFA;strokeColor=#CCCCCC;"
CHH = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#F0F0F0;strokeColor=#CCCCCC;"
    "align=left;verticalAlign=middle;spacingLeft=12;fontStyle=1;"
)
TBA = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#FFFFFF;"
    "strokeColor=#999999;align=center;fontStyle=1;"
)
TBI = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#E8E8E8;"
    "strokeColor=#999999;align=center;fontColor=#666666;"
)
ACC = "rounded=0;whiteSpace=wrap;html=1;fillColor=#4D7EAF;strokeColor=none;"
RDE = "ellipse;fillColor=#FFFFFF;strokeColor=#666666;"
RDF = "ellipse;fillColor=#FFFFFF;strokeColor=#4D7EAF;strokeWidth=2;"
DOT = "ellipse;fillColor=#4D7EAF;strokeColor=none;"
CKE = "rounded=0;fillColor=#FFFFFF;strokeColor=#666666;"
CKC = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#4D7EAF;"
    "strokeColor=#4D7EAF;fontColor=#FFFFFF;fontStyle=1;align=center;fontSize=10;"
)
HNT = "text;html=1;align=left;verticalAlign=middle;fontColor=#666666;fontStyle=2;"
SEC = "text;html=1;align=left;verticalAlign=middle;fontStyle=1;fontSize=12;"
SWA = "rounded=0;whiteSpace=wrap;html=1;fillColor=#FF6633;strokeColor=#666666;"
SLT = "rounded=4;whiteSpace=wrap;html=1;fillColor=#CCCCCC;strokeColor=none;"
SLF = "rounded=4;whiteSpace=wrap;html=1;fillColor=#4D7EAF;strokeColor=none;"
SLH = "ellipse;fillColor=#FFFFFF;strokeColor=#4D7EAF;strokeWidth=2;"
DRP = "triangle;direction=south;fillColor=#666666;strokeColor=none;"  # combobox arrow
LST = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#999999;"
    "align=left;verticalAlign=top;spacingLeft=8;spacingTop=6;"
)
LSI = "text;html=1;align=left;verticalAlign=middle;"
PIL = (
    "rounded=20;whiteSpace=wrap;html=1;fillColor=#4D7EAF;"
    "strokeColor=#4D7EAF;fontColor=#FFFFFF;fontStyle=1;align=center;fontSize=10;"
)
BDG = (
    "rounded=20;whiteSpace=wrap;html=1;fillColor=#FFFFFF;"
    "strokeColor=#999999;fontStyle=1;align=center;fontSize=10;"
)
BAN = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#FFF8DC;"
    "strokeColor=#E1B870;align=left;spacingLeft=10;"
)
DIV = "endArrow=none;dashed=0;html=1;strokeColor=#CCCCCC;"


# ─────────────────────────── primitive emitter ────────────────────────────
@dataclass
class Page:
    """Accumulates mxCell XML fragments for a single draw.io diagram page."""

    name: str
    width: int = 1100
    height: int = 760
    cells: list[str] = field(default_factory=list)
    _next_id: int = 100

    def cid(self) -> str:
        """Return the next unique cell ID."""
        self._next_id += 1
        return f"c{self._next_id}"

    def cell(self, value: str, style: str, x: int, y: int, w: int, h: int) -> str:
        """Append a vertex mxCell and return its ID."""
        cid = self.cid()
        self.cells.append(
            f'<mxCell id="{cid}" value="{html.escape(value)}" style="{style}" '
            f'vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>'
            f"</mxCell>"
        )
        return cid

    def edge(self, x1: int, y1: int, x2: int, y2: int, style: str = DIV) -> None:
        """Append an edge (line) mxCell between two absolute points."""
        cid = self.cid()
        self.cells.append(
            f'<mxCell id="{cid}" style="{style}" edge="1" parent="1">'
            f'<mxGeometry relative="1" as="geometry">'
            f'<mxPoint x="{x1}" y="{y1}" as="sourcePoint"/>'
            f'<mxPoint x="{x2}" y="{y2}" as="targetPoint"/>'
            f"</mxGeometry></mxCell>"
        )


# ───────────────────────── high-level composites ──────────────────────────
def window(p: Page, x: int, y: int, w: int, h: int, title: str) -> None:
    """Render a titled window frame."""
    p.cell("", WIN, x, y, w, h)
    p.cell(title, TIT, x, y, w, 32)


def label(p: Page, x: int, y: int, w: int, h: int, text: str, style: str = LBL) -> None:
    """Render a text label."""
    p.cell(text, style, x, y, w, h)


def textfield(
    p: Page, x: int, y: int, w: int, h: int, placeholder: str = "", filled: str = ""
) -> None:
    """Render a text input; shows placeholder text when not filled."""
    if filled:
        p.cell(filled, INP, x, y, w, h)
    else:
        p.cell(placeholder, PLA, x, y, w, h)


def combobox(p: Page, x: int, y: int, w: int, h: int, current: str) -> None:
    """Render a combobox with a dropdown arrow indicator."""
    p.cell(current, INP, x, y, w, h)
    p.cell("", DRP, x + w - 16, y + (h - 8) // 2, 10, 8)


def primary_button(p: Page, x: int, y: int, w: int, h: int, text: str) -> None:
    """Render a filled primary-action button."""
    p.cell(text, PBT, x, y, w, h)


def button(p: Page, x: int, y: int, w: int, h: int, text: str) -> None:
    """Render a default secondary button."""
    p.cell(text, BTN, x, y, w, h)


def danger_button(p: Page, x: int, y: int, w: int, h: int, text: str) -> None:
    """Render a destructive-action (red) button."""
    p.cell(text, DBT, x, y, w, h)


def radio(p: Page, x: int, y: int, label_text: str, selected: bool, label_w: int = 90) -> None:
    """Render a radio button with its label."""
    if selected:
        p.cell("", RDF, x, y + 4, 14, 14)
        p.cell("", DOT, x + 4, y + 8, 6, 6)
    else:
        p.cell("", RDE, x, y + 4, 14, 14)
    p.cell(label_text, LBL, x + 18, y, label_w, 22)


def checkbox(p: Page, x: int, y: int, label_text: str, checked: bool, label_w: int = 180) -> None:
    """Render a checkbox with its label."""
    if checked:
        p.cell("✓", CKC, x, y + 4, 14, 14)
    else:
        p.cell("", CKE, x, y + 4, 14, 14)
    p.cell(label_text, LBL, x + 20, y, label_w, 22)


SWF = "rounded=0;whiteSpace=wrap;html=1;fillColor=#AACCFF;strokeColor=#666666;"  # fill-color swatch


def shared_header(
    p: Page, x: int, y: int, w: int, name_value: str = "", point_mode: bool = False
) -> int:
    """Render the Name + color/alpha rows common to every form; return y below.

    point_mode=True  → Point: single Color picker + alpha on one row.
    point_mode=False → all others: Line color + Fill color row, then alpha row.
    """
    inner_x = x + 16
    inner_w = w - 32
    # Name row
    label(p, inner_x, y, 60, 28, "Name")
    textfield(p, inner_x + 60, y, inner_w - 60, 28, "e.g. Point A", name_value)
    y += 36

    if point_mode:
        # Single color (marker) + alpha on one row — Point only
        label(p, inner_x, y, 60, 28, "Color")
        p.cell("", SWA, inner_x + 60, y + 2, 24, 24)
        textfield(p, inner_x + 90, y, 90, 28, filled="#FF6633")
        label(p, inner_x + 196, y, 50, 28, "Alpha")
        p.cell("", SLT, inner_x + 246, y + 11, 110, 6)
        p.cell("", SLF, inner_x + 246, y + 11, 80, 6)
        p.cell("", SLH, inner_x + 320, y + 6, 16, 16)
        p.cell("0.80", INP, inner_x + 346, y, 60, 28)
        y += 40
    else:
        # Row 2: line color + fill color
        label(p, inner_x, y, 80, 28, "Line color")
        p.cell("", SWA, inner_x + 80, y + 2, 24, 24)
        textfield(p, inner_x + 110, y, 80, 28, filled="#FF6633")
        label(p, inner_x + 202, y, 74, 28, "Fill color")
        p.cell("", SWF, inner_x + 276, y + 2, 24, 24)
        textfield(p, inner_x + 306, y, 80, 28, filled="#AACCFF")
        y += 36
        # Row 3: alpha
        label(p, inner_x, y, 50, 28, "Alpha")
        p.cell("", SLT, inner_x + 58, y + 11, 120, 6)
        p.cell("", SLF, inner_x + 58, y + 11, 90, 6)
        p.cell("", SLH, inner_x + 142, y + 6, 16, 16)
        p.cell("0.80", INP, inner_x + 168, y, 60, 28)
        y += 40

    return y


def divider(p: Page, x: int, y: int, w: int) -> int:
    """Draw a horizontal rule and return the y-coordinate below it."""
    p.edge(x + 16, y, x + w - 16, y)
    return y + 12


def action_row(
    p: Page, x: int, y: int, w: int, primary: str = "OK", secondary: str = "Cancel"
) -> None:
    """Render Cancel + primary buttons aligned to the bottom-right."""
    button(p, x + w - 16 - 88 - 12 - 88, y, 88, 32, secondary)
    primary_button(p, x + w - 16 - 88, y, 88, 32, primary)


def tabs(p: Page, x: int, y: int, w: int, active_idx: int, names: list[str]) -> int:
    """Render a tab strip; active tab has a 2-px blue accent top border."""
    tab_w = (w - 32) // len(names)
    for i, n in enumerate(names):
        tx = x + 16 + i * tab_w
        p.cell(n, TBA if i == active_idx else TBI, tx, y, tab_w, 32)
        if i == active_idx:
            p.cell("", ACC, tx, y, tab_w, 3)
    return y + 32


def field_row(
    p: Page, x: int, y: int, w: int, label_text: str, current: str, kind: str = "combobox"
) -> int:
    """Render a label + input row; return the y-coordinate below."""
    inner_x = x + 16
    inner_w = w - 32
    label(p, inner_x, y, 110, 28, label_text)
    if kind == "combobox":
        combobox(p, inner_x + 110, y, inner_w - 110, 28, current)
    elif kind == "text":
        textfield(p, inner_x + 110, y, inner_w - 110, 28, filled=current)
    elif kind == "readonly":
        p.cell(current, RDO, inner_x + 110, y, inner_w - 110, 28)
    return y + 36


def radio_row(
    p: Page, x: int, y: int, _w: int, label_text: str, options: list[tuple[str, bool]]
) -> int:
    """Render a label followed by a group of radio buttons; return y below."""
    inner_x = x + 16
    label(p, inner_x, y, 110, 28, label_text)
    rx = inner_x + 110
    for opt, sel in options:
        radio(p, rx, y + 3, opt, sel, label_w=100)
        rx += 18 + 100 + 12
    return y + 32


def reference_subcomponent(p: Page, x: int, y: int, w: int, enabled: bool = False) -> int:
    """Render the shared reference-point checkbox + combobox; return y below."""
    inner_x = x + 16
    inner_w = w - 32
    checkbox(p, inner_x, y, "Use reference point", enabled, label_w=160)
    label(p, inner_x + 200, y, 80, 22, "Reference:")
    if enabled:
        combobox(p, inner_x + 282, y, inner_w - 282, 28, "pt_002 — Origin (5.0, 7.0)")
    else:
        p.cell("(select a point)", PLA, inner_x + 282, y, inner_w - 282, 28)
    return y + 36


def section_label(p: Page, x: int, y: int, text: str, w: int = 460) -> int:
    """Render a bold section heading; return y below."""
    label(p, x + 16, y, w, 22, text, style=SEC)
    return y + 26


# ─────────────────────────── page authors ─────────────────────────────────


def page_main_window() -> Page:
    """Wireframe: main three-column application window."""
    p = Page("Main window", width=1300, height=820)

    # Menubar
    p.cell("", PNL, 0, 0, 1300, 28)
    for i, txt in enumerate(["File", "Edit", "View", "Help"]):
        label(p, 12 + i * 60, 0, 60, 28, txt)
    # Toolbar
    p.cell("", PNL, 0, 28, 1300, 40)
    for i, txt in enumerate(["📂", "💾", "↶", "↷", "↻", "✋", "🔍", "⚙"]):
        p.cell(txt, BTN, 12 + i * 38, 34, 30, 28)

    # Left panel
    p.cell("", PNL, 0, 68, 300, 712)
    label(p, 12, 76, 200, 22, "GeoSketch", style=SEC)
    # Cards
    y = 110
    p.cell("Create objects   ▼", CHH, 12, y, 276, 28)
    p.cell("", WIN, 12, y + 28, 276, 156)
    for i, name in enumerate(["Point", "Line", "Polygon", "Ray", "Vector", "Circle", "Tangent"]):
        col, row = i % 2, i // 2
        button(p, 24 + col * 128, y + 36 + row * 36, 120, 28, name)
    y += 28 + 156 + 12
    p.cell("Import   ▼", CHH, 12, y, 276, 28)
    p.cell("", WIN, 12, y + 28, 276, 80)
    button(p, 24, y + 36, 252, 28, "Import points from text…")
    button(p, 24, y + 70, 252, 28, "Import polygon from file…")
    y += 28 + 80 + 12
    p.cell("Calculations   ▶", CHH, 12, y, 276, 28)
    y += 28 + 12
    p.cell("Measurements   ▼", CHH, 12, y, 276, 28)
    p.cell("", WIN, 12, y + 28, 276, 156)
    for i, name in enumerate(
        ["Polygon Area", "Polygon Perim.", "Circle Area", "Circumf.", "Length", "Angle"]
    ):
        col, row = i % 2, i // 2
        button(p, 24 + col * 128, y + 36 + row * 36, 120, 28, name)

    # Center canvas
    p.cell("", WIN, 300, 68, 700, 712)
    # nav toolbar
    p.cell("", PNL, 308, 76, 684, 32)
    for i, txt in enumerate(["✋ Pan", "🔍 Zoom", "🏠 Fit", "↻ Refresh"]):
        st = PBT if txt == "↻ Refresh" else BTN
        p.cell(txt, st, 316 + i * 92, 82, 84, 22)
    # canvas content (placeholder: a polygon outline)
    p.cell(
        "",
        "rounded=0;whiteSpace=wrap;html=1;fillColor=#FFFCE0;strokeColor=#E1B870;fillOpacity=40;",
        500,
        250,
        280,
        220,
    )
    label(p, 540, 340, 200, 30, "Selected polygon (preview)", style=HNT)
    # cursor readout
    label(p, 308, 752, 280, 24, "Cursor: E 123,456.78  N 4,567,890.12", style=HNT)

    # Right panel
    p.cell("", PNL, 1000, 68, 300, 712)
    label(p, 1012, 76, 200, 22, "Properties", style=SEC)
    # Identity
    p.cell("Identity", CHH, 1012, 110, 276, 24)
    label(p, 1020, 138, 80, 24, "ID")
    p.cell("pg_001", RDO, 1100, 138, 180, 24)
    label(p, 1020, 168, 80, 24, "Name")
    textfield(p, 1100, 168, 180, 24, filled="Triangle ABC")
    # Appearance
    p.cell("Appearance", CHH, 1012, 204, 276, 24)
    label(p, 1020, 232, 72, 24, "Line color")
    p.cell("", SWA, 1092, 232, 20, 20)
    p.cell("#FFFF00", INP, 1116, 232, 68, 24)
    label(p, 1020, 260, 68, 24, "Fill color")
    p.cell("", SWF, 1092, 260, 20, 20)
    p.cell("#FFFFCC", INP, 1116, 260, 68, 24)
    label(p, 1020, 288, 60, 24, "Alpha")
    p.cell("", SLT, 1080, 299, 110, 6)
    p.cell("", SLF, 1080, 299, 82, 6)
    p.cell("", SLH, 1158, 294, 16, 16)
    label(p, 1196, 288, 60, 24, "0.75")
    checkbox(p, 1020, 316, "Visible on canvas", True, label_w=180)
    # Type-specific (polygon)
    p.cell("Polygon details", CHH, 1012, 352, 276, 24)
    label(p, 1020, 380, 140, 22, "Vertices: 3")
    label(p, 1020, 402, 140, 22, "is_convex: true")
    label(p, 1020, 424, 140, 22, "Area: 1,250.50 m²")
    label(p, 1020, 446, 200, 22, "Perimeter: 152.34 m")
    label(p, 1020, 470, 200, 22, "Vertex list:")
    p.cell("pt_001, pt_002, pt_003", RDO, 1020, 494, 260, 24)
    # Actions
    p.cell("Actions", CHH, 1012, 534, 276, 24)
    button(p, 1020, 566, 124, 32, "Edit…")
    danger_button(p, 1156, 566, 124, 32, "Delete…")

    # Status bar
    p.cell("", PNL, 0, 780, 1300, 40)
    label(p, 12, 780, 360, 40, "Triangle Project — geometry.json  •  unsaved")
    label(p, 600, 780, 200, 40, "Canvas: ⚠ stale  ↻ Refresh", style=HNT)
    label(p, 980, 780, 300, 40, "E 123,456.78  N 4,567,890.12", style=HNT)
    return p


# ─────────────────────────── object forms ─────────────────────────────────


def form_window(
    name: str, w: int, h: int, title: str, x: int = 80, y: int = 60
) -> tuple[Page, int, int]:
    """Create a Page sized for a dialog and draw its outer window frame."""
    p = Page(name, width=w + 200, height=h + 120)
    window(p, x, y, w, h, title)
    return p, x, y


def page_point_form() -> Page:
    """Wireframe: Point creation dialog."""
    form_w, form_h = 520, 460
    p, x, y0 = form_window("Point form", form_w, form_h, "New Point")
    y = y0 + 48
    y = shared_header(p, x, y, form_w, point_mode=True)
    y = divider(p, x, y, form_w)
    y = radio_row(p, x, y, form_w, "Input mode", [("Click on canvas", False), ("Form", True)])
    y = divider(p, x, y + 4, form_w)
    section_label(p, x, y, "Coordinates")
    y += 26
    y = field_row(p, x, y, form_w, "Easting (E)", "123456.789", kind="text")
    y = field_row(p, x, y, form_w, "Northing (N)", "4567890.123", kind="text")
    y = divider(p, x, y, form_w)
    y = reference_subcomponent(p, x, y, form_w, enabled=False)
    y = divider(p, x, y, form_w)
    action_row(p, x, y0 + form_h - 48, form_w, primary="Create point")
    return p


def page_line_form() -> Page:
    """Wireframe: Line creation dialog."""
    form_w, form_h = 520, 436
    p, x, y0 = form_window("Line form", form_w, form_h, "New Line")
    y = y0 + 48
    y = shared_header(p, x, y, form_w, name_value="AB")
    y = divider(p, x, y, form_w)
    y = radio_row(p, x, y, form_w, "Input mode", [("Click on canvas", False), ("Form", True)])
    y = divider(p, x, y + 4, form_w)
    y = field_row(p, x, y, form_w, "Point A", "pt_001 — Origin (123456.79, 4567890.12)")
    y = field_row(p, x, y, form_w, "Point B", "pt_002 — Marker (123500.00, 4567950.00)")
    y = divider(p, x, y, form_w)
    label(p, x + 16, y, 110, 28, "Direction")
    p.cell("Azimuth 45.0° (computed)", RDO, x + 16 + 110, y, form_w - 32 - 110, 28)
    y += 36
    action_row(p, x, y0 + form_h - 48, form_w, primary="Create line")
    return p


def page_polygon_select() -> Page:
    """Wireframe: Polygon dialog — Select Points tab."""
    form_w, form_h = 560, 636
    p, x, y0 = form_window("Polygon — Select Points", form_w, form_h, "New Polygon")
    y = y0 + 48
    y = shared_header(p, x, y, form_w, name_value="Triangle ABC")
    y = tabs(p, x, y, form_w, active_idx=0, names=["Select Points", "Enter Vertices"])
    y += 8
    label(p, x + 16, y, 200, 22, "Select 3+ points (order matters)", style=HNT)
    y += 24
    # Listbox
    list_x, list_w = x + 16, form_w - 32 - 100
    p.cell("", LST, list_x, y, list_w, 220)
    items = [
        ("pt_001 — Origin (123456.79, 4567890.12)", 1),
        ("pt_002 — Marker (123500.00, 4567950.00)", 2),
        ("pt_003 — Beacon (123450.00, 4567920.00)", 3),
        ("pt_004 — Stake (123480.00, 4567960.00)", None),
        ("pt_005 — Mark (123510.00, 4567940.00)", None),
        ("pt_006 — Pylon (123430.00, 4567910.00)", None),
    ]
    for i, (text, sel_no) in enumerate(items):
        row_y = y + 6 + i * 32
        if sel_no:
            p.cell(
                "",
                "rounded=0;html=1;fillColor=#E8F0F8;strokeColor=none;",
                list_x + 1,
                row_y - 2,
                list_w - 2,
                28,
            )
        label(p, list_x + 8, row_y, list_w - 60, 24, text)
        if sel_no:
            p.cell(str(sel_no), PIL, list_x + list_w - 36, row_y + 4, 20, 20)
    # Reorder column
    rx = list_x + list_w + 12
    button(p, rx, y, 80, 28, "↑ Up")
    button(p, rx, y + 36, 80, 28, "↓ Down")
    button(p, rx, y + 80, 80, 28, "Clear")
    y += 232
    # Preview
    p.cell(
        "Vertices: 3  •  CCW after import: yes  •  is_convex (predicted): true",
        BAN,
        x + 16,
        y,
        form_w - 32,
        32,
    )
    y += 40
    action_row(p, x, y0 + form_h - 48, form_w, primary="Create polygon")
    return p


def page_polygon_enter() -> Page:
    """Wireframe: Polygon dialog — Enter Vertices tab."""
    form_w, form_h = 600, 716
    p, x, y0 = form_window("Polygon — Enter Vertices", form_w, form_h, "New Polygon")
    y = y0 + 48
    y = shared_header(p, x, y, form_w, name_value="Quad ABCD")
    y = tabs(p, x, y, form_w, active_idx=1, names=["Select Points", "Enter Vertices"])
    y += 8
    label(p, x + 16, y, 160, 28, "Number of vertices")
    p.cell("4", INP, x + 16 + 160, y, 60, 28)
    button(p, x + 16 + 230, y, 28, 28, "−")
    button(p, x + 16 + 264, y, 28, 28, "+")
    y += 40
    # Table header
    cols = [("#", 40), ("E", 180), ("N", 180), ("Label (optional)", 140)]
    cx = x + 16
    for ct, cw in cols:
        p.cell(ct, CHH, cx, y, cw, 28)
        cx += cw
    y += 28
    rows = [
        ("1", "123456.789", "4567890.123", "A"),
        ("2", "123500.000", "4567950.000", "B"),
        ("3", "123450.000", "4567920.000", "C"),
        ("4", "123430.000", "4567880.000", "D"),
    ]
    for r in rows:
        cx = x + 16
        for v, (_, cw) in zip(r, cols):
            p.cell(v, INP, cx, y, cw, 28)
            cx += cw
        y += 30
    y += 8
    y = reference_subcomponent(p, x, y, form_w, enabled=False)
    label(
        p,
        x + 16,
        y,
        form_w - 32,
        22,
        "When enabled, E/N columns are interpreted as ΔE / ΔN from the reference point.",
        style=HNT,
    )
    y += 24
    action_row(p, x, y0 + form_h - 48, form_w, primary="Create polygon")
    return p


def page_ray_form() -> Page:
    """Wireframe: Ray creation dialog."""
    form_w, form_h = 540, 536
    p, x, y0 = form_window("Ray form", form_w, form_h, "New Ray")
    y = y0 + 48
    y = shared_header(p, x, y, form_w, name_value="Ray-N")
    y = divider(p, x, y, form_w)
    y = radio_row(p, x, y, form_w, "Input mode", [("Click", False), ("Form", True)])
    y = divider(p, x, y + 4, form_w)
    y = field_row(p, x, y, form_w, "Origin", "pt_001 — Origin (123456.79, 4567890.12)")
    y = radio_row(p, x, y, form_w, "Direction mode", [("Azimuth", True), ("Angle", False)])
    y = radio_row(p, x, y, form_w, "Units", [("Radians", False), ("Degrees", True)])
    y = field_row(p, x, y, form_w, "Direction value", "90.0", kind="text")
    label(
        p,
        x + 16 + 110,
        y,
        form_w - 32 - 110,
        22,
        "Range: 0 ≤ value < 360 (degrees)",
        style=HNT,
    )
    y += 24
    action_row(p, x, y0 + form_h - 48, form_w, primary="Create ray")
    return p


def page_vector_origin_endpoint() -> Page:
    """Wireframe: Vector dialog — Origin + Endpoint tab."""
    form_w, form_h = 560, 576
    p, x, y0 = form_window("Vector — Origin+Endpoint", form_w, form_h, "New Vector")
    y = y0 + 48
    y = shared_header(p, x, y, form_w, name_value="V-AB")
    y = tabs(p, x, y, form_w, active_idx=0, names=["Origin + Endpoint", "Length + Direction"])
    y += 12
    y = field_row(p, x, y, form_w, "Origin", "pt_001 — Origin (123456.79, 4567890.12)")
    y = field_row(p, x, y, form_w, "Endpoint", "pt_002 — Marker (123500.00, 4567950.00)")
    y += 8
    p.cell("Computed (read-only)", CHH, x + 16, y, form_w - 32, 24)
    y += 28
    y = field_row(p, x, y, form_w, "Direction", "Azimuth 45.0°", kind="readonly")
    y = field_row(p, x, y, form_w, "Length", "75.36 m", kind="readonly")
    label(
        p,
        x + 16,
        y,
        form_w - 32,
        22,
        "endpoint_id will be set to pt_002. Deleting either point deletes this vector.",
        style=HNT,
    )
    y += 24
    action_row(p, x, y0 + form_h - 48, form_w, primary="Create vector")
    return p


def page_vector_length_direction() -> Page:
    """Wireframe: Vector dialog — Length + Direction tab."""
    form_w, form_h = 560, 636
    p, x, y0 = form_window("Vector — Length+Direction", form_w, form_h, "New Vector")
    y = y0 + 48
    y = shared_header(p, x, y, form_w, name_value="V-N100")
    y = tabs(p, x, y, form_w, active_idx=1, names=["Origin + Endpoint", "Length + Direction"])
    y += 12
    y = field_row(p, x, y, form_w, "Origin", "pt_001 — Origin (123456.79, 4567890.12)")
    y = field_row(p, x, y, form_w, "Length (m)", "100.0", kind="text")
    y = radio_row(p, x, y, form_w, "Direction mode", [("Azimuth", True), ("Angle", False)])
    y = radio_row(p, x, y, form_w, "Units", [("Radians", True), ("Degrees", False)])
    y = field_row(p, x, y, form_w, "Direction value", "0.7854", kind="text")
    y += 8
    p.cell("Computed (read-only)", CHH, x + 16, y, form_w - 32, 24)
    y += 28
    y = field_row(p, x, y, form_w, "Endpoint", "(123527.50, 4567961.20)", kind="readonly")
    label(
        p,
        x + 16,
        y,
        form_w - 32,
        22,
        "endpoint_id will be null — endpoint is a computed value, not a referenced Point.",
        style=HNT,
    )
    y += 24
    action_row(p, x, y0 + form_h - 48, form_w, primary="Create vector")
    return p


def page_circle_form() -> Page:
    """Wireframe: Circle creation dialog."""
    form_w, form_h = 520, 456
    p, x, y0 = form_window("Circle form", form_w, form_h, "New Circle")
    y = y0 + 48
    y = shared_header(p, x, y, form_w, name_value="C1")
    y = divider(p, x, y, form_w)
    y = radio_row(p, x, y, form_w, "Input mode", [("Click", False), ("Form", True)])
    y = divider(p, x, y + 4, form_w)
    y = field_row(p, x, y, form_w, "Center", "pt_001 — Origin (123456.79, 4567890.12)")
    y = field_row(p, x, y, form_w, "Radius (m)", "50.0", kind="text")
    label(p, x + 16 + 110, y, form_w - 32 - 110, 22, "Must be > 0", style=HNT)
    y += 24
    action_row(p, x, y0 + form_h - 48, form_w, primary="Create circle")
    return p


def page_tangent_form() -> Page:
    """Wireframe: Tangent creation dialog."""
    form_w, form_h = 540, 516
    p, x, y0 = form_window("Tangent form", form_w, form_h, "New Tangent")
    y = y0 + 48
    y = shared_header(p, x, y, form_w, name_value="T-P4")
    y = divider(p, x, y, form_w)
    y = field_row(p, x, y, form_w, "Circle", "ci_001 — C1 (center pt_001, r=50)")
    y = field_row(p, x, y, form_w, "Point on circle", "pt_004 — Stake ✓ on circumference")
    label(
        p,
        x + 16 + 110,
        y,
        form_w - 32 - 110,
        22,
        "Point must lie on circle within EPS_DISTANCE = 1e-6 m",
        style=HNT,
    )
    y += 26
    p.cell("Computed (read-only)", CHH, x + 16, y, form_w - 32, 24)
    y += 28
    y = field_row(p, x, y, form_w, "Direction", "Azimuth 135.0° (canonical)", kind="readonly")
    button(p, x + 16, y, 160, 28, "⇄ Flip direction (+180°)")
    label(
        p,
        x + 16 + 172,
        y,
        form_w - 32 - 172,
        28,
        "Equivalent line; flip only changes the stored heading.",
        style=HNT,
    )
    y += 36
    action_row(p, x, y0 + form_h - 48, form_w, primary="Create tangent")
    return p


# ─────────────────────────── dialogs ──────────────────────────────────────


def page_point_text_import() -> Page:
    """Wireframe: Import points from text dialog."""
    form_w, form_h = 600, 600
    p, x, y0 = form_window("Point text import", form_w, form_h, "Import points from text")
    y = y0 + 48
    label(
        p,
        x + 16,
        y,
        form_w - 32,
        22,
        "Paste one point per line:  Name  Northing  Easting",
        style=HNT,
    )
    y += 26
    p.cell("", LST, x + 16, y, form_w - 32, 160)
    sample = [
        "PointA  4567890.123  123456.789",
        "PointB  4567950.000  123500.000",
        "PointC  4567920.000  123450.000",
    ]
    for i, line in enumerate(sample):
        label(p, x + 24, y + 6 + i * 22, form_w - 48, 22, line)
    y += 172
    y = reference_subcomponent(p, x, y, form_w, enabled=True)
    p.cell("✓ 3 valid lines  •  0 errors", BAN, x + 16, y, form_w - 32, 32)
    y += 40
    label(p, x + 16, y, form_w - 32, 22, "Preview (first 3):  PointA  PointB  PointC", style=HNT)
    y += 30
    action_row(p, x, y0 + form_h - 48, form_w, primary="Import 3 points")
    return p


def page_polygon_file_import() -> Page:
    """Wireframe: Import polygon from file dialog."""
    form_w, form_h = 640, 716
    p, x, y0 = form_window("Polygon file import", form_w, form_h, "Import polygon from file")
    y = y0 + 48
    # File path
    label(p, x + 16, y, 80, 28, "File")
    textfield(p, x + 16 + 80, y, form_w - 32 - 80 - 96, 28, filled="/projects/site/poly-a.txt")
    button(p, x + form_w - 16 - 90, y, 90, 28, "Browse…")
    y += 40
    # Polygon name
    label(p, x + 16, y, 80, 28, "Name")
    textfield(p, x + 16 + 80, y, form_w - 32 - 80, 28, filled="poly-a")
    y += 40
    # Line color + fill color row, then alpha row
    label(p, x + 16, y, 84, 28, "Line color")
    p.cell("", SWA, x + 16 + 84, y + 2, 24, 24)
    textfield(p, x + 16 + 114, y, 80, 28, filled="#FF6633")
    label(p, x + 16 + 206, y, 74, 28, "Fill color")
    p.cell("", SWF, x + 16 + 280, y + 2, 24, 24)
    textfield(p, x + 16 + 310, y, 80, 28, filled="#AACCFF")
    y += 36
    label(p, x + 16, y, 50, 28, "Alpha")
    p.cell("", SLT, x + 16 + 58, y + 11, 120, 6)
    p.cell("", SLF, x + 16 + 58, y + 11, 90, 6)
    p.cell("", SLH, x + 16 + 142, y + 6, 16, 16)
    p.cell("0.80", INP, x + 16 + 168, y, 60, 28)
    y += 40
    y = reference_subcomponent(p, x, y, form_w, enabled=False)
    # Vertex ordering radios
    label(p, x + 16, y, 120, 28, "Vertex ordering")
    radio(p, x + 16 + 120, y + 3, "Boundary order (default)", True, label_w=220)
    y += 26
    radio(p, x + 16 + 120, y, "Sort (centroid + polar angle)", False, label_w=260)
    y += 28
    label(
        p,
        x + 16 + 120,
        y,
        form_w - 32 - 120,
        22,
        "Sort mode is convex-only; concave inputs will produce a different shape.",
        style=HNT,
    )
    y += 30
    # Preview box
    p.cell("Preview", CHH, x + 16, y, form_w - 32, 24)
    y += 28
    p.cell("", WIN, x + 16, y, form_w - 32, 140)
    label(
        p,
        x + 16,
        y + 60,
        form_w - 32,
        22,
        "✓ 4 vertices  •  signed area: +12,450.30 m²  •  simple: yes",
        style=HNT,
    )
    label(
        p,
        x + 16,
        y + 88,
        form_w - 32,
        22,
        "(line plot of polygon outline rendered here)",
        style=HNT,
    )
    y += 152
    action_row(p, x, y0 + form_h - 48, form_w, primary="Import polygon")
    return p


def page_cascade_confirm() -> Page:
    """Wireframe: Cascade-delete confirmation dialog."""
    form_w, form_h = 580, 480
    p, x, y0 = form_window("Cascade-delete confirm", form_w, form_h, "Delete and cascade?")
    y = y0 + 48
    label(
        p,
        x + 16,
        y,
        form_w - 32,
        44,
        "Deleting pt_001 (Origin) will also remove the following 5 objects:",
    )
    y += 50
    # warning banner
    p.cell("⚠  This cascade can be undone with Ctrl+Z afterwards.", BAN, x + 16, y, form_w - 32, 32)
    y += 40
    # List
    p.cell("", LST, x + 16, y, form_w - 32, 220)
    rows = [
        "● pt_001     Origin                 (the selected Point)",
        "▱ ln_001     AB                     (line — references pt_001)",
        "▱ ln_002     AC                     (line — references pt_001)",
        "▱ ry_001     Ray-N                  (ray — origin = pt_001)",
        "▱ ci_001     C1                     (circle — center = pt_001)",
        "▱ pg_001     Triangle ABC           (polygon — vertex pt_001)",
    ]
    for i, r in enumerate(rows):
        bg = (
            "rounded=0;html=1;fillColor=#FFF8DC;strokeColor=none;"
            if i == 0
            else "rounded=0;html=1;fillColor=#FFFFFF;strokeColor=none;"
        )
        p.cell("", bg, x + 18, y + 4 + i * 30, form_w - 36, 28)
        label(p, x + 28, y + 4 + i * 30, form_w - 56, 28, r)
    y += 232
    # actions: Cancel + destructive
    button(p, x + form_w - 16 - 88 - 12 - 168, y, 88, 32, "Cancel")
    p.cell("Delete all (6)", DBT, x + form_w - 16 - 168, y, 168, 32)
    return p


def page_measurement_dialogs() -> Page:
    """Wireframe: Measurements tool panel."""
    form_w, form_h = 760, 540
    p, x, y0 = form_window("Measurement dialogs", form_w, form_h, "Measurements")
    y = y0 + 48
    # Left rail
    rail_w = 200
    p.cell("", PNL, x + 16, y, rail_w, form_h - 80)
    items = [
        ("Polygon Area", False),
        ("Polygon Perimeter", False),
        ("Circle Area", False),
        ("Circle Circumference", False),
        ("Segment / Vector Len.", False),
        ("Angle Between Dirs.", True),
    ]
    selected_row_style = (
        "rounded=0;html=1;fillColor=#E8F0F8;strokeColor=none;fontStyle=1;align=left;spacingLeft=12;"
    )
    default_row_style = (
        "rounded=0;html=1;fillColor=#FFFFFF;strokeColor=none;align=left;spacingLeft=12;"
    )
    for i, (txt, sel) in enumerate(items):
        bg = selected_row_style if sel else default_row_style
        p.cell(txt, bg, x + 18, y + 4 + i * 34, rail_w - 4, 32)
    # Right pane: details for "Angle Between Directions"
    px = x + 16 + rail_w + 16
    pw = form_w - 32 - rail_w - 16
    label(p, px, y, pw, 24, "Angle Between Directions", style=SEC)
    label(
        p,
        px,
        y + 24,
        pw,
        22,
        "Pick two direction-bearing objects (Line, Ray, Vector, or Tangent).",
        style=HNT,
    )
    y2 = y + 56
    label(p, px, y2, 80, 28, "Object 1")
    combobox(p, px + 90, y2, pw - 90, 28, "ln_001 — AB (azimuth 45°)")
    y2 += 40
    label(p, px, y2, 80, 28, "Object 2")
    combobox(p, px + 90, y2, pw - 90, 28, "ry_001 — Ray-N (azimuth 90°)")
    y2 += 48
    primary_button(p, px, y2, 120, 32, "Compute")
    y2 += 48
    # Result block
    p.cell("Result", CHH, px, y2, pw, 24)
    y2 += 28
    p.cell("", WIN, px, y2, pw, 88)
    label(p, px + 12, y2 + 8, pw - 24, 24, "θ = 0.7854 rad", style=SEC)
    label(p, px + 12, y2 + 32, pw - 24, 24, "θ = 45.0°", style=SEC)
    label(p, px + 12, y2 + 56, pw - 24, 24, "(unsigned, range [0, π])", style=HNT)
    y2 += 96
    button(p, px, y2, 140, 28, "📋 Copy result")
    # Bottom-right close
    button(p, x + form_w - 16 - 88, y0 + form_h - 48, 88, 32, "Close")
    return p


def page_options_dialog() -> Page:
    """Wireframe: Options / Preferences dialog — Appearance tab active."""
    form_w, form_h = 620, 540
    p, x, y0 = form_window("Options dialog", form_w, form_h, "Options")
    y = y0 + 48
    y = tabs(p, x, y, form_w, active_idx=0, names=["Appearance", "Directions", "Canvas", "Tolerances"])
    y += 16

    inner_x = x + 16
    inner_w = form_w - 32

    # ── Appearance tab ──────────────────────────────────────────────────────
    y = section_label(p, x, y, "New object defaults")
    # Default line color
    label(p, inner_x, y, 150, 28, "Default line color")
    p.cell("", SWA, inner_x + 150, y + 2, 24, 24)
    textfield(p, inner_x + 180, y, 80, 28, filled="#4D7EAF")
    y += 34
    # Default fill color
    label(p, inner_x, y, 150, 28, "Default fill color")
    p.cell("", SWF, inner_x + 150, y + 2, 24, 24)
    textfield(p, inner_x + 180, y, 80, 28, filled="#AACCFF")
    y += 34
    # Default point color
    label(p, inner_x, y, 150, 28, "Default point color")
    p.cell("", SWA, inner_x + 150, y + 2, 24, 24)
    textfield(p, inner_x + 180, y, 80, 28, filled="#FF6633")
    y += 34
    # Default alpha
    label(p, inner_x, y, 150, 28, "Default alpha")
    p.cell("", SLT, inner_x + 150, y + 11, 140, 6)
    p.cell("", SLF, inner_x + 150, y + 11, 112, 6)
    p.cell("", SLH, inner_x + 284, y + 6, 16, 16)
    p.cell("0.80", INP, inner_x + 310, y, 60, 28)
    y += 40
    y = divider(p, x, y, form_w)
    y = section_label(p, x, y, "Rendering")
    # Point marker size
    label(p, inner_x, y, 150, 28, "Point marker size")
    p.cell("8", INP, inner_x + 150, y, 60, 28)
    label(p, inner_x + 216, y, 30, 28, "px")
    label(p, inner_x + 254, y, 100, 28, "(4 – 16)", style=HNT)
    y += 36
    # Stroke width
    label(p, inner_x, y, 150, 28, "Stroke width")
    p.cell("1", INP, inner_x + 150, y, 60, 28)
    label(p, inner_x + 216, y, 30, 28, "px")
    label(p, inner_x + 254, y, 100, 28, "(1 – 5)", style=HNT)
    y += 36
    # Canvas background
    label(p, inner_x, y, 150, 28, "Canvas background")
    p.cell(
        "",
        "rounded=0;fillColor=#FFFFFF;strokeColor=#666666;",
        inner_x + 150,
        y + 2,
        24,
        24,
    )
    textfield(p, inner_x + 180, y, 90, 28, filled="#FFFFFF")
    y += 36

    # ── Bottom actions: Cancel (left) | Reset to defaults (center) | OK (right) ──
    button(p, x + 16, y0 + form_h - 48, 88, 32, "Cancel")
    button(p, x + form_w // 2 - 74, y0 + form_h - 48, 148, 32, "Reset to defaults")
    primary_button(p, x + form_w - 16 - 88, y0 + form_h - 48, 88, 32, "OK")
    return p


# ─────────────────────────── assembler ────────────────────────────────────


def build() -> str:
    """Assemble all pages into a complete mxfile XML string."""
    pages = [
        page_main_window(),
        page_point_form(),
        page_line_form(),
        page_polygon_select(),
        page_polygon_enter(),
        page_ray_form(),
        page_vector_origin_endpoint(),
        page_vector_length_direction(),
        page_circle_form(),
        page_tangent_form(),
        page_point_text_import(),
        page_polygon_file_import(),
        page_cascade_confirm(),
        page_measurement_dialogs(),
        page_options_dialog(),
    ]
    parts = [
        '<mxfile host="electron" modified="2026-05-16T00:00:00.000Z"'
        ' agent="geometry-app-spec" version="22.0.0">'
    ]
    for p in pages:
        diag_id = "p_" + uuid.uuid5(uuid.NAMESPACE_DNS, p.name).hex[:12]
        parts.append(f'  <diagram id="{diag_id}" name="{html.escape(p.name)}">')
        parts.append(
            f'    <mxGraphModel dx="{p.width}" dy="{p.height}" grid="1" gridSize="10" '
            f'guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" '
            f'pageScale="1" pageWidth="{p.width}" pageHeight="{p.height}" math="0" shadow="0">'
        )
        parts.append("      <root>")
        parts.append('        <mxCell id="0"/>')
        parts.append('        <mxCell id="1" parent="0"/>')
        for c in p.cells:
            parts.append("        " + c)
        parts.append("      </root>")
        parts.append("    </mxGraphModel>")
        parts.append("  </diagram>")
    parts.append("</mxfile>")
    return "\n".join(parts) + "\n"


def main() -> None:
    """Write the drawio file to disk next to this script."""
    here = Path(__file__).resolve().parent
    out = here / "geometry-app-ui-ux.drawio"
    out.write_text(build(), encoding="utf-8")
    print(f"wrote {out}  ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
