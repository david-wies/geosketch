# GeoSketch - MVP Specification

**Version**: 1.0  
**Date**: May 16, 2026  
**Target Platform**: Desktop Application (Python with tkinter + matplotlib)  
**Coordinate System**: UTM (Universal Transverse Mercator) in meters  
**Precision**: NumPy float64 (IEEE 754 double precision)  
**Persistence**: JSON file format  

---

## Executive Summary

GeoSketch is a desktop application that enables users to create, visualize, manipulate, and analyze geometric objects and their spatial relationships. Users construct geometric scenes by adding points, lines, rays, vectors, circles, polygons, and tangents, then perform calculations to determine directions, convexity, intersections, and distances between objects.

The application supports multiple input methods (clicking on canvas, form inputs, file imports), real-time visualization, and project persistence via JSON files.

---

## Core Concepts

### Coordinate System
- **System**: Universal Transverse Mercator (UTM)
- **Units**: Meters
- **Notation**: All coordinates expressed as (Easting, Northing) pairs
- **Azimuth Convention**: Measured clockwise from North, range [0, 2π) radians
- **Angle Convention**: Standard mathematical angles, measured counter-clockwise from East, range [0, 2π) radians or [0°, 360°)

### Precision & Numeric Handling
- The application uses NumPy float64 as the reference precision level for all geometry results, even though not every operation must be implemented with NumPy.
- Calculations may use NumPy, Python math, or other numeric libraries, but outputs must be consistent with NumPy float64 semantics.
- Distance calculations: Euclidean (√[(Δeast)² + (Δnorth)²])
- Angle calculations: atan2-based with proper quadrant handling
- Polygon vertex ordering: Counter-clockwise (CCW)

### Mode Enumerations
Selection and creation modes use enumerated values rather than free-form strings.
The in-memory enum and the JSON wire format are deliberately different so they can evolve independently:

| Concept | In-memory enum (Python) | JSON string (on disk) |
|---|---|---|
| Direction mode | `DirectionMode.AZIMUTH`, `DirectionMode.ANGLE` | `"azimuth"`, `"angle"` |
| Direction units | `DirectionUnits.RADIANS`, `DirectionUnits.DEGREES` | `"radians"`, `"degrees"` |
| Input mode (UI) | `InputMode.CLICK`, `InputMode.FORM` | not persisted |

Serialization MUST lowercase the enum name; deserialization MUST be case-insensitive but produce canonical lowercase on re-save.

### Numerical Tolerances
All comparisons that involve floating-point geometry use named tolerances, not bare literals. These are the reference values; implementations may centralize them in a constants module:

| Name | Value | Use |
|---|---|---|
| `EPS_DISTANCE` | `1e-6` m | "is point on circle", "are segments coincident", "do polygons touch" |
| `EPS_ANGLE` | `1e-9` rad | "are lines parallel", "is cross product zero" |
| `EPS_AREA` | `1e-9` m² | signed-area sign check for CCW reorder |
| `EPS_PARAM` | `1e-9` | parametric `t` clipping for segment/line intersection |

Validation that a tangent point lies on its circle uses `|distance(point, center) - radius| < EPS_DISTANCE`. Parallel-line detection uses `|cross(d1, d2)| < EPS_ANGLE`.

### Object Identity
- Each object has a unique ID (string format: "type_NNN", e.g., "pt_001", "ln_001")
- IDs are immutable and persist across save/load cycles
- References between objects use ID strings, not memory pointers

---

## Object Types

### 1. Point
**Description**: A single location in UTM space.

**Properties**:
- `name`: string (user-assigned identifier)
- `id`: string (system-generated unique ID)
- `type`: "point"
- `easting`: float (UTM easting coordinate)
- `northing`: float (UTM northing coordinate)
- `color`: RGB tuple or hex code
- `alpha`: float (transparency level, 0.0 to 1.0)
- `visibility`: boolean

**Creation Methods**:
- **Click Mode**: User clicks on canvas; coordinates captured from click location
- **Form Input**: User enters easting, northing, name, color in dialog
- **Relative Coordinates**: User selects reference point + delta easting/northing; absolute coordinates calculated as: `absolute = reference + delta`
- **Text Import**: User provides text; regex extracts name, northing, easting. The import dialog includes a `Use reference point` checkbox; when checked, a combobox of existing points becomes enabled and the parsed `(northing, easting)` values are interpreted as **deltas** from the selected reference point (absolute = reference + delta). When unchecked, values are absolute UTM coordinates and the combobox is disabled.

**Regex Pattern for Text Import**: `(\w+)\s+([\d.-]+)\s+([\d.-]+)`  
Captures: [1] name, [2] northing, [3] easting

> ⚠️ **Axis-order foot-gun**: the text-import format is `name northing easting`, but the polygon file format and every internal API use `easting northing`. The order is reversed *only* for point text import (it matches a common survey-export convention). Do not "normalize" this without changing the spec.

---

### 2. Line
**Description**: An infinite line connecting two points.

**Properties**:
- `name`: string
- `id`: string
- `type`: "line"
- `point_a_id`: string (reference to Point)
- `point_b_id`: string (reference to Point)
- `direction`: float (stored as radians, supports azimuth/angle and radians/degrees conversion)
- `direction_mode`: string ("azimuth" or "angle")
- `direction_units`: string ("radians" or "degrees")
- `line_color`: hex color code (stroke color)
- `fill_color`: hex color code (stored; not rendered — Line has no interior)
- `alpha`: float (transparency level, 0.0 to 1.0)
- `visibility`: boolean

**Creation Methods**:
- **Click Mode**: User selects 2 distinct points via clicks or dropdown
- **Form Input**: User selects point A and point B from dropdowns

**Automatic Calculations**:
- Direction: `azimuth = atan2(Δeast, Δnorth)`, normalized to [0, 2π)

---

### 3. Polygon
**Description**: A closed shape defined by 3 or more points in counter-clockwise order.

**Properties**:
- `name`: string
- `id`: string
- `type`: "polygon"
- `point_ids`: list of strings (ordered references to Points in CCW order)
- `is_convex`: boolean (cached convexity flag; computed on creation/modification)
- `line_color`: hex color code (stroke/outline color)
- `fill_color`: hex color code (interior fill color)
- `alpha`: float (transparency level, 0.0 to 1.0)
- `visibility`: boolean

**Creation Methods**:
- **Click Mode**: User selects 3+ points in sequence; CCW ordering automatically applied
- **Form Input**: User multi-selects points from list; CCW ordering automatically applied
- **File Import**: User selects polygon file with coordinate lines. The import dialog exposes two controls:
  - `Use reference point` checkbox + point combobox (deltas vs. absolute coordinates). Identical in layout and behavior to the one used for point text import; the two dialogs share a single reusable subcomponent.
  - `Vertex ordering` radio-button group with two options:
    - **Boundary order (default)**: trust the file's row order as the polygon's boundary traversal. Apply signed-area reverse only if needed to make it CCW. Works for any simple polygon, convex or concave.
    - **Sort (centroid + polar angle)**: treat the file as an unordered point set; sort vertices CCW by polar angle around their centroid. **Convex polygons only** — for concave inputs the result will be a different (convex-ish) shape than the user drew. If the centroid lies on or near a vertex (`< EPS_DISTANCE`), the sort is ambiguous and import is rejected with a message asking the user to switch to Boundary order.
  - In both modes the resulting polygon is then validated for **simplicity** (no self-intersections via segment-segment tests over non-adjacent edges) and **non-degeneracy** (`|signed_area| ≥ EPS_AREA`). A failure rejects the import with a specific reason; no polygon is created.
- **Simple Polygon Validation**: Polygon must be simple (no self-intersections); the system verifies simplicity before approval using segment-segment intersection tests over all non-adjacent edge pairs.

**File Import Format**:
```
4
123456.789 4567890.123
123457.456 4567891.456
123458.123 4567892.789
123457.890 4567891.234
```
First line: number of vertices  
Subsequent lines: easting northing (space-separated)

**Automatic Calculations**:
- Vertex ordering: the user's input order is preserved. The system computes the signed shoelace area; if it is negative (CW), the vertex list is **reversed in place**. Centroid-based angle sorting is **not** used — it mangles concave polygons. If `|signed_area| < EPS_AREA`, the polygon is degenerate and rejected.
- Convexity: Cached on creation; uses cross-product method for all consecutive vertex triplets. Sign of every cross product must agree.

---

### 4. Ray
**Description**: An infinite half-line with an origin point and direction.

**Properties**:
- `name`: string
- `id`: string
- `type`: "ray"
- `origin_id`: string (reference to Point)
- `direction`: float (stored as radians, supports azimuth/angle and radians/degrees conversion)
- `direction_mode`: string ("azimuth" or "angle")
- `direction_units`: string ("radians" or "degrees")
- `line_color`: hex color code (stroke color)
- `fill_color`: hex color code (stored; not rendered — Ray has no interior)
- `alpha`: float (transparency level, 0.0 to 1.0)
- `visibility`: boolean

**Creation Methods**:
- **Click Mode**: User clicks origin point, then secondary point; direction determined from origin to secondary point
- **Form Input**: User selects origin point and enters direction (azimuth or angle, radians or degrees)

---

### 5. Vector
**Description**: A directed line segment with origin, direction, and length.

**Properties**:
- `name`: string
- `id`: string
- `type`: "vector"
- `origin_id`: string (reference to Point)
- `direction`: float (stored as radians, supports azimuth/angle and radians/degrees conversion)
- `direction_mode`: string ("azimuth" or "angle")
- `direction_units`: string ("radians" or "degrees")
- `length`: float (distance in meters, must be > 0)
- `endpoint`: computed as (easting, northing) = (origin_easting + length × sin(azimuth), origin_northing + length × cos(azimuth))
- `endpoint_id`: string or null. Set to a Point ID **only** when the vector was created via the `Origin + Endpoint` tab (or click mode); in that case `length` and `direction` are derived from the two referenced points and are recomputed if either point is edited. Null when created via `Length + Direction` — the endpoint is a pure computed value and no Point object exists for it. Deleting the referenced endpoint Point cascades to delete this vector (same rule as origin).
- `line_color`: hex color code (stroke color, including arrowhead)
- `fill_color`: hex color code (stored; not rendered — Vector has no interior)
- `alpha`: float (transparency level, 0.0 to 1.0)
- `visibility`: boolean

**Creation Methods**:
- **Click Mode**: User clicks origin point, then endpoint point; direction and length calculated from origin to endpoint
- **Form Input**: User may create by either:
  - length + direction (azimuth or angle, radians or degrees)
  - origin + endpoint point selection

**Direction Input Modes**:
- **Azimuth Mode**: Angle in radians or degrees, measured clockwise from North
- **Angle Mode**: Standard math angle in radians or degrees, measured counter-clockwise from East

**Automatic Calculations**:
- Endpoint: calculated from origin, direction, and length
- Direction conversion: bidirectional conversion between azimuth and angle modes

---

### 6. Circle
**Description**: A circular shape with center point and radius.

**Properties**:
- `name`: string
- `id`: string
- `type`: "circle"
- `center_id`: string (reference to Point)
- `radius`: float (distance in meters, must be > 0)
- `line_color`: hex color code (stroke/outline color)
- `fill_color`: hex color code (interior fill color)
- `alpha`: float (transparency level, 0.0 to 1.0)
- `visibility`: boolean

**Creation Methods**:
- **Click Mode**: User clicks center point, then secondary point; radius calculated as Euclidean distance from center to secondary point
- **Form Input**: User selects center point and enters radius value

---

### 7. Tangent
**Description**: A line perpendicular to a circle's radius at a point on the circumference.

**Properties**:
- `name`: string
- `id`: string
- `type`: "tangent"
- `circle_id`: string (reference to Circle)
- `point_id`: string (reference to Point on circumference)
- `direction`: float (stored as radians, supports azimuth/angle and radians/degrees conversion)
- `direction_mode`: string ("azimuth" or "angle")
- `direction_units`: string ("radians" or "degrees")
- `line_color`: hex color code (stroke color)
- `fill_color`: hex color code (stored; not rendered — Tangent has no interior)
- `alpha`: float (transparency level, 0.0 to 1.0)
- `visibility`: boolean

**Creation Methods**:
- **Click Mode**: User clicks a point on a circle's circumference; tangent line created perpendicular to radius at that point

**Validation**: Point must be on circumference of circle (within numerical tolerance)

**Automatic Calculations**:
- Direction: a tangent line has two opposite-facing directions 180° apart. Canonical stored direction is `tangent_azimuth = (radius_azimuth + π/2) mod 2π`, where `radius_azimuth = atan2(point_e − center_e, point_n − center_n)`. The opposite direction `(tangent_azimuth + π) mod 2π` is geometrically equivalent and may be exposed in the UI as a "Flip" action; the rendered line itself does not change.

---

## Calculations & Operations

### Direction Calculation
**Input**: Line object (or two points)  
**Output**: Azimuth (float, radians [0, 2π))  
**Formula**: `azimuth = atan2(Δeast, Δnorth)`, normalized to [0, 2π)  
**Description**: Determines the compass direction a line points, measured clockwise from North. Direction calculation is also relevant for tangent objects and for all geometry objects that store an orientation.

### Convexity Check
**Input**: Polygon object  
**Output**: Boolean (True = convex, False = concave)  
**Method**: Cross-product method for all consecutive vertex triplets  
**Description**: Determines if all interior angles are less than 180°.

### Convex Hull Calculation
**Input**: Polygon object  
**Output**: New Polygon object (named "[original_name]_convex_hull")  
**Method**: Graham scan or similar  
**Description**: Creates smallest convex polygon containing all vertices of input polygon.

### Intersection Point (Line ↔ Line)
**Input**: Two Line objects  
**Output**: Point object or "No Intersection" (for parallel lines)  
**Method**: Parametric line equation solving  
**Description**: Finds point where two lines cross. Returns None for parallel lines.

### Intersection Points (Line ↔ Polygon)
**Input**: Line object, Polygon object  
**Output**: List of Point objects (ordered along line)  
**Description**: Finds all points where line crosses polygon boundary.

### Intersection Distance (Ray ↔ Polygon)
**Input**: Ray object, Polygon object  
**Output**: Float (distance in meters) or Infinity  
**Description**: Returns distance from ray origin to nearest intersection point on polygon. If ray doesn't intersect polygon, returns Infinity.

### Intersection Points (Polygon ↔ Polygon)
**Input**: Two Polygon objects  
**Output**: List of Point objects (ordered)  
**Description**: Finds all points where polygon boundaries cross.

### Distance (Point ↔ Point)

**Input**: Two Point objects  
**Output**: Float (distance in meters)  
**Formula**: `distance = √[(Δeast)² + (Δnorth)²]`  
**Description**: Euclidean distance between two points.

### Distance (Point ↔ Polygon)
**Input**: Point object, Polygon object  
**Output**: Float (distance in meters)  
**Rules**:
- If point is inside polygon: distance = 0
- If point is outside polygon: distance = minimum distance to any polygon edge
**Description**: Shortest distance from point to polygon boundary or interior.

### Distance (Ray ↔ Polygon)
**Input**: Ray object, Polygon object  
**Output**: Float (distance in meters) or Infinity  
**Description**: Same as "Intersection Distance" - distance from ray origin to nearest intersection point.

### Distance (Polygon ↔ Polygon)
**Input**: Two Polygon objects  
**Output**: Float (distance in meters)  
**Rules**:
- If polygons intersect or touch: distance = 0
- Otherwise: distance = minimum distance between any edge of one polygon and any edge of the other polygon
**Description**: Shortest distance between two polygon boundaries.

---

## Measurements

Measurement tools compute scalar properties of existing objects. They are read-only operations: invoking a measurement does **not** create a new persisted object — the result is shown in a result panel and may be copied to the clipboard.

### Polygon Area
**Input**: Polygon object  
**Output**: Float (square meters)  
**Formula**: shoelace — `area = 0.5 · |Σᵢ (eᵢ · nᵢ₊₁ − eᵢ₊₁ · nᵢ)|`, indices mod n  
**Description**: Signed shoelace magnitude. Always non-negative because polygons are stored CCW; the sign of the raw shoelace is also used internally by the CCW-reverse step but the user-facing value is the absolute area.

### Polygon Perimeter
**Input**: Polygon object  
**Output**: Float (meters)  
**Formula**: `perimeter = Σᵢ √[(eᵢ₊₁ − eᵢ)² + (nᵢ₊₁ − nᵢ)²]`, indices mod n  
**Description**: Sum of edge lengths.

### Circle Area
**Input**: Circle object  
**Output**: Float (square meters)  
**Formula**: `area = π · r²`  
**Description**: Disk area enclosed by the circle.

### Circle Circumference
**Input**: Circle object  
**Output**: Float (meters)  
**Formula**: `circumference = 2 · π · r`  
**Description**: Perimeter of the circle. Surfaced under the same "perimeter" mental model as polygons so a user looking at the Measurements card finds both in one place.

### Segment / Vector Length
**Input**: Vector object **or** two Points  
**Output**: Float (meters)  
**Formula**: Euclidean — `√[(Δe)² + (Δn)²]`  
**Description**: For a Vector this is exactly its `length` property (no recomputation needed); for two selected Points it is the same as `Distance(Point ↔ Point)`. Surfaced as a measurement so the user has a single discoverable entry point.

### Angle Between Directions
**Input**: Two direction-bearing objects (any combination of Line, Ray, Vector, Tangent)  
**Output**: Float, displayed in both radians and degrees, range `[0, π]` (unsigned angle between the lines they define)  
**Formula**: `θ = arccos(|cos(d₁ − d₂)|)` where `d₁`, `d₂` are the stored radian directions. Using the absolute value collapses the 180°-supplementary pair so a line and its 180°-flipped twin measure as 0, not π.  
**Description**: The unsigned acute/obtuse angle between two oriented objects, treating each as the infinite line it lies on. Parallel directions return 0; perpendicular returns π/2. Both `direction_mode` settings are normalized to radians before comparison, so the result is convention-independent.

### Measurement UI
- Measurements are invoked from a `Measurements` collapsible card in the left panel, alongside the existing creation/calculation cards.
- Each measurement opens a small dialog with object pickers matching its input signature. The dialog has a `Compute` button; results render in the dialog and persist in the right panel under a `Last measurement` field until cleared or a new measurement is taken.
- Polygon Area and Polygon Perimeter are *also* shown automatically in the right-panel properties whenever a Polygon is selected — these are cheap and free of ambiguity.
- Circle Area and Circle Circumference are likewise shown automatically in the right-panel properties whenever a Circle is selected.

---

## Visualization

### Canvas Display
- **2D Rendering**: Cartesian coordinate system with UTM axes/grid displayed.
- **Render on Demand**: the canvas does *not* redraw on every model mutation. A redraw is triggered by exactly these events:
  1. User clicks the explicit `Refresh` / `Redraw` button.
  2. User pans or zooms the canvas (matplotlib navigation toolbar action).
  3. Selection changes (an object is clicked on the canvas or in a list; the selection highlight is the only thing redrawn — other geometry is not recomputed).
  4. Project load / new project.
  5. Window resize.
  Property edits, object creations, and cascading deletes mark the canvas **stale** (shown via a subtle indicator near the Refresh button) but do not redraw until trigger #1 fires.
- **Viewport clipping**: Lines and Rays are infinite in the model but finite on screen. At render time they are clipped to the current canvas viewport (Liang–Barsky or matplotlib's built-in clipping); when the user pans/zooms (trigger #2) they are re-clipped against the new viewport. A Line whose two defining points are both off-canvas still renders if it crosses the viewport.
- **Coordinate Cursor**: Display cursor coordinates in UTM format (easting, northing) as mouse moves over canvas. The cursor read-out updates continuously and is exempt from render-on-demand (it is a text label, not a geometry redraw).

### Object Rendering
- **Point**: Marker/dot at (easting, northing)
- **Line**: Line segment extending through both points to canvas edges
- **Ray**: Line extending from origin through secondary point to canvas edge
- **Polygon**: Filled or outlined shape with all vertices connected
- **Vector**: Arrow from origin to endpoint, length represents magnitude
- **Circle**: Circular outline with center and radius
- **Tangent**: Line perpendicular to circle at point on circumference

### Visual Properties
- **Point** rendered in its assigned `color` (marker color).
- All other objects rendered using `line_color` for stroke/outline and `fill_color` for interior fill. Circle and Polygon use both; 1D objects (Line, Ray, Vector, Tangent) use only `line_color` at render time — `fill_color` is stored in the schema but ignored.
- Each object uses its assigned `alpha` transparency level (applies to both `line_color` and `fill_color`) so overlapping objects can be layered and visually distinguished
- Objects with `visibility = false` are not rendered
- Selected objects highlighted/emphasized on canvas

---

## UI/UX Requirements

### Main Window Layout
- **Window icon**: `GeoSketch.png` (project root), set on the root `Tk` window via `iconphoto()` at startup.
- The app uses a three-column layout:
  - Left panel for object creation, import/export, and calculation tools
  - Center panel for the main visualization canvas
  - Right panel for selected object properties and metadata
- Object creation and calculation tools are grouped as collapsible cards or sections in the left panel.
- Forms open in the center panel or as a modal panel with the same structural layout.

### Shared Form Patterns
- Every object form starts with `Name` on the top row, spanning full width.
- **Point** form: second row contains a single `Color` (marker) picker + alpha slider. All other forms: second row contains `Line color` + `Fill color` pickers; third row contains the alpha slider.
- Mode selection uses radio buttons, not dropdowns.
- Primary actions are aligned consistently at the bottom of each form.
- Forms validate as users type, and inline error messages appear beneath invalid fields.
- The form prevents submission until required fields are valid.

### Object Form Guidelines
- Object edit uses the same add-dialog layout, with form fields prefilled from the selected object.
- Modes are presented as enum-based radio button groups, including:
  - Input mode: `Click` / `Form`
  - Direction mode: `Azimuth` / `Angle`
  - Units mode: `Radians` / `Degrees`

### Vector Form
- Vector creation uses two tabs: `Origin + Endpoint` and `Length + Direction`.
- `Origin + Endpoint` tab includes origin selector, endpoint selector, and read-only computed direction and length.
- `Length + Direction` tab includes origin selector, length field, direction mode radio buttons, units radio buttons, and direction input.

### Polygon Form
- Polygon creation offers two options: `Select Points` or `Enter Vertices`.
- These options are presented as tabs and as a clear mode choice in the polygon form.
- `Select Points` tab allows multi-select of existing points with selection order visible.
- `Enter Vertices` tab shows a dynamic vertex table with a row count spinner and scroll behavior. The tab also exposes the same `Use reference point` checkbox + combobox pair used by the import dialogs; when active, each row's `easting`/`northing` is interpreted as a delta from the selected reference point. The reusable subcomponent is the single source of truth — point text import, polygon file import, and this tab share it.
- Vertex rows include easting, northing, and optional labels.
- Polygon validation checks for minimum vertex count and self-intersection before creation.

### Interaction Behavior
- Clicking an object on the canvas selects it and updates the right panel.
- Selected objects are visually emphasized on the canvas.
- The properties panel reflects the current selection immediately.
- Tabs keep complex workflows discoverable and manageable.

### Accessibility
- Use clear labels and grouped radio button sets.
- Ensure keyboard navigation works across tabs and form inputs.
- Maintain sufficient contrast between left/center/right panels.
- Provide visible focus outlines for interactive controls.

---

## Data Persistence

### Project Save Format (JSON)

**Versioning policy**

- The MVP writes `"version": "1.0"` and accepts only `"1.0"` on load.
- The version field uses semantic-versioning major.minor. The loader rule:
  - **Same major, same-or-lower minor** → load directly.
  - **Same major, higher minor** → load with a warning that newer fields may be ignored. Unknown top-level keys and unknown object `properties` keys are preserved verbatim on re-save so a newer-app file round-trips through an older app without data loss.
  - **Different major** → reject with a clear error; conversion is the responsibility of a future migration tool.
- Files missing the `version` field are rejected.

```json
{
  "version": "1.0",
  "metadata": {
    "created": "2026-05-16T10:30:00Z",
    "lastModified": "2026-05-16T10:45:00Z",
    "title": "My Geometry Project",
    "description": "Project description (optional)"
  },
  "objects": [
    {
      "id": "pt_001",
      "type": "point",
      "name": "Point A",
      "color": "#FF0000",
      "alpha": 1.0,
      "visibility": true,
      "properties": {
        "easting": 123456.789,
        "northing": 4567890.123
      }
    },
    {
      "id": "pt_002",
      "type": "point",
      "name": "Point B",
      "color": "#00FF00",
      "alpha": 1.0,
      "visibility": true,
      "properties": {
        "easting": 123500.000,
        "northing": 4567950.000
      }
    },
    {
      "id": "ln_001",
      "type": "line",
      "name": "Line AB",
      "line_color": "#0000FF",
      "fill_color": "#0000FF",
      "alpha": 1.0,
      "visibility": true,
      "properties": {
        "point_a_id": "pt_001",
        "point_b_id": "pt_002",
        "direction": 0.7854,
        "direction_mode": "azimuth",
        "direction_units": "radians"
      }
    },
    {
      "id": "pg_001",
      "type": "polygon",
      "name": "Triangle ABC",
      "line_color": "#FFFF00",
      "fill_color": "#FFFFCC",
      "alpha": 0.75,
      "visibility": true,
      "properties": {
        "point_ids": ["pt_001", "pt_002", "pt_003"],
        "is_convex": true
      }
    },
    {
      "id": "ry_001",
      "type": "ray",
      "name": "Ray from A",
      "line_color": "#FF00FF",
      "fill_color": "#FF00FF",
      "alpha": 1.0,
      "visibility": true,
      "properties": {
        "origin_id": "pt_001",
        "direction": 1.5708,
        "direction_mode": "azimuth",
        "direction_units": "radians"
      }
    },
    {
      "id": "vc_001",
      "type": "vector",
      "name": "Vector AB",
      "line_color": "#00FFFF",
      "fill_color": "#00FFFF",
      "alpha": 1.0,
      "visibility": true,
      "properties": {
        "origin_id": "pt_001",
        "direction": 0.7854,
        "direction_mode": "azimuth",
        "direction_units": "radians",
        "length": 100.0
      }
    },
    {
      "id": "ci_001",
      "type": "circle",
      "name": "Circle at A",
      "line_color": "#FF6600",
      "fill_color": "#FFD699",
      "alpha": 1.0,
      "visibility": true,
      "properties": {
        "center_id": "pt_001",
        "radius": 50.0
      }
    },
    {
      "id": "tg_001",
      "type": "tangent",
      "name": "Tangent at P",
      "line_color": "#00FF66",
      "fill_color": "#00FF66",
      "alpha": 1.0,
      "visibility": true,
      "properties": {
        "circle_id": "ci_001",
        "point_id": "pt_004",
        "direction": 2.3562,
        "direction_mode": "azimuth",
        "direction_units": "radians"
      }
    }
  ]
}
```

### Polygon Import File Format

**File Format**: Plain text, space-separated values  
**First Line**: Integer count of vertices  
**Subsequent Lines**: Easting Northing pairs (space-separated floats). The file format itself is **order-agnostic** — rows may be in boundary order or unordered. The import dialog requires the user to declare which case applies via the `Vertex ordering` radio buttons (see §Polygon → Creation Methods → File Import).

**Ordering resolution at import time**:
- **Boundary order**: rows are treated as a boundary traversal. Apply signed-area reverse if needed to canonicalize to CCW. This is the only path that supports concave polygons.
- **Sort (centroid + polar angle)**: rows are treated as an unordered point set. Compute the centroid `(Σe / n, Σn / n)`, sort vertices by `atan2(n_i − n_c, e_i − e_c)` ascending, then reverse if needed to canonicalize to CCW. Result is always a simple polygon **only if the input is convex-positioned**; non-convex point sets will produce a different shape than the user may have intended, which is why this mode is opt-in.

Both modes finish by validating: (1) `|signed_area| ≥ EPS_AREA`, (2) simplicity via segment-segment intersection tests on non-adjacent edges, (3) vertex count ≥ 3. Any failure rejects the import with the failing rule named in the error dialog.

**Example**:
```
3
123456.789 4567890.123
123500.000 4567950.000
123450.000 4567920.000
```

**Error Handling**:
- If vertex count < 3: Error (minimum polygon size)
- If polygon is not simple (self-intersecting): Error and import rejected
- If line cannot be parsed as valid floats: Error with line number
- Imported polygon automatically ordered CCW
- Default imported polygon name is derived from the source file name
- Polygon coordinates are extracted from file content using regex-based parsing
- Import may be performed with absolute coordinates or with relative offsets from a selected reference point

### Point Import from Text

**Method**: Regex-based extraction from user-provided text  
**Regex Pattern**: `(\w+)\s+([\d.-]+)\s+([\d.-]+)`  
**Capture Groups**:
- [1] Point name (word characters)
- [2] Northing coordinate (number with optional decimal/negative)
- [3] Easting coordinate (number with optional decimal/negative)

**Relative Point Option**:
- User may choose an existing reference point and specify delta northing/easting offsets instead of absolute coordinates

**Example Text**:
```
PointA 4567890.123 123456.789
PointB 4567950.000 123500.000
PointC 4567920.000 123450.000
```

**Error Handling**:
- If regex extraction fails for a line: Display error with line content
- Invalid floats: Display error message
- Successful points: Create and add to scene

---

## User Workflows

### Workflow 1: Create Basic Geometry
1. User adds 3+ points (via clicks or form)
2. User selects points and creates polygon
3. User checks polygon convexity
4. User saves project to JSON

### Workflow 2: Import and Analyze
1. User imports polygon from file
2. User calculates convex hull
3. User adds test points
4. User calculates distances from points to polygon
5. User saves project

### Workflow 3: Line Intersection Study
1. User creates multiple lines
2. User requests intersection calculations
3. System creates intersection points
4. User visualizes intersection points on canvas
5. User saves project

### Workflow 4: Vector Analysis
1. User creates vectors with specific directions and lengths
2. User creates rays to test intersection with geometric shapes
3. User calculates intersection distances
4. User visualizes results

### Workflow 5: Malformed Import Recovery (failure path)
1. User opens the polygon-import dialog and selects a file.
2. File parsing fails on line 4 (non-numeric token).
3. System aborts the import — **no partial polygon is created** — and shows an error dialog naming the file, the offending line number, and the raw line content.
4. User edits the file externally and retries; the dialog remembers the previously chosen `Use reference point` checkbox state and reference-point selection.
5. On the retry, vertex count is below 3 → the system rejects again with the rule that triggered (`minimum_vertex_count`) and the same dialog stays open.
6. User adjusts the file once more, import succeeds, polygon is added and the canvas is marked stale.

### Workflow 6: Recovering from an Accidental Cascading Delete (failure path)
1. User selects a Point that is referenced by 3 Lines and 1 Polygon and presses Delete.
2. The confirmation dialog enumerates the 5 objects (1 Point + 3 Lines + 1 Polygon) that will be removed.
3. User clicks Cancel — nothing is deleted.
4. (If user had instead confirmed and only then realized the mistake, `Ctrl+Z` restores all 5 objects with their original IDs — the cascade is a single command.)

---

## File Operations

### New Project
- Clear all objects from scene
- Reset to blank state
- Prompt to save if unsaved changes exist

### Open Project
- Display file browser
- Load JSON project file
- Reconstruct all objects in scene
- Display project title in application

### Save Project
- Write current state to JSON file
- Preserve all object properties and IDs
- Update "lastModified" timestamp
- If save location not specified: prompt user for file location

### Export Project
- Write current state to new JSON file (user specifies filename)
- Preserve all data

### Close Project
- Clear scene
- Prompt to save if unsaved changes

---

## Object Interaction Rules

### Deletion
- User can delete any object.
- **Cascading delete** follows the full reference DAG, not just point→dependents. Every object stores the IDs it depends on; deleting object `X` deletes every object whose dependency set contains `X`, recursively. Specifically:
  - Delete a **Point** → deletes every Line / Ray / Vector / Circle that references it, every Polygon whose vertex list contains it, every Tangent whose `point_id` matches, and any intersection-derived Point that has it as a parent.
  - Delete a **Circle** → deletes every Tangent referencing it.
  - Delete a **Line / Polygon** → deletes any intersection-derived Point that was generated from it (if the implementation tags such points with parent IDs).
- The user is shown a **confirmation dialog listing every object that will be removed by the cascade** before deletion proceeds. Cancelling aborts the entire delete.
- Deletion triggers a refresh of the dependent-object list and (if visible) the right-panel properties.

### Modification
- User can modify object properties: name, color, alpha, visibility
- Modifying a point position (easting, northing) updates all dependent objects (direction calculations, distances, etc.)
- Modifying an object opens the same form dialog used to add that object type, with all fields pre-filled using the object's current properties
- Modifying a polygon's point list reorders CCW, validates that the polygon is simple, and updates the convexity flag

### Reference Integrity
- When object is deleted, all references must be cleaned up.
- Cannot create object with references to non-existent objects.
- Load validation: ensure all referenced objects exist before load completes.

### Undo / Redo

Undo/redo is an **MVP-scope feature**, not deferred. Without it, a misclick that cascades through a deeply-referenced point is unrecoverable except by re-opening the last saved file, which is unacceptable for an interactive geometry tool.

**Coverage** — every state-mutating operation is undoable as a single command:
- Create object (any type, any input mode — click, form, file/text import).
- Delete object, **including the full cascade**. Redoing a cascade-delete deletes the same set; undoing it restores every removed object with its original IDs.
- Modify object properties (name, color, alpha, visibility, direction_mode, direction_units, etc.).
- Modify a point's `easting`/`northing`, *including all auto-recomputed dependent values* (line directions, vector endpoints, intersection points). The recomputation is part of the command's forward action; undo reverses the recomputation by restoring the prior snapshot of dependents.
- Modify a polygon's vertex list (add/remove/reorder vertices); undo restores the prior list and the prior cached `is_convex` value.
- Bulk imports (point text import, polygon file import) are recorded as a **single command** so one Undo removes the whole batch.

**Non-coverage** — pure-view operations are not in the history:
- Selection changes.
- Canvas pan / zoom / Refresh.
- Property-panel scroll, dialog open/close.
- Save / Open / New / Close project. Opening a project **clears** the history; the loaded state is the new baseline.

**Implementation contract**:
- Command-pattern, each command stores `do()` and `undo()` closures plus the object state required to reverse the action.
- History is a bounded ring buffer of **100 commands**. Pushing onto a full buffer drops the oldest command (it becomes permanent).
- Doing a new action while the redo stack is non-empty **discards the redo stack** (standard linear history).
- The history is *not* persisted — it lives only for the lifetime of the in-memory scene.

**Keyboard shortcuts** (and matching `Edit` menu items):
- `Ctrl+Z` → Undo
- `Ctrl+Y` and `Ctrl+Shift+Z` → Redo

The cascade-delete **confirmation dialog from §Deletion is still required** even with undo available — undo is a recovery mechanism, not a substitute for showing the user what is about to happen.

### ID Allocation and Collisions
- The application maintains a per-type counter so new IDs are always `<type>_<next>` with `<next>` strictly greater than every existing same-type ID in the scene.
- **Opening a project** (`Open Project`) replaces the scene; loaded IDs are preserved verbatim. The counters are reseeded from the loaded data.
- **Importing into an existing scene** (point text import, polygon file import) never reuses IDs from the import payload, because those formats do not carry IDs — new IDs are minted from the current counters.
- **Merging two project files is out of MVP scope.** If a future merge feature is added, the spec must define a collision policy (renumber-with-mapping is the expected choice); until then, the loader rejects any payload whose ID format violates `<type>_<positive int>` or whose IDs duplicate within the file.

---

## Input Validation Rules

| Input | Validation Rule |
|-------|-----------------|
| Coordinate (easting/northing) | Must be valid float; typically > 0 for UTM |
| Azimuth, `direction_units = radians` | `0 ≤ value < 2π` (with `2π − EPS_ANGLE` accepted as the upper bound) |
| Azimuth, `direction_units = degrees` | `0 ≤ value < 360` |
| Angle, `direction_units = radians` | `0 ≤ value < 2π` |
| Angle, `direction_units = degrees` | `0 ≤ value < 360` |
| Length/Radius | Must be positive float > 0 |
| Color | Valid hex code (#RRGGBB) or RGB tuple |
| Name | Non-empty string, max 100 characters |
| Point selection | Must select valid, existing point |
| Polygon vertex count | Minimum 3 points required |
| Polygon simplicity | Polygon must be simple (no self intersections) |
| Tangent point | Must be on or near circle circumference (within tolerance) |
| Alpha | Must be float between 0.0 and 1.0 |

---

## Success Criteria for MVP

✅ User can create all 7 object types (points, lines, polygons, rays, vectors, circles, tangents)  
✅ User can input objects via clicking, forms, and file imports  
✅ User can visualize all objects on 2D canvas  
✅ All four calculation categories produce correct results: **(1) Direction**, **(2) Convexity & Convex Hull**, **(3) Intersection (line↔line, line↔polygon, ray↔polygon, polygon↔polygon)**, **(4) Distance (point↔point, point↔polygon, ray↔polygon, polygon↔polygon)**  
✅ Data persists correctly via JSON save/load  
✅ Application handles invalid input gracefully  
✅ Coordinate system displays correctly in UTM  
✅ All object properties (name, color, visibility) work as specified  
✅ Relative point coordinates calculated correctly  
✅ Polygon CCW ordering applied automatically  
✅ Convexity calculation correct  
✅ Intersection calculations return correct results  
✅ Distance calculations use proper Euclidean formula  
✅ Polygon-to-polygon distance calculation available and correct  
✅ Undo/redo reverses every mutating operation (create, delete-with-cascade, property edit, point move with auto-recompute, bulk imports), bounded to 100 commands  
✅ Measurement tools available: polygon area (shoelace), polygon perimeter, circle area (πr²), circle circumference (2πr), segment/vector length, unsigned angle between two direction-bearing objects  

---

## Future Enhancements (Out of MVP Scope)

- **Merge / append project files** with collision-aware ID renumbering.
- 3D geometry support
- Real-time collaborative editing
- Constraint-based geometry solver
- Animation and simulation
- Advanced drawing tools (bezier curves, arcs)
- Dimension annotations
- Layer system for object organization
- History/timeline viewer
- Export to CAD formats (DXF, DWG)
- Different rendering backends (OpenGL, WebGL, etc.)

---

## Glossary

| Term | Definition |
|------|-----------|
| **Azimuth** | Compass direction measured clockwise from North (0-2π radians) |
| **UTM** | Universal Transverse Mercator coordinate system in meters |
| **CCW** | Counter-Clockwise vertex ordering for polygons |
| **Convex** | All interior angles < 180°; shape "bulges outward" |
| **Concave** | At least one interior angle > 180°; shape has "indentations" |
| **Euclidean Distance** | Straight-line distance between two points |
| **Tangent** | Line perpendicular to radius at a point on circle circumference |
| **Ray** | Infinite half-line with origin and direction |
| **Convex Hull** | Smallest convex polygon containing all points |
| **Simple Polygon** | Polygon whose edges do not cross each other and share endpoints only with their two neighbours |
| **Graham Scan** | Standard O(n log n) algorithm for computing a convex hull by sorting points by polar angle around an extreme point |
| **direction_mode** | Per-object setting choosing how `direction` is interpreted by the UI: `azimuth` (clockwise from North) or `angle` (CCW from East). Storage is always radians; only display and input change. |
| **Cascading Delete** | Deleting an object automatically removes every other object whose reference chain depends on it, recursively |
| **Shoelace Formula** | Standard O(n) algorithm computing the signed area of a polygon from its vertex coordinates; sign indicates CW vs CCW |
| **Perimeter** | Sum of the edge lengths of a polygon |
| **Circumference** | Perimeter of a circle; `2 · π · r` |

---
