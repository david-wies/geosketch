# GeoSketch — Implementation Design Document

**Version**: 2.0
**Date**: 2026-06-01
**Author**: Architecture pass for the 10-type, 3D-capable spec

---

## Preamble

This document supersedes and refines `docs/geo-sketch-design.md`. It is reconciled with the current `spec/MVP.md` (v1.1, which added Ball, Cylinder, Solid, altitude on Point, elevation on Line/Ray/Vector, and the `shape_id`+`shape_type` Tangent binding) and with `spec/design/geometry-app-ui-ux.md` (v1.1, 2026-05-31).

The existing GitHub issue backlog (#12–#44) was written against the old **7-type, 2D-only** model. Every open issue that touches models, services, persistence, or UI must be re-scoped against this document. The most material delta is:

- Issues #10, #13, #17, #26–#34, #37–#39 assumed 7 types. They now cover **10 types**: Point, Line, Polygon, Ray, Vector, Circle, Ball, Cylinder, Solid, Tangent.
- `distance()` (#13) was 2D; it is now 3D.
- `vector_endpoint()` (#13) was 2D; it now carries elevation.
- `Tangent.circle_id` becomes `Tangent.shape_id` + `Tangent.shape_type` — touching models (#10), serializer (#17), dep-graph (#15), and validation (#16). The project is pre-release, so this is a clean replacement: `circle_id` is removed outright, with no compatibility path.
- Three new model files must be created: `ball.py`, `cylinder.py`, `solid.py`.
- Two new service files must be created: `services/slice.py`, `models/slice_plane.py`.
- `ui/canvas_tabs.py` and `ui/slice_controls.py` are net-new.

---

## 1. Tolerance Constants

File: `geometry/utils/constants.py`

All floating-point comparisons use named constants from this module. No service or model file may use a bare numeric literal for a tolerance.

| Constant | Value | Unit | Use |
|---|---|---|---|
| `EPS_DISTANCE` | `1e-6` | m | Point-on-circle, segment-coincident, polygon-touch |
| `EPS_ANGLE` | `1e-9` | rad | Parallelism (cross-product zero test), convexity |
| `EPS_AREA` | `1e-9` | m² | Signed-area sign check, polygon degeneracy |
| `EPS_VOLUME` | `1e-9` | m³ | Solid/Ball/Cylinder degeneracy: `|volume| < EPS_VOLUME` rejects (3D analog of `EPS_AREA`) |
| `EPS_PARAM` | `1e-9` | dimensionless | Parametric `t` clipping on segment intersection |
| `EPS_ALTITUDE` | `1e-6` | m | Slice-plane membership: `|aE+bN+cZ−d| ≤ EPS_ALTITUDE + slab_thickness` when normal is unit-length |

**Delta from current**: `EPS_ALTITUDE` and `EPS_VOLUME` are both new. Add them to `__all__`. The four existing constants are correct.

`EPS_VOLUME` is the 3D counterpart of `EPS_AREA`: just as a polygon with `|signed_area| < EPS_AREA` is degenerate (zero extent in 2D), a Solid/Ball/Cylinder with `|volume| < EPS_VOLUME` is degenerate (zero extent in 3D — e.g. a coplanar-layer Solid, a zero-radius Ball, or a zero-height/zero-radius Cylinder). It is the floor for the "is this volume effectively zero?" test that the coplanar-hull fallback and the volume measurements rely on; without it those paths would have to compare against a bare `0.0` or an inline literal, which the no-bare-literals rule forbids.

---

## 2. Object Identity & ID Prefixes

The `IDFactory` in `geometry/utils/id_factory.py` is correct as-is. The full prefix table:

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

No changes to `IDFactory` itself. The serializer must call `reseed()` with all loaded IDs, including the three new prefixes.

---

## 3. Models Package (`geometry/models/`)

### 3.1 Ten-type model matrix

| Type | Base class | Key type-specific fields | `type` literal | Has `fill_color` rendered |
|---|---|---|---|---|
| Point | `GeoObject` | `easting`, `northing`, `altitude`, `color` | `"point"` | N/A (single `color`) |
| Line | `ElevatedObject` | `point_a_id`, `point_b_id`, `line_color`, `fill_color` | `"line"` | No |
| Polygon | `GeoObject` | `point_ids`, `is_convex`, `line_color`, `fill_color` | `"polygon"` | Yes |
| Ray | `ElevatedObject` | `origin_id`, `line_color`, `fill_color` | `"ray"` | No |
| Vector | `ElevatedObject` | `origin_id`, `length`, `endpoint_id`, `line_color`, `fill_color` | `"vector"` | No |
| Circle | `GeoObject` | `center_id`, `radius`, `line_color`, `fill_color` | `"circle"` | Yes |
| Ball | `GeoObject` | `center_id`, `radius`, `line_color`, `fill_color` | `"ball"` | Yes |
| Cylinder | `GeoObject` | `base_center_id`, `radius`, `height`, `axis_mode`, `axis_azimuth`, `axis_elevation`, `direction_mode`, `direction_units`, `line_color`, `fill_color` | `"cylinder"` | Yes |
| Solid | `GeoObject` | `layers`, `line_color`, `fill_color` | `"solid"` | Yes |
| Tangent | `ElevatedObject` | `shape_id`, `shape_type`, `point_id`, `line_color`, `fill_color` | `"tangent"` | No |

### 3.2 `geometry/models/common.py`

**Δ from current**: rename `DirectedObject` → `ElevatedObject` and give it an `elevation` field. The project is pre-release, so this is a hard rename with **no alias** — every reference (`models/__init__.py`, `line.py`, `ray.py`, `vector.py`, `tangent.py`, `services/geometry.py`) moves to the new name in the same change and `DirectedObject` disappears entirely.

Rationale: the spec gives Line, Ray, Vector, **and** Tangent an `elevation: float` in `[-π/2, π/2]` (Tangent needs it for Ball tangents). Those four are exactly the current subclasses of the shared direction-bearing base, so `elevation` belongs on that base — a rename plus one field, not a class split. `Cylinder` is deliberately **not** an `ElevatedObject`: it stores `axis_azimuth`/`axis_elevation` as its own named geometry parameters rather than the generic `direction`/`elevation` of a directed line. Ball and Circle have no direction at all.

`elevation` is a **required, defaultless** field, matching the existing convention in which every concrete model receives all of its envelope and geometry fields explicitly (the only defaulted field on any model is the `init=False` `type` literal). It sits next to `direction` so the two angles stay together; because no field after it carries a default, dataclass field-ordering is satisfied with no special handling. The "default 0.0" for a horizontal object lives at the boundaries — the UI form pre-fills `0.0` and the loader injects `0.0` when JSON omits it (§7) — not in the dataclass.

```python
@dataclass
class ElevatedObject(GeoObject):
    """Abstract base for direction-bearing objects that also carry a vertical angle.

    Fields
    ------
    direction : float
        Horizontal bearing in radians (internal storage).
    elevation : float
        Angle above the horizontal plane in radians, range [-π/2, π/2];
        0.0 = horizontal. Required at construction (forms/loader supply 0.0).
    direction_mode : DirectionMode
    direction_units : DirectionUnits
        Applies to both ``direction`` and ``elevation`` display.
    """
    direction: float
    elevation: float
    direction_mode: DirectionMode
    direction_units: DirectionUnits

    def __post_init__(self) -> None:
        super().__post_init__()
        if type(self) is ElevatedObject:
            raise TypeError(
                "ElevatedObject is abstract; use Line, Ray, Vector, or Tangent."
            )
```

The `GeoObject.__post_init__` guard message must be updated to reference the 10 concrete types.

### 3.3 `geometry/models/point.py`

**Δ from current**: add a required `altitude: float` field (no constructor default, matching every other model field).

```python
@dataclass
class Point(GeoObject):
    easting: float
    northing: float
    altitude: float
    color: str
    type: str = field(init=False, default="point")
```

Field order follows the spec (`easting`, `northing`, `altitude`, `color`). All four are required; the only defaulted field is the `init=False` `type` literal, so dataclass ordering needs no special handling. Per the spec, `altitude` *defaults to 0.0 when absent or null in the JSON* — that tolerance lives in the loader (§7), which injects `0.0` before constructing the Point, and in the UI form, which pre-fills `0.0`. The serializer always writes `altitude` explicitly.

### 3.4 `geometry/models/line.py`

**Δ from current**: change the base class from `DirectedObject` to `ElevatedObject`. `elevation` is inherited, so no field is added to `Line` itself; every `Line(...)` call site now passes `elevation` explicitly (forms supply `0.0` for a horizontal line).

No other changes. `fill_color` remains stored-but-not-rendered.

### 3.5 `geometry/models/ray.py`

Same delta as Line: replace `DirectedObject` with `ElevatedObject`. No new fields in `Ray` itself.

### 3.6 `geometry/models/vector.py`

Same delta. The endpoint formula changes: the 2D `vector_endpoint()` signature in geometry.py will be extended to 3D (see §5.1). The model stores `length`, `endpoint_id`, and the inherited `elevation` from `ElevatedObject`.

### 3.7 `geometry/models/tangent.py`

**Delta from current**: This is the most invasive model change.

- Replace `DirectedObject` with `ElevatedObject` (elevation field inherited).
- Replace `circle_id: str` with `shape_id: str` and `shape_type: str`.
- `elevation` is `0.0` for Circle tangents and user-supplied for Ball tangents.

```python
@dataclass
class Tangent(ElevatedObject):
    """Tangent to a Circle or Ball at a point on its surface.

    Fields
    ------
    shape_id : str
        ID of the target Circle or Ball.
    shape_type : str
        ``"circle"`` or ``"ball"``. Identifies which object ``shape_id`` refers to.
    point_id : str
        ID of the surface point.
    line_color : str
    fill_color : str
        Stored; not rendered.
    """
    shape_id: str
    shape_type: str
    point_id: str
    line_color: str
    fill_color: str
    type: str = field(init=False, default="tangent")
```

**`shape_type` drives dispatch**: services and validation pick the Circle-tangent vs Ball-tangent path on `shape_type` — `"circle"` → 2D horizontal tangent (`elevation = 0.0`); `"ball"` → 3D tangent perpendicular to the sphere radius (user-supplied `elevation`). The dep-graph edge is `Tangent → {shape_id, point_id}` for both. Since the project is pre-release, `circle_id` is removed everywhere — there is no compatibility path and no serializer migration to read it.

### 3.8 `geometry/models/polygon.py`

No changes. Polygon is unchanged by the 3D expansion. Its vertices carry 3D altitude via their Point references; the polygon's 2D geometry calculations use only `(easting, northing)`.

### 3.9 `geometry/models/circle.py`

No changes. Circle is always a horizontal 2D disk; it renders at `center.altitude` in the 3D view.

### 3.10 `geometry/models/ball.py` (NEW)

```python
@dataclass
class Ball(GeoObject):
    """A 3D sphere defined by a center Point and radius.

    Fields
    ------
    center_id : str
        ID of the Point at the geometric center of the sphere.
    radius : float
        Radius in metres; must be > 0.
    line_color : str
        Wireframe/stroke color.
    fill_color : str
        Interior fill color (rendered in 3D and Slice views; projected circle in 2D flat).
    """
    center_id: str
    radius: float
    line_color: str
    fill_color: str
    type: str = field(init=False, default="ball")
```

### 3.11 `geometry/models/cylinder.py` (NEW)

```python
@dataclass
class Cylinder(GeoObject):
    """A 3D cylinder defined by a base-center Point, radius, height, and axis orientation.

    ``axis_mode`` controls whether the axis is vertical (axis points straight up,
    azimuth and elevation are forced to 0 and π/2 respectively) or inclined
    (azimuth and elevation are user-supplied).

    Fields
    ------
    base_center_id : str
        ID of the Point at the center of the base circular face.
    radius : float
        Radius in metres; must be > 0.
    height : float
        Length of the cylinder along its axis in metres; must be > 0.
    axis_mode : str
        ``"vertical"`` or ``"inclined"``.
    axis_azimuth : float
        Horizontal bearing of the axis in radians (stored even when vertical, as 0.0).
    axis_elevation : float
        Angle of the axis above the horizontal plane in radians; range ``(0, π/2]``.
        π/2 = vertical. Must be > 0 (0 = flat disk, rejected by validation).
    direction_mode : DirectionMode
        Controls display of ``axis_azimuth``.
    direction_units : DirectionUnits
        Controls display of both ``axis_azimuth`` and ``axis_elevation``.
    line_color : str
    fill_color : str
    """
    base_center_id: str
    radius: float
    height: float
    axis_mode: str
    axis_azimuth: float
    axis_elevation: float
    direction_mode: DirectionMode
    direction_units: DirectionUnits
    line_color: str
    fill_color: str
    type: str = field(init=False, default="cylinder")
```

Note: `Cylinder` intentionally does **not** extend `ElevatedObject`. Its `axis_azimuth`/`axis_elevation` are geometry parameters with their own names, not the generic `direction`/`elevation` of a directed line. Using `ElevatedObject` would add an unwanted `direction` field and confuse serialization.

### 3.12 `geometry/models/solid.py` (NEW)

```python
@dataclass
class Solid(GeoObject):
    """A 3D solid defined by an ordered stack of cross-section layers.

    Each layer is a Polygon ID or a Point ID (apex/nadir). Layers are ordered
    bottom-to-top by user declaration — not derived from altitude. The closed
    shell is formed by connecting adjacent layers; the volume is computed by
    the Mirtich (1996) polyhedral mass algorithm.

    Fields
    ------
    layers : list[str]
        Ordered references to existing Polygon or Point IDs. At least 2 entries.
        At most one entry may be a Point ID; it must be first or last.
    line_color : str
        Edge/stroke color.
    fill_color : str
        Face fill color (rendered in 3D and Slice views).
    """
    layers: list[str]
    line_color: str
    fill_color: str
    type: str = field(init=False, default="solid")

    def __post_init__(self) -> None:
        super().__post_init__()
        self.layers = list(self.layers)   # defensive copy, same pattern as Polygon.point_ids
```

### 3.13 `geometry/models/slice_plane.py` (NEW)

`SlicePlane` is **not** a `GeoObject`. It is ephemeral UI state and is never persisted.

```python
@dataclass
class SlicePlane:
    """Cutting plane definition for the Slice view tab.

    The plane equation is ``a·E + b·N + c·Z = d`` where the coefficients
    (a, b, c) form a unit normal vector for the three axis-aligned presets.
    For Custom mode the UI must normalize before constructing this object
    (see ``EPS_ALTITUDE`` contract in ``spec/MVP.md``).

    Fields
    ------
    mode : str
        One of ``"horizontal"``, ``"easting"``, ``"northing"``, ``"custom"``.
    a : float
        Coefficient of Easting in the plane equation.
    b : float
        Coefficient of Northing.
    c : float
        Coefficient of Altitude.
    d : float
        Right-hand-side constant.
    thickness : float
        Half-thickness of the slab in metres (default 0 = exact plane).
        Points within ±``thickness`` of the plane are included.
        Inclusion test: ``|a·E + b·N + c·Z - d| ≤ EPS_ALTITUDE + thickness``.

    Preset encodings
    ----------------
    Horizontal Z=v  →  a=0, b=0, c=1, d=v
    Easting E=v     →  a=1, b=0, c=0, d=v
    Northing N=v    →  a=0, b=1, c=0, d=v
    Custom          →  UI normalizes so sqrt(a²+b²+c²)=1, then d is offset.
    """
    mode: str
    a: float
    b: float
    c: float
    d: float
    thickness: float = field(default=0.0)
```

### 3.14 `geometry/models/__init__.py`

**Δ from current**: add Ball, Cylinder, Solid, SlicePlane to imports and `__all__`. Update the `GeoObject.__post_init__` docstring reference. Export `ElevatedObject` (replaces `DirectedObject` outright — no alias; `DirectedObject` is gone).

```python
from geometry.models.ball import Ball
from geometry.models.cylinder import Cylinder
from geometry.models.solid import Solid
from geometry.models.slice_plane import SlicePlane
# ... existing imports ...

__all__ = [
    "GeoObject", "ElevatedObject",
    "DirectionMode", "DirectionUnits",
    "Point", "Line", "Polygon", "Ray", "Vector",
    "Circle", "Ball", "Cylinder", "Solid", "Tangent",
    "SlicePlane",
]
```

---

## 4. Utils Package (`geometry/utils/`)

### 4.1 `geometry/utils/constants.py`

Add `EPS_ALTITUDE = 1e-6` and `EPS_VOLUME = 1e-9`, plus their `__all__` entries. No other changes.

### 4.2 `geometry/utils/angles.py`

No changes. All existing functions are correct. New callers that handle `elevation` use the same `to_radians()` / `to_degrees()` helpers — elevation is just another angle.

### 4.3 `geometry/utils/id_factory.py`

No changes. The new prefixes (`ba`, `cy`, `so`) work automatically.

### 4.4 `geometry/utils/events.py`

No changes. The seven event constants cover all new functionality.

---

## 5. Services Package (`geometry/services/`)

### 5.1 `geometry/services/geometry.py`

This is the largest set of changes. Existing functions keep their names; several gain a 3D-aware signature (noted per function). The project is pre-release, so callers are updated in lockstep with each signature change — there is no compatibility shim.

#### 5.1.1 Changes to existing functions

**`distance(pt_a, pt_b)`** — currently 2D (`np.hypot(Δe, Δn)`). Must become 3D:

```python
def distance(pt_a: Point, pt_b: Point) -> np.float64:
    """3D Euclidean distance: sqrt(Δe² + Δn² + Δz²)."""
    d_e = np.float64(pt_b.easting) - np.float64(pt_a.easting)
    d_n = np.float64(pt_b.northing) - np.float64(pt_a.northing)
    d_z = np.float64(pt_b.altitude) - np.float64(pt_a.altitude)
    return np.sqrt(d_e**2 + d_n**2 + d_z**2)
```

This is a **breaking change** for the one test that currently asserts 2D distance. When both altitudes are 0.0, the result equals the old 2D formula — existing tests pass without change if their test points have no altitude.

**`vector_endpoint(origin, length, az)`** — currently 2D. New signature adds `el`:

```python
def vector_endpoint(
    origin: Point,
    length: float,
    az: float,
    el: float = 0.0,
) -> np.ndarray:
    """3D endpoint of a vector.

    Formula (azimuth convention, intentional sin/cos swap):
        E = origin.easting  + L * sin(az) * cos(el)
        N = origin.northing + L * cos(az) * cos(el)
        Z = origin.altitude + L * sin(el)

    Parameters
    ----------
    origin : Point
    length : float
    az : float
        Azimuth in radians (clockwise from North).
    el : float
        Elevation in radians, range [-π/2, π/2]. Default 0.0.

    Returns
    -------
    numpy.ndarray
        Shape (3,): (easting, northing, altitude).
    """
```

`el` defaults to `0.0` purely as ergonomics for a horizontal vector; callers normally pass the vector's stored elevation. The return shape changes from `(2,)` to `(3,)`, so every caller (tests, render, command layer) updates from `e, n = vector_endpoint(...)` to `e, n, z = vector_endpoint(...)`.

**`direction_unit_vector(obj)`** — currently returns a 2D `(e, n)` unit vector from `ElevatedObject.direction`. This function is used for `ray_polygon_distance` (2D ray-polygon test) which is correct — the ray-polygon intersection is a 2D operation on `(easting, northing)`. No change needed to this function; the 2D projection is intentional.

**`_xy(point)`** — currently returns `(easting, northing)`. No change; it is used by 2D operations only. A new helper `_xyz(point)` is added for 3D operations:

```python
def _xyz(point: Point) -> np.ndarray:
    """Return point as float64 (easting, northing, altitude) array."""
    return np.array([point.easting, point.northing, point.altitude], dtype=np.float64)
```

**`convex_hull(polygon, points, new_id)`** — unchanged. Operates on `(E, N)` only.

**`tangent_direction(center, point)`** — unchanged. Circle tangent is 2D and horizontal; it calls the existing `distance()` which now uses 3D. The zero-radius guard `distance(center, point) < EPS_DISTANCE` still works correctly because the 3D distance to a coincident point is also zero.

#### 5.1.2 New functions

```python
# --- elevation helpers ---

def elevation(pt_a: Point, pt_b: Point) -> np.float64:
    """Elevation angle from pt_a to pt_b: atan2(Δz, sqrt(Δe²+Δn²)).

    Returns float64 in [-π/2, π/2]. Returns 0.0 if both points are coincident.
    """

# --- 3D hull → Solid ---

def convex_hull_3d(
    points_3d: Mapping[str, Point],
    point_ids: list[str],
    new_solid_id: str,
    new_polygon_ids: list[str],
    new_point_ids: list[str],
) -> Solid:
    """Convex hull of 3D points via scipy.spatial.ConvexHull on (E,N,Z).

    Returns a Solid whose layers are the triangulated facets of the hull.
    Each facet is a new Polygon (triangle) referencing existing or new Point IDs.
    If all input points are coplanar (QhullError on 3D hull), falls back to
    calling convex_hull() on (E,N) and returns a Polygon wrapped in a Solid
    with two identical layers (degenerate flat solid — caller must handle).

    Parameters
    ----------
    points_3d : Mapping[str, Point]
        Full point lookup.
    point_ids : list[str]
        IDs of the input points (subset of points_3d).
    new_solid_id : str
        ID for the returned Solid.
    new_polygon_ids : list[str]
        Pre-allocated IDs for each facet Polygon (len = number of hull facets).
    new_point_ids : list[str]
        Pre-allocated IDs for any new Points needed (hull vertices that are
        not in the original point set; in practice QhullHull always returns
        indices into the input, so this list is typically empty).

    Returns
    -------
    tuple[Solid, list[Polygon]]
        The Solid and the list of its constituent facet Polygons (to be
        inserted into the project store by the command layer).

    Raises
    ------
    ValueError
        If fewer than 4 non-coplanar points are provided.
    """

# --- Ball geometry ---

def ball_cross_section_radius(ball_radius: float, distance_to_plane: float) -> np.float64 | None:
    """Radius of the circular cross-section of a ball at a given plane distance.

    Parameters
    ----------
    ball_radius : float
    distance_to_plane : float
        Signed distance from the ball's center to the cutting plane.

    Returns
    -------
    numpy.float64 or None
        Cross-section radius, or None if |distance_to_plane| > ball_radius.
    """

def ball_volume(radius: float) -> np.float64:
    """(4/3) * π * r³"""

def ball_surface_area(radius: float) -> np.float64:
    """4 * π * r²"""

def ball_tangent_direction(center: Point, surface_point: Point) -> np.float64:
    """Azimuth from center to surface point (the radius direction).

    The Ball tangent must be perpendicular to this; validation uses
    abs(dot(direction_unit, radius_unit)) < EPS_ANGLE.
    Returns azimuth of the radius in [0, 2π).
    """

# --- Cylinder geometry ---

def cylinder_volume(radius: float, height: float) -> np.float64:
    """π * r² * h"""

def cylinder_lateral_surface_area(radius: float, height: float) -> np.float64:
    """2 * π * r * h"""

def cylinder_total_surface_area(radius: float, height: float) -> np.float64:
    """2 * π * r * h + 2 * π * r²"""

def cylinder_axis_vector(cylinder: "Cylinder") -> np.ndarray:
    """Unit vector along the cylinder axis in (E, N, Z) space.

    For vertical mode: (0, 0, 1).
    For inclined: (sin(az)*cos(el), cos(az)*cos(el), sin(el)).
    """

# --- Solid geometry (Mirtich 1996) ---

def solid_faces(
    solid: "Solid",
    objects: Mapping[str, "GeoObject"],
    points: Mapping[str, Point],
) -> list[list[np.ndarray]]:
    """Convert a Solid's layer stack to a list of triangle/quad face vertex lists.

    Used by solid_volume_centroid and solid_surface_areas.
    Returns list of faces, each face being a list of (E,N,Z) numpy arrays.
    """

def solid_volume_centroid(
    solid: "Solid",
    objects: Mapping[str, "GeoObject"],
    points: Mapping[str, Point],
) -> tuple[np.float64, np.ndarray]:
    """Mirtich (1996) polyhedral mass properties.

    Converts the layer stack to a closed B-rep (base face + top face +
    lateral triangulated faces), then runs the O(n) divergence-theorem
    surface-integral pass. Returns (volume, centroid) where centroid is
    a (3,) float64 array (E, N, Z).

    Cross-check formula (Wuttke 2021, Eq. 22):
        Vol = (1/3) * Σ_k Ar(face_k) * r_perp_k
    """

def solid_lateral_surface_area(
    solid: "Solid",
    objects: Mapping[str, "GeoObject"],
    points: Mapping[str, Point],
) -> np.float64:
    """Sum of all lateral face areas (triangles between layers)."""

def solid_total_surface_area(
    solid: "Solid",
    objects: Mapping[str, "GeoObject"],
    points: Mapping[str, Point],
) -> np.float64:
    """Lateral area + cap face areas (polygon layers at bottom and top)."""

# --- Measurements (scalars, no objects created) ---

def polygon_area(polygon: "Polygon", points: Mapping[str, Point]) -> np.float64:
    """abs(signed_area(polygon, points)) — always non-negative."""

def polygon_perimeter(polygon: "Polygon", points: Mapping[str, Point]) -> np.float64:
    """Sum of 2D edge lengths (easting, northing only)."""

def angle_between_directions(obj_a: "ElevatedObject", obj_b: "ElevatedObject") -> np.float64:
    """Unsigned angle between two direction-bearing objects in [0, π/2].

    Formula: arccos(|cos(d1 - d2)|) where d1, d2 are horizontal directions in radians.
    """

def three_point_azimuth_elevation(
    a: Point, b: Point, c: Point
) -> tuple[np.float64 | None, np.float64]:
    """Angle at vertex B subtended by the arms B→A and B→C (ordered triple).

    Returns ``(azimuth, elevation)`` in radians:

    - ``azimuth`` — directed horizontal turn from arm BA to arm BC, altitude
      ignored, normalized to [0, 2π):
      ``normalize_2pi(atan2(c.e - b.e, c.n - b.n) - atan2(a.e - b.e, a.n - b.n))``.
      ``None`` when either arm has no horizontal extent (purely vertical arm,
      horizontal length < EPS_DISTANCE) — the azimuth is undefined there.
    - ``elevation`` — difference of the two arms' elevation angles, range [-π, π]:
      ``elev(b->c) - elev(b->a)`` where ``elev = atan2(Δz, hypot(Δe, Δn))``.

    Order-dependent: ``three_point_azimuth_elevation(a, b, c)`` and
    ``(c, b, a)`` give explementary azimuth (2π - az) and negated elevation.

    Raises
    ------
    ValueError
        If either arm has zero 3D length (distance(a, b) or distance(c, b)
        < EPS_DISTANCE) — the angle is undefined.
    """
```

`three_point_azimuth_elevation` is a measurement (no object created); it is surfaced by the *Angle at Vertex* measurement dialog (§9) with three ordered Point pickers. It is the three-point sibling of `angle_between_directions` (which takes two existing direction-bearing objects).

**`__all__`** must be updated to include all new public names.

### 5.2 `geometry/services/validation.py`

Currently a license-headed stub. Full implementation:

```python
# Public API

def validate_polygon_non_degenerate(
    polygon: Polygon, points: Mapping[str, Point]
) -> None:
    """Raise ValueError if |signed_area| < EPS_AREA."""

def validate_polygon_simple(
    polygon: Polygon, points: Mapping[str, Point]
) -> None:
    """Raise ValueError if shapely.is_simple() returns False."""

def validate_polygon_vertex_count(polygon: Polygon) -> None:
    """Raise ValueError if fewer than 3 point_ids."""

def validate_circle_tangent_point(
    center: Point, surface_point: Point, radius: float
) -> None:
    """Raise ValueError if |distance(center, surface_point) - radius| >= EPS_DISTANCE."""

def validate_ball_tangent_point(
    center: Point, surface_point: Point, radius: float
) -> None:
    """Raise ValueError if |distance_3d(center, surface_point) - radius| >= EPS_DISTANCE.
    Uses 3D distance.
    """

def validate_ball_tangent_perpendicular(
    center: Point,
    surface_point: Point,
    tangent_direction: float,
    tangent_elevation: float,
) -> None:
    """Raise ValueError if |dot(tangent_unit_3d, radius_unit_3d)| >= EPS_ANGLE.

    tangent_unit_3d = (sin(az)*cos(el), cos(az)*cos(el), sin(el))
    radius_unit_3d  = unit vector from center to surface_point in 3D
    """

def validate_cylinder_axis_elevation(axis_elevation: float) -> None:
    """Raise ValueError if axis_elevation <= 0 (degenerate flat disk)."""

def validate_positive_radius(radius: float) -> None:
    """Raise ValueError if radius <= 0 (used by Circle, Ball, Cylinder)."""

def validate_solid_layers(layers: list[str], objects: Mapping[str, GeoObject]) -> None:
    """Raise ValueError if:
    - fewer than 2 layers
    - more than one Point layer
    - the Point layer is not first or last
    - any layer ID references a non-existent object
    - any layer references an object that is not a Polygon or Point
    """

def validate_solid_non_degenerate(volume: float) -> None:
    """Raise ValueError if |volume| < EPS_VOLUME.

    The 3D analog of validate_polygon_non_degenerate. Called after
    geometry.solid_volume_centroid() computes the volume, to reject solids
    whose layers are coplanar (zero extent) — including the coplanar-hull
    fallback case from geometry.convex_hull_3d() (see §13.7). The structural
    validate_solid_layers() check cannot catch this on its own, because a
    layer stack can be structurally valid yet geometrically flat.
    """

def validate_reference_exists(obj_id: str, objects: Mapping[str, GeoObject]) -> None:
    """Raise ValueError if obj_id not in objects."""

def validate_altitude_finite(altitude: float) -> None:
    """Raise ValueError if not math.isfinite(altitude)."""
```

All tolerance constants imported from `utils/constants.py`. No bare literals.

### 5.3 `geometry/services/slice.py` (NEW)

Pure geometric functions for the Slice tab. No matplotlib, no tkinter.

```python
from geometry.models.slice_plane import SlicePlane
from geometry.models.point import Point
from geometry.models.common import GeoObject

# --- membership ---

def signed_plane_distance(plane: SlicePlane, pt: Point) -> np.float64:
    """Signed distance of pt from the plane: a*E + b*N + c*Z - d.

    For unit-normal planes (the three presets and normalized Custom mode),
    this equals the geometric signed distance in metres.
    """

def point_on_plane(plane: SlicePlane, pt: Point) -> bool:
    """True if |signed_plane_distance(plane, pt)| <= EPS_ALTITUDE + plane.thickness."""

# --- segment intersection ---

def segment_plane_intersection(
    plane: SlicePlane,
    p1: np.ndarray,  # (3,) float64: (E, N, Z)
    p2: np.ndarray,
) -> np.ndarray | None:
    """Intersection of segment p1→p2 with plane, or None if parallel/miss.

    Returns the (3,) float64 intersection point.
    Uses parametric t = (d - dot(normal, p1)) / dot(normal, p2-p1).
    """

# --- object slicing ---

@dataclass
class SliceGeometry:
    """Intersection geometry produced for one GeoObject.

    Fields
    ------
    obj_id : str
    kind : str
        ``"point"``, ``"segment"``, ``"polygon"``, ``"arc"``.
    coords : np.ndarray
        Shape (N, 3) for 3D intersection coords. The Slice canvas
        projects these onto the plane's 2D local axes.
    style : dict
        Matplotlib kwargs (color, linewidth, alpha, etc.).
    """
    obj_id: str
    kind: str
    coords: np.ndarray
    style: dict

def slice_objects(
    objects: Mapping[str, GeoObject],
    points: Mapping[str, Point],
    plane: SlicePlane,
) -> list[SliceGeometry]:
    """Compute all slice geometries for the current plane.

    For each visible object, determines which part (if any) intersects
    the slab around the plane. Returns a list of SliceGeometry records
    for the render layer to consume.

    Per-type behavior:
    - Point: included if point_on_plane(); kind="point"
    - Line/Ray: intersect each infinite line with plane; kind="segment"
    - Vector: intersect the finite segment origin→endpoint with plane; kind="segment"
    - Polygon: intersect each edge with plane; collect segments; kind="polygon"
    - Circle: parametric arc intersection; kind="arc"
    - Ball: if |d_to_center| <= radius, emit circle cross-section; kind="arc"
    - Cylinder: ellipse/rectangle depending on cut angle; kind="polygon"
    - Solid: intersect each lateral face quad/triangle with plane; kind="polygon"
    - Tangent: treated as an infinite directed line
    """

def project_to_plane_axes(
    plane: SlicePlane,
    coords_3d: np.ndarray,  # (N, 3)
) -> np.ndarray:
    """Project 3D intersection coords onto the plane's 2D local axes.

    Returns (N, 2) array in the plane's intrinsic coordinate system.

    For axis-aligned planes:
    - Horizontal (Z=c): axes are (E, N)
    - Easting (E=c):   axes are (N, Z)
    - Northing (N=c):  axes are (E, Z)
    - Custom:          axes are two orthonormal vectors in the plane
                       (derived from the normal via Gram-Schmidt).
    """
```

### 5.4 `geometry/services/dep_graph.py`

Currently a stub. The dependency edge table for all 10 types:

| Object type | Direct dependencies (forward edges) |
|---|---|
| Point | ∅ |
| Line | `{point_a_id, point_b_id}` |
| Polygon | `set(point_ids)` |
| Ray | `{origin_id}` |
| Vector | `{origin_id}` ∪ (`{endpoint_id}` if not None) |
| Circle | `{center_id}` |
| Ball | `{center_id}` |
| Cylinder | `{base_center_id}` |
| Solid | `set(layers)` — all referenced Polygon and Point IDs |
| Tangent | `{shape_id, point_id}` |

```python
class DependencyGraph:
    """Reverse-reference graph for O(|affected|) cascade operations.

    Fields
    ------
    _deps : dict[str, set[str]]
        Forward edges: obj_id → set of IDs it depends on.
    _rdeps : dict[str, set[str]]
        Reverse edges: obj_id → set of IDs that depend on it.
    """

    def __init__(self) -> None:
        self._deps: dict[str, set[str]] = {}
        self._rdeps: dict[str, set[str]] = {}

    def register(self, obj_id: str, dep_ids: set[str]) -> None:
        """Record that obj_id depends on every id in dep_ids.

        Safe to call multiple times (re-registration replaces old edges).
        """

    def unregister(self, obj_id: str) -> None:
        """Remove obj_id from both maps and prune its reverse edges."""

    def dependents_of(self, obj_id: str) -> set[str]:
        """Transitive closure via BFS over _rdeps. Does not include obj_id itself."""

    def deps_for_type(
        self,
        obj: "GeoObject",
    ) -> set[str]:
        """Helper: derive the dep_ids set for any GeoObject instance.

        Centralises the per-type edge table so command code never has to
        pattern-match on type names.
        """
```

### 5.5 `geometry/services/commands.py`

Currently a stub. The Command protocol and CommandHistory ring buffer are straightforward; the edge cases are in the snapshot logic.

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Command(Protocol):
    description: str
    def do(self) -> None: ...
    def undo(self) -> None: ...

class CommandHistory:
    """Bounded deque of 100 commands with undo/redo stacks.

    Fields
    ------
    _done : deque[Command]
        Commands that have been executed (maxlen=100).
    _undone : list[Command]
        Commands available for redo. Cleared on new do().
    _bus : EventBus
        Fires history_changed after every push/undo/redo.
    """

    def __init__(self, bus: "EventBus") -> None: ...

    def push(self, cmd: Command) -> None:
        """Execute cmd.do(), push onto _done, clear _undone, fire history_changed."""

    def undo(self) -> None:
        """Pop _done, call undo(), push to _undone, fire history_changed.
        No-op if _done is empty.
        """

    def redo(self) -> None:
        """Pop _undone, call do(), push to _done, fire history_changed.
        No-op if _undone is empty.
        """

    @property
    def can_undo(self) -> bool: ...

    @property
    def can_redo(self) -> bool: ...

    def clear(self) -> None:
        """Called by project on project_loaded. Clears both stacks."""
```

**Command classes** (all in `services/commands.py`):

```python
class CreateObjectCommand:
    """Create any single GeoObject.

    do():  insert into project.objects, register in dep_graph,
           fire object_created, mark canvas stale.
    undo(): unregister, remove from project.objects,
            fire object_deleted([obj_id]), mark canvas stale.
    """
    def __init__(
        self,
        project: "Project",
        obj: GeoObject,
        dep_ids: set[str],
    ) -> None: ...

class CascadeDeleteCommand:
    """Delete an object and all its transitive dependents as one atomic unit.

    Snapshots the full set of removed objects before do(); restores them
    (in dependency-safe insertion order) on undo().

    do():  collect closure via dep_graph.dependents_of(),
           remove all from project.objects, fire object_deleted(all_ids).
    undo(): re-insert all objects, re-register all dep edges,
            fire object_created for each.
    """
    def __init__(
        self,
        project: "Project",
        root_id: str,
    ) -> None: ...

class ModifyObjectCommand:
    """Modify scalar properties (name, color, alpha, visibility, direction settings).

    Snapshots the before-state dict via dataclasses.asdict(); restores on undo.
    Does NOT handle coordinate moves (use MovePointCommand) or vertex list
    changes (use ModifyPolygonVerticesCommand).
    """
    def __init__(
        self,
        project: "Project",
        obj_id: str,
        **new_values,     # field-name → new value; validated before command construction
    ) -> None: ...

class MovePointCommand:
    """Move a Point's (easting, northing, altitude) and recompute all dependents.

    Snapshots the Point's old coordinates and the old computed values of every
    dependent (line directions, vector endpoints, intersection-derived points).
    On do(): moves the point, recomputes dependents, fires object_modified for
    the point and all dependents. On undo(): restores all values from snapshot.
    """
    def __init__(
        self,
        project: "Project",
        point_id: str,
        new_easting: float,
        new_northing: float,
        new_altitude: float,
    ) -> None: ...

class ModifyPolygonVerticesCommand:
    """Replace a polygon's vertex list and update is_convex.

    Snapshots both point_ids and is_convex before do().
    """
    def __init__(
        self,
        project: "Project",
        polygon_id: str,
        new_point_ids: list[str],
    ) -> None: ...

class BulkImportCommand:
    """Create multiple objects as a single undoable unit (text import, file import).

    do():  create all objects in dependency order (Points before Polygons).
    undo(): delete all in reverse dependency order.
    """
    def __init__(
        self,
        project: "Project",
        objects: list[tuple[GeoObject, set[str]]],  # (obj, dep_ids) pairs
    ) -> None: ...
```

### 5.6 `geometry/services/render.py`

Currently a stub. The render instruction design must accommodate three distinct views.

```python
@dataclass
class RenderInstruction:
    """A single drawable primitive for one object on one canvas tab.

    Fields
    ------
    kind : str
        See the table below.
    coords : np.ndarray
        For 2D/Slice: shape (N, 2) in (E, N) or plane-local axes.
        For 3D:       shape (N, 3) in (E, N, Z).
    style : dict
        Matplotlib artist keyword arguments (color, linewidth, alpha, marker, etc.).
    obj_id : str
        Back-reference to the source GeoObject.
    is_3d : bool
        True when coords is (N, 3) and the consumer uses Axes3D calls.
    """
    kind: str
    coords: np.ndarray
    style: dict
    obj_id: str
    is_3d: bool = False
```

#### RenderInstruction kinds per tab

| `kind` | 2D flat | 3D | Slice |
|---|---|---|---|
| `"point"` | scatter marker | scatter3D | scatter marker |
| `"line"` | infinite line (clipped to viewport) | 3D line between two points | infinite line in plane coords |
| `"ray"` | half-line (clipped) | 3D half-line | half-line in plane coords |
| `"arrow"` | quiver (E,N) | quiver3D (E,N,Z) | quiver in plane coords |
| `"polygon"` | filled patch | Poly3DCollection | filled patch |
| `"arc"` | Arc patch or parametric line | parametric 3D curve | Arc patch or ellipse |
| `"wireframe"` | — | line collection for Ball/Solid shells | — |

Three builder functions, each pure (no matplotlib calls):

```python
def build_2d_instructions(
    objects: Mapping[str, GeoObject],
    points: Mapping[str, Point],
    selected_id: str | None,
) -> list[RenderInstruction]:
    """Produce 2D (E,N) instructions for all visible objects."""

def build_3d_instructions(
    objects: Mapping[str, GeoObject],
    points: Mapping[str, Point],
    selected_id: str | None,
) -> list[RenderInstruction]:
    """Produce 3D (E,N,Z) instructions for all visible objects. is_3d=True."""

def build_slice_instructions(
    slice_geoms: list["SliceGeometry"],
    selected_id: str | None,
) -> list[RenderInstruction]:
    """Convert SliceGeometry records (output of services/slice.py) to RenderInstructions."""
```

**Selection highlight**: The selected object's instruction gets an additional entry in `style` with `linewidth` doubled and an accent color overlay. The blitting strategy uses this — the non-selected background is saved, then only the highlight instruction is drawn on top.

---

## 6. Project Coordinator (`geometry/project.py`)

Currently a license-headed stub. Full design:

```python
@dataclass
class ProjectMetadata:
    """JSON metadata block.

    Fields
    ------
    title : str
    created : str
        ISO-8601 datetime string.
    last_modified : str
        ISO-8601 datetime string.
    description : str
        Optional; defaults to empty string.
    """
    title: str
    created: str
    last_modified: str
    description: str = field(default="")


class Project:
    """Central coordinator: object store, selection, history, dep graph.

    Fields
    ------
    objects : dict[str, GeoObject]
        All objects in the current scene, keyed by ID.
    selection : str | None
        ID of the currently selected object, or None.
    history : CommandHistory
    dep_graph : DependencyGraph
    id_factory : IDFactory
    bus : EventBus
    is_dirty : bool
        True when there are unsaved changes.
    metadata : ProjectMetadata
    """

    def __init__(self, bus: EventBus) -> None: ...

    def execute(self, cmd: Command) -> None:
        """Execute cmd via history.push() → mark dirty → (events fired by cmd)."""

    def select(self, obj_id: str | None) -> None:
        """Set selection and fire SELECTION_CHANGED."""

    def get_objects_of_type(self, type_name: str) -> list[GeoObject]:
        """Return all objects whose .type == type_name."""

    def new(self) -> None:
        """Clear all objects, reset dirty, clear history, reset metadata. Fire PROJECT_LOADED."""

    def load(self, data: dict) -> None:
        """Deserialize via persistence/serializer.py, populate self, reseed IDFactory,
        clear history, fire PROJECT_LOADED.
        """

    def save(self) -> dict:
        """Serialize via persistence/serializer.py. Clear dirty flag."""

    def next_id(self, prefix: str) -> str:
        """Delegate to self.id_factory.next_id(prefix)."""
```

`Project` does not import `tkinter` or `matplotlib`. It subscribes to no events itself — it fires them.

---

## 7. Persistence Package (`geometry/persistence/`)

### 7.1 `geometry/persistence/schema.py`

```python
CURRENT_VERSION = "1.1"

def check_version(version_str: str) -> None:
    """Raise ValueError on major-version mismatch or missing version.

    Same major, lower-or-equal minor → OK.
    Same major, higher minor → issue warning (unknown fields will be passed through).
    Different major → raise ValueError.
    Missing version → raise ValueError.
    """

def extract_unknown_keys(
    raw_obj: dict,
    known_top_level: set[str],
    known_properties: set[str],
) -> tuple[dict, dict]:
    """Return (unknown_top_level, unknown_properties) dicts for round-trip passthrough."""
```

### 7.2 `geometry/persistence/serializer.py`

Currently a stub. The JSON envelope structure: top-level fields `id`, `type`, `name`, `alpha`, `visibility`, plus color fields (`color` for Point; `line_color` + `fill_color` for all others), with type-specific fields nested under `"properties"`.

#### JSON properties split per type

| Type | Top-level color fields | `properties` keys |
|---|---|---|
| Point | `"color"` | `easting`, `northing`, `altitude` |
| Line | `"line_color"`, `"fill_color"` | `point_a_id`, `point_b_id`, `direction`, `elevation`, `direction_mode`, `direction_units` |
| Polygon | `"line_color"`, `"fill_color"` | `point_ids`, `is_convex` |
| Ray | `"line_color"`, `"fill_color"` | `origin_id`, `direction`, `elevation`, `direction_mode`, `direction_units` |
| Vector | `"line_color"`, `"fill_color"` | `origin_id`, `direction`, `elevation`, `direction_mode`, `direction_units`, `length`, `endpoint_id` |
| Circle | `"line_color"`, `"fill_color"` | `center_id`, `radius` |
| Ball | `"line_color"`, `"fill_color"` | `center_id`, `radius` |
| Cylinder | `"line_color"`, `"fill_color"` | `base_center_id`, `radius`, `height`, `axis_mode`, `axis_azimuth`, `axis_elevation`, `direction_mode`, `direction_units` |
| Solid | `"line_color"`, `"fill_color"` | `layers` |
| Tangent | `"line_color"`, `"fill_color"` | `shape_id`, `shape_type`, `point_id`, `direction`, `elevation`, `direction_mode`, `direction_units` |

`SlicePlane` is **never persisted**.

```python
def save(project: "Project") -> dict:
    """Serialize project to a JSON-compatible dict.

    Returns
    -------
    dict
        Top-level keys: ``version``, ``metadata``, ``objects``.
        Enum values serialized as lowercase strings.
        Unknown keys (from round-trip passthrough) re-appended verbatim.
    """

def load(data: dict) -> "Project":
    """Deserialize a JSON dict to a Project.

    Steps:
    1. schema.check_version(data["version"])
    2. Reconstruct each object by dispatching on obj["type"].
    3. For Point: if "altitude" absent from properties, inject 0.0.
    4. For Line/Ray/Vector/Tangent: if "elevation" absent from properties, inject 0.0.
    5. Unknown object types: store as opaque blob in a separate list, warn user,
       do not insert into project.objects but re-emit on next save.
    6. Load validation: verify every referenced ID exists in project.objects.
    7. project.dep_graph: register all objects.
    8. project.id_factory.reseed(list(project.objects.keys())).
    10. project.history.clear().
    11. project.bus.fire(PROJECT_LOADED).
    """
```

#### JSON examples

**Point with altitude**:
```json
{
  "id": "pt_001",
  "type": "point",
  "name": "Summit",
  "color": "#FF0000",
  "alpha": 1.0,
  "visibility": true,
  "properties": {
    "easting": 400000.0,
    "northing": 5000000.0,
    "altitude": 1234.5
  }
}
```

**Ball**:
```json
{
  "id": "ba_001",
  "type": "ball",
  "name": "Test sphere",
  "line_color": "#0000FF",
  "fill_color": "#AAAAFF",
  "alpha": 0.7,
  "visibility": true,
  "properties": {
    "center_id": "pt_001",
    "radius": 50.0
  }
}
```

**Cylinder (inclined)**:
```json
{
  "id": "cy_001",
  "type": "cylinder",
  "name": "Inclined bore",
  "line_color": "#008800",
  "fill_color": "#AAFFAA",
  "alpha": 1.0,
  "visibility": true,
  "properties": {
    "base_center_id": "pt_002",
    "radius": 5.0,
    "height": 30.0,
    "axis_mode": "inclined",
    "axis_azimuth": 0.7854,
    "axis_elevation": 1.0472,
    "direction_mode": "azimuth",
    "direction_units": "radians"
  }
}
```

**Solid (pyramid)**:
```json
{
  "id": "so_001",
  "type": "solid",
  "name": "Pyramid",
  "line_color": "#884400",
  "fill_color": "#FFCC88",
  "alpha": 0.9,
  "visibility": true,
  "properties": {
    "layers": ["pg_001", "pt_005"]
  }
}
```

**Tangent (new schema)**:
```json
{
  "id": "tg_001",
  "type": "tangent",
  "name": "Ball tangent",
  "line_color": "#00FF66",
  "fill_color": "#00FF66",
  "alpha": 1.0,
  "visibility": true,
  "properties": {
    "shape_id": "ba_001",
    "shape_type": "ball",
    "point_id": "pt_003",
    "direction": 2.3562,
    "elevation": 0.5236,
    "direction_mode": "azimuth",
    "direction_units": "radians"
  }
}
```


---

## 8. Canvas Package (`geometry/canvas/`)

### Layer rule

`canvas/` may import from `services/`, `models/`, `utils/`, and `project.py`. **`canvas/` must not import from `ui/`**. Coordination between canvas views and UI controls is done exclusively through callbacks passed by `ui/canvas_tabs.py`.

### 8.1 `geometry/canvas/canvas_view.py`

2D flat tab canvas. Existing design from the design doc is correct; expand to the 10-type instruction set.

```python
class CanvasView:
    """2D flat matplotlib canvas with blit-based selection highlight.

    Parameters
    ----------
    parent : tk.Widget
        The ttk.Frame inside the 2D tab.
    project : Project
    bus : EventBus

    Key attributes
    --------------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes.Axes
    canvas : FigureCanvasTkAgg
    toolbar : NavigationToolbar2Tk
    _bg_buffer : object | None
        Saved background from copy_from_bbox for blit.
    _stale : bool
    """

    def __init__(self, parent: tk.Widget, project: Project, bus: EventBus) -> None: ...

    def mark_stale(self) -> None:
        """Set _stale=True; does not redraw."""

    def redraw_if_stale(self) -> None:
        """Full redraw if _stale. Called on tab activation."""

    def full_redraw(self) -> None:
        """Build 2D instructions, draw all objects, save blit buffer, draw selection highlight."""

    def blit_selection(self, obj_id: str | None) -> None:
        """Restore buffer, draw only the selection highlight, blit."""

    def on_resize(self, event) -> None:
        """Trigger full_redraw."""

    def teardown(self) -> None:
        """Unsubscribe all bus handlers. Called by CanvasTabController on destroy."""
```

### 8.2 `geometry/canvas/canvas_view_3d.py` (NEW)

```python
class CanvasView3D:
    """3D matplotlib canvas (Axes3D). No blit support — full redraw on every change.

    Parameters
    ----------
    parent : tk.Widget
    project : Project
    bus : EventBus
    """

    def __init__(self, parent: tk.Widget, project: Project, bus: EventBus) -> None: ...

    def mark_stale(self) -> None: ...

    def redraw_if_stale(self) -> None: ...

    def full_redraw(self) -> None:
        """Build 3D instructions, draw all objects via Axes3D.
        Default view: elev=30, azim=225; preserve user's current rotation.
        """

    def teardown(self) -> None: ...
```

### 8.3 `geometry/canvas/canvas_view_slice.py` (NEW)

```python
class CanvasViewSlice:
    """Slice tab canvas. Holds the current SlicePlane and rerenders on apply_plane().

    Parameters
    ----------
    parent : tk.Widget
    project : Project
    bus : EventBus
    """

    def __init__(self, parent: tk.Widget, project: Project, bus: EventBus) -> None: ...

    def apply_plane(self, plane: SlicePlane) -> None:
        """Store plane and trigger full_redraw. Called by CanvasTabController
        after the Apply button is pressed. CanvasViewSlice holds no reference to
        SliceControlsFrame; wiring is in canvas_tabs.py only.
        """

    def mark_stale(self) -> None: ...

    def redraw_if_stale(self) -> None: ...

    def full_redraw(self) -> None:
        """Call slice_objects(), build_slice_instructions(), draw, blit."""

    def teardown(self) -> None: ...
```

### 8.4 `geometry/canvas/interaction.py`

State machine for click-capture on the 2D canvas. Currently a stub.

```python
class InteractionMode(enum.Enum):
    IDLE = "idle"
    AWAITING_1 = "awaiting_1"
    AWAITING_2 = "awaiting_2"
    AWAITING_N = "awaiting_n"

class InteractionController:
    """Click-capture state machine.

    Owned by CanvasView (2D). Routes canvas click events to the active dialog's
    on_canvas_click callback. The dialog registers a callback and arms the state
    machine; ESC always returns to IDLE.

    The 3D tab does not support click-creation (Axes3D click coordinates are
    ambiguous without a z-depth pick). The Slice tab supports click-select only.
    """

    def __init__(self, canvas_view: CanvasView) -> None: ...

    def arm(
        self,
        mode: InteractionMode,
        on_click: Callable[[float, float], None],  # (easting, northing)
        on_complete: Callable[[], None] | None = None,
    ) -> None:
        """Arm the state machine. The canvas switches cursor to crosshair."""

    def disarm(self) -> None:
        """Return to IDLE, restore cursor."""

    def on_canvas_click(self, event) -> None:
        """Dispatch click to the registered callback or to select logic (IDLE)."""

    def on_key_press(self, event) -> None:
        """ESC → disarm(). Enter → emit completion in AWAITING_N."""
```

---

## 9. UI Package (`geometry/ui/`)

### Layer rule

`ui/` may import from `canvas/`, `services/`, `models/`, `utils/`, and `project.py`. `canvas/` must not import from `ui/`.

### 9.1 `geometry/ui/main_window.py`

```python
class MainWindow:
    """Root tkinter window. Three-column layout with menubar and status bar.

    Owns the Project, EventBus, CanvasTabController, PropertiesPanel,
    LeftCards, and all top-level menus.

    Parameters
    ----------
    root : tk.Tk
    """

    def __init__(self, root: tk.Tk) -> None: ...

    def _build_menu(self) -> None:
        """File, Edit (Undo/Redo/Delete/Options), View, Help."""

    def _build_toolbar(self) -> None:
        """Open, Save, Undo, Redo, Refresh, Pan, Zoom, Options."""

    def _build_status_bar(self) -> None:
        """Project title | dirty indicator | cursor coords | stale indicator + Refresh link."""

    def _on_undo(self) -> None: ...
    def _on_redo(self) -> None: ...
    def _on_delete(self) -> None: ...

    def _update_cursor_coords(self, e: float, n: float, z: float | None = None) -> None:
        """Update status bar cursor read-out. Called by CanvasTabController."""
```

**Window icon**: `root.iconphoto(True, tk.PhotoImage(file="GeoSketch.png"))` at startup.

**Keyboard shortcuts** wired at the root window level:

| Shortcut | Action |
|---|---|
| `F1` | Switch to 2D tab |
| `F2` | Switch to 3D tab |
| `F3` | Switch to Slice tab |
| `Ctrl+Z` | Undo |
| `Ctrl+Y`, `Ctrl+Shift+Z` | Redo |
| `Del` | Delete selection |
| `F5` | Refresh active canvas tab |
| `Ctrl+N/O/S` | New/Open/Save |
| `Ctrl+Shift+S` | Save As |
| `Ctrl+,` | Options |
| `Ctrl++/-` | Zoom |
| `Ctrl+0` | Fit to extent |

### 9.2 `geometry/ui/canvas_tabs.py`

```python
class CanvasTabController(ttk.Notebook):
    """Owns and coordinates the three canvas tabs.

    This class is the only place that wires SliceControlsFrame → CanvasViewSlice.
    Neither of those two knows about the other.

    Parameters
    ----------
    parent : tk.Widget
    project : Project
    bus : EventBus
    on_cursor_move : Callable[[float, float, float | None], None]
        Callback to update the status bar cursor read-out.
    """

    def __init__(
        self,
        parent: tk.Widget,
        project: Project,
        bus: EventBus,
        on_cursor_move: Callable[[float, float, float | None], None],
    ) -> None: ...

    def _build_tabs(self) -> None:
        """Create three tab frames.

        Tab 1 (2D):    CanvasView inside a ttk.Frame.
        Tab 2 (3D):    CanvasView3D inside a ttk.Frame.
        Tab 3 (Slice): ttk.Frame containing SliceControlsFrame (top) +
                       CanvasViewSlice (fill).
                       Apply button callback:
                           plane = slice_controls.build_plane()
                           canvas_view_slice.apply_plane(plane)
                       This is the ONLY wiring between SliceControlsFrame and
                       CanvasViewSlice.
        """

    def switch_to_2d(self) -> None:  # F1
    def switch_to_3d(self) -> None:  # F2
    def switch_to_slice(self) -> None:  # F3

    def _on_tab_changed(self, event) -> None:
        """Activate the newly selected tab; call redraw_if_stale() on it."""

    def _on_canvas_stale(self) -> None:
        """Mark all three canvas views stale (via their mark_stale() methods).
        Called when CANVAS_STALE event fires.
        """

    def _on_selection_changed(self, obj_id: str | None) -> None:
        """Forward selection to the active tab's blit_selection() or full_redraw()."""

    def teardown(self) -> None:
        """Call teardown() on all three canvas views before window destroy."""
```

### 9.3 `geometry/ui/slice_controls.py`

```python
class SliceControlsFrame(ttk.Frame):
    """Control strip above the Slice canvas.

    Does NOT hold a reference to CanvasViewSlice. Exposes build_plane() for
    CanvasTabController to call when Apply is pressed.

    Parameters
    ----------
    parent : tk.Widget
    project : Project
        Needed to auto-range the offset slider to scene extents.
    """

    def __init__(self, parent: tk.Widget, project: Project) -> None: ...

    def build_plane(self) -> SlicePlane:
        """Read current control state and return a SlicePlane.

        For Custom mode: reads a, b, c, d fields; normalizes (a,b,c) to unit
        length; raises ValueError with a user-visible message if the normal
        is the zero vector.
        """

    def _on_mode_changed(self) -> None:
        """Show/hide Custom coefficient fields. Update slider range."""
```

### 9.4 `geometry/ui/dialogs.py`

All 10 object-type forms live here. The base class pattern:

```python
class ObjectFormDialog(tk.Toplevel):
    """Base for all create/edit forms.

    Provides the shared skeleton: Name row, color/alpha rows, validate-on-keystroke,
    OK/Cancel buttons, modal grab.

    Subclasses implement _build_body() and _collect_result().
    """

    def __init__(
        self,
        parent: tk.Widget,
        project: Project,
        existing: GeoObject | None = None,  # None = create mode; object = edit mode
    ) -> None: ...

    def _build_shared_header(self) -> None:
        """Name entry (full width). Color picker(s) + alpha slider."""

    def _build_body(self) -> None:
        """Override in subclass: type-specific body widgets."""

    def _validate(self) -> bool:
        """Override in subclass: return True if all fields are valid."""

    def _collect_result(self) -> Command:
        """Override in subclass: build and return the appropriate Command."""

    def _on_ok(self) -> None:
        """Validate, collect command, execute via project.execute(), close."""

    def _on_cancel(self) -> None:
        """Close without executing."""
```

Concrete dialogs (one class each, all in `dialogs.py`):

- `PointFormDialog` — easting/northing/altitude fields + reference-point subcomponent + click-mode capture
- `LineFormDialog` — point A/B comboboxes + read-only direction/elevation display
- `PolygonFormDialog` — two tabs: `SelectPointsTab`, `EnterVerticesTab`
- `RayFormDialog` — origin + direction/elevation fields + click mode
- `VectorFormDialog` — two tabs: `OriginEndpointTab`, `LengthDirectionTab`
- `CircleFormDialog` — center + radius + click mode
- `BallFormDialog` — center + radius + click mode (radius = 3D distance)
- `CylinderFormDialog` — base center + radius + height + axis orientation section
- `SolidFormDialog` — ordered layers list with shape-type radios and reorder buttons
- `TangentFormDialog` — shape-type radio (Circle/Ball) + shape combobox + point combobox; Ball mode reveals direction/elevation fields

**Edit mode**: dialog title becomes `"Edit <type>"`, OK label becomes `"Save changes"`. All fields prefilled from the existing object.

### 9.5 `geometry/ui/cards.py`

Left-panel collapsible cards and the shared `ReferencePointWidget`.

```python
class ReferencePointWidget(ttk.Frame):
    """Reusable checkbox + combobox for reference-point offset mode.

    Used in: PointFormDialog, PolygonFileImportDialog, EnterVerticesTab.

    When checkbox is checked, combobox is enabled and (E,N,Z) inputs are
    interpreted as deltas. When unchecked, combobox is disabled and inputs
    are absolute UTM. The combobox lists all Points by "id — name (E, N)".

    If the scene has no Points, the checkbox is disabled with tooltip
    "Create a point first to enable relative offsets".
    """

    def __init__(self, parent: tk.Widget, project: Project) -> None: ...

    @property
    def is_active(self) -> bool: ...

    @property
    def reference_point(self) -> Point | None:
        """Returns the selected Point, or None if checkbox is unchecked."""

class CollapsibleCard(ttk.Frame):
    """Disclosure widget with a chevron header and collapsible body."""

    def __init__(self, parent: tk.Widget, title: str) -> None: ...
    def toggle(self) -> None: ...

class LeftCardsPanel(ttk.Frame):
    """Stacks the four collapsible cards in the left column.

    Cards: Create objects, Import, Calculations, Measurements.
    Each card's buttons open the corresponding dialog or run the calculation.

    The Measurements card includes "Angle at Vertex (3-pt)", which opens a small
    dialog with three ordered Point comboboxes (A = first arm, B = vertex,
    C = second arm) and calls geometry.three_point_azimuth_elevation(a, b, c).
    The result row shows azimuth (altitude ignored) and elevation = elev(BC) -
    elev(BA) in the user's direction units, with an "order matters (A-B-C !=
    C-B-A)" hint. No object is created.
    """

    def __init__(self, parent: tk.Widget, project: Project, bus: EventBus) -> None: ...
```

### 9.6 `geometry/ui/properties_panel.py`

```python
class PropertiesPanel(ttk.Frame):
    """Right-panel display of the currently selected object's properties.

    Subscribes to SELECTION_CHANGED. On change: looks up the object in
    project.objects, rebuilds type-specific property rows, and auto-computes
    measurements for objects that show them automatically.

    Auto-shown measurements by type:
    - Polygon: area, perimeter (cheap; always shown when selected)
    - Circle: area, circumference
    - Ball: volume, surface area
    - Cylinder: volume, lateral area, total area
    - Solid: volume, centroid, lateral area, total area (Mirtich pass)
    """

    def __init__(self, parent: tk.Widget, project: Project, bus: EventBus) -> None: ...

    def _on_selection_changed(self, obj_id: str | None) -> None:
        """Rebuild the panel for the newly selected object (or clear if None)."""

    def _build_for(self, obj: GeoObject) -> None:
        """Dispatch to type-specific builder."""

    def _inline_edit_commit(self, obj_id: str, field: str, value) -> None:
        """Fires a ModifyObjectCommand for inline Name/color edits."""
```

---

## 10. Layer Rules and Import Graph

```
┌──────────────────────────────────────────────────────┐
│  ui/    (tkinter widgets)                            │
│  canvas/ (matplotlib)    ← NO import from ui/        │
├──────────────────────────────────────────────────────┤
│  project.py  (coordinator)                           │
├──────────────────────────────────────────────────────┤
│  services/   (geometry, validation, commands,        │
│               render, dep_graph, slice)              │
├──────────────────────────────────────────────────────┤
│  models/     (pure dataclasses; no logic)            │
├──────────────────────────────────────────────────────┤
│  persistence/    utils/                              │
└──────────────────────────────────────────────────────┘
```

Enforced rules:
- `services/` imports only `models/` and `utils/`. Never `tkinter`, never `matplotlib`.
- `persistence/` imports only `models/` and `utils/`.
- `canvas/` imports `services/`, `models/`, `utils/`, `project.py`. Never `ui/`.
- `ui/` imports `canvas/`, `services/`, `models/`, `utils/`, `project.py`.
- `project.py` imports `services/`, `models/`, `utils/`. Never `tkinter`, never `matplotlib`.
- `models/` imports only `utils/` and Python stdlib.
- `utils/` imports only Python stdlib and `numpy`.

**The canvas↛ui cycle prevention**: `SliceControlsFrame` knows nothing about `CanvasViewSlice`. The Apply button's `command=` callback is `lambda: canvas_view_slice.apply_plane(slice_controls.build_plane())`, set in `CanvasTabController._build_tabs()`. This is the only wiring point; it lives in `ui/canvas_tabs.py` which is in `ui/` and is allowed to import both.

---

## 11. Dependency Graph Edge Table (full, all 10 types)

| Object type | Forward edges (`_deps[obj_id]`) | Cascade note |
|---|---|---|
| Point | `∅` | Deleting a Point cascades to all dependents |
| Line | `{point_a_id, point_b_id}` | |
| Polygon | `set(point_ids)` | Deleting a Polygon cascades to any Solid referencing it |
| Ray | `{origin_id}` | |
| Vector | `{origin_id}` ∪ (`{endpoint_id}` if set) | |
| Circle | `{center_id}` | Deleting a Circle cascades to Tangents with shape_type="circle" |
| Ball | `{center_id}` | Deleting a Ball cascades to Tangents with shape_type="ball" |
| Cylinder | `{base_center_id}` | No dependents beyond the base center |
| Solid | `set(layers)` (all Polygon and Point IDs) | No objects depend on Solid |
| Tangent | `{shape_id, point_id}` | shape_id is the Circle or Ball ID |

---

## 12. Build Sequence for a Fresh Implementer

Implement in this order; each phase depends only on phases before it.

### Phase 1 — Foundation (no deps)
- [ ] `geometry/utils/constants.py` — add `EPS_ALTITUDE`, `EPS_VOLUME`
- [ ] `geometry/utils/angles.py` — already complete; no changes
- [ ] `geometry/utils/id_factory.py` — already complete; no changes
- [ ] `geometry/utils/events.py` — already complete; no changes

### Phase 2 — Models
- [ ] `geometry/models/common.py` — rename `DirectedObject` → `ElevatedObject` (no alias); add `elevation` field
- [ ] `geometry/models/point.py` — add required `altitude: float` field (no constructor default; loader injects 0.0)
- [ ] `geometry/models/line.py` — replace base class reference
- [ ] `geometry/models/ray.py` — replace base class reference
- [ ] `geometry/models/vector.py` — replace base class reference
- [ ] `geometry/models/tangent.py` — replace base class; replace `circle_id` → `shape_id`+`shape_type`
- [ ] `geometry/models/polygon.py` — no change
- [ ] `geometry/models/circle.py` — no change
- [ ] `geometry/models/ball.py` — NEW
- [ ] `geometry/models/cylinder.py` — NEW
- [ ] `geometry/models/solid.py` — NEW
- [ ] `geometry/models/slice_plane.py` — NEW
- [ ] `geometry/models/__init__.py` — update exports

### Phase 3 — Services (geometry engine)
- [ ] `geometry/services/geometry.py` — update `distance()` to 3D; update `vector_endpoint()` to 3D with `el`; add `_xyz()`, `elevation()`, all new 3D functions (Ball, Cylinder, Solid, convex_hull_3d, measurements)
- [ ] `geometry/services/validation.py` — full implementation (all 7 public validators)
- [ ] `geometry/services/dep_graph.py` — full implementation
- [ ] `geometry/services/commands.py` — full implementation
- [ ] `geometry/services/slice.py` — NEW; full implementation
- [ ] `geometry/services/render.py` — full implementation (all three builders)

### Phase 4 — Project + Persistence
- [ ] `geometry/project.py` — full implementation
- [ ] `geometry/persistence/schema.py` — version check + unknown-key extraction
- [ ] `geometry/persistence/serializer.py` — full round-trip for all 10 types

### Phase 5 — Canvas
- [ ] `geometry/canvas/canvas_view.py` — 2D flat blit canvas
- [ ] `geometry/canvas/canvas_view_3d.py` — NEW; 3D Axes3D canvas
- [ ] `geometry/canvas/canvas_view_slice.py` — NEW; Slice blit canvas + `apply_plane()`
- [ ] `geometry/canvas/interaction.py` — click-capture state machine

### Phase 6 — UI
- [ ] `geometry/ui/canvas_tabs.py` — NEW; `CanvasTabController` wiring all three tabs
- [ ] `geometry/ui/slice_controls.py` — NEW; `SliceControlsFrame`
- [ ] `geometry/ui/main_window.py` — three-column layout, menus, keyboard shortcuts
- [ ] `geometry/ui/cards.py` — `ReferencePointWidget`, collapsible cards, left panel
- [ ] `geometry/ui/dialogs.py` — all 10 object forms + import dialogs + cascade-delete dialog
- [ ] `geometry/ui/properties_panel.py` — auto-measurements per type

### Phase 7 — Tests (incrementally alongside each phase)
- [ ] `tests/test_models.py` — dataclass construction, defensive copy, type guard
- [ ] `tests/test_utils.py` — angle conversions, ID factory, event bus
- [ ] `tests/test_geometry.py` — update for 3D `distance()`, 3D `vector_endpoint()`, new functions
- [ ] `tests/test_validation.py` — all 7 validators
- [ ] `tests/test_dep_graph.py` — register/unregister/transitive BFS
- [ ] `tests/test_commands.py` — undo/redo for each command class
- [ ] `tests/test_slice.py` — plane membership, segment intersection, project_to_plane_axes
- [ ] `tests/test_serializer.py` — round-trip all 10 types; unknown-key passthrough; altitude/elevation default-injection on load

---

## 13. Risks, Edge Cases, and Open Problems

### 13.1 Zero-length vector
`vector_endpoint()` with `length=0` produces the origin point as the endpoint. Validation in `VectorFormDialog` must reject `length <= 0`. The geometry module does not guard against it (documented in the `vector_endpoint` docstring as a caller responsibility, same as the existing 2D version).

### 13.2 Vertical cylinder azimuth degeneracy
When `axis_mode = "vertical"`, `axis_azimuth` is meaningless. The model stores it as `0.0`; the form hides the azimuth field. `cylinder_axis_vector()` must short-circuit to `(0, 0, 1)` when `axis_mode == "vertical"`, never computing `sin(axis_azimuth) * cos(axis_elevation)` which would return `0*cos(π/2)` — a numerically fragile path.

### 13.3 Ball cross-section outside radius
`ball_cross_section_radius(r, d)` returns `None` when `|d| > r`. The Slice renderer must skip the ball entirely in this case rather than passing a negative radicand to `sqrt`. The caller checks for `None` before emitting a `SliceGeometry`.

### 13.4 Custom slice-plane normalization
The `SliceControlsFrame.build_plane()` must normalize `(a, b, c)` before constructing `SlicePlane`. If `sqrt(a²+b²+c²) == 0` (all zeros), raise `ValueError` with a user-visible message. Never silently construct a `SlicePlane` with a zero normal — the `EPS_ALTITUDE` tolerance only holds when the normal is unit length.

### 13.5 Polygon winding under 2D projection of 3D points
All existing polygon operations (CCW winding, signed area, convexity, simplicity) operate on `(easting, northing)` only — they ignore altitude. This is correct and intentional. However, a polygon whose points have varying altitudes will render as a non-planar quadrilateral in the 3D view. GeoSketch does not enforce planarity for Polygon objects; that constraint applies only to the vertical-prism measurement (which explicitly documents that "area" is the 2D shoelace area). The Solid type is the correct model for arbitrary 3D planar faces.

### 13.6 Tangent `shape_type` dispatch
`Tangent` binds to a Circle or a Ball, distinguished only by `shape_type`. Every consumer must branch on it: validation (`validate_circle_tangent_point` vs `validate_ball_tangent_point`/`validate_ball_tangent_perpendicular`), the geometry that computes/redraws the tangent line, and the properties panel. A `shape_type` that disagrees with the actual type of `shape_id` (e.g. `shape_type="ball"` pointing at a `ci_` ID) is a corrupt object — load validation must verify `objects[shape_id].type == shape_type` and reject the file otherwise. There is no `circle_id` field anywhere in the schema (pre-release; removed outright), so no legacy-key handling is needed.

### 13.7 3D convex hull open problem — coplanar degenerate case
`scipy.spatial.ConvexHull` (QHull — the Quickhull algorithm, Barber et al. 1996; §14) raises `QhullError` if all input points are coplanar in 3D. `convex_hull_3d()` must catch this and fall back to 2D hull + degenerate Solid. The degenerate Solid (two identical Polygon layers at the same altitude) has zero volume — detected via `validate_solid_non_degenerate(volume)` against `EPS_VOLUME` (`|volume| < EPS_VOLUME`). This is a recognized, correct outcome rather than a crash, but it should be surfaced to the user with a warning dialog rather than silently creating an invisible zero-extent Solid.

### 13.8 Solid Mirtich algorithm — winding order for B-rep faces
The Mirtich (1996) algorithm (§14) requires consistent outward-facing normals on all faces of the closed B-rep. When building the B-rep from the layer stack: bottom cap faces use the polygon's CCW order (as stored); top cap faces reverse the winding (to face upward/outward); lateral faces are wound from the correspondence between adjacent layer vertices. If adjacent polygon layers have different vertex counts, the fan triangulation must also produce consistent outward normals. A sign error in any face normal flips the contribution of that face and produces a wrong volume. Test with a unit cube (known volume = 1) and a tetrahedron (volume = base_area * height / 3).

### 13.9 EventBus listener retention
The `EventBus` holds subscribers strongly (confirmed by implementation). UI components that subscribe in `__init__` must call `bus.unsubscribe(event, handler)` in their teardown path. `CanvasTabController.teardown()` calls `teardown()` on all three canvas views; `MainWindow` calls `canvas_tabs.teardown()` on window close. Failure to unsubscribe causes dead-widget callbacks after tkinter destroys the widget, producing `TclError` on the next event fire.

### 13.10 `direction_unit_vector()` is 2D — intentional
`direction_unit_vector(obj)` returns a 2D `(e, n)` unit vector. It is used by `ray_polygon_distance()`, which is a 2D operation (ray-polygon in the horizontal plane). For the 3D view, rays are rendered using `(sin(az)*cos(el), cos(az)*cos(el), sin(el))` — this computation lives in `build_3d_instructions()` and does not go through `direction_unit_vector()`. Do not change `direction_unit_vector()` to 3D; doing so would break the 2D ray-polygon distance calculation.

### 13.11 `distance()` is now 3D — test impact
The existing test suite for `geometry.py` calls `distance()` on Points without altitude. After the change, those calls still pass because `altitude` defaults to `0.0` and `sqrt(Δe² + Δn² + 0²) == sqrt(Δe² + Δn²)`. No test changes are required for existing test cases, but new test cases must verify the 3D formula with non-zero altitudes.

### 13.12 `convex_hull_3d` allocates new Polygon IDs
`convex_hull_3d()` accepts the `IDFactory` as a parameter and calls `next_id()` internally to mint the required Polygon and Solid IDs. This is the one permitted case where a service function mints IDs rather than the command layer. It is the correct choice here because the number of hull facets is not known until QHull runs; requiring the caller to pre-allocate would force either a double-QHull pass (count facets, allocate, compute) or a complicated count-then-allocate-then-pass protocol. `IDFactory` lives in `utils/`, so this injection is legal under the layer rules (services may import `utils/`). Callers (command layer) pass `project.id_factory` as the argument.

---

## 14. Algorithm references (local copies)

The non-trivial geometric algorithms are backed by papers stored in `docs/articles/`. Each link is relative to this document (which lives in `docs/`).

| Algorithm | Used by | Role | Paper (local) |
|---|---|---|---|
| **Quickhull** — Barber, Dobkin & Huhdanpaa 1996 | `convex_hull` (2D) and `convex_hull_3d` (3D), via `scipy.spatial.ConvexHull` (QHull is the Quickhull implementation) | Primary | [The Quickhull Algorithm for Convex Hulls](articles/The%20Quickhull%20Algorithm%20for%20Convex%20Hulls.pdf) |
| **Polyhedral mass properties** — Mirtich 1996 | `solid_volume_centroid` (B-rep → divergence-theorem pass; see §13.8) | Primary | [Fast and accurate computation of polyhedral mass properties](articles/Fast%20and%20accurate%20computation%20of%20polyhedral%20mass%20properties.pdf) |
| **Stable polygon/polyhedron form factor** — Wuttke 2021 | `solid_volume_centroid` | Volume **cross-check only** (Eq. 22), not the primary computation | [Numerically stable form factor of any polygon and polyhedron](articles/Numerically%20stable%20form%20factor%20of%20any%20polygon%20and%20polyhedron.pdf) |

Two further algorithms are cited in the spec/design but have **no local paper** in `docs/articles/` (noted so the gap is explicit):

- **Convex skull / potato-peeling** — Chang & Yap 1986 (O(n⁷) exact); used by the 2D convex-skull operation. No local copy.
- **CudaHull** — Stein, Geva & El-Sana 2012; referenced only as a future GPU option, not implemented. No local copy.

---

The above is the complete implementation design document.

**Files directly referenced**:
- `/home/david/VS Code Projects/Geometry/geometry/models/common.py` — `ElevatedObject` replaces `DirectedObject`; `elevation` field added
- `/home/david/VS Code Projects/Geometry/geometry/models/point.py` — required `altitude: float` added after `northing` (no default; loader/form supply 0.0)
- `/home/david/VS Code Projects/Geometry/geometry/models/tangent.py` — `circle_id` → `shape_id` + `shape_type`; base class → `ElevatedObject`
- `/home/david/VS Code Projects/Geometry/geometry/models/__init__.py` — exports Ball, Cylinder, Solid, SlicePlane
- `/home/david/VS Code Projects/Geometry/geometry/utils/constants.py` — `EPS_ALTITUDE = 1e-6`, `EPS_VOLUME = 1e-9` added
- `/home/david/VS Code Projects/Geometry/geometry/services/geometry.py` — `distance()` goes 3D; `vector_endpoint()` gains `el` param; ~12 new functions
- `/home/david/VS Code Projects/Geometry/geometry/services/validation.py` — full implementation from stub
- `/home/david/VS Code Projects/Geometry/docs/geo-sketch-design.md` — this document supersedes it (do not delete the old file; it is referenced by existing issues)

**New files to create**:
- `/home/david/VS Code Projects/Geometry/geometry/models/ball.py`
- `/home/david/VS Code Projects/Geometry/geometry/models/cylinder.py`
- `/home/david/VS Code Projects/Geometry/geometry/models/solid.py`
- `/home/david/VS Code Projects/Geometry/geometry/models/slice_plane.py`
- `/home/david/VS Code Projects/Geometry/geometry/services/slice.py`
- `/home/david/VS Code Projects/Geometry/geometry/canvas/canvas_view_3d.py`
- `/home/david/VS Code Projects/Geometry/geometry/canvas/canvas_view_slice.py`
- `/home/david/VS Code Projects/Geometry/geometry/ui/canvas_tabs.py`
- `/home/david/VS Code Projects/Geometry/geometry/ui/slice_controls.py`
- `/home/david/VS Code Projects/Geometry/docs/implementation-design.md` (this document, to be saved verbatim)
