# GeoSketch Design Document

## Overview

GeoSketch is a Python desktop geometry application for creating, visualizing, and analyzing geometric objects in UTM coordinates. Points carry an optional altitude (Z) value (defaulting to 0), enabling a 3D view tab and a general-plane Slice view tab alongside the primary 2D flat view. It is a data-driven CAD-like tool with strong geometric correctness, a render-on-demand canvas model, and a UI guided by `spec/design/geometry-app-ui-ux.md`.

This design targets an Apache 2.0-compatible Python stack. All libraries are permissively licensed and selected for correctness, performance, and low maintenance cost at expected scene sizes (tens to low hundreds of objects).

---

## Technology Stack

### Chosen libraries

| Library | Version | Role | License |
|---------|---------|------|---------|
| `numpy` | `>=2.0` | float64 arithmetic, vectorized operations | BSD-3 |
| `matplotlib` | `>=3.8` | embedded 2D canvas, navigation toolbar | PSF |
| `tkinter` / `ttk` | stdlib | desktop UI, forms, dialogs | Python stdlib |
| `shapely` | `>=2.0` | polygon validity, intersection, distance | BSD |
| `scipy` | `>=1.13` | convex hull (QHull), spatial indexing | BSD-3 |

### Performance rationale

**shapely 2.x over 1.x**: The 2.x series rebuilt the Python bindings with a vectorized GEOS API and `STRtree` spatial indexing. The new API calls into GEOS directly from NumPy arrays, eliminating per-object Python overhead. For this project's scene sizes the throughput improvement is secondary; the primary reason to pin `>=2.0` is that the 1.x API is EOL and the 2.x shape-method names are cleaner.

**scipy for convex hull**: `scipy.spatial.ConvexHull` uses QHull (C library, O(n log n) expected). Critically, it returns vertex indices into the original point array, making it trivial to build the hull polygon from existing Point IDs without creating new point objects. `shapely.convex_hull` computes the same geometry but returns a new coordinate array that must then be matched back to existing Point objects — expensive and error-prone. Use `scipy` here.

**matplotlib blitting for selection highlight**: matplotlib redraws are expensive (~50–200 ms for a scene of 50 objects). Selection changes should never trigger a full redraw. Instead, `canvas_view.py` uses matplotlib's **blit API**: the background buffer (all non-selected geometry) is saved once after a full refresh; when selection changes, the buffer is restored and only the highlight artists are drawn and blitted. This reduces selection-highlight latency to <5 ms.

**No numba**: JIT warm-up cost (~1 s for the first call per function) would hurt responsiveness on first use. Scene sizes never justify it. Use NumPy vectorization for any tight loops.

**No jax**: Out-of-scope overhead.

### Library license compatibility

All selected libraries carry BSD-3 or equivalent licenses, which are compatible with Apache 2.0 for application distribution.

---

## Package Layout

```
geometry/               ← main package
  __init__.py
  __main__.py           ← entry point (geometry.__main__:main per pyproject.toml)
  project.py            ← Document/Project: object store, selection, dirty state

  models/               ← pure data classes only — no geometry logic
    __init__.py
    common.py           ← GeoObject base, color/visibility fields, enum definitions
    point.py
    line.py
    polygon.py
    ray.py
    vector.py
    circle.py           ← 2D flat circle (always horizontal)
    ball.py             ← 3D sphere
    cylinder.py         ← 3D cylinder with axis orientation
    solid.py            ← 3D layered solid; references ordered list of Polygon/Point IDs
    tangent.py
    slice_plane.py      ← SlicePlane dataclass (ephemeral view state; not a GeoObject, not persisted)

  services/             ← all business logic; zero tkinter/matplotlib imports
    __init__.py
    geometry.py         ← direction, distance, intersection, area, perimeter, convex skull
    validation.py       ← polygon simplicity, tangent membership, tolerance checks
    commands.py         ← undoable command classes and the 100-slot ring-buffer history
    render.py           ← produces RenderInstruction lists from model objects (no matplotlib)
    dep_graph.py        ← reverse-reference graph for O(1) cascade delete/recompute
    slice.py            ← slice-plane geometry: plane definition, point membership, segment intersection

  canvas/               ← matplotlib integration
    __init__.py
    canvas_view.py      ← CanvasView base: 2D flat tab — FigureCanvasTkAgg, blit strategy, stale tracking
    canvas_view_3d.py   ← CanvasView3D: 3D tab (Axes3D, full-redraw on selection — no blit)
    canvas_view_slice.py ← CanvasViewSlice: Slice tab canvas — exposes apply_plane(SlicePlane); knows nothing about SliceControlsFrame
    interaction.py      ← click-capture state machine (routes to active tab's CanvasView)

  ui/                   ← tkinter widgets; calls services, never calls geometry directly
    __init__.py
    main_window.py      ← three-column layout, menu, toolbar, status bar
    canvas_tabs.py      ← CanvasTabController (ttk.Notebook): owns 3 CanvasView instances + SliceControlsFrame; wires Apply button → CanvasViewSlice.apply_plane(); tab-switch stale logic
    slice_controls.py   ← SliceControlsFrame: Z-level entry + slider + plane-mode radios + Apply
    dialogs.py          ← create/edit dialogs for all 7 types, import dialogs
    properties_panel.py ← right-panel selection details
    cards.py            ← left-panel collapsible cards

  persistence/          ← JSON serialization; no tkinter
    __init__.py
    serializer.py       ← Document → JSON dict and back
    schema.py           ← version checking, unknown-key passthrough

  utils/                ← shared utilities; no geometry logic, no tkinter
    __init__.py
    constants.py        ← EPS_DISTANCE, EPS_ANGLE, EPS_AREA, EPS_PARAM, EPS_ALTITUDE
    angles.py           ← azimuth ↔ angle ↔ radians ↔ degrees conversions
    id_factory.py       ← per-type counter, ID generation, counter reseeding on load
    events.py           ← lightweight synchronous event bus

tests/                  ← pytest suite
main.py                 ← thin shim for `python main.py` during development only
pyproject.toml
requirements.txt        ← numpy, matplotlib, shapely, scipy
requirements-dev.txt    ← adds ruff, pytest, flake8, pylint
```

> **Entry-point note**: `pyproject.toml` declares `geosketch = "geometry.__main__:main"`, so the real entry point is `geometry/__main__.py`. The root `main.py` is a convenience shim (`from geometry.__main__ import main; main()`) for running with `python main.py` during development. Do not move startup logic into `main.py`.

---

## Architecture

### Layer rules

```
┌─────────────────────────────────────────┐
│  ui/  +  canvas/                        │  calls services; never imports shapely/numpy directly
├─────────────────────────────────────────┤
│  project.py                             │  owns object store, selection, history
├─────────────────────────────────────────┤
│  services/                              │  geometry, validation, commands, dep_graph, render
├─────────────────────────────────────────┤
│  models/                                │  pure data; no logic, no imports above utils/
├─────────────────────────────────────────┤
│  persistence/   utils/                  │  no cross-layer imports
└─────────────────────────────────────────┘
```

- `ui/` and `canvas/` may import from `services/`, `models/`, `utils/`, and `project.py`.
- **`canvas/` must NOT import from `ui/`** — `ui/` already imports `canvas/`, so the reverse creates a cycle. Coordination between canvas views and UI controls is done via callbacks wired in `ui/canvas_tabs.py`.
- `services/` may import `models/` and `utils/` only.
- `persistence/` imports `models/` and `utils/` only.
- Nothing below `project.py` imports `tkinter` or `matplotlib`.

### Data flow

1. **Object creation/update**: dialog validates inputs → calls command (`services/commands.py`) → command calls `services/geometry.py` + `services/validation.py` → mutates `project.py` object store → fires `object_created` / `object_modified` on event bus → `project.py` marks canvas stale
2. **Selection**: canvas click or list click → `project.py.select(id)` → fires `selection_changed` → properties panel refreshes → canvas_view blits selection highlight (no full redraw)
3. **Canvas full refresh**: explicit user action or viewport change → `canvas_view` calls `services/render.py` to get `RenderInstruction` list → draws all visible objects → saves background buffer for blitting → clears stale indicator
4. **Cascade delete**: command calls `dep_graph.dependents_of(id)` to collect full closure → confirmation dialog lists them → user confirms → single command removes all; undo restores all
5. **Persistence**: save/load uses `persistence/serializer.py` ↔ `project.py`; no UI involvement

---

## Dependency Graph (`services/dep_graph.py`)

The dependency graph enables O(|affected|) cascade operations instead of O(|all objects|) linear scans.

### Structure

```python
# Forward edges: what this object depends on
_deps: dict[str, set[str]]   # obj_id → {dependency_id, ...}

# Reverse edges: what depends on this object  
_rdeps: dict[str, set[str]]  # obj_id → {dependent_id, ...}
```

When creating an object, register its dependencies (e.g., a Line depends on `point_a_id` and `point_b_id`). When deleting, call `dependents_of(id)` which walks `_rdeps` via BFS to collect the full transitive closure of dependents.

### Update rules

- `register(obj_id, dep_ids)` — called by every create command after the object is added to the store
- `unregister(obj_id)` — called by every delete command; removes the object from both maps and prunes edges
- `dependents_of(obj_id) → set[str]` — returns all objects transitively dependent on `obj_id`

Dependency edges by type:
- Point → none
- Line → {point_a_id, point_b_id}
- Polygon → set(point_ids)
- Ray → {origin_id}
- Vector → {origin_id} ∪ ({endpoint_id} if set)
- Circle → {center_id}
- Ball → {center_id}
- Cylinder → {base_center_id}
- Solid → set(layers)  (all referenced Polygon and Point IDs)
- Tangent → {shape_id, point_id}
- Intersection-derived Point → the two parent object IDs that generated it

---

## Event Bus (`utils/events.py`)

A minimal synchronous publish-subscribe bus. Components subscribe to named events; the model fires them. This decouples model mutations from UI refreshes and avoids callback spaghetti.

```python
# usage
bus.subscribe("canvas_stale", status_bar.show_stale_indicator)
bus.subscribe("selection_changed", properties_panel.refresh)
bus.subscribe("object_deleted", cards.rebuild_lists)
bus.fire("canvas_stale")
```

### Defined events

| Event | Payload | Fired by |
|-------|---------|---------|
| `object_created` | `obj_id: str` | create command |
| `object_modified` | `obj_id: str` | modify command |
| `object_deleted` | `obj_ids: list[str]` | delete command (full cascade set) |
| `selection_changed` | `obj_id: str \| None` | project.py |
| `canvas_stale` | — | project.py on any model mutation |
| `project_loaded` | — | project.py after load completes |
| `history_changed` | `can_undo: bool, can_redo: bool` | command history |

Keep the bus synchronous. Async dispatch is not needed; tkinter is single-threaded and all handlers run in the main loop.

---

## Model Design

### Common object envelope (`models/common.py`)

```python
@dataclass
class GeoObject:
    id: str
    name: str
    type: str          # "point", "line", etc.
    alpha: float       # [0.0, 1.0]
    visibility: bool
```

Point extends GeoObject with `color`. All other types extend GeoObject with `line_color` + `fill_color`.

`GeoObject` is treated as abstract: its `__post_init__` raises `TypeError` if `type(self) is GeoObject`, so callers cannot construct a base object with an arbitrary `type` string. Every concrete subclass pins `type` to its canonical literal via `field(init=False, default="<type>")`.

### Enumerations

```python
class DirectionMode(Enum):
    AZIMUTH = "azimuth"
    ANGLE = "angle"

class DirectionUnits(Enum):
    RADIANS = "radians"
    DEGREES = "degrees"
```

In-memory: `DirectionMode.AZIMUTH`. JSON wire: `"azimuth"`. Serialization lowercases the `.value`; deserialization is case-insensitive and always re-saves canonical lowercase.

### Object specifics

| Type | Key fields |
|------|-----------|
| Point | `easting: float`, `northing: float`, `altitude: float` (default 0.0), `color: str` |
| Line | `point_a_id`, `point_b_id`, direction + elevation metadata |
| Polygon | `point_ids: list[str]` (CCW by 2D projection), `is_convex: bool` (cached) |
| Ray | `origin_id`, direction + elevation metadata |
| Vector | `origin_id`, `length: float`, `endpoint_id: str \| None`, direction + elevation metadata |
| Circle | `center_id`, `radius: float` — 2D flat, always horizontal |
| Ball | `center_id`, `radius: float` — 3D sphere |
| Cylinder | `base_center_id`, `radius: float`, `height: float`, `axis_mode`, `axis_azimuth`, `axis_elevation`, direction metadata |
| Solid | `layers: list[str]` (ordered Polygon/Point IDs, bottom→top; ≥ 2 entries; ≤ 1 Point) |
| Tangent | `shape_id` (Circle or Ball), `shape_type`, `point_id`, direction + elevation metadata |

Direction metadata = `direction: float` (radians) + `direction_mode: DirectionMode` + `direction_units: DirectionUnits`.

### Immutability convention

Model objects are mutable dataclasses (allows in-place undo). Commands snapshot the before-state when constructed so they can restore it on `undo()`. Do not mutate model objects outside of command `do()` / `undo()`.

In particular, `Polygon.point_ids` is a plain mutable `list[str]`. It must only be modified by `ModifyPolygonVerticesCommand`; nothing else should append, remove, or reorder elements directly. The `Polygon` constructor defensively copies the supplied list (`self.point_ids = list(self.point_ids)`), so two polygons constructed from the same source list never share storage — undo snapshots and command-time mutations therefore cannot leak across polygons.

`dataclasses.replace()` caveat for command authors: `replace(some_point, easting=5.0)` works as expected, but `replace(some_point, type="other")` raises `TypeError` because every concrete subclass declares `type` as `init=False`. This is correct behaviour — `type` is a *construction-time* invariant, pinned by each subclass's `field(init=False, default=...)`. Note that the dataclass is not frozen, so a raw `obj.type = "other"` assignment is still legal at the Python level; nothing in the runtime guards against it. Treat `type` as read-only by convention (the command layer never writes to it), and prefer subclass identity (`isinstance(obj, Point)`) over `obj.type` when the difference matters in code that has to defend itself.

`Line.direction` is authoritative only for UI round-trip (preserving the user's authoring convention). The geometric direction of a `Line` segment is fully determined by `point_a_id` and `point_b_id` coordinates and must be (re)computed from them — moving either endpoint via `MovePointCommand` would otherwise leave the stored `direction` stale. The cascading-update rule (point-move-recompute via `dep_graph`) is responsible for re-recording `Line.direction` whenever an endpoint moves; `Ray`, `Vector`, and `Tangent` do not have this concern because their `direction` is a primary input, not a derived value.

`Polygon.is_convex` follows the same single-writer convention as `point_ids`: it must only be updated by the services layer (specifically `PolygonService.create()` and `ModifyPolygonVerticesCommand.do()`/`undo()`). Nothing else should write to it directly — UI code and other commands must treat it as read-only and let the services layer re-cache it after any vertex change.

---

## Geometry Services (`services/geometry.py`)

### Core operations and implementation choices

| Operation | Implementation | Notes |
|-----------|---------------|-------|
| Azimuth | `np.arctan2(Δe, Δn)` normalized to [0,2π) | NumPy for float64 semantics |
| Euclidean distance | `np.hypot(Δe, Δn)` | Numerically stable |
| Point-in-polygon | `shapely.contains` | GEOS; handles edge cases |
| Polygon simplicity | `shapely.is_simple` | GEOS Bentley-Ottmann; O(n log n) |
| Polygon signed area | Shoelace via `np.dot` | Vectorized; also provides CCW sign |
| Convexity | Cross-product on consecutive triplets via `np.cross` | Vectorized over vertex array |
| 2D convex hull | `scipy.spatial.ConvexHull` on (E, N) | Returns vertex indices → hull polygon reuses existing Point IDs. Quickhull, Barber et al. 1996. |
| 3D convex hull | `scipy.spatial.ConvexHull` on (E, N, Z) | Returns triangular facets → hull stored as a Solid. Same Quickhull implementation. CudaHull (Stein et al. 2012) noted for GPU-scale future use. |
| 2D convex skull | O(n^7) exact for n ≤ 12; approximation for larger | Chang & Yap 1986. **2D planar polygons only.** 3D skull: open problem, to be added. |
| Cylinder volume | `π r² h` | Exact for any axis orientation |
| Solid volume + centroid | Mirtich (1996) O(n) polyhedral mass algorithm | Layer stack → closed B-rep (polygon caps + triangulated lateral faces) → divergence theorem reduction. Cross-check: Vol = ⅓ Σₖ Ar(Γₖ)·r_⊥ₖ (Wuttke 2021, Eq. 22). For two congruent parallel layers the volume simplifies to base_area × height (Wuttke 2021, §3.5). |
| Line-line intersection | Parametric solve with `np.linalg.solve` | Returns None for parallel |
| Line-polygon intersections | `shapely.intersection` on each edge | GEOS handles all edge cases |
| Polygon-polygon intersections | `shapely.intersection` on boundary geometries | GEOS |
| Ray-polygon distance | Parametric ray + shapely boundary intersection | Custom: filters t ≥ 0 |
| Point-polygon distance | `0 if shapely.contains else shapely.distance` | GEOS distance is exact |
| Polygon-polygon distance | `0 if shapely.intersects else shapely.distance` | GEOS distance |
| Tangent direction | `(atan2(Δe, Δn) + π/2) mod 2π` | Custom per spec formula |
| Vector endpoint | `(origin_e + L·sin(az)·cos(el), origin_n + L·cos(az)·cos(el), origin_z + L·sin(el))` | sin/cos swap is the azimuth convention; do not change |
| Three-point azimuth/elevation (angle at vertex B) | azimuth `= normalize_2π(atan2(C−B) − atan2(A−B))` on (E,N); elevation `= elev(B→C) − elev(B→A)` | Custom; ordered triple A,B,C, so `ABC ≠ CBA`. Azimuth ignores altitude; arms are B→A and B→C |

### Shapely integration pattern

Convert geometry to shapely objects only at the service boundary; keep models as plain dataclasses everywhere else. Create shapely geometries from the project's in-memory coordinates rather than from cached objects to avoid stale wrappers.

```python
# services/geometry.py pattern — create on demand, discard after use
def polygon_contains_point(pg: Polygon, pt: Point, points: dict[str, Point]) -> bool:
    coords = [(points[pid].easting, points[pid].northing) for pid in pg.point_ids]
    return shapely.contains(shapely.Polygon(coords), shapely.Point(pt.easting, pt.northing))
```

---

## Validation (`services/validation.py`)

| Rule | Method | Threshold |
|------|--------|-----------|
| Tangent point on circle | `abs(dist(pt, center) - radius) < EPS_DISTANCE` | `1e-6` m |
| Ball tangent point on sphere | `abs(distance_3d(pt, center) - radius) < EPS_DISTANCE` | `1e-6` m |
| Ball tangent perpendicular to radius | `abs(np.dot(dir_unit, rad_unit)) < EPS_ANGLE` | `1e-9` rad |
| Lines parallel | `abs(np.cross(d1, d2)) < EPS_ANGLE` | `1e-9` rad |
| Polygon non-degenerate | `abs(signed_area) >= EPS_AREA` | `1e-9` m² |
| Polygon simple | `shapely.is_simple(shapely.Polygon(coords))` | GEOS |
| Parametric clipping | segment `t ∈ [EPS_PARAM, 1 - EPS_PARAM]` | `1e-9` |
| Cylinder axis elevation | `axis_elevation > 0` (0 = degenerate flat disk, rejected) | strict |

All tolerance constants are imported from `utils/constants.py`; no bare literals in service code.

---

## Canvas Design (`canvas/`)

### Three-tab architecture

The center column hosts a `CanvasTabController` (`ui/canvas_tabs.py`, a `ttk.Notebook` subclass) that owns three independent canvas views. Each view has its own `matplotlib.figure.Figure`, `FigureCanvasTkAgg`, and `NavigationToolbar2Tk`. Only the active tab renders; inactive tabs are marked stale and redraw on activation.

| Tab | Class | Axes type | Blit support |
|---|---|---|---|
| 2D flat | `CanvasView` | `matplotlib.axes.Axes` | Yes — full blit strategy |
| 3D | `CanvasView3D` | `mpl_toolkits.mplot3d.Axes3D` | No — full redraw always |
| Slice | `CanvasViewSlice` | `matplotlib.axes.Axes` | Yes — same blit path as 2D |

`CanvasTabController` receives all event-bus events (`canvas_stale`, `project_loaded`, etc.) and marks all three tabs stale. It forwards selection events only to the active tab.

### Render-on-demand with blitting (2D flat and Slice tabs)

The full redraw path and the selection-highlight path are distinct:

**Full redraw** (trigger: Refresh button, pan/zoom, project load, window resize, tab activation when stale):
1. Clear the axes.
2. Fetch `RenderInstruction` list from `services/render.py` (2D or slice builder).
3. Draw all visible objects (respecting `visibility`, `alpha`, colors).
4. Save the background buffer: `bg = canvas.copy_from_bbox(ax.bbox)`.
5. Draw selection highlight if any.
6. `canvas.draw()` — full flush to screen.
7. Clear stale indicator.

**Selection-highlight update only** (trigger: selection changes):
1. `canvas.restore_region(bg)` — restore saved background.
2. Draw highlight artists for the newly selected object.
3. `canvas.blit(ax.bbox)` — push just the highlight to screen.
4. No geometry recompute, no redraw of other objects.

This keeps selection latency under 10 ms regardless of scene complexity.

### 3D tab rendering (`canvas/canvas_view_3d.py`)

`CanvasView3D` uses `Axes3D` and cannot use blitting (`Axes3D` does not implement `copy_from_bbox`). Both full redraws and selection changes trigger `canvas.draw()`. Default view: elevation 30°, azimuth 225°; preserved across redraws. Per-object rendering: Points → `ax.scatter`, line objects → `ax.plot([e1,e2],[n1,n2],[z1,z2])`, polygons → `Poly3DCollection`, vectors → `ax.quiver`, circles/tangents → parametric horizontal ring at center altitude. Axes labeled `Easting (m)`, `Northing (m)`, `Altitude (m)`.

### Slice tab controls (`ui/slice_controls.py`)

`SliceControlsFrame` is a `ttk.Frame` docked above the slice canvas. It exposes:
- **Plane mode** radio group: `Horizontal (Z=c)` / `Easting (E=c)` / `Northing (N=c)` / `Custom (aE+bN+cZ=d)`
- **Offset** numeric entry (the constant `c` or `d`) + slider auto-ranged to scene extents along that axis
- **Slab thickness** numeric entry (default 0 — exact plane)
- **Apply** button — builds a `SlicePlane` and calls `CanvasViewSlice.apply_plane(plane)` via a callback wired by `CanvasTabController`. `SliceControlsFrame` holds no reference to `CanvasViewSlice`; the wiring is entirely in `canvas_tabs.py`.

`SlicePlane` (in `models/slice_plane.py`) is a plain dataclass, not a `GeoObject`. It is ephemeral — never persisted.

### Render instructions (`services/render.py`)

`render.py` translates model objects into `RenderInstruction` dataclasses. No matplotlib or tkinter imports — pure data transformation, fully testable without a display.

```python
@dataclass
class RenderInstruction:
    kind: str              # "point", "line", "polygon", "arc", "arrow"
    coords: np.ndarray     # shape (N, 2) for 2D/slice; (N, 3) for 3D
    style: dict            # matplotlib artist kwargs
    obj_id: str
    is_3d: bool = False    # True → coords is (N, 3); consumer uses Axes3D calls
```

Three builder functions: `build_2d_instructions(objects, points)`, `build_3d_instructions(objects, points)`, `build_slice_instructions(slice_geoms)`. The slice builder consumes output from `services/slice.py`.

`services/slice.py` handles the plane geometry: `SliceGeometry` dataclass, `point_on_plane()`, `segment_plane_intersection()`, `slice_objects()`. No matplotlib or tkinter imports.

### Click interaction state machine (`canvas/interaction.py`)

```
IDLE
  ↓ user selects "Create Point" in click mode
AWAITING_1  (expecting first canvas click)
  ↓ click
IDLE + emit point coordinates

IDLE
  ↓ user selects "Create Line/Vector/Circle" in click mode
AWAITING_1
  ↓ click → store origin
AWAITING_2
  ↓ click → emit (origin, target)
IDLE

IDLE
  ↓ user selects "Create Polygon" in click mode
AWAITING_N  (collecting clicks until user double-clicks or presses Enter)
  ↓ double-click or Enter → emit vertex list
IDLE
```

The state machine is owned by `canvas_view.py`. On state transitions it updates cursor shape and a status-bar hint. The `ESC` key always returns to `IDLE` and discards the partial input.

---

## Undo/Redo (`services/commands.py`)

### Command protocol

```python
class Command(Protocol):
    def do(self) -> None: ...
    def undo(self) -> None: ...
    description: str   # shown in Edit menu tooltip
```

Each command captures the full before/after state it needs. Cascading deletes are a single `CascadeDeleteCommand` that stores the snapshot of every removed object and re-inserts them all on `undo()`.

### History ring buffer

```python
class CommandHistory:
    _buffer: deque[Command]   # maxlen=100
    _redo: list[Command]
```

Pushing a new command while `_redo` is non-empty discards the redo stack. When the buffer is full, the oldest command is silently dropped (becomes permanent). The history is not persisted; `project_loaded` clears it.

### Commands that must be undoable

- `CreateObjectCommand` (any type, any input mode)
- `DeleteObjectCommand` (wraps full cascade as a unit; undo restores all removed objects)
- `ModifyObjectCommand` (name, color, alpha, visibility, direction settings)
- `MovePointCommand` (easting/northing change + snapshot of all recomputed dependent values)
- `ModifyPolygonVerticesCommand` (vertex list change + cached `is_convex`)
- `BulkImportCommand` (point text import, polygon file import — entire batch is one command)

---

## Project (`project.py`)

`Project` is the central coordinator:

```python
class Project:
    objects: dict[str, GeoObject]    # id → object
    selection: str | None
    history: CommandHistory
    dep_graph: DependencyGraph
    is_dirty: bool
    metadata: ProjectMetadata        # title, created, lastModified

    def execute(self, cmd: Command) -> None: ...   # do() + push history + mark dirty + fire events
    def select(self, obj_id: str | None) -> None: ...
    def get_objects_of_type(self, type_name: str) -> list[GeoObject]: ...
```

`Project` depends on `services/` and `utils/events.py`. It does not import `tkinter` or `matplotlib`.

---

## Persistence (`persistence/`)

### Serializer (`persistence/serializer.py`)

- `save(project: Project) -> dict` — returns the JSON-serializable dict
- `load(data: dict) -> Project` — validates version, rebuilds objects, reseeds ID counters

Version policy:
- **Same major, same-or-lower minor** → load directly.
- **Same major, higher minor** → load with warning; unknown keys in objects are passed through verbatim on re-save (round-trip safety).
- **Different major** → reject with clear error.
- **Missing version field** → reject.

### ID allocation (`utils/id_factory.py`)

- Per-type counters: `{type_prefix: int}` (e.g. `"pt": 3` means next ID is `pt_004`)
- `next_id(type_prefix) → str` — atomically increments and returns the formatted ID
- `reseed(ids: list[str])` — on project load, finds the max `N` per type and sets counters above it

---

## UI Architecture (`ui/`)

### Main window (`ui/main_window.py`)

Three-column layout with PanedWindow or grid weights:

```
┌──────────────┬─────────────────────────┬──────────────┐
│  Left panel  │  [2D] [3D] [Slice]      │ Right panel  │
│  (280px)     │  ─────────────────────  │  (320px)     │
│              │  CanvasTabController    │              │
│  Cards:      │  (active tab's Figure   │  Properties  │
│  • Create    │   + NavigationToolbar)  │  panel for   │
│  • Import    │                         │  selection   │
│  • Calculate │  Slice tab also has     │              │
│  • Measure   │  SliceControlsFrame     │              │
│              │  above the canvas       │              │
└──────────────┴─────────────────────────┴──────────────┘
│  Status bar: filename | dirty | cursor (E, N[, Z]) | stale  │
└──────────────────────────────────────────────────────────────┘
```

### Dialog pattern

All 10 object-type dialogs share a common `ObjectFormDialog` base that provides:
- `Name` entry (full width, row 0)
- Color + alpha row(s) — Point gets one color picker; all others get `line_color` + `fill_color`
- Validation loop: validate-on-keystroke, inline error labels, Submit disabled until valid
- Edit mode: prefill all fields from the existing object

Dialogs are modal (`grab_set()`) and live in `ui/dialogs.py`. The same class handles create and edit (the caller passes an existing object or `None`).

### Reusable reference-point subcomponent

`ui/cards.py` contains `ReferencePointWidget(ttk.Frame)`: a checkbox labeled "Use reference point" + a combobox. When the checkbox is unchecked the combobox is disabled. Used in:
- Point text import dialog
- Polygon file import dialog
- Polygon `Enter Vertices` tab

This is the single source of truth; do not duplicate the logic.

---

## Deployment

### Requirements files

`requirements.txt`:
```
numpy>=2.0
matplotlib>=3.8
shapely>=2.0
scipy>=1.13
```

`requirements-dev.txt`:
```
-r requirements.txt
ruff>=0.6
pytest>=8.0
flake8>=7.0
pylint>=4.0
```

### Packaging

```toml
[project]
name = "geosketch"
requires-python = ">=3.14"
dependencies = ["numpy>=2.0", "matplotlib>=3.8", "shapely>=2.0", "scipy>=1.13"]
```

For standalone executables: `briefcase` (cross-platform, PyPI-compatible) preferred over `pyinstaller` because it integrates with `pyproject.toml` and handles the tkinter/matplotlib dependency bundle cleanly.

---

## Rationale for Key Choices

**Why `scipy` for convex hull and not `shapely`?**  
`shapely.convex_hull` returns a new geometry with new coordinates; to build the GeoSketch hull Polygon we need to map those coordinates back to existing Point IDs (or create new Point objects and reference them). `scipy.spatial.ConvexHull` returns indices into the original array directly — the hull Polygon is `[point_ids[i] for i in hull.vertices]` in one step, with no coordinate-matching roundtrip.

**Why a render-instruction intermediary (`services/render.py`)?**  
Separating geometry-to-instruction translation from instruction-to-matplotlib rendering makes the geometry engine testable without a display, allows swapping the rendering backend in the future, and keeps `services/` free of matplotlib imports.

**Why a synchronous event bus rather than direct callbacks?**  
Direct callbacks couple publishers to subscriber interfaces. With the bus, `project.py` fires `"canvas_stale"` without knowing that `canvas_view.py` or `status_bar` subscribes. This lets UI components be added, removed, or replaced without touching the model layer.

**Why `dep_graph.py` as a separate module?**  
The cascading delete and point-move-recompute logic involves the same reverse-reference traversal. Centralizing it avoids duplicating the graph walk in both the delete command and the modify-point command, and makes it straightforward to unit-test the traversal independently.

---

## Next Steps

The package structure, stubs, entry point, and CI gate are in place. Active work proceeds in this order:

1. Complete `services/geometry.py` — remaining operations: convex hull (2D + 3D), convex skull, polygon/polygon intersection, distance variants (point↔polygon, ray↔polygon, polygon↔polygon), Ball/Cylinder/Solid geometry.
2. Complete `services/validation.py` — Ball tangent perpendicularity, sphere-surface membership, Cylinder axis-elevation guard, Solid layer-count compatibility check.
3. Implement `services/dep_graph.py` with tests — reverse-reference graph, cascade delete and point-move-recompute traversals.
4. Implement `services/commands.py` with tests — command protocol, ring-buffer history, all six undoable command classes.
5. Implement `persistence/` with round-trip tests — serializer, version policy (1.1), unknown-type passthrough.
6. Implement `canvas/` (CanvasView 2D blit, CanvasView3D, CanvasViewSlice) and wire to services + event bus.
7. Scaffold `ui/` main window, cards, and dialogs for all 10 object types per the wireframe.
