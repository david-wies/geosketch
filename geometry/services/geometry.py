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
convexity, convex hull, the four intersection types, the polygon distances,
the tangent direction, and the vector endpoint. It depends only on the model
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
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np
import shapely
from scipy.spatial import ConvexHull

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


def _cross2d(u: np.ndarray, v: np.ndarray) -> np.float64:
    """2-D scalar cross product ``ux*vy - uy*vx``.

    Used instead of ``np.cross`` because NumPy 2.x deprecated the 2-D form of
    ``np.cross``; the explicit determinant is identical and warning-free.
    """
    return np.float64(u[0] * v[1] - u[1] * v[0])


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
    d_e = np.float64(pt_b.easting) - np.float64(pt_a.easting)
    d_n = np.float64(pt_b.northing) - np.float64(pt_a.northing)
    return normalize_to_2pi(np.arctan2(d_e, d_n))


def distance(pt_a: Point, pt_b: Point) -> np.float64:
    """Euclidean distance between two points via ``np.hypot`` (float64)."""
    d_e = np.float64(pt_b.easting) - np.float64(pt_a.easting)
    d_n = np.float64(pt_b.northing) - np.float64(pt_a.northing)
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
    pair. A polygon is convex iff every turn has the same orientation (all
    cross products non-negative or all non-positive); collinear triplets
    (cross ≈ 0 within :data:`EPS_ANGLE`) are ignored so that redundant
    boundary vertices do not flip the result.

    Returns
    -------
    bool
        ``True`` if convex, ``False`` if concave.
    """
    coords = _polygon_coords(polygon, points)
    if len(coords) < 3:
        return False
    edges = np.roll(coords, -1, axis=0) - coords  # edge[i] = V[i+1] - V[i]
    saw_positive = False
    saw_negative = False
    for i in range(len(edges)):
        cross = _cross2d(edges[i], edges[(i + 1) % len(edges)])
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
    """
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
    ``A1 + t·d1 == A2 + s·d2`` via :func:`numpy.linalg.solve`. Parallel lines
    (cross product of the direction vectors below :data:`EPS_ANGLE`) have no
    unique solution and return ``None``.

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
    if abs(_cross2d(d1, d2)) < EPS_ANGLE:
        return None
    # Columns: [d1, -d2] · [t, s]^T = a2 - a1
    matrix = np.array([[d1[0], -d2[0]], [d1[1], -d2[1]]], dtype=np.float64)
    rhs = a2 - a1
    t, _s = np.linalg.solve(matrix, rhs)
    return a1 + t * d1


def _line_span(coords: np.ndarray, *extra: np.ndarray) -> float:
    """A length comfortably larger than the bounding box of all given coords."""
    stacked = np.vstack([coords, *([e.reshape(1, 2) for e in extra] or [])])
    mins = stacked.min(axis=0)
    maxs = stacked.max(axis=0)
    diag = float(np.hypot(maxs[0] - mins[0], maxs[1] - mins[1]))
    return diag * 10.0 + 1.0


def _collect_points(geom) -> list[np.ndarray]:
    """Flatten a shapely intersection result into a list of coordinate arrays."""
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
    return []


def _dedup(pts: Sequence[np.ndarray]) -> list[np.ndarray]:
    """Drop points that coincide within :data:`EPS_DISTANCE`."""
    unique: list[np.ndarray] = []
    for p in pts:
        if not any(np.hypot(p[0] - q[0], p[1] - q[1]) < EPS_DISTANCE for q in unique):
            unique.append(p)
    return unique


def line_polygon_intersections(
    line: Line, polygon: Polygon, points: Mapping[str, Point]
) -> list[np.ndarray]:
    """Points where an infinite line crosses a polygon boundary, ordered along the line.

    The line is extended well beyond the polygon and intersected with each
    polygon edge via :func:`shapely.intersection`. Results are de-duplicated
    (a line passing exactly through a vertex hits two edges) and ordered by
    their projection parameter along the line's direction, so the returned
    list reads in travel order from the line's first defining point toward the
    second.

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
    span = _line_span(coords, a, b)
    far_a = a - unit * span
    far_b = b + unit * span
    long_line = shapely.LineString([far_a, far_b])

    hits: list[np.ndarray] = []
    n = len(coords)
    for i in range(n):
        edge = shapely.LineString([coords[i], coords[(i + 1) % n]])
        hits.extend(_collect_points(shapely.intersection(long_line, edge)))

    unique = _dedup(hits)
    unique.sort(key=lambda p: float(np.dot(p - a, unit)))
    return unique


def polygon_polygon_intersections(
    poly_a: Polygon, poly_b: Polygon, points: Mapping[str, Point]
) -> list[np.ndarray]:
    """Points where two polygon boundaries cross.

    Intersects the two boundary geometries via :func:`shapely.intersection`,
    de-duplicates, and returns the crossings ordered lexicographically by
    ``(easting, northing)`` for deterministic output.

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


def ray_polygon_distance(ray: Ray, polygon: Polygon, points: Mapping[str, Point]) -> np.float64:
    """Distance from a ray's origin to the nearest polygon-boundary hit.

    The ray is ``origin + t · direction`` with ``t ≥ 0`` and a unit direction
    vector, so ``t`` is the distance. Each polygon edge is solved
    parametrically against the ray; only forward hits (``t ≥ -EPS_PARAM``)
    that land within the edge (``s ∈ [-EPS_PARAM, 1 + EPS_PARAM]``) count. The
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
    for i in range(n):
        a = coords[i]
        b = coords[(i + 1) % n]
        edge = b - a
        # Solve origin + t*unit = a + s*edge  ->  [unit, -edge] · [t, s] = a - origin
        matrix = np.array([[unit[0], -edge[0]], [unit[1], -edge[1]]], dtype=np.float64)
        if abs(_cross2d(unit, edge)) < EPS_ANGLE:
            continue  # ray parallel to this edge
        t, s = np.linalg.solve(matrix, a - origin)
        if t >= -EPS_PARAM and -EPS_PARAM <= s <= 1.0 + EPS_PARAM:
            best = min(best, float(t))
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
    """
    sp_poly = _shapely_polygon(polygon, points)
    sp_point = shapely.Point(point.easting, point.northing)
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
    """
    sp_a = _shapely_polygon(poly_a, points)
    sp_b = _shapely_polygon(poly_b, points)
    if shapely.intersects(sp_a, sp_b):
        return np.float64(0.0)
    return np.float64(shapely.distance(sp_a, sp_b))


# ---------------------------------------------------------------------------
# tangent / vector
# ---------------------------------------------------------------------------


def tangent_direction(center: Point, point: Point) -> np.float64:
    """Azimuth of the tangent to a circle at ``point`` on its circumference.

    The tangent is perpendicular to the radius, so its azimuth is the radius
    azimuth plus ``π/2`` (mod ``2π``), where the radius azimuth is
    ``atan2(Δe, Δn)`` from ``center`` to ``point``. The opposite-facing
    direction (``+π``) is geometrically equivalent; this returns the canonical
    one per the spec.

    Returns
    -------
    numpy.float64
        Tangent azimuth in radians in ``[0, 2π)``.
    """
    d_e = np.float64(point.easting) - np.float64(center.easting)
    d_n = np.float64(point.northing) - np.float64(center.northing)
    radius_azimuth = np.arctan2(d_e, d_n)
    return normalize_to_2pi(radius_azimuth + _HALF_PI)


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
