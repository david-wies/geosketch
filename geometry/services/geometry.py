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

"""Pure geometric calculations for GeoSketch.

This module is the single home for every numeric geometry operation in the
app: direction (azimuth), Euclidean distance, polygon signed area and
convexity, convex hull, the direction unit vector, three intersection
functions (line–line, line–polygon, polygon–polygon), the ray-polygon
distance, the point/polygon and polygon/polygon distances, the tangent
direction, and the vector endpoint. It depends only on the model
dataclasses (:mod:`geometry.models`) and the math utilities
(:mod:`geometry.utils`); it imports neither ``tkinter`` nor ``matplotlib``.

Conventions
-----------
* Coordinates are UTM metres expressed as ``(easting, northing)`` — easting
  first. All coordinate arrays returned by this module follow that order.
* Scalar results are returned as :class:`numpy.float64` so they drop straight
  into further NumPy expressions without an implicit cast. Coordinate results
  are returned as ``numpy.ndarray`` of shape ``(2,)``.
* Functions that consume polygons or direction-bearing objects take a
  ``points`` mapping (``id -> Point``) and resolve coordinates on demand. No
  function caches geometry — shapely objects are built at the call boundary
  and discarded, per the design doc, so stale wrappers cannot accumulate.
* This module computes raw coordinates for intersections rather than minting
  new :class:`~geometry.models.point.Point` objects: ID allocation and object
  creation belong to the command layer. :func:`convex_hull` is the one
  exception — it returns a :class:`~geometry.models.polygon.Polygon` because
  the hull reuses the *existing* vertex Point IDs (no new points are created).

Notes
-----
NumPy 2.x deprecated ``np.cross`` on 2-D vectors, so the 2-D cross product is
computed explicitly via :func:`_cross2d` (``ux*vy - uy*vx``). The result is
mathematically identical to the deprecated call but emits no warning.

Failure contracts are **not uniform**. The intersection and distance
functions degrade gracefully — they return ``None`` (no unique line-line
intersection), ``[]`` (no boundary crossings), or ``numpy.float64(inf)`` (a
ray that misses) rather than raising. :func:`convex_hull` is the deliberate
exception: it *propagates* :class:`scipy.spatial.QhullError` on degenerate
input (collinear or too-few vertices), because a hull over a degenerate
polygon is undefined. Do not assume every function here degrades silently.

Referenced IDs are resolved via ``points[pid]`` and are **fail-loud**: a
function handed a polygon/line/ray that references a missing point ID raises
``KeyError`` rather than guessing or skipping. This is intentional — upstream
referential integrity (cascading delete, validation) is assumed to guarantee
that every referenced ID is present, so a ``KeyError`` here signals a bug in
that invariant, not a recoverable condition.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np
import shapely
from scipy.spatial import ConvexHull  # pylint: disable=no-name-in-module

from geometry.models.common import DirectedObject, DirectionMode
from geometry.models.line import Line
from geometry.models.point import Point
from geometry.models.polygon import Polygon
from geometry.models.ray import Ray
from geometry.utils.angles import azimuth_to_angle, normalize_to_2pi
from geometry.utils.constants import EPS_ANGLE, EPS_DISTANCE, EPS_PARAM

__all__ = [
    "azimuth",
    "distance",
    "signed_area",
    "is_convex",
    "convex_hull",
    "direction_unit_vector",
    "line_intersection",
    "line_polygon_intersections",
    "polygon_polygon_intersections",
    "ray_polygon_distance",
    "point_polygon_distance",
    "polygon_polygon_distance",
    "tangent_direction",
    "vector_endpoint",
]

_HALF_PI = math.pi / 2.0


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------


def _xy(point: Point) -> np.ndarray:
    """Return ``point`` as a ``float64`` ``(easting, northing)`` array."""
    return np.array([point.easting, point.northing], dtype=np.float64)


def _delta(a: Point, b: Point) -> tuple[np.float64, np.float64]:
    """Return ``(Δeasting, Δnorthing)`` from ``a`` to ``b`` as ``float64``.

    Centralises the ``b - a`` component subtraction used directly by
    :func:`azimuth` and :func:`distance` (and indirectly by
    :func:`tangent_direction` via :func:`azimuth`) so the easting-first
    convention lives in exactly one place.
    """
    return (
        np.float64(b.easting) - np.float64(a.easting),
        np.float64(b.northing) - np.float64(a.northing),
    )


def _cross2d(u: np.ndarray, v: np.ndarray) -> np.float64:
    """2-D scalar cross product ``ux*vy - uy*vx``.

    Used instead of ``np.cross`` because NumPy 2.x deprecated the 2-D form of
    ``np.cross``; the explicit determinant is identical and warning-free.
    """
    return np.float64(u[0] * v[1] - u[1] * v[0])


def _unit(v: np.ndarray) -> np.ndarray | None:
    """Return ``v`` scaled to unit length, or ``None`` if it is ~zero-length.

    A vector shorter than :data:`EPS_DISTANCE` has no well-defined direction
    (e.g. a duplicated vertex producing a zero-length edge), so callers treat
    ``None`` as "no direction".
    """
    norm = float(np.hypot(v[0], v[1]))
    if norm < EPS_DISTANCE:
        return None
    return v / norm


def _are_parallel(u: np.ndarray, v: np.ndarray) -> bool:
    """Whether directions ``u`` and ``v`` are parallel within :data:`EPS_ANGLE`.

    The test is performed on the **unit** directions, so ``|cross(û, v̂)| =
    |sin θ|`` and :data:`EPS_ANGLE` is a genuine angular tolerance rather than
    one that silently scales with the input vectors' magnitudes. A vector with
    no defined direction (``_unit`` returns ``None``) is treated as parallel to
    everything, which collapses degenerate inputs to the "no unique
    intersection" branch its callers already handle.
    """
    u_hat = _unit(u)
    v_hat = _unit(v)
    if u_hat is None or v_hat is None:
        return True
    return abs(_cross2d(u_hat, v_hat)) < EPS_ANGLE


def _polygon_coords(polygon: Polygon, points: Mapping[str, Point]) -> np.ndarray:
    """Resolve a polygon's vertices to an ``(N, 2)`` ``float64`` array."""
    return np.array(
        [[points[pid].easting, points[pid].northing] for pid in polygon.point_ids], dtype=np.float64
    )


def _shapely_polygon(polygon: Polygon, points: Mapping[str, Point]) -> shapely.Polygon:
    """Build a shapely polygon from the project's in-memory coordinates."""
    return shapely.Polygon(_polygon_coords(polygon, points))


def _line_endpoints(line: Line, points: Mapping[str, Point]) -> tuple[np.ndarray, np.ndarray]:
    """Return the two defining endpoints of ``line`` as coordinate arrays."""
    return _xy(points[line.point_a_id]), _xy(points[line.point_b_id])


# ---------------------------------------------------------------------------
# direction / distance
# ---------------------------------------------------------------------------


def azimuth(pt_a: Point, pt_b: Point) -> np.float64:
    """Azimuth from ``pt_a`` to ``pt_b`` in radians, normalised to ``[0, 2π)``.

    Azimuth is measured clockwise from North, so the easting delta is the
    first argument to ``arctan2`` and the northing delta the second
    (``atan2(Δe, Δn)``) — the swap relative to the standard math angle is
    intentional and matches the spec.

    Parameters
    ----------
    pt_a, pt_b : Point
        Start and end points.

    Returns
    -------
    numpy.float64
        Azimuth in radians in ``[0, 2π)``.
    """
    d_e, d_n = _delta(pt_a, pt_b)
    return normalize_to_2pi(np.arctan2(d_e, d_n))


def distance(pt_a: Point, pt_b: Point) -> np.float64:
    """Euclidean distance between two points via ``np.hypot`` (float64)."""
    d_e, d_n = _delta(pt_a, pt_b)
    return np.hypot(d_e, d_n)


# ---------------------------------------------------------------------------
# polygon scalars
# ---------------------------------------------------------------------------


def signed_area(polygon: Polygon, points: Mapping[str, Point]) -> np.float64:
    """Signed shoelace area of ``polygon`` (positive when CCW).

    Computed as ``0.5 * (e · roll(n, -1) - n · roll(e, -1))``. The sign
    encodes winding order — positive for counter-clockwise vertices — and is
    what the polygon-creation path uses to decide whether to reverse the
    boundary. The magnitude is the polygon's area; ``abs(signed_area(...))``
    compared against ``EPS_AREA`` is the degeneracy test.

    Returns
    -------
    numpy.float64
        Signed area in square metres.
    """
    coords = _polygon_coords(polygon, points)
    e = coords[:, 0]
    n = coords[:, 1]
    return np.float64(0.5) * (np.dot(e, np.roll(n, -1)) - np.dot(n, np.roll(e, -1)))


def is_convex(polygon: Polygon, points: Mapping[str, Point]) -> bool:
    """Return ``True`` if ``polygon`` is convex.

    Walks the consecutive edge pairs and takes the 2-D cross product of each
    pair of **unit** edge directions (so the comparison is ``sin θ`` and
    :data:`EPS_ANGLE` is a true angular tolerance regardless of edge length).
    A polygon is convex iff every turn has the same orientation (all cross
    products non-negative or all non-positive); near-collinear triplets
    (``|sin θ| < EPS_ANGLE``) are ignored so that redundant boundary vertices
    do not flip the result. Zero-length edges from duplicated vertices have no
    direction and are skipped.

    Returns
    -------
    bool
        ``True`` if convex, ``False`` if concave.
    """
    coords = _polygon_coords(polygon, points)
    if len(coords) < 3:
        return False
    edges = np.roll(coords, -1, axis=0) - coords  # edge[i] = V[i+1] - V[i]
    units = [_unit(edge) for edge in edges]
    n_edges = len(units)
    saw_positive = False
    saw_negative = False
    for i, u in enumerate(units):
        v = units[(i + 1) % n_edges]
        if u is None or v is None:
            continue  # zero-length edge (duplicate vertex) — no turn to classify
        cross = _cross2d(u, v)
        if cross > EPS_ANGLE:
            saw_positive = True
        elif cross < -EPS_ANGLE:
            saw_negative = True
        if saw_positive and saw_negative:
            return False
    return True


def convex_hull(polygon: Polygon, points: Mapping[str, Point], new_id: str) -> Polygon:
    """Return the convex hull of ``polygon`` as a new CCW polygon.

    Uses :class:`scipy.spatial.ConvexHull`, whose ``vertices`` attribute gives
    the indices of the hull points in counter-clockwise order. Those indices
    map back onto the original vertex Point IDs, so the hull reuses the
    existing points (no new geometry is minted) and its winding is CCW to
    match the storage convention. The result is named
    ``"<original_name>_convex_hull"`` and copies the source polygon's display
    attributes.

    Parameters
    ----------
    polygon : Polygon
        The source polygon.
    points : Mapping[str, Point]
        Point lookup covering every ID in ``polygon.point_ids``.
    new_id : str
        ID to assign to the returned hull polygon (allocated by the caller).

    Returns
    -------
    Polygon
        A new convex polygon over the subset of original vertices that lie on
        the hull, with ``is_convex=True``.

    Raises
    ------
    scipy.spatial.QhullError
        If the input is degenerate for hull construction (fewer than three
        vertices, or all vertices collinear). Unlike the intersection/distance
        functions — which degrade to ``None``/``inf``/``[]`` — this propagates
        the error, because a hull over a degenerate polygon is undefined. The
        polygon-creation path already rejects degenerate polygons
        (``|signed_area| < EPS_AREA``), so a well-formed source polygon never
        triggers this.
    """
    coords = _polygon_coords(polygon, points)
    hull = ConvexHull(coords)
    hull_point_ids = [polygon.point_ids[i] for i in hull.vertices]
    return Polygon(
        id=new_id,
        name=f"{polygon.name}_convex_hull",
        alpha=polygon.alpha,
        visibility=polygon.visibility,
        point_ids=hull_point_ids,
        is_convex=True,
        line_color=polygon.line_color,
        fill_color=polygon.fill_color,
    )


# ---------------------------------------------------------------------------
# direction vectors
# ---------------------------------------------------------------------------


def direction_unit_vector(obj: DirectedObject) -> np.ndarray:
    """Unit ``(easting, northing)`` vector for a direction-bearing object.

    ``obj.direction`` is stored in radians but means either an azimuth
    (CW from North) or a math angle (CCW from East) depending on
    ``obj.direction_mode``. This normalises both to a math angle and returns
    ``(cos θ, sin θ)`` in ``(easting, northing)`` order, which is consistent
    with the azimuth-based vector-endpoint formula
    (``(sin az, cos az) == (cos angle, sin angle)``).

    Returns
    -------
    numpy.ndarray
        Unit direction vector, shape ``(2,)``.

    Raises
    ------
    ValueError
        If ``obj.direction`` is not finite (``nan``/``inf``). Without this
        guard ``np.cos``/``np.sin`` would propagate ``nan`` into a
        ``[nan, nan]`` vector that silently poisons downstream callers (e.g.
        :func:`ray_polygon_distance` would return ``+∞``, indistinguishable
        from a legitimate miss). Failing loud here pins the corruption — most
        plausibly a malformed JSON deserialisation — to the right callsite.
    """
    if not math.isfinite(obj.direction):
        raise ValueError(
            f"direction_unit_vector: obj.direction is {obj.direction!r}; "
            "expected a finite radian value"
        )
    if obj.direction_mode is DirectionMode.AZIMUTH:
        angle = azimuth_to_angle(obj.direction)
    else:
        angle = np.float64(obj.direction)
    return np.array([np.cos(angle), np.sin(angle)], dtype=np.float64)


# ---------------------------------------------------------------------------
# intersections
# ---------------------------------------------------------------------------


def line_intersection(line_a: Line, line_b: Line, points: Mapping[str, Point]) -> np.ndarray | None:
    """Intersection point of two infinite lines, or ``None`` if parallel.

    Each line is treated as the infinite line through its two defining points.
    The intersection is found by the parametric solve
    ``A1 + t·d1 == A2 + s·d2`` via :func:`numpy.linalg.solve`. Parallelism is
    tested by :func:`_are_parallel`, which normalises both directions to
    **unit** vectors before taking the cross product, so the comparison is
    ``|sin θ|`` against :data:`EPS_ANGLE` — a genuine angular tolerance that
    does not scale with the input magnitudes, consistent with
    :func:`_are_parallel` and :func:`is_convex`. Parallel lines have no unique
    solution and return ``None``.

    Returns
    -------
    numpy.ndarray or None
        The ``(easting, northing)`` intersection, or ``None`` for parallel
        (including collinear) lines.
    """
    a1, b1 = _line_endpoints(line_a, points)
    a2, b2 = _line_endpoints(line_b, points)
    d1 = b1 - a1
    d2 = b2 - a2
    if _are_parallel(d1, d2):
        return None
    # Columns: [d1, -d2] · [t, s]^T = a2 - a1
    matrix = np.array([[d1[0], -d2[0]], [d1[1], -d2[1]]], dtype=np.float64)
    rhs = a2 - a1
    t, _s = np.linalg.solve(matrix, rhs)
    return a1 + t * d1


def _line_span(coords: np.ndarray, *extra: np.ndarray) -> float:
    """A length comfortably larger than the bounding box of all given coords."""
    stacked = np.vstack([coords, *(e.reshape(1, 2) for e in extra)])
    mins = stacked.min(axis=0)
    maxs = stacked.max(axis=0)
    diag = float(np.hypot(maxs[0] - mins[0], maxs[1] - mins[1]))
    return diag * 10.0 + 1.0


def _collect_points(geom) -> list[np.ndarray]:
    """Flatten a shapely intersection result into a list of coordinate arrays.

    Handles the geometry types that intersecting **1-D** geometries can yield:
    ``Point``/``MultiPoint`` (transversal crossings), ``LineString``/
    ``MultiLineString`` (collinear overlaps, whose endpoints are kept), and
    ``GeometryCollection`` (a mix of the above, flattened recursively). The two
    callers only ever feed it such results — ``_edge_crossings`` intersects a
    LineString with a LineString, and :func:`polygon_polygon_intersections`
    intersects two ring *boundaries* (1-D), never the filled polygons — so an
    areal ``Polygon``/``MultiPolygon`` cannot arise here. Any other type is
    therefore an unexpected-input bug and raises ``ValueError`` rather than
    being silently dropped.
    """
    if geom.is_empty:
        return []
    gtype = geom.geom_type
    if gtype == "Point":
        return [np.array([geom.x, geom.y], dtype=np.float64)]
    if gtype == "MultiPoint":
        return [np.array([p.x, p.y], dtype=np.float64) for p in geom.geoms]
    if gtype in ("LineString", "MultiLineString"):
        # Collinear overlap: keep the segment endpoints.
        out: list[np.ndarray] = []
        geoms = geom.geoms if gtype == "MultiLineString" else [geom]
        for ls in geoms:
            for x, y in ls.coords:
                out.append(np.array([x, y], dtype=np.float64))
        return out
    if gtype == "GeometryCollection":
        out = []
        for g in geom.geoms:
            out.extend(_collect_points(g))
        return out
    raise ValueError(f"unexpected intersection geometry: {gtype}")


def _dedup(pts: Sequence[np.ndarray]) -> list[np.ndarray]:
    """Drop points that coincide within :data:`EPS_DISTANCE`."""
    unique: list[np.ndarray] = []
    for p in pts:
        if not any(np.hypot(p[0] - q[0], p[1] - q[1]) < EPS_DISTANCE for q in unique):
            unique.append(p)
    return unique


def _extended_line(
    a: np.ndarray, b: np.ndarray, unit: np.ndarray, coords: np.ndarray
) -> shapely.LineString:
    """Stretch the segment ``a``→``b`` past ``coords`` to stand in for an infinite line."""
    span = _line_span(coords, a, b)
    return shapely.LineString([a - unit * span, b + unit * span])


def _edge_crossings(long_line: shapely.LineString, coords: np.ndarray) -> list[np.ndarray]:
    """Collect every point where ``long_line`` meets a polygon edge of ``coords``."""
    hits: list[np.ndarray] = []
    n = len(coords)
    for i, vertex in enumerate(coords):
        edge = shapely.LineString([vertex, coords[(i + 1) % n]])
        hits.extend(_collect_points(shapely.intersection(long_line, edge)))
    return hits


def line_polygon_intersections(
    line: Line, polygon: Polygon, points: Mapping[str, Point]
) -> list[np.ndarray]:
    """Points where an infinite line crosses a polygon boundary, ordered along the line.

    The line is extended well beyond the polygon and intersected with each
    polygon edge via :func:`shapely.intersection`. Results are de-duplicated
    (a line passing exactly through a vertex hits two edges) and ordered by
    their projection parameter along the line's direction, so the returned
    list reads in travel order from the line's first defining point toward the
    second. Note the ordering rule differs from
    :func:`polygon_polygon_intersections`, which orders lexicographically by
    ``(easting, northing)`` rather than along a travel direction.

    Returns
    -------
    list[numpy.ndarray]
        Ordered ``(easting, northing)`` crossings; empty if the line misses.
    """
    a, b = _line_endpoints(line, points)
    direction = b - a
    norm = float(np.hypot(direction[0], direction[1]))
    if norm < EPS_DISTANCE:
        return []
    unit = direction / norm
    coords = _polygon_coords(polygon, points)
    long_line = _extended_line(a, b, unit, coords)
    unique = _dedup(_edge_crossings(long_line, coords))
    unique.sort(key=lambda p: float(np.dot(p - a, unit)))
    return unique


def polygon_polygon_intersections(
    poly_a: Polygon, poly_b: Polygon, points: Mapping[str, Point]
) -> list[np.ndarray]:
    """Points where two polygon boundaries cross.

    Intersects the two boundary geometries via :func:`shapely.intersection`,
    de-duplicates, and returns the crossings ordered lexicographically by
    ``(easting, northing)`` for deterministic output. Note the ordering rule
    differs from :func:`line_polygon_intersections`, which orders along the
    line's travel direction; a caller expecting entry/exit pairing from this
    result should not assume that ordering here.

    Returns
    -------
    list[numpy.ndarray]
        Ordered ``(easting, northing)`` crossings; empty if the boundaries
        do not cross.
    """
    boundary_a = _shapely_polygon(poly_a, points).boundary
    boundary_b = _shapely_polygon(poly_b, points).boundary
    hits = _collect_points(shapely.intersection(boundary_a, boundary_b))
    unique = _dedup(hits)
    unique.sort(key=lambda p: (float(p[0]), float(p[1])))
    return unique


def _ray_edge_t(origin: np.ndarray, unit: np.ndarray, a: np.ndarray, b: np.ndarray) -> float | None:
    """Forward distance ``t`` where ray ``origin + t·unit`` meets segment ``a``→``b``.

    Because ``unit`` is a unit vector, ``t`` is a metric distance in metres,
    so the forward-hit gate uses :data:`EPS_DISTANCE` (the metric tolerance).
    The edge-span parameter ``s`` is dimensionless (``s ∈ [0, 1]`` spans the
    edge), so its clip uses the dimensionless :data:`EPS_PARAM`.

    Returns ``None`` when the ray is parallel to the edge, the hit is behind
    the origin (``t < -EPS_DISTANCE``), or it falls outside the edge span. A
    hit in the snap zone ``t ∈ [-EPS_DISTANCE, 0)`` — an origin sitting a
    sub-tolerance step outside the boundary — is clamped to ``0.0`` so the
    returned value is never negative, preserving the caller's "distance or
    ``+∞``" (non-negative) contract.
    """
    edge = b - a
    if _are_parallel(unit, edge):
        return None  # ray parallel to this edge
    # Solve origin + t*unit = a + s*edge  ->  [unit, -edge] · [t, s] = a - origin
    matrix = np.array([[unit[0], -edge[0]], [unit[1], -edge[1]]], dtype=np.float64)
    t, s = np.linalg.solve(matrix, a - origin)
    if t >= -EPS_DISTANCE and -EPS_PARAM <= s <= 1.0 + EPS_PARAM:
        return max(0.0, float(t))
    return None


def ray_polygon_distance(ray: Ray, polygon: Polygon, points: Mapping[str, Point]) -> np.float64:
    """Distance from a ray's origin to the nearest polygon-boundary hit.

    The ray is ``origin + t · direction`` with ``t ≥ 0`` and a unit direction
    vector, so ``t`` is the distance in metres. Each polygon edge is solved
    parametrically against the ray; only forward hits (``t ≥ -EPS_DISTANCE``,
    a metric tolerance because ``t`` is a distance) that land within the edge
    (the dimensionless span ``s ∈ [-EPS_PARAM, 1 + EPS_PARAM]``) count. The
    smallest such ``t`` is the answer; a ray that never meets the polygon
    returns ``+∞``.

    Returns
    -------
    numpy.float64
        Distance to the nearest intersection, or ``numpy.float64(inf)``.
    """
    origin = _xy(points[ray.origin_id])
    unit = direction_unit_vector(ray)
    coords = _polygon_coords(polygon, points)
    n = len(coords)
    best = math.inf
    for i, vertex in enumerate(coords):
        t = _ray_edge_t(origin, unit, vertex, coords[(i + 1) % n])
        if t is not None:
            best = min(best, t)
    return np.float64(best)


# ---------------------------------------------------------------------------
# distances involving polygons
# ---------------------------------------------------------------------------


def point_polygon_distance(
    point: Point, polygon: Polygon, points: Mapping[str, Point]
) -> np.float64:
    """Distance from a point to a polygon: ``0`` if inside, else nearest edge.

    Returns
    -------
    numpy.float64
        ``0`` when the point is inside the polygon, otherwise the minimum
        distance to its boundary.

    Notes
    -----
    Assumes ``polygon`` is a valid (simple, closed) ring; results are
    undefined for self-intersecting boundaries. Simplicity is enforced
    upstream at polygon-creation time, so this function does not re-validate.
    """
    sp_poly = _shapely_polygon(polygon, points)
    sp_point = shapely.Point(point.easting, point.northing)
    # explicit: shapely.distance already returns 0 here; kept to document intent.
    if shapely.contains(sp_poly, sp_point):
        return np.float64(0.0)
    return np.float64(shapely.distance(sp_poly, sp_point))


def polygon_polygon_distance(
    poly_a: Polygon, poly_b: Polygon, points: Mapping[str, Point]
) -> np.float64:
    """Distance between two polygons: ``0`` if they touch/overlap, else min gap.

    Returns
    -------
    numpy.float64
        ``0`` when the polygons intersect or touch, otherwise the minimum
        edge-to-edge distance.

    Notes
    -----
    Assumes both polygons are valid (simple, closed) rings; results are
    undefined for self-intersecting boundaries. Simplicity is enforced
    upstream at polygon-creation time, so this function does not re-validate.
    """
    sp_a = _shapely_polygon(poly_a, points)
    sp_b = _shapely_polygon(poly_b, points)
    # explicit: shapely.distance already returns 0 here; kept to document intent.
    if shapely.intersects(sp_a, sp_b):
        return np.float64(0.0)
    return np.float64(shapely.distance(sp_a, sp_b))


# ---------------------------------------------------------------------------
# tangent / vector
# ---------------------------------------------------------------------------


def tangent_direction(center: Point, point: Point) -> np.float64:
    """Azimuth of the tangent to a circle at ``point`` on its circumference.

    The tangent is perpendicular to the radius, so its azimuth is the radius
    azimuth plus ``π/2`` (mod ``2π``). The radius azimuth is obtained from
    :func:`azimuth` (``center`` → ``point``), which already normalises into
    ``[0, 2π)``; adding ``π/2`` and re-normalising is always valid since the
    result is brought back into ``[0, 2π)``. The opposite-facing direction
    (``+π``) is geometrically equivalent; this returns the canonical one per
    the spec.

    Returns
    -------
    numpy.float64
        Tangent azimuth in radians in ``[0, 2π)``.

    Raises
    ------
    ValueError
        If ``center`` and ``point`` are coincident within
        :data:`EPS_DISTANCE` (a zero-radius circle). The radius then has no
        direction — :func:`azimuth` would return ``atan2(0, 0) == 0`` — so the
        tangent is undefined and reporting ``π/2`` would be a silent fiction.
    """
    if distance(center, point) < EPS_DISTANCE:
        raise ValueError(
            "tangent_direction: center and circumference point are coincident; "
            "a zero-radius circle has no tangent"
        )
    return normalize_to_2pi(azimuth(center, point) + _HALF_PI)


def vector_endpoint(origin: Point, length: float, az: float) -> np.ndarray:
    """Endpoint of a vector from ``origin`` of the given ``length`` and azimuth.

    Uses the azimuth-convention formula
    ``(e + L·sin(az), n + L·cos(az))``. The ``sin``/``cos`` swap relative to a
    standard math angle is intentional (azimuth is CW from North) and must not
    be "corrected".

    Parameters
    ----------
    origin : Point
        Vector origin.
    length : float
        Vector magnitude in metres.
    az : float
        Azimuth in radians.

    Returns
    -------
    numpy.ndarray
        The ``(easting, northing)`` endpoint, shape ``(2,)``.

    Notes
    -----
    ``az`` is **azimuth-only**. Unlike :func:`direction_unit_vector` — which is
    mode-aware and resolves ``direction_mode`` — this function does *not* look
    at ``direction_mode`` and always interprets ``az`` as an azimuth. For a
    :class:`~geometry.models.common.DirectedObject` whose ``direction_mode`` is
    :attr:`DirectionMode.ANGLE`, callers must convert ``direction`` to an
    azimuth first (e.g. via :func:`~geometry.utils.angles.angle_to_azimuth`) or
    use :func:`direction_unit_vector` instead; passing a raw ANGLE-mode
    ``direction`` here yields a wrong endpoint.

    ``az`` and ``length`` are assumed **finite**. This function intentionally
    carries no ``math.isfinite`` guard — unlike :func:`direction_unit_vector`,
    which validates because it resolves a stored ``direction`` that may have
    been corrupted on deserialisation. ``vector_endpoint`` takes plain scalar
    arguments that the command layer computes locally, so the validation
    responsibility sits with the caller. A non-finite ``az`` or ``length``
    propagates silently into a ``nan``/``inf`` endpoint array; callers passing
    values from an untrusted source must check them before calling.
    """
    length = np.float64(length)
    az = np.float64(az)
    return np.array(
        [
            np.float64(origin.easting) + length * np.sin(az),
            np.float64(origin.northing) + length * np.cos(az),
        ],
        dtype=np.float64,
    )
