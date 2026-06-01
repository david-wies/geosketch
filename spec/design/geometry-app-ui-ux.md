# GeoSketch — UI / UX Design

**Version**: 1.1  **Date**: 2026-05-31
**Companion**: `MVP.md` (functional spec). When this doc and `MVP.md` disagree, `MVP.md` wins for *behavior*; this doc wins for *layout and interaction*.
**Wireframes**: every form, tab, and dialog described below has a matching page in `geometry-app-ui-ux.drawio`. Each section cites its page name.

---

## 1. Global UI conventions

These rules apply to every screen unless an object section overrides them explicitly.

### 1.1 Three-column main window

| Column | Width | Contents |
|---|---|---|
| Left | 280 px (resizable, collapsible to 40 px) | Stack of collapsible cards: `Create objects`, `Import`, `Calculations`, `Measurements`. Each card opens an in-panel form or launches a modal dialog. |
| Center | flex | **Three-tab canvas**: `2D` (flat, altitude ignored) · `3D` (altitude-aware, rotatable) · `Slice` (general cutting plane with controls strip). Each tab has its own Matplotlib Figure + NavigationToolbar. Cursor read-out (UTM `E, N` in 2D/Slice; `E, N, Z` in 3D) docked bottom-left of the active canvas. |
| Right | 320 px (resizable) | Properties of the current selection. Empty-state message when nothing selected. Auto-shows polygon/circle measurements (area, perimeter/circumference). |

A persistent menubar (`File`, `Edit`, `View`, `Help`) and toolbar sit above the columns. A status bar at the bottom shows project title, save state (`unsaved changes` indicator), and a *stale canvas* indicator when the model has mutated since the last redraw.

### 1.2 Shared form layout

Every object-creation form (Point, Line, Polygon, Ray, Vector, Circle, Ball, Cylinder, Solid, Tangent) follows the same skeleton so muscle memory carries across types:

```
+---------------------------------------+
| <Form title>                          |
+---------------------------------------+
| Name:  [_____________________________] |   <- row 1: name spans full width
| Line: [#______] □  Fill: [#______] ■  |   <- row 2 (non-Point): two color pickers
| Color: [#______] ■  Alpha: [===|=][▸] |   <- row 2 (Point only): single color + alpha
| Alpha: [============|===] [0.80]       |   <- row 3 (non-Point): alpha slider
| Mode:  ( ) Click   (•) Form           |   <- row 4 (when applicable): radio group
| ------------------------------------- |
| <type-specific body>                  |
| ------------------------------------- |
|                       [Cancel] [OK]   |   <- bottom-right primary actions
+---------------------------------------+
```

Rules:
- Inline validation runs on `<Tab>`, `<Enter>`, and field blur. Invalid fields get a red 1px border and a sentence-fragment error tucked beneath the field.
- `OK` is disabled until every required field validates. The disabled state has a tooltip listing the first failing rule.
- `Esc` cancels; `Enter` activates `OK` when focus is in a non-multiline field.
- The Edit dialog is the same dialog with fields prefilled. Title becomes `Edit <type>` and the OK button reads `Save changes`.

### 1.3 Tab convention (Polygon, Vector)

- Tab strip sits **below** the shared header rows (Name, Color/Alpha).
- The active tab is white with a 2 px accent top border; inactive tabs are gray with no top border.
- Switching tabs **preserves any already-filled state on the previous tab** until the dialog closes.
- The OK button submits whichever tab is currently active; field values on the other tab are ignored. The active tab is what creates the object.

### 1.4 Reference-point subcomponent (shared)

A reusable composite control appears in three places: point text import, polygon file import, polygon `Enter Vertices` tab.

```
[x] Use reference point   Reference: [pt_002 ▼]
```

- Disabled-by-default checkbox + combobox.
- Checking enables the combobox and changes the interpretation of all subsequent (E, N) inputs from absolute UTM to deltas from the selected point.
- Combobox lists every existing Point by `id — name (E, N)`; sorted by ID.
- If the scene has zero points, the checkbox is disabled with a tooltip `Create a point first to enable relative offsets`.
- The control is implemented as a single widget class so the three call sites share identical look + behavior.

### 1.5 Color + alpha controls

**Point** (single color):
- `Color` swatch (28 × 28 px, click to open system picker) + hex read-only field + alpha slider all on one row.

**All other objects** (two colors):
- Row 1: `Line color` swatch + hex field, then `Fill color` swatch + hex field. Each swatch is 28 × 28 px.
- Row 2: `Alpha` slider (0.0 → 1.0, 0.05 increments) + numeric spinbox for precise entry.
- `fill_color` is stored for all non-Point objects but only rendered for objects with a closed surface: Circle, Polygon, Ball, Cylinder, and Solid. The picker is never disabled — the stored value is simply not drawn for 1D objects (Line, Ray, Vector, Tangent).

### 1.6 Radio button groups (not dropdowns)

Mode choices use radio buttons because they:
- Make all options visible at a glance.
- Don't hide the inverse mode behind a click.
- Keyboard-navigate with arrow keys.

Three canonical groups recur:
- `Input mode`: `Click` / `Form`
- `Direction mode`: `Azimuth` / `Angle`
- `Direction units`: `Radians` / `Degrees`

### 1.7 Validation messages

| Severity | Treatment |
|---|---|
| Field-level error | Red 1px border on field + inline message in red, ≤80 chars. |
| Form-level error | Banner above action buttons; appears on failed submit only. |
| Warning | Yellow 1px border + inline message in dark yellow. Form can still submit. |
| Info | No border change; gray italic helper text under the field. |

---

## 2. Main window

**Diagram**: `geometry-app-ui-ux.drawio` → page **Main window**.

Top-level regions, top to bottom:

1. **Window icon** — `GeoSketch.png` (project root), applied to the root `Tk` window via `iconphoto()` at startup. The same image is shown in the OS taskbar and window switcher.
2. **Menubar** — `File` (New, Open, Save, Save As, Close, Exit) | `Edit` (Undo `Ctrl+Z`, Redo `Ctrl+Y`/`Ctrl+Shift+Z`, Delete `Del`, — Options… `Ctrl+,`) | `View` (Refresh canvas, Fit to extent, Toggle grid, Toggle left/right panel) | `Help` (About, Spec).
3. **Toolbar** — Open, Save, Undo, Redo, Refresh canvas, Pan tool, Zoom tool, Options. Icon-only buttons with tooltip labels.
4. **Three-column workspace** — see §1.1.
5. **Status bar** — Project title • unsaved-changes dot • cursor UTM coordinates • stale-canvas indicator with a `Refresh` link.

### 2.1 Left panel cards

Each card is a collapsible disclosure with a chevron in the header. Collapsed cards remember state across sessions.

- **Create objects** — 10 buttons (Point, Line, Polygon, Ray, Vector, Circle, Ball, Cylinder, Solid, Tangent). Clicking a button opens the corresponding form dialog.
- **Import** — `Import points from text…`, `Import polygon from file…`.
- **Calculations** — Direction, Convexity, Convex Hull 2D (polygon), Convex Hull 3D (solid / point set), Convex Skull 2D (polygon only), Line ∩ Line, Line ∩ Polygon, Ray ∩ Polygon, Polygon ∩ Polygon, Distance (Point↔Point, Point↔Polygon, Ray↔Polygon, Polygon↔Polygon).
- **Measurements** — Polygon Area, Polygon Perimeter, Polygon Prism Volume, Circle Area, Circle Circumference, Circle Cylinder Volume, Segment/Vector Length, Angle Between Directions, Angle at Vertex (three-point azimuth & elevation — pick ordered points A, B, C; azimuth ignores altitude, elevation = elev(BC) − elev(BA); order matters).

### 2.2 Center canvas

The center column hosts a `ttk.Notebook` tab bar with three tabs: **2D**, **3D**, and **Slice**. Each tab embeds its own Matplotlib `Figure` via `FigureCanvasTkAgg` with its own NavigationToolbar.

- Pan/zoom uses the standard matplotlib nav toolbar (compact mode), independently per tab.
- Selection: single-click on an object selects; `Ctrl+click` extends the selection (multi-select for future bulk operations). Empty-canvas click clears selection.
- The canvas is **render-on-demand** (see `MVP.md`). A persistent `Refresh` button sits inline in the active tab's nav toolbar and pulses subtly when the model is stale. Switching to a stale tab triggers an automatic redraw of that tab.

See §2.4 for per-tab details.

### 2.3 Right panel

Tree of grouped property rows. Sections:

- `Identity`: ID (read-only), Name (editable inline).
- `Appearance`: for Point — color swatch + alpha slider + visibility checkbox. For all other types — line color swatch, fill color swatch, alpha slider, visibility checkbox.
- `Type-specific`: e.g. for a polygon — vertex count, `is_convex` flag, area, perimeter, vertex list. For 3D solids: Ball shows volume + surface area; Cylinder shows volume + lateral area + total area; Solid shows volume + centroid + lateral area + total area (all auto-computed, no extra input required).
- `Actions`: `Edit…` (opens prefilled form dialog), `Delete…` (opens cascade-confirm dialog).

Inline edits commit on blur and produce undoable commands.

### 2.4 Canvas tabs

#### Tab 1 — 2D (flat)

Default tab on project open. All objects rendered in `(Easting, Northing)` regardless of their altitude. Standard 2D matplotlib axes with UTM grid. Blit strategy active for selection highlights (see `MVP.md`).

#### Tab 2 — 3D

Full 3D axes (`mpl_toolkits.mplot3d.Axes3D`). Axes labeled `Easting (m)`, `Northing (m)`, `Altitude (m)`. Default view angle: elevation 30°, azimuth 225°; user may rotate/tilt freely with the mouse. Blit is not available; both full redraws and selection changes do a full `canvas.draw()`. Points with altitude = 0 (default) render at Z = 0. The 3D tab shows all objects at their respective altitudes.

#### Tab 3 — Slice

2D view of the cross-section of the scene at a user-defined cutting plane. A **SliceControlsFrame** strip is docked above the canvas:

```
┌────────────────────────────────────────────────────────────┐
│ Plane:  (•) Horizontal Z=c  ( ) Easting E=c               │
│         ( ) Northing N=c    ( ) Custom aE+bN+cZ=d          │
│ Offset: [__0.0__] m    [====|=========================]    │
│ Thickness: [__0.0__] m                        [Apply]      │
└────────────────────────────────────────────────────────────┘
│                                                            │
│         Matplotlib canvas (active slice view)             │
│         NavigationToolbar                                  │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

Controls:
- **Plane mode** radio group: four options (Horizontal, Easting, Northing, Custom). Selecting Custom reveals four coefficient fields `a`, `b`, `c`, `d` for the equation `aE + bN + cZ = d`.
- **Offset** numeric entry + horizontal slider. For the three axis-aligned presets the slider range is auto-set to ±10% beyond the scene's extent along that axis. For Custom mode the offset fields are entered directly.
- **Thickness** numeric entry (meters; default 0 = exact plane). Positive values include objects within ±thickness of the plane.
- **Apply** button — triggers a Slice tab redraw. Does not auto-apply on every keystroke (avoid expensive recomputes while typing).

When the slice plane produces no intersecting objects, the canvas shows a centered text annotation: *"No objects intersect this plane — adjust the offset or thickness."*

The in-plane axes are the two coordinates not fixed by the cutting plane (e.g. for Horizontal Z=c, the axes are Easting and Northing; for Easting E=c, the axes are Northing and Altitude).

---

## 3. Object forms

Every form below follows §1.2. Only the type-specific body is described in each section.

### 3.1 Point form

**Diagram**: page **Point form**.

Appearance row: single `Color` (marker) picker + alpha slider on one row (Point does not have a fill area — see §1.5).

Body:
- `Input mode`: radio `Click` / `Form`.
  - `Click`: form shrinks to just `Name` + appearance, with hint text `Click on the canvas to place the point.` and a `Capture` button that arms the canvas for one click.
  - `Form`: shows Easting / Northing / Altitude fields.
- `Easting (E)`: numeric, float64.
- `Northing (N)`: numeric, float64.
- `Altitude (Z)`: numeric, float64; default 0.0. Blank entry is accepted and treated as 0.0. Helper text: *"Z-coordinate in metres above datum. 0 = ground level."*
- **Reference-point subcomponent** (§1.4). When enabled, E/N/Z labels change to `ΔE` / `ΔN` / `ΔZ`.

### 3.2 Line form

**Diagram**: page **Line form**.

Body:
- `Input mode`: radio `Click` / `Form`.
- `Point A`: combobox of existing Points.
- `Point B`: combobox of existing Points.
- `Direction (read-only, computed)`: shows the resulting azimuth in the currently selected direction-units, updated live as A/B change.
- `Elevation (read-only, computed)`: shows the angle above the horizontal plane (`atan2(Δaltitude, √(Δeast² + Δnorth²))`), in the same units as Direction, updated live as A/B change.

### 3.3 Polygon form — `Select Points` tab

**Diagram**: page **Polygon — Select Points**.

Body of the tab:
- Multi-select listbox of existing Points (`id — name (E, N)`), with a small badge on each row showing its order-of-selection number once selected.
- `Reorder` controls: `↑` `↓` buttons to bump the focused row.
- `Clear selection` button.
- Live preview row: `Vertices: 4 • CCW after import: yes • is_convex (predicted): true`.

### 3.4 Polygon form — `Enter Vertices` tab

**Diagram**: page **Polygon — Enter Vertices**.

Body of the tab:
- `Number of vertices`: spinbox, min 3, max 256. Changing the value resizes the table preserving existing rows.
- Vertex table (scrollable):
  - Columns: `#`, `E`, `N`, `Z`, `Label (optional)`. Z defaults to 0.0 when left blank.
  - Tab between cells; Enter on the last row adds a new row.
- **Reference-point subcomponent** (§1.4). When enabled, the E/N/Z column headers change to `ΔE` / `ΔN` / `ΔZ`.

### 3.5 Ray form

**Diagram**: page **Ray form**.

Body:
- `Input mode`: radio `Click` / `Form`.
- `Origin`: combobox of existing Points.
- `Direction mode`: radio `Azimuth` / `Angle`.
- `Direction units`: radio `Radians` / `Degrees`.
- `Direction value`: numeric (horizontal bearing), with valid-range hint to its right.
- `Elevation`: numeric (angle above horizontal, same units; default 0.0 = horizontal; range [-90°, 90°]).

In `Click` mode the body collapses to: origin combobox + `Click endpoint on canvas` armed-capture button; direction and elevation are computed from the 3D coordinates of origin and clicked point.

### 3.6 Vector form — `Origin + Endpoint` tab

**Diagram**: page **Vector — Origin+Endpoint**.

Body of the tab:
- `Origin`: combobox of existing Points.
- `Endpoint`: combobox of existing Points.
- `Direction (computed, read-only)` shown in the user's preferred direction mode + units.
- `Length (computed, read-only)` in meters.

Creating from this tab sets `endpoint_id` to the chosen endpoint Point; deletes of either point cascade-delete the Vector (see `MVP.md` §Vector).

### 3.7 Vector form — `Length + Direction` tab

**Diagram**: page **Vector — Length+Direction**.

Body of the tab:
- `Origin`: combobox of existing Points.
- `Length`: numeric, > 0.
- `Direction mode`: radio `Azimuth` / `Angle`.
- `Direction units`: radio `Radians` / `Degrees`.
- `Direction value`: numeric (horizontal bearing).
- `Elevation`: numeric (angle above horizontal, same units; default 0.0 = horizontal).
- `Endpoint (computed, read-only)` showing `(E, N, Z)`.

Creating from this tab leaves `endpoint_id = null`.

### 3.8 Circle form

**Diagram**: page **Circle form**.

Body:
- `Input mode`: radio `Click` / `Form`.
- `Center`: combobox of existing Points.
- `Radius`: numeric, > 0.
- Helper text: *"Circle is always a flat 2D disk in the horizontal plane at the center point's altitude. For a 3D sphere use Ball; for a 3D cylinder use Cylinder."*

In `Click` mode the body shows center combobox + `Click radius point on canvas` armed-capture button.

### 3.8a Ball form

**Diagram**: page **Ball form**.

Body:
- `Input mode`: radio `Click` / `Form`.
- `Center`: combobox of existing Points (the 3D center of the sphere).
- `Radius`: numeric, > 0.
- Helper text: *"Ball renders as a wireframe sphere in the 3D view. In 2D flat view it projects as a circle."*

In `Click` mode the body shows center combobox + `Click radius point on canvas` armed-capture button (radius = 3D distance from center to clicked point).

### 3.8b Cylinder form

**Diagram**: page **Cylinder form**.

Body:
- `Base center`: combobox of existing Points (center of the base circular face).
- `Radius`: numeric, > 0.
- `Height`: numeric, > 0.
- `Axis orientation`: radio `Vertical` / `Inclined`.
  - **Vertical** (default): axis points straight up; no further direction fields shown.
  - **Inclined**: reveals two additional rows:
    - `Axis azimuth`: direction mode radio (`Azimuth` / `Angle`) + units radio (`Radians` / `Degrees`) + numeric entry. The azimuth is the horizontal bearing of the axis projected onto the EN plane.
    - `Axis elevation`: numeric entry (same units as azimuth). Angle of the axis above the horizontal plane. Range `(0°, 90°]`; must be > 0 (0° would produce a flat disk, not a cylinder).

No Click mode — cylinder parameters cannot be captured with two canvas clicks.

Helper text (below axis section): *"In 2D flat view the cylinder renders as its base circle. In 3D view the full cylinder surface is drawn along the axis direction."*

### 3.8c Solid form

**Diagram**: page **Solid form**.

Body:
- **Layers** (scrollable ordered list, ≥ 2 rows):
  - Each row: row number · shape-type radio (`Polygon` / `Point`) · combobox selecting an existing Polygon or Point · reorder buttons (`↑` `↓`) · remove button (`×`)
  - Rows represent the solid's cross-sections in order from bottom to top
  - Combobox lists change based on the shape-type radio: Polygon shows existing Polygons with vertex count; Point shows existing Points with `(E, N, Z)`
  - A row whose shape type is **Point** creates an apex/nadir; only one Point row is allowed; it must be the first or last row
- `Add layer` button — appends a new Polygon row at the bottom
- Validation hint shown live: *"⚠ Layer 2 has 4 vertices, layer 3 has 6 — faces will be triangulated"* when adjacent layers have different vertex counts
- Helper text: *"Box: two rectangles · Pyramid: polygon + Point · Frustum: two different-size polygons · Loft: any sequence"*

No Click mode.

### 3.9 Tangent form

**Diagram**: page **Tangent form**.

Body:
- `Shape type`: radio `Circle` / `Ball`. Determines which combobox is shown and how direction is handled.
- `Circle / Ball`: combobox of existing objects of the selected type (`id — name`).
- `Point on surface`: combobox of existing Points; entries flagged with a ✓ if the point lies on the selected shape's surface within `EPS_DISTANCE`.
- **For Circle** (direction is fully automatic):
  - `Direction (computed, read-only)`: `radius_azimuth + π/2 mod 2π`, elevation 0.
  - `Flip direction` toggle: shows the 180°-opposite heading; the line is unchanged.
- **For Ball** (direction must be supplied — any direction perpendicular to the radius is valid):
  - `Direction mode`: radio `Azimuth` / `Angle`.
  - `Direction units`: radio `Radians` / `Degrees`.
  - `Azimuth`: numeric entry.
  - `Elevation`: numeric entry (angle above horizontal; the constraint `direction_vector ⊥ radius_vector` is validated on submit).
  - Helper: *"Direction must be perpendicular to the radius at the selected point."*
  - `Flip direction` toggle: adds 180° to azimuth.

---

## 4. Dialogs

### 4.1 Point text import dialog

**Diagram**: page **Point text import**.

- Title: `Import points from text`.
- Multiline textarea (8 visible rows, monospaced) with placeholder `Name Northing Easting — one point per line`.
- **Reference-point subcomponent** (§1.4).
- Preview panel: live-parses the textarea, shows `n valid lines • m errors` and a 3-row sample of what will be created.
- Actions: `Cancel`, `Import` (disabled until ≥1 valid line).
- Errors are listed under the textarea with line numbers.

### 4.2 Polygon file import dialog

**Diagram**: page **Polygon file import**.

- Title: `Import polygon from file`.
- File path field + `Browse…` button.
- **Reference-point subcomponent** (§1.4).
- `Vertex ordering` radio group:
  - `Boundary order` (default) — file rows are the polygon's boundary traversal; signed-area reverse to canonicalize CCW.
  - `Sort (centroid + polar angle)` — file rows are an unordered point set; convex-only; warns at submit if the result looks concave.
- `Polygon name`: defaults to the file basename, editable.
- Color/alpha controls (same as forms).
- Preview area shows vertex count and a tiny line-plot of the parsed polygon.
- Actions: `Cancel`, `Import`.

### 4.3 Cascade-delete confirmation dialog

**Diagram**: page **Cascade-delete confirm**.

- Title: `Delete and cascade?`.
- Body: `Deleting <Object A (pt_001)> will also remove the following <N> objects:`
- Scrolling list, grouped by type, each row `<icon> <type> <id> — <name>`.
- Footer note: `This action can be undone with Ctrl+Z.`
- Actions: `Cancel` (default), `Delete all (N + 1)` — destructive red.

### 4.4 Measurement dialogs

**Diagram**: page **Measurement dialogs**.

The following measurements share one container with a left rail of options:

| Measurement | Inputs |
|---|---|
| Polygon Area | 1 polygon |
| Polygon Perimeter | 1 polygon |
| Polygon Prism Volume | 1 polygon + height (m) |
| Circle Area | 1 circle |
| Circle Circumference | 1 circle |
| Circle Cylinder Volume | 1 circle + height (m) |
| Ball Volume | 1 ball |
| Ball Surface Area | 1 ball |
| Cylinder Volume | 1 cylinder |
| Cylinder Lateral Surface Area | 1 cylinder |
| Cylinder Total Surface Area | 1 cylinder |
| Solid Volume | 1 solid |
| Solid Centroid | 1 solid |
| Solid Lateral Surface Area | 1 solid |
| Solid Total Surface Area | 1 solid |
| Segment / Vector Length | 1 vector OR 2 points |
| Angle Between Directions | 2 direction-bearing objects |

Layout:
- Left rail: list of measurement names; click to switch.
- Right pane: input pickers for the selected measurement + a `Compute` button + a read-only result block (with both unit forms where relevant: e.g. angle shown as radians and degrees).
- `Copy result` button copies the numeric value to the clipboard.
- Dialog is non-modal so users can keep it open while selecting on the canvas.

### 4.5 Options dialog

**Diagram**: page **Options dialog**.

- Title: `Options`.
- Opened via `Edit → Options…` (keyboard `Ctrl+,`) or the toolbar gear button (`⚙`).
- Modal; settings take effect when the user presses `OK`. `Cancel` discards all unsaved changes.
- Four tabs: `Appearance`, `Directions`, `Canvas`, `Tolerances`.

**Appearance tab:**
- `Default line color` — color swatch + hex text field. Initial stroke color assigned to new non-Point objects.
- `Default fill color` — color swatch + hex text field. Initial fill color assigned to new non-Point objects.
- `Default point color` — color swatch + hex text field. Initial marker color assigned to new Point objects.
- `Default alpha` — slider (0.0–1.0, 0.05 increments) + numeric spinbox. Initial alpha for all new objects.
- `Point marker size` — integer spinbox, 4–16 px. Diameter of the dot rendered for Point objects.
- `Stroke width` — integer spinbox, 1–5 px. Line width for all geometric objects.
- `Canvas background` — color swatch + hex text field.

**Directions tab:**
- `Default direction mode` — radio `Azimuth` / `Angle`. Pre-selects the direction-mode radio in all direction-bearing forms (Ray, Vector, Line, Tangent).
- `Default direction units` — radio `Radians` / `Degrees`. Pre-selects the units radio in direction-bearing forms.
- `Angle decimal places` — spinbox 1–8. Controls display precision for computed direction values.

**Canvas tab:**
- `Show grid` — checkbox (default: on).
- `Grid color` — color swatch + hex field; enabled only when `Show grid` is checked.
- `Show axis labels` — checkbox (default: on).
- `Coordinate decimal places` — spinbox 1–6. Controls decimal digits in the cursor read-out and computed coordinate values.

**Tolerances tab:**
- One row per named tolerance: `EPS_DISTANCE (m)`, `EPS_ANGLE (rad)`, `EPS_AREA (m²)`, `EPS_PARAM`. Each row: numeric text field + `Reset` button that restores the documented default value.
- Info banner below the table: `Changing tolerances affects all geometric comparisons. Reset to defaults if results become incorrect.`

**Bottom actions** (three buttons across the dialog footer):
- `Cancel` (left-aligned) — discards all changes and closes.
- `Reset to defaults` (center) — resets all four tabs to factory values; dialog stays open.
- `OK` (right-aligned, primary) — applies and closes.

---

## 5. Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+,` | Options |
| `Ctrl+N` | New project |
| `Ctrl+O` | Open project |
| `Ctrl+S` | Save project |
| `Ctrl+Shift+S` | Save As |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` / `Ctrl+Shift+Z` | Redo |
| `Del` | Delete selection (opens cascade-confirm) |
| `Esc` | Cancel current dialog / deselect on canvas |
| `Enter` | Activate default action in dialog |
| `F5` | Refresh canvas (active tab) |
| `F1` | Switch to 2D flat tab |
| `F2` | Switch to 3D tab |
| `F3` | Switch to Slice tab |
| `Ctrl++` / `Ctrl+-` | Zoom in / out canvas |
| `Ctrl+0` | Fit to extent |

---

## 6. Accessibility

- Every form control has a `<label for>`-equivalent association.
- Tab order follows visual order top-to-bottom, left-to-right.
- Focus outlines are 2 px high-contrast and never suppressed.
- Color is never the sole carrier of state: validation also uses iconography and text; selection on the canvas also uses a thickened stroke, not only a color change.
- Minimum touch/click target 32 × 32 px; toolbar icons have hit areas that extend past the visual icon.
- Color picker exposes a hex-text fallback so users who can't operate the swatch can still set color.

---

## 7. Visual style tokens

| Token | Value | Use |
|---|---|---|
| `--bg-app` | `#f5f5f5` | Window background |
| `--bg-panel` | `#ffffff` | Form / dialog interior |
| `--bg-card` | `#fafafa` | Collapsible card body |
| `--border` | `#cccccc` | Default control border |
| `--border-focus` | `#4d7eaf` | Focused control border |
| `--border-error` | `#c0392b` | Validation error border |
| `--accent` | `#4d7eaf` | Active tab underline, primary buttons |
| `--accent-danger` | `#c0392b` | Destructive buttons |
| `--text` | `#222222` | Primary text |
| `--text-muted` | `#666666` | Helper / placeholder text |

Implementations may map these tokens to a tkinter theme (`ttk.Style`) of their choice; the spec only requires the *roles* be distinguishable.

## 8. Assets

| File | Location | Use |
|---|---|---|
| `GeoSketch.png` | project root | Application window icon — set via `root.iconphoto()` at startup; also appears in the OS taskbar and window switcher. |

---
