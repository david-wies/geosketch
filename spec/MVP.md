# GeoSketch - MVP Specification

**Version**: 1.0  
**Date**: May 16, 2026  
**Target Platform**: Desktop Application (Python with tkinter + matplotlib)  
**Coordinate System**: UTM (Universal Transverse Mercator) in meters  
**Precision**: NumPy float64 (IEEE 754 double precision)  
**Persistence**: JSON file format  

---

## Executive Summary

GeoSketch is a desktop application that enables users to create, visualize, manipulate, and analyze geometric objects and their spatial relationships. Users construct geometric scenes by adding points, lines, rays, vectors, circles, polygons, balls, cylinders, solids, and tangents, then perform calculations to determine directions, convexity, intersections, and distances between objects.

The application supports multiple input methods (clicking on canvas, form inputs, file imports), real-time visualization, and project persistence via JSON files.

---

## Core Concepts

### Coordinate System
- **System**: Universal Transverse Mercator (UTM)
- **Units**: Meters
- **Notation**: All coordinates expressed as (Easting, Northing) pairs
- **Altitude (Z)**: Every Point has an altitude (Z) value in meters above datum, defaulting to 0.0. Altitude enables the 3D view tab and the Slice view tab. The domain's 2D geometric calculations (direction, area, intersection, distance) always use only (Easting, Northing) and are unaffected by altitude.
- **Azimuth Convention**: Measured clockwise from North, range [0, 2π) radians
- **Angle Convention**: Standard mathematical angles, measured counter-clockwise from East, range [0, 2π) radians or [0°, 360°)

### Precision & Numeric Handling
- The application uses NumPy float64 as the reference precision level for all geometry results, even though not every operation must be implemented with NumPy.
- Calculations may use NumPy, Python math, or other numeric libraries, but outputs must be consistent with NumPy float64 semantics.
- Distance calculations: 3D Euclidean (√[(Δeast)² + (Δnorth)² + (Δaltitude)²])
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
| `EPS_ALTITUDE` | `1e-6` m | slice-plane membership test: `\|aE + bN + cZ − d\| / sqrt(a² + b² + c²) ≤ EPS_ALTITUDE + slab_thickness`. For the three axis-aligned presets the denominator equals 1. For Custom mode the UI must pre-normalize the coefficients so `sqrt(a² + b² + c²) = 1` before constructing `SlicePlane`; otherwise the effective tolerance widens by the normal's magnitude and points further from the plane than intended are silently included. |

Validation that a tangent point lies on its circle uses `|distance(point, center) - radius| < EPS_DISTANCE`. Parallel-line detection uses `|cross(d1, d2)| < EPS_ANGLE`.

### Object Identity
- Each object has a unique ID (string format: "type_NNN")
- IDs are immutable and persist across save/load cycles
- References between objects use ID strings, not memory pointers

| Object type | ID prefix | Example |
|---|---|---|
| Point | `pt` | `pt_001` |
| Line | `ln` | `ln_001` |
| Polygon | `pg` | `pg_001` |
| Ray | `ry` | `ry_001` |
| Vector | `vc` | `vc_001` |
| Circle | `ci` | `ci_001` |
| Ball | `ba` | `ba_001` |
| Cylinder | `cy` | `cy_001` |
| Solid | `so` | `so_001` |
| Tangent | `tg` | `tg_001` |

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
- `altitude`: float (UTM altitude in meters above datum; default 0.0 when absent or null in the JSON file)
- `color`: hex color code (e.g. `#FF0000`)
- `alpha`: float (transparency level, 0.0 to 1.0)
- `visibility`: boolean

**Creation Methods**:
- **Click Mode**: User clicks on canvas; coordinates captured from click location
- **Form Input**: User enters easting, northing, name, color, and optionally altitude (Z) in dialog. Leaving altitude blank defaults to 0.0.
- **Relative Coordinates**: User selects reference point + delta easting/northing; absolute coordinates calculated as: `absolute = reference + delta`
- **Text Import**: User provides text; regex extracts name, northing, easting. The import dialog includes a `Use reference point` checkbox; when checked, a combobox of existing points becomes enabled and the parsed `(northing, easting)` values are interpreted as **deltas** from the selected reference point (absolute = reference + delta). When unchecked, values are absolute UTM coordinates and the combobox is disabled.

**Regex Pattern for Text Import**: `(\w+)\s+([\d.-]+)\s+([\d.-]+)`  
Captures: [1] name, [2] northing, [3] easting

> ⚠️ **Axis-order foot-gun**: the text-import format is `name northing easting`, but the polygon file format and every internal API use `easting northing`. The order is reversed *only* for point text import (it matches a common survey-export convention). Do not "normalize" this without changing the spec.

---

### 2. Line
**Description**: An infinite line through two points in 3D space.

**Properties**:
- `name`: string
- `id`: string
- `type`: "line"
- `point_a_id`: string (reference to Point)
- `point_b_id`: string (reference to Point)
- `direction`: float (stored as radians — horizontal azimuth or angle depending on `direction_mode`)
- `elevation`: float (stored as radians; angle of the line above the horizontal plane, range [-π/2, π/2]; 0 = horizontal; default 0.0)
- `direction_mode`: string ("azimuth" or "angle")
- `direction_units`: string ("radians" or "degrees") — applies to both `direction` and `elevation` display
- `line_color`: hex color code (stroke color)
- `fill_color`: hex color code (stored; not rendered — Line has no interior)
- `alpha`: float (transparency level, 0.0 to 1.0)
- `visibility`: boolean

**Creation Methods**:
- **Click Mode**: User selects 2 distinct points via clicks or dropdown; direction and elevation computed from their 3D coordinates
- **Form Input**: User selects point A and point B from dropdowns

**Automatic Calculations**:
- Direction (azimuth): `atan2(Δeast, Δnorth)`, normalized to [0, 2π)
- Elevation: `atan2(Δaltitude, √(Δeast² + Δnorth²))`, range [-π/2, π/2]

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
**Description**: An infinite half-line in 3D space with an origin point, horizontal direction, and elevation angle.

**Properties**:
- `name`: string
- `id`: string
- `type`: "ray"
- `origin_id`: string (reference to Point)
- `direction`: float (stored as radians — horizontal azimuth or angle depending on `direction_mode`)
- `elevation`: float (stored as radians; angle above the horizontal plane, range [-π/2, π/2]; 0 = horizontal; default 0.0)
- `direction_mode`: string ("azimuth" or "angle")
- `direction_units`: string ("radians" or "degrees") — applies to both `direction` and `elevation`
- `line_color`: hex color code (stroke color)
- `fill_color`: hex color code (stored; not rendered — Ray has no interior)
- `alpha`: float (transparency level, 0.0 to 1.0)
- `visibility`: boolean

**Creation Methods**:
- **Click Mode**: User clicks origin point, then secondary point; direction and elevation computed from origin to secondary point using their 3D coordinates
- **Form Input**: User selects origin point and enters direction (azimuth or angle, radians or degrees) and elevation angle

---

### 5. Vector
**Description**: A directed line segment in 3D space with origin, direction, elevation, and length.

**Properties**:
- `name`: string
- `id`: string
- `type`: "vector"
- `origin_id`: string (reference to Point)
- `direction`: float (stored as radians — horizontal azimuth or angle depending on `direction_mode`)
- `elevation`: float (stored as radians; angle above the horizontal plane, range [-π/2, π/2]; 0 = horizontal; default 0.0)
- `direction_mode`: string ("azimuth" or "angle")
- `direction_units`: string ("radians" or "degrees") — applies to both `direction` and `elevation`
- `length`: float (3D distance in meters, must be > 0)
- `endpoint`: computed as `(origin_e + L·sin(az)·cos(el), origin_n + L·cos(az)·cos(el), origin_z + L·sin(el))` where `az` = azimuth, `el` = elevation, `L` = length
- `endpoint_id`: string or null. Set to a Point ID **only** when the vector was created via the `Origin + Endpoint` tab (or click mode); in that case `length`, `direction`, and `elevation` are derived from the two referenced points' 3D coordinates and are recomputed if either point is edited. Null when created via `Length + Direction` — the endpoint is a pure computed value. Deleting the referenced endpoint Point cascades to delete this vector.
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
- Endpoint 3D: `(origin_e + L·sin(az)·cos(el), origin_n + L·cos(az)·cos(el), origin_z + L·sin(el))`; the `sin(az)/cos(az)` swap is the azimuth convention — do not change
- Horizontal distance (2D projected length): `L·cos(el)`
- Direction and elevation conversion: bidirectional between azimuth/angle and radians/degrees

---

### 6. Circle
**Description**: A 2D flat circle (horizontal disk) with center point and radius. Always rendered in the horizontal plane at the center point's altitude. For a 3D sphere use Ball; for a cylindrical shape use Cylinder.

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

### 7. Ball
**Description**: A 3D sphere defined by a center point and radius. In the 2D flat view it projects as a circle; in the 3D view it renders as a wireframe sphere; in the Slice view the cross-section is a circle whose radius depends on the plane's distance from the center.

**Properties**:
- `name`: string
- `id`: string (format: `ba_NNN`)
- `type`: "ball"
- `center_id`: string (reference to Point; the 3D center of the sphere)
- `radius`: float (distance in meters, must be > 0)
- `line_color`: hex color code (stroke/wireframe color)
- `fill_color`: hex color code (interior fill color)
- `alpha`: float (transparency level, 0.0 to 1.0)
- `visibility`: boolean

**Creation Methods**:
- **Click Mode**: User clicks center point, then secondary point; radius calculated as 3D Euclidean distance from center to secondary point
- **Form Input**: User selects center point and enters radius value

**Rendering**:
- **2D flat**: circle at `(center.easting, center.northing)` with radius `r` (same appearance as Circle)
- **3D**: wireframe sphere at the center's 3D position
- **Slice**: if the cutting plane is within radius of the center, shows the circular cross-section of radius `√(r² − d²)` where `d` is the signed distance from the center to the plane; otherwise not shown

---

### 8. Cylinder
**Description**: A 3D cylinder with a circular cross-section, defined by a base-center point, radius, height, and axis orientation. The axis can be vertical (pointing straight up) or inclined at any azimuth and elevation angle.

**Properties**:
- `name`: string
- `id`: string (format: `cy_NNN`)
- `type`: "cylinder"
- `base_center_id`: string (reference to Point; center of the base circular face)
- `radius`: float (distance in meters, must be > 0)
- `height`: float (length of cylinder along its axis, must be > 0)
- `axis_mode`: string (`"vertical"` or `"inclined"`)
- `axis_azimuth`: float (stored as radians; azimuth of the axis projected onto the EN plane, clockwise from North; ignored when `axis_mode = "vertical"`)
- `axis_elevation`: float (stored as radians; angle of the axis above the horizontal plane; range `(0, π/2]`; π/2 = vertical; must be > 0)
- `direction_mode`: string (`"azimuth"` or `"angle"`) — applies to `axis_azimuth` display
- `direction_units`: string (`"radians"` or `"degrees"`) — applies to both `axis_azimuth` and `axis_elevation` display
- `line_color`: hex color code (stroke color)
- `fill_color`: hex color code (fill color)
- `alpha`: float (transparency level, 0.0 to 1.0)
- `visibility`: boolean

> **Note**: When `axis_mode = "vertical"`, `axis_azimuth` is stored as 0 and `axis_elevation` as π/2 but neither is shown in the form. The rendered cylinder is a right-circular cylinder pointing straight up from the base center.

**Creation Methods**:
- **Form Input**: User selects base center point; enters radius and height; chooses axis mode (`Vertical` / `Inclined`). In Inclined mode: enters azimuth (direction mode + units radios) and elevation angle (same units). No click mode — a cylinder requires multiple numeric parameters that cannot be captured by two canvas clicks.

**Rendering**:
- **2D flat**: base circle at `(base_center.easting, base_center.northing)` with radius `r`; a dashed line indicates the projected axis direction for inclined cylinders
- **3D**: cylinder surface (base circle + top circle + lateral surface) positioned along the axis vector from the base center
- **Slice**: cross-section shape depends on cutting angle relative to axis — a plane perpendicular to the axis gives a circle; oblique planes give an ellipse; a plane parallel to the axis gives a rectangle

---

### 9. Tangent
**Description**: A line that is tangent (perpendicular to the radius) to a Circle or a Ball at a point on its surface.

- **Circle tangent**: the tangent line lies in the horizontal plane of the circle. Its direction is uniquely determined by the point on the circumference — no extra input required.
- **Ball tangent**: the tangent line lies in the plane tangent to the sphere at the given point. Any direction in that plane is valid; the user must supply both azimuth and elevation. Validation requires that the direction vector is perpendicular to the radius vector at that point (dot product < EPS_ANGLE).

**Properties**:
- `name`: string
- `id`: string
- `type`: "tangent"
- `shape_id`: string (reference to a Circle **or** a Ball by ID)
- `shape_type`: string (`"circle"` or `"ball"`) — identifies which type `shape_id` refers to
- `point_id`: string (reference to Point on surface)
- `direction`: float (stored as radians — horizontal azimuth or angle)
- `elevation`: float (stored as radians; angle above horizontal; for Circle tangents always 0.0; for Ball tangents set by user)
- `direction_mode`: string ("azimuth" or "angle")
- `direction_units`: string ("radians" or "degrees") — applies to both `direction` and `elevation`
- `line_color`: hex color code (stroke color)
- `fill_color`: hex color code (stored; not rendered — Tangent has no interior)
- `alpha`: float (transparency level, 0.0 to 1.0)
- `visibility`: boolean

> ⚠️ **JSON migration note**: Files written before this schema change used `circle_id` instead of `shape_id` + `shape_type`. The loader treats a present `circle_id` key as `shape_id = circle_id, shape_type = "circle"` for backward compatibility.

**Creation Methods**:
- **Click Mode**: User clicks a point on a circle's circumference; tangent direction is computed automatically. Click mode is available for Circle only — Ball tangents require an explicit direction and must use Form Input.
- **Form Input**: User selects shape type (Circle / Ball radio), then selects the shape and a Point. For Circle the direction is computed automatically. For Ball the user also enters azimuth and elevation.

**Validation**:
- Circle: `|distance(point, center) − radius| < EPS_DISTANCE`
- Ball: same distance check; additionally `|direction_vector · radius_unit_vector| < EPS_ANGLE` (perpendicularity)

**Automatic Calculations**:
- **Circle tangent direction**: `tangent_azimuth = (radius_azimuth + π/2) mod 2π`, `elevation = 0`. The opposite direction `(tangent_azimuth + π) mod 2π` is geometrically equivalent and may be exposed via a "Flip" action.
- **Ball tangent direction**: user-supplied; validated as perpendicular to radius; Flip action available.

---

### 10. Solid
**Description**: A general 3D solid defined by an ordered stack of cross-section **layers**. Each layer is either a Polygon (a cross-section at some altitude) or a single Point (a pyramid apex/nadir). The solid's surface is the closed shell formed by connecting adjacent layers. This covers boxes (two rectangles), pyramids (polygon + apex point), frustums (two differently-sized polygons), lofted blades (any sequence of polygons), and more.

**Properties**:
- `name`: string
- `id`: string (format: `so_NNN`)
- `type`: "solid"
- `layers`: list of strings — ordered references to existing **Polygon** or **Point** IDs, bottom to top. At least 2 entries. At most one entry may be a Point ID (the apex/nadir); it must be the first or last element.
- `line_color`: hex color code (stroke/edge color)
- `fill_color`: hex color code (face fill color)
- `alpha`: float (transparency level, 0.0 to 1.0)
- `visibility`: boolean

**Layer rules**:
- Adjacent Polygon layers should have the same vertex count so that corresponding vertices can be connected into quadrilateral lateral faces. If vertex counts differ, the solid uses triangulated fan faces between the layers (with a warning shown on creation).
- A Point layer produces a triangulated fan from that apex point to all edges of the adjacent polygon.
- Polygons do not need to be horizontally flat — each polygon's vertices carry their own 3D altitudes via the Point model. The layer order is the user's declared bottom-to-top sequence, not derived from altitude.

**Cascade note**: Deleting any Polygon or Point that appears in a Solid's `layers` list cascades to delete the Solid.

**Creation Methods**:
- **Form Input**: User builds an ordered list of layers. Each row in the list specifies a shape type (`Polygon` / `Point`) and selects an existing object from a combobox. Rows can be reordered and added/removed. No click mode.

> **Shape examples:**
> - **Box**: two rectangular Polygons at different altitudes
> - **Pyramid**: one base Polygon + one apex Point
> - **Frustum**: two similar Polygons of different sizes
> - **Loft**: three or more Polygons whose vertex positions change between layers
> - **Wedge**: a triangle polygon + a line segment — use a degenerate 2-vertex "polygon" if needed, or place two vertices of the top layer at the same point

**Rendering**:
- **2D flat**: outline of the bottom-layer polygon projected to (E, N)
- **3D**: wireframe shell — each polygon layer drawn, plus lateral edges connecting corresponding vertices of adjacent layers
- **Slice**: the plane intersects each lateral face (a triangle or quad); collect all intersection line segments and render as a 2D polygon cross-section

**Mass properties** (auto-shown in right panel when a Solid is selected):
- **Volume**: exact, computed by [Mirtich (1996)](https://www.cs.uaf.edu/2015/spring/cs482/lecture/02_20_boundary/Fast%20and%20accurate%20computation%20of%20polyhedral%20mass%20properties.pdf) algorithm — the layer stack is converted to a closed B-rep (base face + top face + lateral triangulated faces) and the single O(n) traversal runs over all faces
- **Centroid**: `(Tx/V, Ty/V, Tz/V)` from the same Mirtich pass; displayed as `(E, N, Z)` in meters. Cross-check: [Wuttke (2021)](https://journals.iucr.org/j/issues/2021/02/00/vg5135/vg5135.pdf) Eq. 22 — Vol = ⅓ Σₖ Ar(Γₖ)·r_⊥ₖ
- **Lateral Surface Area**: sum of all lateral face areas (triangles and quads between layers)
- **Total Surface Area**: lateral area + area of any polygon cap faces (first and last layers if they are polygons)

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

### Convex Hull Calculation — 2D
**Input**: Polygon object  
**Output**: New Polygon object (named `"[original_name]_convex_hull"`)  
**Method**: `scipy.spatial.ConvexHull` — the QHull implementation of the [Quickhull algorithm (Barber, Dobkin & Huhdanpaa 1996)](https://doi.org/10.1145/235815.235821). Returns vertex indices into the original point array; hull polygon reuses existing Point IDs without creating new points. O(n log r) for n input points, r hull vertices.  
**Description**: Creates the smallest convex polygon containing all vertices of the input polygon. Operates on `(easting, northing)` only — altitude is ignored.

### Convex Hull Calculation — 3D
**Input**: Solid object (uses all 3D vertex positions across all layers) OR a user-selected set of 3 or more Points with non-trivial altitude variation  
**Output**: New Solid object (named `"[original_name]_convex_hull_3d"`) whose faces are the triangulated facets of the convex hull  
**Method**: `scipy.spatial.ConvexHull` in 3D — the same QHull/Quickhull algorithm ([Barber et al. 1996](https://doi.org/10.1145/235815.235821)) applied to `(easting, northing, altitude)` coordinates. Returns triangular facets and vertex indices. The output Solid stores these hull facets as triangulated layers. O(n log r) expected complexity.  
**GPU note**: For very large point sets (millions of points) the CudaHull parallel algorithm ([Stein, Geva & El-Sana 2012](https://doi.org/10.1016/j.cag.2012.02.012)) achieves 30–40× speedup over CPU QHull. GeoSketch uses CPU QHull (via scipy) at typical scene sizes; CudaHull is noted for future large-scale applications.  
**Description**: Creates the smallest convex polyhedron containing all 3D vertices of the input. The output hull reuses existing Point IDs where possible. If all input points are coplanar the result degenerates to a flat polygon and the 2D hull is returned instead.

### Convex Skull Calculation (Potato Peeling) — 2D only
**Scope**: Applies to **2D polygons** (planar point sets in (E, N)) only. See Future Enhancements for the 3D case.

**Input**: Polygon object  
**Output**: New Polygon object (named `"[original_name]_skull"`)  
**Method**: Maximum inscribed convex polygon — also known as the *potato peeling problem* ([Goodman 1981](https://doi.org/10.1007/BF00183192)). [Chang and Yap (1986)](https://doi.org/10.1007/BF02187692) gave the best known exact algorithm in **O(n^7)** time; no better general bound is known (as of 2004 this remained an open question). Skull vertices are unconstrained: they may lie anywhere on the input boundary or interior, not only at the input's vertices. Implementation strategy: for convex polygons (detected via `is_convex`) return the polygon itself immediately. For concave polygons with small vertex counts (≤ 12) consider the O(n^7) exact algorithm; for larger polygons use a documented approximation (e.g. iterative half-plane refinement or vertex-subset DP) with a note in the result dialog that the answer is approximate.  
**Description**: Computes the **convex skull** of the polygon: the largest-area convex polygon that lies entirely inside the input polygon. Contrasted with convex hull (smallest convex polygon *containing* the input), the convex skull is the largest convex polygon *contained within* the input. The exact solution is O(n^7) and practical only for small polygons; the implementation transparently flags whether the result is exact or approximate.

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
**Formula**: `distance = √[(Δeast)² + (Δnorth)² + (Δaltitude)²]`  
**Description**: 3D Euclidean distance between two points. Matches the `length` property of a Vector defined by the same two points. When altitude is 0.0 for both points the result equals the 2D formula.

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

### Polygon Prism Volume
**Input**: Polygon object + height (meters, positive float)  
**Output**: Float (cubic meters)  
**Formula**: `volume = area · height`  
**Description**: Volume of the vertical prism formed by extruding the polygon by the given height. "Area" is the 2D shoelace area computed from (Easting, Northing). Height is a user-supplied scalar (e.g. the elevation extent of the formation). This measurement does **not** require altitude to be set on the polygon's points — the height is entered independently.

### Circle Cylinder Volume
**Input**: Circle object + height (meters, positive float)  
**Output**: Float (cubic meters)  
**Formula**: `volume = π · r² · height`  
**Description**: Volume of the vertical cylinder formed by extruding the circle by the given height. Height is a user-supplied scalar. Same independence from altitude as Polygon Prism Volume.

### Ball Volume
**Input**: Ball object  
**Output**: Float (cubic meters)  
**Formula**: `volume = (4/3) · π · r³`  
**Description**: Volume of the sphere.

### Ball Surface Area
**Input**: Ball object  
**Output**: Float (square meters)  
**Formula**: `surface_area = 4 · π · r²`  
**Description**: Total surface area of the sphere.

### Cylinder Volume
**Input**: Cylinder object  
**Output**: Float (cubic meters)  
**Formula**: `volume = π · r² · height`  
**Description**: Volume of the cylinder (height is the stored axis length, not a user-supplied value).

### Cylinder Lateral Surface Area
**Input**: Cylinder object  
**Output**: Float (square meters)  
**Formula**: `lateral_area = 2 · π · r · height`  
**Description**: Area of the curved lateral surface only (excluding the two circular base faces).

### Cylinder Total Surface Area
**Input**: Cylinder object  
**Output**: Float (square meters)  
**Formula**: `total_area = 2 · π · r · height + 2 · π · r²`  
**Description**: Total surface area including both circular base faces.

### Solid Volume
**Input**: Solid object  
**Output**: Float (cubic meters)  
**Algorithm**: **[Mirtich (1996)](https://www.cs.uaf.edu/2015/spring/cs482/lecture/02_20_boundary/Fast%20and%20accurate%20computation%20of%20polyhedral%20mass%20properties.pdf)** — "Fast and Accurate Computation of Polyhedral Mass Properties". The prism is treated as a closed polyhedron (base face + top face + lateral faces). Volume integrals are reduced via the divergence theorem to surface integrals, then to line integrals via Green's theorem. The projection axis per face is chosen adaptively for numerical accuracy. This handles inclined prisms exactly; `base_area × height` is only valid for vertical prisms.

**Cross-check formula** ([Wuttke 2021](https://journals.iucr.org/j/issues/2021/02/00/vg5135/vg5135.pdf), Eq. 22): Vol = ⅓ Σₖ Ar(Γₖ)·r_⊥ₖ where r_⊥ₖ is the signed distance from the coordinate origin to face k. This coordinate-free formula (from the divergence theorem) can serve as a fast cross-check. For a vertical prism it reduces to `base_area × height`.

**Uniform-layer simplification** ([Wuttke 2021](https://journals.iucr.org/j/issues/2021/02/00/vg5135/vg5135.pdf), §3.5): For a two-layer solid where both layers are congruent and parallel (the classic prism case), the form factor separates as F(**q**, Π) = h·sinc(q_⊥·h/2)·f(**q**_∥, Γ). For general multi-layer solids the full polyhedral algorithm is required. This separability is a useful property if scattering analysis is ever added.

**Description**: Exact volume for any solid layer configuration. Auto-shown in right panel.

### Solid Centroid (Center of Mass)
**Input**: Solid object (assumed uniform density)  
**Output**: `(easting, northing, altitude)` triple — the centroid of the prism volume  
**Algorithm**: [Mirtich (1996)](https://www.cs.uaf.edu/2015/spring/cs482/lecture/02_20_boundary/Fast%20and%20accurate%20computation%20of%20polyhedral%20mass%20properties.pdf) — the same single pass that computes volume also computes the three first-moment integrals `(Tx, Ty, Tz)`. Centroid = `(Tx/V, Ty/V, Tz/V)`.  
**Description**: The 3D centroid of the solid. For a simple vertical solid with uniform layers, this approximates the midpoint between layers. For general multi-layer solids the Mirtich pass computes it exactly. Auto-shown in right panel.

### Solid Lateral Surface Area
**Input**: Solid object  
**Output**: Float (square meters)  
**Formula**: Sum of all lateral face areas. Each lateral face is a triangle (fan from apex) or a quadrilateral (corresponding edges of adjacent polygon layers); area computed via cross product.  
**Description**: Area of all lateral faces, excluding any polygon cap faces (first/last layers). Auto-shown in right panel.

### Solid Total Surface Area
**Input**: Solid object  
**Output**: Float (square meters)  
**Formula**: lateral area + area of any polygon cap faces (first layer if it is a polygon + last layer if it is a polygon)  
**Description**: All faces of the closed shell. Auto-shown in right panel.

### Segment / Vector Length
**Input**: Vector object **or** two Points  
**Output**: Float (meters)  
**Formula**: 3D Euclidean — `√[(Δe)² + (Δn)² + (Δz)²]`  
**Description**: For a Vector this is exactly its `length` property (no recomputation needed); for two selected Points it is the same as `Distance(Point ↔ Point)`. Surfaced as a measurement so the user has a single discoverable entry point.

### Angle Between Directions
**Input**: Two direction-bearing objects (any combination of Line, Ray, Vector, Tangent)  
**Output**: Float, displayed in both radians and degrees, range `[0, π/2]` (unsigned angle between the lines they define)  
**Formula**: `θ = arccos(|cos(d₁ − d₂)|)` where `d₁`, `d₂` are the stored radian directions. Using the absolute value collapses the 180°-supplementary pair so a line and its 180°-flipped twin measure as 0, not π.  
**Description**: The unsigned acute/obtuse angle between two oriented objects, treating each as the infinite line it lies on. Parallel directions return 0; perpendicular returns π/2. Both `direction_mode` settings are normalized to radians before comparison, so the result is convention-independent.

### Angle at Vertex (Three-Point Azimuth & Elevation)
**Input**: Three Point objects in fixed order — A, B, C. The vertex is B; the two arms are the segments B→A and B→C.  
**Output**: Azimuth (float, radians normalized to `[0, 2π)`) **and** Elevation (float, radians, range `[−π, π]`), each displayed in the user's selected direction units (radians/degrees).  
**Formulas**:  
- **Azimuth** — the directed horizontal turn from arm BA to arm BC, *altitude ignored* (computed in the (Easting, Northing) plane):  
  `az_BA = atan2(A.easting − B.easting, A.northing − B.northing)`  
  `az_BC = atan2(C.easting − B.easting, C.northing − B.northing)`  
  `azimuth = normalize_2pi(az_BC − az_BA)`  
- **Elevation** — the difference between the two arms' elevation angles:  
  `el_BA = atan2(A.altitude − B.altitude, √((A.easting − B.easting)² + (A.northing − B.northing)²))`  
  `el_BC = atan2(C.altitude − B.altitude, √((C.easting − B.easting)² + (C.northing − B.northing)²))`  
  `elevation = el_BC − el_BA`  
**Order matters**: the triple is ordered — `ABC ≠ CBA`. Reversing to `C, B, A` yields the explementary azimuth (`2π − azimuth`) and the negated elevation (`−elevation`).  
**Degenerate cases**: if either arm has zero 3D length (A coincides with B, or C coincides with B — distance `< EPS_DISTANCE`) the measurement is rejected. The azimuth term is undefined for a purely vertical arm (horizontal length `< EPS_DISTANCE`) and is reported as `undefined` while the elevation difference remains valid.  
**Description**: Measures the angle subtended at B by the arms to A and C — the horizontal opening between them (altitude ignored) plus the vertical tilt difference between the two arms. Unlike *Angle Between Directions* (which compares two existing direction-bearing objects and returns a single unsigned angle), this takes three freely chosen points and returns a signed, order-dependent azimuth/elevation pair.

### Measurement UI
- Measurements are invoked from a `Measurements` collapsible card in the left panel, alongside the existing creation/calculation cards.
- Each measurement opens a small dialog with object pickers matching its input signature. The dialog has a `Compute` button; results render in the dialog and persist in the right panel under a `Last measurement` field until cleared or a new measurement is taken.
- Polygon Area and Polygon Perimeter are *also* shown automatically in the right-panel properties whenever a Polygon is selected — these are cheap and free of ambiguity.
- Circle Area and Circle Circumference are likewise shown automatically in the right-panel properties whenever a Circle is selected.
- Polygon Prism Volume and Circle Cylinder Volume appear in the Measurements card but are **not** auto-shown in the right panel (they require a user-supplied height).
- Ball Volume and Ball Surface Area are auto-shown in the right panel whenever a Ball is selected.
- Cylinder Volume, Cylinder Lateral Surface Area, and Cylinder Total Surface Area are auto-shown in the right panel whenever a Cylinder is selected (height is already stored on the object).
- Solid Volume, Solid Centroid, Solid Lateral Surface Area, and Solid Total Surface Area are auto-shown in the right panel whenever a Solid is selected.
- Angle at Vertex (Three-Point Azimuth & Elevation) is invoked from the Measurements card with three ordered Point pickers (A = first arm, B = vertex, C = second arm); it is never auto-shown in the right panel because it requires a user-chosen ordered triple. The dialog notes that order is significant (`A-B-C ≠ C-B-A`).

---

## Visualization

### Canvas Display

#### Three-tab canvas

The center panel hosts three independent view tabs. Only the active tab renders; inactive tabs are marked stale and redraw when the user switches to them. Each tab owns its own matplotlib `Figure`, `FigureCanvasTkAgg`, and `NavigationToolbar`.

- **Tab 1 — 2D (flat)**: Cartesian 2D axes with UTM Easting × Northing grid. Altitude is ignored; all objects are rendered using only `(easting, northing)`. This is the primary working view and the default tab on project open.
- **Tab 2 — 3D**: Full 3D axes (Easting × Northing × Altitude). Points with no altitude set render at Z = 0 (altitude defaults to 0). Lines, Rays, Vectors, and Polygon edges connect their constituent Point altitudes in 3D. Circles and Tangents render as horizontal disks/lines at their center Point's altitude. The 3D tab does not support blitting — selection changes trigger full redraws (`mpl_toolkits.mplot3d.Axes3D` does not implement `copy_from_bbox`). Default view angle: elevation 30°, azimuth 225°; the user may rotate freely.
- **Tab 3 — Slice**: 2D cross-section through the scene defined by a user-chosen cutting plane. The plane is specified as a linear equation over any two of the three coordinates (Easting, Northing, Altitude): for example `Z = c` (horizontal slice), `E = c` (north-south vertical slice), `N = c` (east-west vertical slice), or the general form `aE + bN + cZ = d`. The in-plane view is a 2D projection onto the cutting plane's local axes. A control strip above the canvas exposes plane mode (preset or custom coefficients), the offset value, and an optional slab thickness (default 0) that widens the inclusion zone to ±thickness metres around the plane. Only objects that intersect the plane within the slab are shown. The slice plane is ephemeral UI state — it is never saved to the project file and resets to `Z = 0` on project open.

#### Render on Demand

The canvas does *not* redraw on every model mutation. Each tab tracks its own stale state. A redraw is triggered by exactly these events:

1. User clicks the explicit `Refresh` / `Redraw` button (refreshes the active tab only).
2. User pans or zooms the canvas (matplotlib navigation toolbar action — active tab only).
3. Selection changes (active tab only; for the 2D and Slice tabs, the selection highlight is blitted without a full redraw; the 3D tab triggers a full redraw).
4. Project load / new project (all three tabs marked stale; active tab redraws immediately).
5. Window resize (active tab redraws).
6. User clicks **Apply** in the Slice tab's control strip (Slice tab only).
7. User switches to a tab that is stale (that tab redraws on activation).

Property edits, object creations, and cascading deletes mark **all three tabs** stale (shown via a subtle indicator near the Refresh button) but do not redraw until one of the above triggers fires.

#### Viewport clipping

Lines and Rays are infinite in the model but finite on screen. In the 2D and Slice tabs they are clipped to the current canvas viewport at render time; when the user pans/zooms they are re-clipped against the new viewport. In the 3D tab, matplotlib's native 3D clipping handles this.

#### Coordinate Cursor

Displays cursor coordinates in UTM format as the mouse moves over the active canvas. In the 2D and Slice tabs: `E, N`. In the 3D tab: `E, N, Z` (reads the Z of the last clicked 3D artist or the scene floor). The read-out updates continuously and is exempt from render-on-demand.

### Object Rendering
- **Point**: Marker/dot at (easting, northing)
- **Line**: Line segment extending through both points to canvas edges
- **Ray**: Line extending from origin through secondary point to canvas edge
- **Polygon**: Filled or outlined shape with all vertices connected
- **Vector**: Arrow from origin to endpoint, length represents magnitude
- **Circle**: Circular outline with center and radius (always horizontal)
- **Ball**: Circle in 2D flat view; wireframe sphere in 3D; circular cross-section in Slice (if plane intersects)
- **Cylinder**: Base circle in 2D flat view; 3D cylinder surface in 3D; circle/ellipse/rectangle cross-section in Slice
- **Solid**: Bottom-layer polygon outline in 2D flat; wireframe shell (all layers + lateral edges) in 3D; polygon cross-section of lateral face intersections in Slice
- **Tangent**: Line perpendicular to circle at point on circumference

### Visual Properties
- **Point** rendered in its assigned `color` (marker color).
- All other objects rendered using `line_color` for stroke/outline and `fill_color` for interior fill. Circle, Ball, Cylinder, Polygon, and Solid use both; 1D objects (Line, Ray, Vector, Tangent) use only `line_color` at render time — `fill_color` is stored in the schema but ignored.
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

- The current schema version is `"1.1"`. This version added Ball, Cylinder, and Solid object types and changed the Tangent schema from `circle_id` to `shape_id` + `shape_type`.
- The version field uses semantic-versioning major.minor. The loader rule:
  - **Same major, same-or-lower minor** → load directly.
  - **Same major, higher minor** → load with a warning that newer fields may be ignored. Unknown top-level keys and unknown object `properties` keys are preserved verbatim on re-save so a newer-app file round-trips through an older app without data loss.
  - **Different major** → reject with a clear error; conversion is the responsibility of a future migration tool.
- Files missing the `version` field are rejected.
- **Unknown object `type` values** (e.g. a type added in a future version) are preserved verbatim in the objects list on re-save and a warning is shown, but they are not rendered or available for selection — the loader treats them as opaque blobs.

```json
{
  "version": "1.1",
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
        "northing": 4567890.123,
        "altitude": 150.0
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
        "elevation": 0.0,
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
        "elevation": 0.0,
        "direction_mode": "azimuth",
        "direction_units": "radians",
        "length": 100.0,
        "endpoint_id": null
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
        "shape_id": "ci_001",
        "shape_type": "circle",
        "point_id": "pt_004",
        "direction": 2.3562,
        "elevation": 0.0,
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
  - Delete a **Point** → deletes every Line / Ray / Vector / Circle / Ball / Cylinder that references it, every Polygon whose vertex list contains it (which in turn cascades to any Solid referencing that Polygon), every Tangent whose `point_id` matches, and any intersection-derived Point that has it as a parent.
  - Delete a **Circle** → deletes every Tangent referencing it.
  - Delete a **Ball** → cascades to delete every Tangent whose `shape_id` references it (same rule as Circle). After cascade, delete is immediate after confirmation.
  - Delete a **Cylinder** → no dependents; delete is immediate after confirmation.
  - Delete a **Polygon** → deletes every Solid whose `layers` list references it.
  - Delete a **Solid** → no dependents; delete is immediate.
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
| Altitude (Z) | Must be a finite float (no NaN, no ±Infinity); blank or absent defaults to 0.0 |
| Height (volume measurements) | Must be a positive finite float > 0 |
| Azimuth, `direction_units = radians` | `0 ≤ value < 2π` (with `2π − EPS_ANGLE` accepted as the upper bound) |
| Azimuth, `direction_units = degrees` | `0 ≤ value < 360` |
| Angle, `direction_units = radians` | `0 ≤ value < 2π` |
| Angle, `direction_units = degrees` | `0 ≤ value < 360` |
| Length/Radius/Height | Must be positive float > 0 |
| Axis elevation (Cylinder) | Must be in range `(0, π/2]` radians (or `(0°, 90°]`); 0 is rejected (degenerate flat disk) |
| Color | Valid hex code (`#RRGGBB`) |
| Name | Non-empty string, max 100 characters |
| Point selection | Must select valid, existing point |
| Polygon vertex count | Minimum 3 points required |
| Polygon simplicity | Polygon must be simple (no self intersections) |
| Tangent point | Must be on or near circle circumference (within tolerance) |
| Alpha | Must be float between 0.0 and 1.0 |

---

## Success Criteria for MVP

✅ User can create all 10 object types (points, lines, polygons, rays, vectors, circles, balls, cylinders, solids, tangents)  
✅ User can input objects via clicking, forms, and file imports  
✅ User can visualize all objects across three canvas tabs: 2D flat (altitude ignored), 3D (altitude-aware), and Slice (cross-section at a user-chosen cutting plane)  
✅ All calculation categories produce correct results: **(1) Direction**, **(2) Convexity, 2D Convex Hull (polygon→polygon), 3D Convex Hull (solid/points→solid), Convex Skull 2D (potato peeling, polygon only)**, **(3) Intersection (line↔line, line↔polygon, ray↔polygon, polygon↔polygon)**, **(4) Distance (point↔point, point↔polygon, ray↔polygon, polygon↔polygon)**  
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
✅ Measurement tools available: polygon area, polygon perimeter, circle area/circumference, polygon prism volume (area × h), circle cylinder volume (πr²h), ball volume (4/3πr³), ball surface area (4πr²), cylinder volume/lateral/total surface area, solid volume/centroid/lateral/total surface area (Mirtich 1996), segment/vector length, unsigned angle between direction-bearing objects  

---

## Future Enhancements (Out of MVP Scope)

- **Merge / append project files** with collision-aware ID renumbering.
- **3D Convex Skull** (potato peeling in 3D): largest convex polyhedron inscribed in a Solid. The 3D version is a harder open problem than the 2D case; approximate algorithms to be referenced in a future update.
- **Form factor computation** for Solid, Ball, and Cylinder (Fourier transform of the shape's indicator function, useful for small-angle X-ray/neutron scattering analysis). The numerically stable algorithm is described in [Wuttke (2021)](https://journals.iucr.org/j/issues/2021/02/00/vg5135/vg5135.pdf) "Numerically stable form factor of any polygon and polyhedron", J. Appl. Cryst. 54, 580–587.
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
| **Ball** | 3D sphere defined by center Point and radius |
| **Cylinder** | 3D cylinder defined by base center Point, radius, height, and axis orientation (vertical or inclined) |
| **Solid** | General 3D solid defined by an ordered stack of Polygon/Point layers; the surface is the closed shell connecting adjacent layers |
| **Layer** | One cross-section in a Solid — either a Polygon or a single Point (apex/nadir) |
| **Axis elevation** | Angle of an axis above the horizontal plane; 0 = horizontal (degenerate for Cylinder, rejected), π/2 = vertical |
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
