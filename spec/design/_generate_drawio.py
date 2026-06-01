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

Produces spec/design/geometry-app-ui-ux.drawio with 20 pages of
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
    for i, name in enumerate(
        ["Point", "Line", "Polygon", "Ray", "Vector", "Circle",
         "Ball", "Cylinder", "Solid", "Tangent"]
    ):
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
    p.cell("", WIN, 12, y + 28, 276, 192)
    for i, name in enumerate(
        [
            "Polygon Area", "Polygon Perim.", "Prism Volume", "Circle Area",
            "Circumf.", "Cyl. Volume", "Length", "Angle",
        ]
    ):
        col, row = i % 2, i // 2
        button(p, 24 + col * 128, y + 36 + row * 36, 120, 28, name)

    # Center canvas — three-tab canvas (2D active)
    p.cell("", WIN, 300, 68, 700, 712)
    nav_y = tabs(p, 300, 76, 700, active_idx=0, names=["2D (flat)", "3D", "Slice"])
    # nav toolbar below tab bar
    p.cell("", PNL, 308, nav_y, 684, 32)
    for i, txt in enumerate(["✋ Pan", "🔍 Zoom", "🏠 Fit", "↻ Refresh"]):
        st = PBT if txt == "↻ Refresh" else BTN
        p.cell(txt, st, 316 + i * 92, nav_y + 5, 84, 22)
    # canvas content (placeholder: a polygon outline — 2D flat view)
    p.cell(
        "",
        "rounded=0;whiteSpace=wrap;html=1;fillColor=#FFFCE0;strokeColor=#E1B870;fillOpacity=40;",
        500,
        280,
        280,
        200,
    )
    label(p, 540, 365, 200, 30, "Selected polygon (preview)", style=HNT)
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
    form_w, form_h = 520, 540
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
    y = field_row(p, x, y, form_w, "Altitude (Z)", "150.0", kind="text")
    label(
        p,
        x + 16 + 110,
        y,
        form_w - 32 - 110,
        22,
        "metres above datum; blank = 0.0",
        style=HNT,
    )
    y += 26
    y = divider(p, x, y, form_w)
    y = reference_subcomponent(p, x, y, form_w, enabled=False)
    label(
        p,
        x + 16,
        y,
        form_w - 32,
        22,
        "When enabled, E / N / Z become ΔE / ΔN / ΔZ from the reference point.",
        style=HNT,
    )
    y += 26
    y = divider(p, x, y, form_w)
    action_row(p, x, y0 + form_h - 48, form_w, primary="Create point")
    return p


def page_line_form() -> Page:
    """Wireframe: Line creation dialog."""
    form_w, form_h = 520, 476
    p, x, y0 = form_window("Line form", form_w, form_h, "New Line")
    y = y0 + 48
    y = shared_header(p, x, y, form_w, name_value="AB")
    y = divider(p, x, y, form_w)
    y = radio_row(p, x, y, form_w, "Input mode", [("Click on canvas", False), ("Form", True)])
    y = divider(p, x, y + 4, form_w)
    y = field_row(p, x, y, form_w, "Point A", "pt_001 — Origin (123456.79, 4567890.12, Z 150)")
    y = field_row(p, x, y, form_w, "Point B", "pt_002 — Marker (123500.00, 4567950.00, Z 80)")
    y = divider(p, x, y, form_w)
    p.cell("Computed (read-only)", CHH, x + 16, y, form_w - 32, 24)
    y += 28
    y = field_row(p, x, y, form_w, "Direction", "Azimuth 45.0°  (computed)", kind="readonly")
    y = field_row(p, x, y, form_w, "Elevation", "−25.4°  (computed)", kind="readonly")
    label(p, x + 16, y, form_w - 32, 22,
          "Elevation = atan2(ΔZ, √(ΔE² + ΔN²)); negative = descending.", style=HNT)
    y += 26
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
        ("pt_001 — Origin (123456.79, 4567890.12, Z 150.0)", 1),
        ("pt_002 — Marker (123500.00, 4567950.00, Z 80.0)", 2),
        ("pt_003 — Beacon (123450.00, 4567920.00, Z 0.0)", 3),
        ("pt_004 — Stake (123480.00, 4567960.00, Z 0.0)", None),
        ("pt_005 — Mark (123510.00, 4567940.00, Z 120.0)", None),
        ("pt_006 — Pylon (123430.00, 4567910.00, Z 0.0)", None),
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
    # Table header — now includes Z column
    cols = [("#", 36), ("E", 148), ("N", 148), ("Z", 80), ("Label (opt.)", 128)]
    cx = x + 16
    for ct, cw in cols:
        p.cell(ct, CHH, cx, y, cw, 28)
        cx += cw
    y += 28
    rows = [
        ("1", "123456.789", "4567890.123", "150.0", "A"),
        ("2", "123500.000", "4567950.000", "80.0", "B"),
        ("3", "123450.000", "4567920.000", "0.0", "C"),
        ("4", "123430.000", "4567880.000", "0.0", "D"),
    ]
    for r in rows:
        cx = x + 16
        for v, (_, cw) in zip(r, cols):
            p.cell(v, INP, cx, y, cw, 28)
            cx += cw
        y += 30
    y += 8
    y = reference_subcomponent(p, x, y, form_w, enabled=False)
    label(p, x + 16, y, form_w - 32, 22,
          "When enabled, E/N/Z columns are interpreted as ΔE / ΔN / ΔZ from the reference point.",
          style=HNT)
    y += 24
    action_row(p, x, y0 + form_h - 48, form_w, primary="Create polygon")
    return p


def page_ray_form() -> Page:
    """Wireframe: Ray creation dialog."""
    form_w, form_h = 540, 576
    p, x, y0 = form_window("Ray form", form_w, form_h, "New Ray")
    y = y0 + 48
    y = shared_header(p, x, y, form_w, name_value="Ray-N")
    y = divider(p, x, y, form_w)
    y = radio_row(p, x, y, form_w, "Input mode", [("Click", False), ("Form", True)])
    y = divider(p, x, y + 4, form_w)
    y = field_row(p, x, y, form_w, "Origin", "pt_001 — Origin (123456.79, 4567890.12, Z 150)")
    y = radio_row(p, x, y, form_w, "Direction mode", [("Azimuth", True), ("Angle", False)])
    y = radio_row(p, x, y, form_w, "Units", [("Radians", False), ("Degrees", True)])
    y = field_row(p, x, y, form_w, "Direction value", "90.0", kind="text")
    label(p, x + 16 + 110, y, form_w - 32 - 110, 22,
          "Range: 0 ≤ value < 360 (degrees)", style=HNT)
    y += 26
    y = field_row(p, x, y, form_w, "Elevation", "0.0", kind="text")
    label(p, x + 16 + 110, y, form_w - 32 - 110, 22,
          "Range: −90° to +90°; 0 = horizontal", style=HNT)
    y += 26
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
    y = field_row(p, x, y, form_w, "Origin", "pt_001 — Origin (123456.79, 4567890.12, Z 150)")
    y = field_row(p, x, y, form_w, "Endpoint", "pt_002 — Marker (123500.00, 4567950.00, Z 80)")
    y += 8
    p.cell("Computed (read-only)", CHH, x + 16, y, form_w - 32, 24)
    y += 28
    y = field_row(p, x, y, form_w, "Direction", "Azimuth 45.0°", kind="readonly")
    y = field_row(p, x, y, form_w, "Elevation", "−48.2°", kind="readonly")
    y = field_row(p, x, y, form_w, "Length (3D)", "101.28 m", kind="readonly")
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
    form_w, form_h = 560, 676
    p, x, y0 = form_window("Vector — Length+Direction", form_w, form_h, "New Vector")
    y = y0 + 48
    y = shared_header(p, x, y, form_w, name_value="V-N100")
    y = tabs(p, x, y, form_w, active_idx=1, names=["Origin + Endpoint", "Length + Direction"])
    y += 12
    y = field_row(p, x, y, form_w, "Origin", "pt_001 — Origin (123456.79, 4567890.12, Z 150)")
    y = field_row(p, x, y, form_w, "Length (m)", "100.0", kind="text")
    y = radio_row(p, x, y, form_w, "Direction mode", [("Azimuth", True), ("Angle", False)])
    y = radio_row(p, x, y, form_w, "Units", [("Radians", True), ("Degrees", False)])
    y = field_row(p, x, y, form_w, "Direction value", "0.7854", kind="text")
    y = field_row(p, x, y, form_w, "Elevation", "0.0000", kind="text")
    label(p, x + 16 + 110, y, form_w - 32 - 110, 22,
          "Range: −π/2 to +π/2  (0 = horizontal)", style=HNT)
    y += 26
    p.cell("Computed (read-only)", CHH, x + 16, y, form_w - 32, 24)
    y += 28
    y = field_row(p, x, y, form_w, "Endpoint (E, N, Z)",
                  "(123527.50, 4567961.20, 150.00)", kind="readonly")
    label(p, x + 16, y, form_w - 32, 22,
          "endpoint_id will be null — endpoint is a computed value, not a referenced Point.",
          style=HNT)
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
    y = field_row(p, x, y, form_w, "Center", "pt_001 — Origin (123456.79, 4567890.12, Z 150)")
    y = field_row(p, x, y, form_w, "Radius (m)", "50.0", kind="text")
    label(p, x + 16 + 110, y, form_w - 32 - 110, 22, "Must be > 0", style=HNT)
    y += 24
    action_row(p, x, y0 + form_h - 48, form_w, primary="Create circle")
    return p


def page_solid_form() -> Page:
    """Wireframe: Solid creation dialog (layered cross-sections)."""
    form_w, form_h = 600, 620
    p, x, y0 = form_window("Solid form", form_w, form_h, "New Solid")
    y = y0 + 48
    y = shared_header(p, x, y, form_w, name_value="Pyramid-1")
    y = divider(p, x, y, form_w)
    label(p, x + 16, y, form_w - 32, 22, "Layers  (ordered bottom → top)", style=SEC)
    y += 26
    label(p, x + 16, y, form_w - 32, 22,
          "Box: 2 rectangles · Pyramid: polygon + Point · Frustum: 2 polygons · Loft: any sequence",
          style=HNT)
    y += 26
    # Layer list header
    hcols = [("#", 28), ("Type", 84), ("Shape", 320), ("", 80)]
    cx = x + 16
    for ct, cw in hcols:
        p.cell(ct, CHH, cx, y, cw, 26)
        cx += cw
    y += 26
    # Layer rows
    layers = [
        ("1", "Polygon", "pg_001 — Base Square (4 vertices, Z 0)"),
        ("2", "Polygon", "pg_002 — Mid Square  (4 vertices, Z 50)"),
        ("3", "Point",   "pt_005 — Apex        (Z 100.0)"),
    ]
    for num, shape_type, shape_name in layers:
        cx = x + 16
        p.cell(num, INP, cx, y, 28, 28); cx += 28
        p.cell(shape_type, INP, cx, y, 84, 28); cx += 84
        p.cell(shape_name, INP, cx, y, 320, 28); cx += 320
        button(p, cx + 4, y, 34, 28, "↑")
        button(p, cx + 40, y, 34, 28, "↓")
        y += 32
    button(p, x + 16, y, 120, 28, "+ Add layer")
    y += 40
    # Validation hint
    p.cell("✓ Layer 1→2: 4 vertices each — quad faces.  Layer 2→3: Point apex — triangle fan.",
           BAN, x + 16, y, form_w - 32, 32)
    y += 40
    action_row(p, x, y0 + form_h - 48, form_w, primary="Create solid")
    return p


def page_ball_form() -> Page:
    """Wireframe: Ball (sphere) creation dialog."""
    form_w, form_h = 520, 456
    p, x, y0 = form_window("Ball form", form_w, form_h, "New Ball")
    y = y0 + 48
    y = shared_header(p, x, y, form_w, name_value="Sphere-1")
    y = divider(p, x, y, form_w)
    y = radio_row(p, x, y, form_w, "Input mode", [("Click", False), ("Form", True)])
    y = divider(p, x, y + 4, form_w)
    y = field_row(p, x, y, form_w, "Center", "pt_001 — Origin (123456.79, 4567890.12, Z 150.0)")
    y = field_row(p, x, y, form_w, "Radius (m)", "50.0", kind="text")
    label(p, x + 16 + 110, y, form_w - 32 - 110, 22, "Must be > 0", style=HNT)
    y += 26
    label(p, x + 16, y, form_w - 32, 22,
          "Renders as circle in 2D flat view, wireframe sphere in 3D view.", style=HNT)
    y += 26
    action_row(p, x, y0 + form_h - 48, form_w, primary="Create ball")
    return p


def page_cylinder_form() -> Page:
    """Wireframe: Cylinder creation dialog."""
    form_w, form_h = 560, 600
    p, x, y0 = form_window("Cylinder form", form_w, form_h, "New Cylinder")
    y = y0 + 48
    y = shared_header(p, x, y, form_w, name_value="Cyl-1")
    y = divider(p, x, y, form_w)
    y = field_row(p, x, y, form_w, "Base center",
                  "pt_001 — Origin (123456.79, 4567890.12, Z 0.0)")
    y = field_row(p, x, y, form_w, "Radius (m)", "25.0", kind="text")
    y = field_row(p, x, y, form_w, "Height (m)", "100.0", kind="text")
    y = divider(p, x, y, form_w)
    # Axis orientation
    label(p, x + 16, y, 130, 22, "Axis orientation", style=SEC)
    y += 26
    radio(p, x + 16, y + 3, "Vertical (straight up)", True, label_w=200)
    y += 32
    radio(p, x + 16, y + 3, "Inclined", False, label_w=100)
    y += 32
    # Inclined fields (shown dimmed here to indicate they activate on Inclined selection)
    label(p, x + 16, y, form_w - 32, 22,
          "When Inclined is selected, azimuth and elevation fields appear below:", style=HNT)
    y += 26
    y = radio_row(p, x + 20, y, form_w - 20,
                  "Direction mode", [("Azimuth", True), ("Angle", False)])
    y = radio_row(p, x + 20, y, form_w - 20,
                  "Units", [("Radians", False), ("Degrees", True)])
    y = field_row(p, x + 20, y, form_w - 20, "Axis azimuth", "45.0 °", kind="text")
    y = field_row(p, x + 20, y, form_w - 20, "Axis elevation", "60.0 °  (0°–90°, > 0)",
                  kind="text")
    action_row(p, x, y0 + form_h - 48, form_w, primary="Create cylinder")
    return p


def page_tangent_form() -> Page:
    """Wireframe: Tangent creation dialog."""
    form_w, form_h = 540, 516
    p, x, y0 = form_window("Tangent form", form_w, form_h, "New Tangent")
    y = y0 + 48
    y = shared_header(p, x, y, form_w, name_value="T-P4")
    y = divider(p, x, y, form_w)
    y = radio_row(p, x, y, form_w, "Shape type", [("Circle", True), ("Ball", False)])
    y = field_row(p, x, y, form_w, "Circle / Ball", "ci_001 — C1 (center pt_001, r=50)")
    label(p, x + 16 + 110, y, form_w - 32 - 110, 22,
          "Combobox lists Circles and Balls; icon indicates type.", style=HNT)
    y += 26
    y = field_row(p, x, y, form_w, "Point on surface", "pt_004 — Stake ✓ on surface")
    label(p, x + 16 + 110, y, form_w - 32 - 110, 22,
          "✓ = lies on the shape within EPS_DISTANCE", style=HNT)
    y += 26
    # Ball tangent needs explicit direction (any direction in the tangent plane)
    label(p, x + 16, y, form_w - 32, 22,
          "For Ball: specify tangent line direction (must be ⊥ to radius).", style=HNT)
    y += 26
    y = radio_row(p, x, y, form_w, "Direction mode", [("Azimuth", True), ("Angle", False)])
    y = radio_row(p, x, y, form_w, "Units", [("Radians", False), ("Degrees", True)])
    y = field_row(p, x, y, form_w, "Azimuth", "135.0 °", kind="text")
    y = field_row(p, x, y, form_w, "Elevation", "0.0 °  (0 = horizontal)", kind="text")
    p.cell("Computed (read-only)", CHH, x + 16, y, form_w - 32, 24)
    y += 28
    y = field_row(p, x, y, form_w, "Direction", "Azimuth 135.0°  Elev 0.0°", kind="readonly")
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
    label(p, x + 16, y, form_w - 32, 22,
          "Paste one point per line:  Name  Northing  Easting  (Z defaults to 0.0)",
          style=HNT)
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
        ("Polygon Prism Vol.", False),
        ("Circle Area", False),
        ("Circle Circumference", False),
        ("Circle Cylinder Vol.", False),
        ("Segment / Vector Len.", False),
        ("Angle Between Dirs.", False),
        ("Angle at Vertex (3-pt)", True),
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
    # Right pane: details for "Angle at Vertex (Three-Point Azimuth & Elevation)"
    px = x + 16 + rail_w + 16
    pw = form_w - 32 - rail_w - 16
    label(p, px, y, pw, 24, "Angle at Vertex — Azimuth & Elevation", style=SEC)
    label(
        p,
        px,
        y + 24,
        pw,
        22,
        "Pick three ordered points. Vertex is B; arms are B→A and B→C.",
        style=HNT,
    )
    y2 = y + 56
    label(p, px, y2, 116, 28, "Point A (arm)")
    combobox(p, px + 120, y2, pw - 120, 28, "pt_001 — A")
    y2 += 40
    label(p, px, y2, 116, 28, "Point B (vertex)")
    combobox(p, px + 120, y2, pw - 120, 28, "pt_002 — B")
    y2 += 40
    label(p, px, y2, 116, 28, "Point C (arm)")
    combobox(p, px + 120, y2, pw - 120, 28, "pt_003 — C")
    y2 += 34
    label(p, px, y2, pw, 22, "Order matters:  A-B-C  ≠  C-B-A", style=HNT)
    y2 += 30
    primary_button(p, px, y2, 120, 32, "Compute")
    y2 += 44
    # Result block
    p.cell("Result", CHH, px, y2, pw, 24)
    y2 += 28
    p.cell("", WIN, px, y2, pw, 104)
    label(p, px + 12, y2 + 8, pw - 24, 22, "Azimuth = 1.2345 rad  (70.7°)", style=SEC)
    label(p, px + 12, y2 + 30, pw - 24, 22, "Elevation = 0.2618 rad  (15.0°)", style=SEC)
    label(p, px + 12, y2 + 54, pw - 24, 22, "Azimuth ignores altitude; elev = elev(BC) − elev(BA).", style=HNT)
    label(p, px + 12, y2 + 76, pw - 24, 22, "(signed, order-dependent)", style=HNT)
    y2 += 112
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


def page_3d_tab() -> Page:
    """Wireframe: center canvas — 3D tab view with Axes3D."""
    p = Page("3D tab", width=960, height=720)
    x, y0 = 60, 40
    w, h = 840, 640

    p.cell("", WIN, x, y0, w, h)
    nav_y = tabs(p, x, y0 + 8, w, active_idx=1, names=["2D (flat)", "3D", "Slice"])
    # nav toolbar
    p.cell("", PNL, x + 8, nav_y, w - 16, 32)
    for i, txt in enumerate(["✋ Pan", "🔄 Rotate", "🏠 Fit", "↻ Refresh"]):
        st = PBT if txt == "↻ Refresh" else BTN
        p.cell(txt, st, x + 16 + i * 100, nav_y + 5, 92, 22)
    canvas_y = nav_y + 40
    canvas_h = y0 + h - canvas_y - 32
    # 3D axes background
    p.cell(
        "",
        "rounded=0;whiteSpace=wrap;html=1;fillColor=#F8F8FF;strokeColor=#CCCCCC;",
        x + 8,
        canvas_y,
        w - 16,
        canvas_h,
    )
    # Axis label annotations
    label(p, x + 60, canvas_y + 20, 120, 22, "Altitude (m) ↑", style=SEC)
    label(p, x + 20, canvas_y + canvas_h - 36, 120, 22, "← Easting (m)", style=HNT)
    label(p, x + w - 160, canvas_y + canvas_h - 36, 140, 22, "Northing (m) →", style=HNT)
    label(p, x + w // 2 - 140, canvas_y + canvas_h // 2, 280, 22,
          "(3D scatter + lines — rotate/tilt with mouse)", style=HNT)
    label(p, x + w // 2 - 140, canvas_y + canvas_h // 2 + 26, 280, 22,
          "Default view: elev 30°, azim 225°", style=HNT)
    # cursor readout
    label(p, x + 16, y0 + h - 26, 340, 22,
          "Cursor: E 123,456.78  N 4,567,890.12  Z 150.00", style=HNT)
    return p


def page_slice_tab() -> Page:
    """Wireframe: center canvas — Slice tab with SliceControlsFrame."""
    p = Page("Slice tab", width=960, height=760)
    x, y0 = 60, 40
    w, h = 840, 680

    p.cell("", WIN, x, y0, w, h)
    nav_y = tabs(p, x, y0 + 8, w, active_idx=2, names=["2D (flat)", "3D", "Slice"])

    # SliceControlsFrame strip
    ctrl_h = 100
    p.cell("", PNL, x + 8, nav_y, w - 16, ctrl_h)
    # Row 1 — plane mode radios
    label(p, x + 16, nav_y + 8, 54, 22, "Plane:")
    rx = x + 74
    for mode, sel in [
        ("Horizontal  Z = c", True),
        ("Easting  E = c", False),
        ("Northing  N = c", False),
        ("Custom  aE+bN+cZ = d", False),
    ]:
        radio(p, rx, nav_y + 8, mode, sel, label_w=150)
        rx += 168
    # Row 2 — offset + slider + thickness + Apply
    label(p, x + 16, nav_y + 38, 56, 28, "Offset:")
    textfield(p, x + 74, nav_y + 38, 72, 28, filled="0.0")
    label(p, x + 152, nav_y + 38, 18, 28, "m")
    p.cell("", SLT, x + 178, nav_y + 49, 240, 6)
    p.cell("", SLF, x + 178, nav_y + 49, 120, 6)
    p.cell("", SLH, x + 292, nav_y + 44, 16, 16)
    label(p, x + 432, nav_y + 38, 90, 28, "Thickness:")
    textfield(p, x + 526, nav_y + 38, 60, 28, filled="0.0")
    label(p, x + 592, nav_y + 38, 18, 28, "m")
    primary_button(p, x + w - 16 - 88, nav_y + 38, 88, 28, "Apply")

    # nav toolbar below controls
    toolbar_y = nav_y + ctrl_h
    p.cell("", PNL, x + 8, toolbar_y, w - 16, 32)
    for i, txt in enumerate(["✋ Pan", "🔍 Zoom", "🏠 Fit", "↻ Refresh"]):
        st = PBT if txt == "↻ Refresh" else BTN
        p.cell(txt, st, x + 16 + i * 100, toolbar_y + 5, 92, 22)

    # Canvas area
    canvas_y = toolbar_y + 40
    canvas_h = y0 + h - canvas_y - 32
    p.cell(
        "",
        "rounded=0;whiteSpace=wrap;html=1;fillColor=#F0F8FF;strokeColor=#CCCCCC;",
        x + 8,
        canvas_y,
        w - 16,
        canvas_h,
    )
    # Axis labels for Horizontal Z=c mode (axes are Easting & Northing)
    label(p, x + 16, canvas_y + 12, 120, 22, "Northing (m) ↑", style=HNT)
    label(p, x + w - 148, canvas_y + canvas_h - 24, 140, 22, "Easting (m) →", style=HNT)
    # Cross-section hint
    label(p, x + w // 2 - 180, canvas_y + canvas_h // 2 - 14, 360, 22,
          "2D cross-section at Z = 0.0 m  (objects intersecting the plane)", style=HNT)
    label(p, x + w // 2 - 180, canvas_y + canvas_h // 2 + 10, 360, 22,
          "Slab thickness: 0 m  —  exact-plane intersection", style=HNT)
    # Empty-state note
    label(p, x + w // 2 - 220, canvas_y + canvas_h // 2 + 44, 440, 22,
          "If no objects intersect: 'No objects intersect this plane — adjust offset or thickness'",
          style=HNT)
    # cursor readout
    label(p, x + 16, y0 + h - 26, 280, 22,
          "Cursor: E 123,456.78  N 4,567,890.12", style=HNT)
    return p


# ─────────────────────────── assembler ────────────────────────────────────


def build() -> str:
    """Assemble all pages into a complete mxfile XML string."""
    pages = [
        page_main_window(),
        page_3d_tab(),
        page_slice_tab(),
        page_point_form(),
        page_line_form(),
        page_polygon_select(),
        page_polygon_enter(),
        page_ray_form(),
        page_vector_origin_endpoint(),
        page_vector_length_direction(),
        page_circle_form(),
        page_ball_form(),
        page_cylinder_form(),
        page_solid_form(),
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
