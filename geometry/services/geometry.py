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
app, spanning both 2-D and 3-D/solid work.

**2-D:** direction (azimuth), Euclidean distance, polygon signed area and
convexity, the 2-D convex hull, the direction unit vector, three intersection
functions (line–line, line–polygon, polygon–polygon), the ray-polygon
distance, the point/polygon and polygon/polygon distances, the tangent
direction (including tangent-perpendicularity), and the vector endpoint.

**3-D / solids:** the 3-D convex hull (:func:`convex_hull_3d`, with the
coplanar/precision flat-Solid fallback), ball and cylinder and solid volumes,
cylinder cross-section classification (:class:`CylinderCrossSection`), solid
B-rep faces, and lateral/total surface area (Mirtich 1996 polyhedral mass
properties for volume + centroid).

It depends only on the model dataclasses (:mod:`geometry.models`) and the math
utilities (:mod:`geometry.utils`); it imports neither ``tkinter`` nor
``matplotlib``.

Conventions
-----------
* Coordinates are UTM metres expressed as ``(easting, northing)`` — easting
  first. All coordinate arrays returned by this module follow that order.
* Scalar results are returned as :class:`numpy.float64` so they drop straight
  into further NumPy expressions without an implicit cast. 2-D coordinate
  results (e.g. intersection points) are returned as ``numpy.ndarray`` of
  shape ``(2,)``; 3-D coordinate results (e.g. :func:`vector_endpoint`) use
  shape ``(3,)``.
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

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import shapely
from scipy.spatial import ConvexHull, QhullError  # pylint: disable=no-name-in-module

from geometry.models.common import ElevatedObject, DirectionMode, GeoObject
from geometry.models.cylinder import Cylinder
from geometry.models.line import Line
from geometry.models.point import Point
from geometry.models.polygon import Polygon
from geometry.models.ray import Ray
from geometry.models.solid import Solid
from geometry.utils.angles import azimuth_to_angle, normalize_to_2pi
from geometry.utils.constants import EPS_ANGLE, EPS_DISTANCE, EPS_PARAM, EPS_VOLUME
from geometry.utils.id_factory import IDFactory

__all__ = [
    "azimuth",
    "distance",
    "elevation",
    "three_point_azimuth_elevation",
    "signed_area",
    "is_convex",
    "convex_hull",
    "horizontal_unit_vector",
    "line_intersection",
    "line_polygon_intersections",
    "polygon_polygon_intersections",
    "ray_polygon_distance",
    "point_polygon_distance",
    "polygon_polygon_distance",
    "tangent_direction",
    "vector_endpoint",
    "convex_hull_3d",
    "ball_volume",
    "ball_surface_area",
    "ball_cross_section_radius",
    "ball_tangent_direction",
    "cylinder_volume",
    "cylinder_lateral_surface_area",
    "cylinder_total_surface_area",
    "cylinder_axis_vector",
    "cylinder_cross_section",
    "CylinderCrossSection",
    "solid_faces",
    "solid_volume_centroid",
    "solid_lateral_surface_area",
    "solid_total_surface_area",
]

_logger = logging.getLogger(__name__)

_HALF_PI = math.pi / 2.0


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------


def _xy(point: Point) -> np.ndarray:
    """Return ``point`` as a ``float64`` ``(easting, northing)`` array."""
    return np.array([point.easting, point.northing], dtype=np.float64)


def _xyz(point: Point) -> np.ndarray:
    """Return ``point`` as a ``float64`` ``(easting, northing, altitude)`` array.

    The 3-D sibling of :func:`_xy`, used by the 3-D operations
    (:func:`elevation`) so the easting-first, altitude-last ordering lives in
    one place.
    """
    return np.array([point.easting, point.northing, point.altitude], dtype=np.float64)


def _delta(a: Point, b: Point) -> tuple[float, float]:
    """Return ``(Δeasting, Δnorthing)`` from ``a`` to ``b``.

    Centralises the ``b - a`` component subtraction used directly by
    :func:`azimuth` and :func:`distance` (and indirectly by
    :func:`tangent_direction` via :func:`azimuth`) so the easting-first
    convention lives in exactly one place.
    """
    return (b.easting - a.easting, b.northing - a.northing)


def _cross2d(u: np.ndarray, v: np.ndarray) -> np.float64:
    """2-D scalar cross product ``ux*vy - uy*vx``.

    Used instead of ``np.cross`` because NumPy 2.x deprecated the 2-D form of
    ``np.cross``; the explicit determinant is identical and warning-free.
    """
    return u[0] * v[1] - u[1] * v[0]


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
    """3-D Euclidean distance between two points (float64).

    Computes ``√[(Δe)²+(Δn)²+(Δz)²]`` per the domain rule that distance
    between two Points is always 3-D. This matches the Vector ``length``
    formula and the spec's point-import text format.

    Parameters
    ----------
    pt_a, pt_b : Point
        Start and end points, each with an ``altitude`` field.

    Returns
    -------
    numpy.float64
        3-D Euclidean distance in metres.
    """
    d_e, d_n = _delta(pt_a, pt_b)
    d_z = pt_b.altitude - pt_a.altitude
    return np.sqrt(d_e**2 + d_n**2 + d_z**2)


def elevation(pt_a: Point, pt_b: Point) -> np.float64:
    """Elevation angle from ``pt_a`` to ``pt_b`` in radians.

    The elevation is the angle of the arm ``pt_a → pt_b`` above the horizontal
    plane, ``atan2(Δz, √(Δe²+Δn²))``. It is the vertical counterpart of
    :func:`azimuth`: azimuth answers *which horizontal bearing*, elevation
    answers *how steeply up or down*.

    Parameters
    ----------
    pt_a, pt_b : Point
        Start and end points, each with an ``altitude`` field.

    Returns
    -------
    numpy.float64
        Elevation in radians in ``[-π/2, π/2]``. Positive when ``pt_b`` is
        higher than ``pt_a``, negative when lower, ``±π/2`` for a purely
        vertical arm, and ``0.0`` when the two points are coincident (the
        ``atan2(0, 0)`` degenerate case is well-defined as ``0.0``).
    """
    d_e, d_n, d_z = _xyz(pt_b) - _xyz(pt_a)
    return np.arctan2(d_z, np.hypot(d_e, d_n))


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
    do not flip the result.

    Zero-length edges from duplicated vertices have no direction and are
    **compacted out before turns are paired**, not merely skipped index-wise.
    Pairing by raw index would mask the turn that straddles a duplicated vertex
    (the real turn spans the zero-length edge) and could misclassify a concave
    polygon as convex; pairing consecutive *surviving* edges measures it.

    Returns
    -------
    bool
        ``True`` if convex, ``False`` if concave.
    """
    coords = _polygon_coords(polygon, points)
    if len(coords) < 3:
        return False
    edges = np.roll(coords, -1, axis=0) - coords  # shape (N, 2)
    norms = np.hypot(edges[:, 0], edges[:, 1])  # shape (N,)
    valid = norms >= EPS_DISTANCE
    # Keep only real (non-degenerate) edge directions, in cyclic order, then
    # pair *consecutive surviving* edges so a reflex turn hidden behind a
    # duplicated vertex is still measured.
    unit_e = edges[valid, 0] / norms[valid]
    unit_n = edges[valid, 1] / norms[valid]
    if unit_e.shape[0] < 3:
        return False  # fewer than three real edges → degenerate, not convex
    # cross[i] = 2D cross product of surviving unit_edge[i] with unit_edge[i+1]
    crosses = unit_e * np.roll(unit_n, -1) - unit_n * np.roll(unit_e, -1)
    has_pos = bool(np.any(crosses > EPS_ANGLE))
    has_neg = bool(np.any(crosses < -EPS_ANGLE))
    return not (has_pos and has_neg)


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
    ValueError
        If any vertex coordinate is non-finite (``nan``/``±inf``). Mirrors the
        up-front screen in :func:`convex_hull_3d`: without it a poisoned vertex
        would surface as an opaque QHull message rather than an actionable
        error pinned to the input.
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
    if not np.all(np.isfinite(coords)):
        raise ValueError("convex_hull: input coordinates contain nan or ±inf")
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


def horizontal_unit_vector(obj: ElevatedObject) -> np.ndarray:
    """Horizontal unit ``(easting, northing)`` vector for a direction-bearing object.

    Computes a **2-D horizontal projection** of the bearing stored in
    ``obj.direction``, deliberately ignoring ``obj.elevation``. This is the
    correct input for 2-D geometry operations such as ray-polygon distance,
    where the plane geometry is independent of the ray's vertical tilt.

    ``obj.direction`` is stored in radians but means either an azimuth
    (CW from North) or a math angle (CCW from East) depending on
    ``obj.direction_mode``. This normalises both to a math angle and returns
    ``(cos θ, sin θ)`` in ``(easting, northing)`` order, which is consistent
    with the azimuth-based vector-endpoint formula
    (``(sin az, cos az) == (cos angle, sin angle)``).

    Returns
    -------
    numpy.ndarray
        Horizontal unit direction vector, shape ``(2,)``.

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
            f"horizontal_unit_vector: obj.direction is {obj.direction!r}; "
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
    ``A1 + t·d1 == A2 + s·d2`` via Cramer's rule on the 2×2 system. Parallelism is
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
    # Solve [d1, -d2] · [t, s]^T = (a2 - a1) via Cramer's rule.
    rhs = a2 - a1
    det = d2[0] * d1[1] - d1[0] * d2[1]
    t = (d2[0] * rhs[1] - rhs[0] * d2[1]) / det
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
    n = len(coords)
    ends = np.roll(coords, -1, axis=0)
    # Build all N edge geometries in one batch call (Shapely 2.x vectorised API).
    coord_seq = np.stack([coords, ends], axis=1).reshape(-1, 2)
    idx = np.repeat(np.arange(n), 2)
    edges_geom = shapely.linestrings(coord_seq, indices=idx)
    results = shapely.intersection(long_line, edges_geom)
    hits: list[np.ndarray] = []
    for geom in results[~shapely.is_empty(results)]:
        hits.extend(_collect_points(geom))
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
    # Solve [unit, -edge] · [t, s]^T = (a - origin) via Cramer's rule.
    rhs = a - origin
    det = edge[0] * unit[1] - unit[0] * edge[1]
    t = (edge[0] * rhs[1] - rhs[0] * edge[1]) / det
    s = (unit[0] * rhs[1] - rhs[0] * unit[1]) / det
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
    unit = horizontal_unit_vector(ray)
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
        :data:`EPS_DISTANCE` in the **horizontal (2D) plane** (a zero-radius
        circle). The coincidence test uses only ``(easting, northing)`` because
        ``azimuth`` — and therefore the tangent direction — is a 2-D quantity;
        two points that differ only in altitude have no horizontal separation and
        thus no well-defined azimuth. Reporting ``π/2`` would be a silent
        fiction, so this raises instead.
    """
    d_e, d_n = _delta(center, point)
    if math.hypot(d_e, d_n) < EPS_DISTANCE:
        raise ValueError(
            "tangent_direction: center and circumference point are coincident; "
            "a zero-radius circle has no tangent"
        )
    return normalize_to_2pi(azimuth(center, point) + _HALF_PI)


def vector_endpoint(origin: Point, length: float, az: float, el: float = 0.0) -> np.ndarray:
    """3-D endpoint of a vector from ``origin`` of the given ``length``, azimuth, and elevation.

    Uses the azimuth + elevation convention from the spec::

        E = origin_e + length·sin(az)·cos(el)
        N = origin_n + length·cos(az)·cos(el)
        Z = origin_z + length·sin(el)

    The ``sin``/``cos`` swap between easting and northing is intentional
    (azimuth is CW from North) and must not be "corrected". The elevation term
    shortens the horizontal reach by ``cos(el)`` and adds a vertical component
    via ``sin(el)``.

    Parameters
    ----------
    origin : Point
        Vector origin (provides easting, northing, altitude).
    length : float
        Vector magnitude in metres.
    az : float
        Azimuth in radians.
    el : float, optional
        Elevation angle above the horizontal plane in radians; default 0.0
        (horizontal).  The caller is responsible for keeping this in
        ``[-π/2, π/2]``; values outside that range are not rejected here.

    Returns
    -------
    numpy.ndarray
        The ``(easting, northing, altitude)`` endpoint, shape ``(3,)``.

    Notes
    -----
    ``az`` is **azimuth-only**. Unlike :func:`horizontal_unit_vector` — which is
    mode-aware and resolves ``direction_mode`` — this function does *not* look
    at ``direction_mode`` and always interprets ``az`` as an azimuth. For a
    :class:`~geometry.models.common.ElevatedObject` whose ``direction_mode`` is
    :attr:`DirectionMode.ANGLE`, callers must convert ``direction`` to an
    azimuth first (e.g. via :func:`~geometry.utils.angles.angle_to_azimuth`) or
    use :func:`horizontal_unit_vector` instead; passing a raw ANGLE-mode
    ``direction`` here yields a wrong endpoint.

    ``az``, ``el``, and ``length`` are assumed **finite**. This function
    intentionally carries no ``math.isfinite`` guard — unlike
    :func:`horizontal_unit_vector`, which validates because it resolves a stored
    ``direction`` that may have been corrupted on deserialisation.
    ``vector_endpoint`` takes plain scalar arguments that the command layer
    computes locally, so the validation responsibility sits with the caller. A
    non-finite argument propagates silently into a ``nan``/``inf`` endpoint
    array; callers passing values from an untrusted source must check them
    before calling.
    """
    sin_az = math.sin(az)
    cos_az = math.cos(az)
    sin_el = math.sin(el)
    cos_el = math.cos(el)
    h = length * cos_el
    return np.array(
        [
            origin.easting + h * sin_az,
            origin.northing + h * cos_az,
            origin.altitude + length * sin_el,
        ],
        dtype=np.float64,
    )


# ---------------------------------------------------------------------------
# angle measurements
# ---------------------------------------------------------------------------


def three_point_azimuth_elevation(
    a: Point, b: Point, c: Point
) -> tuple[np.float64 | None, np.float64]:
    """Azimuth and elevation of the angle at vertex ``b`` for the ordered triple.

    The vertex is ``b``; the two arms are ``b → a`` and ``b → c``. The result is
    the *directed* turn from arm ``BA`` to arm ``BC``, split into a horizontal
    component (azimuth) and a vertical component (elevation). This is the
    three-point sibling of :func:`azimuth`/:func:`elevation`, surfaced by the
    *Angle at Vertex* measurement.

    The triple is **ordered**: swapping ``a`` and ``c`` yields the explementary
    azimuth (``2π − az``, for a non-zero turn) and the negated elevation.

    Parameters
    ----------
    a, b, c : Point
        The first arm endpoint, the vertex, and the second arm endpoint.

    Returns
    -------
    tuple[numpy.float64 | None, numpy.float64]
        ``(azimuth, elevation)`` in radians.

        ``azimuth`` is the horizontal turn from ``BA`` to ``BC``, altitude
        ignored, normalised to ``[0, 2π)``. It is ``None`` when either arm has
        no horizontal extent (a purely vertical arm whose horizontal length is
        ``< EPS_DISTANCE``) — the bearing is undefined there.

        ``elevation`` is ``elevation(b, c) − elevation(b, a)`` in ``[-π, π]``;
        always defined when the arms have non-zero 3-D length.

    Raises
    ------
    ValueError
        If either arm has zero 3-D length (``distance(a, b)`` or
        ``distance(c, b)`` ``< EPS_DISTANCE``) — the angle is undefined.
    """
    # The arm deltas are recomputed across distance() (guard), the inline
    # azimuth below, and elevation() (return). That redundancy is intentional:
    # this runs once per measurement, so the few extra subtractions cost
    # nothing, and delegating to distance()/elevation() keeps those formulas
    # single-sourced rather than duplicating them here.
    if distance(a, b) < EPS_DISTANCE:
        raise ValueError("three_point_azimuth_elevation: arm BA has zero length")
    if distance(c, b) < EPS_DISTANCE:
        raise ValueError("three_point_azimuth_elevation: arm BC has zero length")

    ba_e, ba_n = a.easting - b.easting, a.northing - b.northing
    bc_e, bc_n = c.easting - b.easting, c.northing - b.northing
    if np.hypot(ba_e, ba_n) < EPS_DISTANCE or np.hypot(bc_e, bc_n) < EPS_DISTANCE:
        azimuth_turn = None
    else:
        azimuth_turn = normalize_to_2pi(np.arctan2(bc_e, bc_n) - np.arctan2(ba_e, ba_n))

    return azimuth_turn, elevation(b, c) - elevation(b, a)


# ---------------------------------------------------------------------------
# 3-D convex hull → Solid
# ---------------------------------------------------------------------------


def _is_coplanar(coords: np.ndarray) -> bool:
    """Whether all rows of ``coords`` lie on a common plane in 3-D.

    The mean-centred coordinates span a subspace of rank ``< 3`` iff every point
    lies on a single plane (or line, or coincide). Used by :func:`convex_hull_3d`
    to classify coplanarity *deliberately*, instead of inferring it from a
    :class:`~scipy.spatial.QhullError` (which also fires for precision/duplicate
    failures unrelated to coplanarity).
    """
    centered = coords - coords.mean(axis=0)
    return bool(np.linalg.matrix_rank(centered, tol=EPS_DISTANCE) < 3)


def convex_hull_3d(
    points_3d: Mapping[str, Point],
    point_ids: Sequence[str],
    id_factory: IDFactory,
) -> tuple[Solid, list[Polygon]]:
    """Convex hull of a 3-D point set as a :class:`Solid` of triangular facets.

    Runs :class:`scipy.spatial.ConvexHull` on the ``(easting, northing,
    altitude)`` coordinates of the named points (QHull is the Quickhull
    implementation, Barber et al. 1996). Each hull facet becomes a new triangle
    :class:`Polygon` referencing the original vertex Point IDs (QHull's
    ``simplices`` index into the input set, so no new points are minted); the
    returned :class:`Solid` lists those facet polygons as its ``layers``.

    .. warning::
       The returned Solid is a **boundary-representation (B-rep) shell** of
       triangular facets, *not* the ordered bottom-to-top cross-section *stack*
       that :func:`solid_volume_centroid`, :func:`solid_faces`, and
       :func:`solid_lateral_surface_area` consume. Its ``layers`` are facets,
       not stacked cross-sections, so feeding this Solid to those functions is a
       category error — they detect the facet shell and raise ``ValueError``
       rather than return a wrong number. Use the per-facet geometry directly
       (or a dedicated B-rep volume routine) to measure a hull.

    This is the one service function permitted to mint IDs (design doc
    ``docs/implementation-design.md`` §13.12):
    the number of facets is unknown until QHull runs, so the function takes an
    :class:`~geometry.utils.id_factory.IDFactory` and calls ``next_id`` for the
    Solid (``so``) and each facet Polygon (``pg``). The command layer passes
    ``project.id_factory``.

    Facet triangles are wound so their right-hand normal matches the outward
    normal QHull reports in ``hull.equations`` — consistent outward orientation
    across the shell. Orientation relies on QHull's convention that the
    ``hull.equations`` plane normals point **outward** from the hull interior;
    the facet winding is derived from those normals.

    Coplanar fallback (design doc ``docs/implementation-design.md`` §13.7):
    coplanarity is detected **deliberately** up front — the mean-centred
    coordinates' matrix rank is ``< 3`` iff every point lies on a common plane —
    rather than inferred from a QHull exception, so a genuine coplanar set is
    distinguished from non-finite coordinates or other precision failures (which
    raise a clear error instead of silently taking the flat-Solid path). On the
    coplanar branch the function builds the 2-D hull on ``(easting, northing)``
    and returns a *degenerate* Solid with two identical Polygon layers (zero
    vertical extent, hence zero volume). The caller is expected to flag it via
    :func:`geometry.services.validation.validate_solid_non_degenerate` against
    :data:`~geometry.utils.constants.EPS_VOLUME` and warn the user rather than
    silently storing an invisible zero-extent Solid.

    Parameters
    ----------
    points_3d : Mapping[str, Point]
        Point lookup covering every ID in ``point_ids``.
    point_ids : Sequence[str]
        IDs of the input points (a subset of ``points_3d``). At least 4 are
        required for a 3-D hull.
    id_factory : IDFactory
        Allocator for the new Solid and facet Polygon IDs.

    Returns
    -------
    tuple[Solid, list[Polygon]]
        The hull Solid and the list of its facet Polygons, for the command
        layer to insert into the project store.

    Raises
    ------
    ValueError
        If fewer than 4 point IDs are supplied, if any input coordinate is
        non-finite (``nan`` or ``±inf``), or if the coplanar fallback's 2-D hull
        is itself degenerate (all points collinear).
    """
    ids = list(point_ids)
    if len(ids) < 4:
        raise ValueError(f"convex_hull_3d requires at least 4 points; got {len(ids)}")
    coords = np.array([_xyz(points_3d[pid]) for pid in ids], dtype=np.float64)

    # Guard non-finite coordinates up front so a nan/inf does not get funnelled
    # into the coplanar fallback and silently masquerade as flat geometry. Only
    # a *deliberately*-detected coplanar set should take that branch.
    if not np.all(np.isfinite(coords)):
        raise ValueError("convex_hull_3d: input coordinates contain nan or ±inf")

    # Detect coplanarity deliberately (see _is_coplanar) rather than inferring
    # it from a QhullError, which also fires for precision/duplicate failures.
    if _is_coplanar(coords):
        return _coplanar_fallback_solid(coords, ids, id_factory)

    try:
        hull = ConvexHull(coords)
    except QhullError as exc:
        # Reached only for a genuinely degenerate/precision-borderline set that
        # passed the rank screen; fall back to the flat 2-D hull.
        #
        # NOTE (deferred — two-fallback ambiguity): this QHull-failure fallback
        # and the deliberate-coplanar fallback above both return a degenerate
        # flat Solid, distinguishable today only by the Solid's ``name``
        # substring (a brittle, stringly-typed discriminator the command layer
        # must parse). A structured discriminator (e.g. an enum returned
        # alongside the Solid, or a transient non-persisted field on the result)
        # was deferred: ``Solid`` is a persisted model with a strict
        # ``__post_init__`` and the return type is the bare
        # ``tuple[Solid, list[Polygon]]`` used by every caller, so a faithful
        # structured fix means widening the return signature (or the schema) —
        # a larger, breaking refactor outside this change's scope. Recommended
        # fix: return ``tuple[Solid, list[Polygon], HullFallback]`` where
        # ``HullFallback`` is an enum of ``{NONE, COPLANAR, QHULL_FAILURE}``,
        # and migrate callers off the name-substring sniff.
        _logger.warning(
            "convex_hull_3d: a rank-3 point set failed QHull on a "
            "precision/degeneracy borderline; routing to the flat 2-D fallback.",
            exc_info=exc,
        )
        return _coplanar_fallback_solid(
            coords,
            ids,
            id_factory,
            name="Convex Hull 3D (QHull failure — degenerate)",
        )

    facets: list[Polygon] = []
    for simplex, equation in zip(hull.simplices, hull.equations):
        tri = list(simplex)
        normal = equation[:3]
        # Orient the triangle so its right-hand normal agrees with QHull's
        # outward facet normal; QHull's simplex order is not itself consistent.
        # NOTE: hull facets are wound by 3-D OUTWARD NORMAL, deliberately NOT by
        # 2-D CCW (invariant #3). Do not "fix" this by running facets through
        # 2-D CCW normalization — that would corrupt the shell's orientation.
        v0, v1, v2 = (coords[tri[0]], coords[tri[1]], coords[tri[2]])
        if float(np.dot(np.cross(v1 - v0, v2 - v0), normal)) < 0.0:
            tri = [tri[0], tri[2], tri[1]]
        facets.append(
            Polygon(
                id=id_factory.next_id("pg"),
                name="hull_facet",
                alpha=1.0,
                visibility=True,
                point_ids=[ids[i] for i in tri],
                is_convex=True,
                line_color="#000000",
                fill_color="#808080",
            )
        )

    # NOTE: this Solid is a B-rep *facet shell*, not a cross-section *stack*.
    # Its ``layers`` are triangular hull facets that share vertices across the
    # shell; it is NOT a valid input to solid_volume_centroid / solid_faces /
    # solid_lateral_surface_area, which assume a monotonic bottom-to-top stack
    # and explicitly reject a facet shell (see _ensure_solid_is_stack).
    return (
        Solid(
            id=id_factory.next_id("so"),
            name="Convex Hull 3D",
            alpha=1.0,
            visibility=True,
            layers=tuple(f.id for f in facets),
            line_color="#000000",
            fill_color="#808080",
        ),
        facets,
    )


def _coplanar_fallback_solid(
    coords: np.ndarray,
    ids: Sequence[str],
    id_factory: IDFactory,
    name: str = "Convex Hull 3D (degenerate)",
) -> tuple[Solid, list[Polygon]]:
    """Degenerate flat Solid for the coplanar :func:`convex_hull_3d` case.

    Computes the 2-D hull on ``(easting, northing)`` and wraps it in a Solid
    with two identical Polygon layers (zero extent → zero volume). Raises
    ``ValueError`` if the 2-D hull is itself degenerate (collinear points).

    Two :func:`convex_hull_3d` call sites share this helper, and they pass
    distinct ``name`` values so the command layer can tell the causes apart from
    the resulting Solid's name alone (no schema-level flag exists):

    * the **deliberately coplanar** branch (the expected flat-input feature)
      keeps the default ``"Convex Hull 3D (degenerate)"``;
    * the **QhullError** branch (an unexpected rank-3 cloud that trips QHull on a
      precision/degeneracy borderline) passes
      ``"Convex Hull 3D (QHull failure — degenerate)"``.

    The zero-volume / ``EPS_VOLUME`` degeneracy semantics are identical for both
    names; only the label differs.

    Parameters
    ----------
    coords : numpy.ndarray
        Point cloud, shape ``(n, 3)`` in ``(easting, northing, altitude)`` order.
    ids : Sequence[str]
        Object IDs aligned with ``coords`` rows.
    id_factory : IDFactory
        Source of the new Polygon and Solid IDs.
    name : str, optional
        Name for the resulting degenerate Solid; see the two callers above.
    """
    try:
        flat = ConvexHull(coords[:, :2])
    except QhullError as exc:
        raise ValueError("convex_hull_3d: input points are collinear; no hull exists") from exc
    hull_ids = [ids[i] for i in flat.vertices]
    polygon = Polygon(
        id=id_factory.next_id("pg"),
        name="hull_facet",
        alpha=1.0,
        visibility=True,
        point_ids=hull_ids,
        is_convex=True,
        line_color="#000000",
        fill_color="#808080",
    )
    solid = Solid(
        id=id_factory.next_id("so"),
        name=name,
        alpha=1.0,
        visibility=True,
        # The SAME polygon ID is stored twice on purpose: the two layers are the
        # identical flat ring, giving a zero-extent (zero-volume) degenerate
        # Solid that solid_volume_centroid reports as 0.0. CAVEAT: this duplicate
        # layer ID means the object store / cascading-delete logic must tolerate
        # a layer ID appearing more than once within a single Solid (deleting the
        # polygon must clean up both references, not just the first).
        layers=(polygon.id, polygon.id),
        line_color="#000000",
        fill_color="#808080",
    )
    return solid, [polygon]


# ---------------------------------------------------------------------------
# Ball geometry
# ---------------------------------------------------------------------------


def _require_non_negative_radius(radius: float) -> None:
    """Reject a non-finite or negative radius before a volume/area formula.

    Defense-in-depth for the measurement functions, which would otherwise turn
    a corrupt ``radius`` into a wrong-signed or ``nan`` result and propagate it
    silently. This local copy exists because
    :mod:`geometry.services.validation` imports this module, so importing
    :func:`~geometry.services.validation.validate_positive_radius` back here
    would be circular.

    The two helpers are deliberately **not** in lockstep, despite the similar
    naming. Only the *finite* check matches word-for-word; the bound and its
    message diverge on purpose:

    * This helper rejects ``radius < 0.0`` with ``"Radius must be >= 0"`` — a
      radius of exactly ``0`` is **permitted** (it yields a well-defined zero
      volume/area).
    * :func:`~geometry.services.validation.validate_positive_radius` rejects
      ``radius <= EPS_DISTANCE`` with ``"Radius must be > 1e-06"`` — it
      **forbids** zero (a degenerate object the user is constructing).

    A maintainer should not assume these stay in sync.
    """
    if not math.isfinite(radius):
        raise ValueError(f"Radius must be finite; got {radius!r}")
    if radius < 0.0:
        raise ValueError(f"Radius must be >= 0; got {radius!r}")


def _require_non_negative_height(height: float) -> None:
    """Reject a non-finite or negative height before a volume/area formula.

    The height counterpart of :func:`_require_non_negative_radius`; a non-finite
    or negative ``height`` would otherwise yield a ``nan`` or negative cylinder
    volume/area with no error. A height of exactly ``0`` is permitted (a
    well-defined zero-extent degenerate cylinder).
    """
    if not math.isfinite(height):
        raise ValueError(f"Height must be finite; got {height!r}")
    if height < 0.0:
        raise ValueError(f"Height must be >= 0; got {height!r}")


def ball_volume(radius: float) -> np.float64:
    """Volume of a ball of the given radius: ``(4/3)·π·r³``.

    Raises
    ------
    ValueError
        If ``radius`` is non-finite or negative (defense-in-depth: a corrupt
        radius would otherwise yield a ``nan`` or negative volume silently).
    """
    _require_non_negative_radius(radius)
    return np.float64(4.0 / 3.0 * math.pi * radius**3)


def ball_surface_area(radius: float) -> np.float64:
    """Surface area of a ball of the given radius: ``4·π·r²``.

    Raises
    ------
    ValueError
        If ``radius`` is non-finite or negative.
    """
    _require_non_negative_radius(radius)
    return np.float64(4.0 * math.pi * radius**2)


def ball_cross_section_radius(ball_radius: float, distance_to_plane: float) -> np.float64 | None:
    """Radius of a ball's circular cross-section at a given plane distance.

    The intersection of a ball (radius ``r``) with a plane at signed distance
    ``d`` from its centre is a circle of radius ``√(r² − d²)`` when ``|d| ≤ r``.
    Returns ``None`` when ``|d| > r`` (the plane misses the ball) so the Slice
    renderer can skip the ball rather than feed a negative radicand to ``sqrt``
    (``docs/implementation-design.md`` §13.3). A plane tangent to the ball
    (``|d| = r``) yields ``0.0``.

    Parameters
    ----------
    ball_radius : float
        Ball radius in metres.
    distance_to_plane : float
        Signed distance from the ball centre to the cutting plane.

    Returns
    -------
    numpy.float64 or None
        The cross-section radius, or ``None`` if the plane does not meet the
        ball.

    Raises
    ------
    ValueError
        If ``ball_radius`` is non-finite or negative. Without this guard a
        negative radius would make ``abs(distance_to_plane) > ball_radius``
        always true and the function would silently return ``None``, masking
        the corrupt input instead of rejecting it (consistent with
        :func:`ball_volume` and the other ball/cylinder measures).
    ValueError
        If ``distance_to_plane`` is non-finite. A ``nan`` distance makes the
        miss-guard ``abs(distance_to_plane) > ball_radius`` evaluate ``False``,
        so the function would return ``sqrt(r² − nan) = nan`` and corrupt the
        ``None``-means-"plane misses ball" contract.
    """
    _require_non_negative_radius(ball_radius)
    if not math.isfinite(distance_to_plane):
        raise ValueError(f"distance_to_plane must be finite; got {distance_to_plane!r}")
    if abs(distance_to_plane) > ball_radius:
        return None
    return np.sqrt(np.float64(ball_radius) ** 2 - np.float64(distance_to_plane) ** 2)


def ball_tangent_direction(center: Point, surface_point: Point) -> np.float64:
    """Azimuth of the radius from a ball's centre to a point on its surface.

    A ball tangent at ``surface_point`` must be perpendicular to this radius
    direction; validation enforces ``|dot(tangent_unit, radius_unit)| <
    EPS_ANGLE`` in 3-D. This returns the horizontal azimuth of the radius in
    ``[0, 2π)`` (the radius bearing), delegating to :func:`azimuth`.

    Returns
    -------
    numpy.float64
        Radius azimuth in radians in ``[0, 2π)``.
    """
    return azimuth(center, surface_point)


# ---------------------------------------------------------------------------
# Cylinder geometry
# ---------------------------------------------------------------------------


def cylinder_volume(radius: float, height: float) -> np.float64:
    """Volume of a right cylinder: ``π·r²·h``.

    Raises
    ------
    ValueError
        If ``radius`` or ``height`` is non-finite or negative (defense-in-depth:
        a corrupt input would otherwise yield a ``nan`` or negative volume).
    """
    _require_non_negative_radius(radius)
    _require_non_negative_height(height)
    return np.float64(math.pi * radius**2 * height)


def cylinder_lateral_surface_area(radius: float, height: float) -> np.float64:
    """Lateral (side) surface area of a cylinder: ``2·π·r·h``.

    Raises
    ------
    ValueError
        If ``radius`` or ``height`` is non-finite or negative.
    """
    _require_non_negative_radius(radius)
    _require_non_negative_height(height)
    return np.float64(2.0 * math.pi * radius * height)


def cylinder_total_surface_area(radius: float, height: float) -> np.float64:
    """Total surface area of a closed cylinder: ``2·π·r·h + 2·π·r²``.

    Raises
    ------
    ValueError
        If ``radius`` or ``height`` is non-finite or negative.
    """
    _require_non_negative_radius(radius)
    _require_non_negative_height(height)
    return np.float64(2.0 * math.pi * radius * height + 2.0 * math.pi * radius**2)


def cylinder_axis_vector(cylinder: Cylinder) -> np.ndarray:
    """Unit vector along a cylinder's axis in ``(easting, northing, altitude)``.

    Vertical cylinders short-circuit to ``(0, 0, 1)`` without touching
    ``axis_azimuth`` — which is meaningless in vertical mode and stored as
    ``0.0`` (``docs/implementation-design.md`` §13.2). Inclined cylinders use
    the azimuth + elevation
    convention ``(sin(az)·cos(el), cos(az)·cos(el), sin(el))``, matching
    :func:`vector_endpoint`.

    Returns
    -------
    numpy.ndarray
        Unit axis vector, shape ``(3,)``.
    """
    if cylinder.axis_mode == "vertical":
        return np.array([0.0, 0.0, 1.0], dtype=np.float64)
    az = cylinder.axis_azimuth
    el = cylinder.axis_elevation
    cos_el = math.cos(el)
    return np.array(
        [math.sin(az) * cos_el, math.cos(az) * cos_el, math.sin(el)],
        dtype=np.float64,
    )


_CROSS_SECTION_ARITY: dict[str, int] = {"circle": 1, "ellipse": 2, "rectangle": 2}


@dataclass(frozen=True)
class CylinderCrossSection:
    """Shape of a planar slice through a cylinder.

    The class makes illegal states unrepresentable. Instances are built **only**
    through the kind-specific classmethod constructors :meth:`circle`,
    :meth:`ellipse`, and :meth:`rectangle`; ``kind`` and ``_dimensions`` are
    ``init=False`` fields set by those factories, so the per-kind arity
    invariant (circle = 1 dimension, ellipse/rectangle = 2) is structurally
    unviolatable — there is no positional path that could pair, say, ``"circle"``
    with two dimensions. ``__post_init__`` still validates positivity and the
    ellipse ordering as defence in depth. The dataclass is frozen, so once
    validated an instance stays consistent.

    Fields
    ------
    kind : Literal["circle", "ellipse", "rectangle"]
        The classified slice shape. ``init=False`` — set by the classmethod
        constructor, never passed in.
    _dimensions : tuple[float, ...]
        Geometry of the cross-section, by ``kind`` (every entry must be finite
        and ``> 0``). ``init=False`` and **private**: read it through the
        kind-aware typed accessors (``radius`` / ``semi_major`` /
        ``semi_minor`` / ``width`` / ``height``), which are the only public
        read path.

        * ``"circle"`` — ``(radius,)`` (arity 1).
        * ``"ellipse"`` — ``(semi_major, semi_minor)`` (arity 2) where
          ``semi_minor`` is the cylinder radius and
          ``semi_major = radius / cos(θ) >= semi_minor`` for cut angle ``θ``
          between the plane normal and the cylinder axis (``semi_major >=
          semi_minor`` is enforced at construction).
        * ``"rectangle"`` — ``(width, height)`` = ``(2·radius, height)`` (arity
          2) for a plane parallel to the axis.
    approximate : bool
        ``True`` when the dimensions are a *through-axis* simplification that
        ignores the cutting plane's offset and may overstate the true chord;
        ``False`` when exact. :func:`cylinder_cross_section` sets it ``True`` for
        the offset-dependent ``ellipse``/``rectangle`` cases and ``False`` for
        the ``circle`` case (radius ``r`` regardless of offset). A ``circle``
        forbids ``approximate=True`` (it is always exact).

    Raises
    ------
    ValueError
        If any dimension is non-finite or ``<= 0``, if an ``ellipse`` has
        ``semi_major < semi_minor``, or if a ``circle`` is built with
        ``approximate=True``.
    """

    kind: Literal["circle", "ellipse", "rectangle"] = field(init=False)
    _dimensions: tuple[float, ...] = field(init=False)
    approximate: bool = False

    @classmethod
    def circle(cls, radius: float) -> "CylinderCrossSection":
        """Build a circular cross-section (offset-independent perpendicular cut).

        Parameters
        ----------
        radius : float
            Cylinder radius; must be finite and ``> 0``.

        Returns
        -------
        CylinderCrossSection
            A ``kind="circle"`` instance with ``approximate=False`` (a circle is
            always exact).
        """
        return cls._build("circle", (radius,), approximate=False)

    @classmethod
    def ellipse(
        cls, semi_major: float, semi_minor: float, *, approximate: bool = True
    ) -> "CylinderCrossSection":
        """Build an elliptical cross-section (oblique cut).

        Parameters
        ----------
        semi_major : float
            Semi-major axis ``r / cos(θ)``; must be ``>= semi_minor``.
        semi_minor : float
            Semi-minor axis (the cylinder radius ``r``).
        approximate : bool, keyword-only, optional
            ``True`` (default) when the span assumes a through-axis plane.

        Returns
        -------
        CylinderCrossSection
            A ``kind="ellipse"`` instance.
        """
        return cls._build("ellipse", (semi_major, semi_minor), approximate=approximate)

    @classmethod
    def rectangle(
        cls, width: float, height: float, *, approximate: bool = True
    ) -> "CylinderCrossSection":
        """Build a rectangular cross-section (cut parallel to the axis).

        Parameters
        ----------
        width : float
            Rectangle width ``2·radius``.
        height : float
            Rectangle height (the cylinder height).
        approximate : bool, keyword-only, optional
            ``True`` (default) when the span assumes a through-axis plane.

        Returns
        -------
        CylinderCrossSection
            A ``kind="rectangle"`` instance.
        """
        return cls._build("rectangle", (width, height), approximate=approximate)

    @classmethod
    def _build(
        cls,
        kind: Literal["circle", "ellipse", "rectangle"],
        dimensions: tuple[float, ...],
        *,
        approximate: bool,
    ) -> "CylinderCrossSection":
        """Set the ``init=False`` fields on a fresh frozen instance.

        Routing every classmethod through this single factory keeps the
        ``kind``↔arity pairing in one place, so the constructors cannot mint an
        inconsistent instance.
        """
        instance = cls(approximate=approximate)
        object.__setattr__(instance, "kind", kind)
        object.__setattr__(instance, "_dimensions", dimensions)
        instance.__validate__()
        return instance

    def __validate__(self) -> None:
        """Validate the ``init=False`` fields after the factory sets them.

        Not ``__post_init__``: the auto-generated ``__init__`` runs before
        ``kind``/``_dimensions`` are assigned, so validation is invoked by
        :meth:`_build` once the instance is fully populated.
        """
        expected = _CROSS_SECTION_ARITY[self.kind]
        if len(self._dimensions) != expected:
            raise ValueError(
                f"CylinderCrossSection {self.kind!r} requires {expected} "
                f"dimension(s); got {self._dimensions!r}"
            )
        for value in self._dimensions:
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(
                    f"CylinderCrossSection {self.kind!r} dimensions must be "
                    f"finite and > 0; got {self._dimensions!r}"
                )
        if self.kind == "ellipse" and self._dimensions[0] < self._dimensions[1]:
            raise ValueError(
                f"CylinderCrossSection ellipse semi_major must be >= semi_minor; "
                f"got {self._dimensions!r}"
            )
        # A circular cross-section is the offset-independent perpendicular cut:
        # its radius ``r`` is exact regardless of the cutting plane's offset, so
        # ``approximate`` must never be True for a circle. Ellipse/rectangle may
        # be either (their through-axis spans are a simplification).
        if self.kind == "circle" and self.approximate:
            raise ValueError(
                "CylinderCrossSection circle is always exact; approximate must be False"
            )

    @property
    def radius(self) -> float:
        """Cylinder radius — ``circle`` or ``ellipse`` semi-minor; raises for ``rectangle``."""
        if self.kind == "circle":
            return self._dimensions[0]
        if self.kind == "ellipse":
            return self._dimensions[1]
        raise AttributeError(f"{self.kind!r} cross-section has no radius")

    @property
    def semi_major(self) -> float:
        """Semi-major axis — ``ellipse`` only; raises ``AttributeError`` otherwise."""
        if self.kind == "ellipse":
            return self._dimensions[0]
        raise AttributeError(f"{self.kind!r} cross-section has no semi_major axis")

    @property
    def semi_minor(self) -> float:
        """Semi-minor axis (cylinder radius) — ``ellipse`` only; raises otherwise."""
        if self.kind == "ellipse":
            return self._dimensions[1]
        raise AttributeError(f"{self.kind!r} cross-section has no semi_minor axis")

    @property
    def width(self) -> float:
        """Width (``2·radius``) — ``rectangle`` only; raises ``AttributeError`` otherwise."""
        if self.kind == "rectangle":
            return self._dimensions[0]
        raise AttributeError(f"{self.kind!r} cross-section has no width")

    @property
    def height(self) -> float:
        """Height (cylinder height) — ``rectangle`` only; raises ``AttributeError`` otherwise."""
        if self.kind == "rectangle":
            return self._dimensions[1]
        raise AttributeError(f"{self.kind!r} cross-section has no height")


def cylinder_cross_section(cylinder: Cylinder, plane_normal: np.ndarray) -> CylinderCrossSection:
    """Classify and size the cross-section of a cylinder cut by a plane.

    The shape is governed by the angle ``θ`` between the cutting plane's normal
    and the cylinder axis:

    * normal **parallel** to the axis (cut perpendicular to the axis) → a
      **circle** of radius ``r``;
    * normal **perpendicular** to the axis (cut parallel to the axis) → a
      **rectangle** ``2r`` wide and ``h`` tall;
    * otherwise → an **ellipse** with semi-minor axis ``r`` and semi-major axis
      ``r / cos(θ)``.

    Classification is performed on ``cos θ`` directly — where ``θ`` is the angle
    between the plane normal and the cylinder axis — **not** on the ``acos``
    output. ``acos`` is ill-conditioned near its endpoints (its derivative
    diverges as ``cos θ → ±1``), so a tolerance applied to ``θ`` would demand
    ``cos θ`` lie within ~5e-19 of 1.0 — finer than float64 resolution — and a
    realistic inclined or trig-derived normal would misclassify as an ellipse,
    blowing up ``semi_major = r / cos θ``. Testing in the well-conditioned
    ``cos θ`` domain — **circle** when ``(1 − cos θ) < EPS_ANGLE``, **rectangle**
    when ``cos θ < EPS_ANGLE`` — keeps the thresholds numerically reachable.

    Parameters
    ----------
    cylinder : Cylinder
        Source cylinder (provides ``radius``, ``height``, and axis).
    plane_normal : numpy.ndarray
        Normal vector of the cutting plane, shape ``(3,)``. Need not be unit
        length; it is normalised internally.

    Returns
    -------
    CylinderCrossSection
        The classified cross-section and its dimensions.

    Raises
    ------
    ValueError
        If ``plane_normal`` has (near) zero length, so its direction — and the
        cut angle — is undefined.
    ValueError
        If ``plane_normal`` contains a non-finite component (``nan`` or
        ``±inf``). A ``nan`` component bypasses the zero-length guard (``norm``
        is ``nan`` and ``nan < EPS_DISTANCE`` is ``False``), then ``cos_theta``
        clamps to ``1.0`` and the function would fabricate an exact ``circle``
        result from corrupt input.

    Notes
    -----
    This is a **through-axis** simplification: only the plane *normal* is
    consumed, not its offset along that normal. The reported sizes assume the
    cutting plane passes through the cylinder axis, so the rectangle width is
    the full ``2r`` and the ellipse spans the full radius. An off-axis plane
    parallel to one of these but offset by a perpendicular distance ``d``
    actually yields a narrower chord — width ``2·√(r² − d²)`` rather than
    ``2r`` — which this function does not model.

    The returned ``approximate`` flag reflects this: ``True`` for the
    offset-dependent ``ellipse``/``rectangle`` cases and ``False`` for the exact
    ``circle`` case, so callers can distinguish an exact slice from this one.
    """
    axis = cylinder_axis_vector(cylinder)
    normal = np.asarray(plane_normal, dtype=np.float64)
    if not np.all(np.isfinite(normal)):
        raise ValueError(
            f"cylinder_cross_section: plane_normal contains nan or ±inf; got {plane_normal!r}"
        )
    norm = float(np.linalg.norm(normal))
    if norm < EPS_DISTANCE:
        raise ValueError("cylinder_cross_section: plane_normal has zero length")
    cos_theta = abs(float(np.dot(axis, normal / norm)))
    # Clamp to guard against a dot product nudged just past 1.0 by rounding.
    cos_theta = min(1.0, cos_theta)
    r = float(cylinder.radius)
    # Classify in the well-conditioned cos-θ domain (see docstring), never on
    # acos(cos_theta): near the endpoints acos amplifies error past float64
    # resolution and misclassifies realistic inclined normals as ellipses.
    # ``approximate``: circle radius is offset-independent (exact); the ellipse
    # and rectangle spans assume a through-axis plane (simplified).
    if (1.0 - cos_theta) < EPS_ANGLE:  # normal ∥ axis → perpendicular cut
        return CylinderCrossSection.circle(r)
    if cos_theta < EPS_ANGLE:  # normal ⊥ axis → parallel cut
        return CylinderCrossSection.rectangle(2.0 * r, float(cylinder.height))
    return CylinderCrossSection.ellipse(r / cos_theta, r)


# ---------------------------------------------------------------------------
# Solid geometry (Mirtich 1996 polyhedral mass properties)
# ---------------------------------------------------------------------------


def _ensure_solid_is_stack(solid: Solid, objects: Mapping[str, GeoObject]) -> None:
    """Reject a Solid whose ``layers`` are a facet shell, not a cross-section stack.

    The whole Solid B-rep / volume machinery interprets ``Solid.layers`` as an
    **ordered bottom-to-top stack of cross-sections**: the first and last layers
    are the caps and each adjacent pair forms one lateral band. A 3-D convex
    hull (:func:`convex_hull_3d`), by contrast, stores triangular *facets* of a
    closed shell in ``layers`` — a structurally different object. Fed a facet
    shell, the band builder would silently pair facet *i* with facet *i+1* and
    return a meaningless volume with no error, because every facet is a triangle
    so the equal-vertex-count band path accepts it.

    A facet shell is detected structurally: in a valid cross-section stack each
    vertex Point ID belongs to exactly one layer's polygon (distinct
    cross-sections share no vertices), whereas in a hull shell every vertex is
    shared by three or more facets. So a vertex appearing in **more than two**
    polygon layers cannot be a stack and is rejected. (The coplanar-hull
    fallback's two *identical* layers — each vertex in exactly two layers — is a
    legitimate zero-extent stack and is intentionally *not* rejected.)

    This is the proportionate guard for a geometry-services PR: it refuses a
    facet-shell Solid with a clear error rather than expanding the persistence
    schema to carry an explicit ``layers``-kind discriminator.

    Parameters
    ----------
    solid : Solid
        The candidate solid.
    objects : Mapping[str, GeoObject]
        Object lookup resolving each polygon layer to its Polygon (for its
        ``point_ids``).

    Raises
    ------
    ValueError
        If a vertex Point ID appears in more than two polygon layers, i.e. the
        Solid is a facet shell rather than a cross-section stack.
    """
    layer_counts: dict[str, int] = {}
    for layer_id in solid.layers:
        if layer_id.startswith("pt_"):
            continue
        polygon = objects[layer_id]
        for pid in set(polygon.point_ids):  # one count per layer per vertex
            layer_counts[pid] = layer_counts.get(pid, 0) + 1
    offenders = sorted(pid for pid, count in layer_counts.items() if count > 2)
    if offenders:
        raise ValueError(
            "Solid.layers look like a convex-hull facet shell, not a "
            f"bottom-to-top cross-section stack: vertices {offenders!r} appear "
            "in more than two polygon layers. solid_volume_centroid / "
            "solid_faces require a stack; pass a stacked Solid, or measure the "
            "hull's facets directly."
        )


def _solid_layer_rings(
    solid: Solid,
    objects: Mapping[str, GeoObject],
    points: Mapping[str, Point],
) -> list[tuple[bool, list[np.ndarray]]]:
    """Resolve a Solid's layer stack to ``(is_point, vertices)`` per layer.

    ``Solid.layers`` is contractually an **ordered bottom-to-top stack of
    cross-sections** — the first and last entries are the caps and each adjacent
    pair defines one lateral band — **not** a list of B-rep faces/facets. A
    convex-hull Solid (:func:`convex_hull_3d`) violates that contract by storing
    triangular facets here; :func:`_ensure_solid_is_stack` rejects such input
    before this resolver runs.

    Each polygon layer yields ``(False, [v0, v1, ...])`` of ``(3,)`` vertex
    arrays in stored order; each point (apex/nadir) layer yields
    ``(True, [vertex])``.

    Raises
    ------
    ValueError
        If any resolved vertex is non-finite (``nan``/``±inf``). This is the
        single up-front screen shared by every Solid metric routing through
        here — :func:`solid_faces`, :func:`solid_volume_centroid`, and both
        surface-area paths — so an area computation fails loud rather than
        returning a silent ``nan``. (The volume path keeps its own late
        non-finite gate for defence in depth, but a poisoned vertex is now
        caught here first.)
    """
    rings: list[tuple[bool, list[np.ndarray]]] = []
    for layer_id in solid.layers:
        if layer_id.startswith("pt_"):
            rings.append((True, [_xyz(points[layer_id])]))
        else:
            polygon = objects[layer_id]
            rings.append((False, [_xyz(points[pid]) for pid in polygon.point_ids]))
    if not all(np.all(np.isfinite(v)) for _, ring in rings for v in ring):
        raise ValueError("solid layer vertices contain nan or ±inf")
    return rings


def _lateral_faces(
    lower: tuple[bool, list[np.ndarray]], upper: tuple[bool, list[np.ndarray]]
) -> list[list[np.ndarray]]:
    """Outward-wound lateral faces between two adjacent layers.

    Handles equal-vertex-count polygon bands (quads) and the apex cases (a
    point layer on either side → triangle fan). Bands between polygons of
    *differing* vertex counts are rejected — the vertex correspondence is
    ambiguous and outside this issue's scope.

    .. note::
       For an equal-count polygon band this assumes **positional vertex
       correspondence**: ``low[i]`` connects to ``up[i]`` (and ``low[i+1]`` to
       ``up[i+1]``). If the upper polygon is rotated relative to the lower —
       same vertex count but offset start index, or reversed winding — the quads
       wind into a twisted, self-intersecting shell whose volume is wrong, and
       the only thing rejected today is the *differing*-count case. A twist is
       **not** caught here: a cheap zero-area-quad screen was considered and
       rejected because the legitimate coplanar-hull fallback (two identical
       flat layers, :func:`_coplanar_fallback_solid`) produces zero-area bands
       by design, so such a screen would false-positive on valid degenerate
       input. Callers must therefore supply layers in corresponding vertex
       order.
    """
    lower_is_pt, low = lower
    upper_is_pt, up = upper
    faces: list[list[np.ndarray]] = []
    if upper_is_pt:
        apex = up[0]
        n = len(low)
        for i in range(n):
            faces.append([low[i], low[(i + 1) % n], apex])
    elif lower_is_pt:
        apex = low[0]
        n = len(up)
        for i in range(n):
            faces.append([apex, up[(i + 1) % n], up[i]])
    else:
        if len(low) != len(up):
            raise ValueError(
                "solid lateral band between polygons of differing vertex counts is not supported"
            )
        n = len(low)
        for i in range(n):
            faces.append([low[i], low[(i + 1) % n], up[(i + 1) % n], up[i]])
    return faces


def solid_faces(
    solid: Solid,
    objects: Mapping[str, GeoObject],
    points: Mapping[str, Point],
) -> list[list[np.ndarray]]:
    """Closed B-rep of a Solid as a list of outward-wound polygon faces.

    Builds the boundary representation from the layer stack
    (``docs/implementation-design.md`` §13.8):
    a bottom cap (first layer, reversed so its normal faces down/outward), a
    top cap (last layer, kept as stored so its normal faces up/outward), and
    the lateral faces between every pair of adjacent layers. Point (apex/nadir)
    end layers have no cap; their band is a triangle fan. All faces are wound
    with consistent outward normals so the divergence-theorem volume in
    :func:`solid_volume_centroid` is sign-consistent.

    Parameters
    ----------
    solid : Solid
        The solid whose layer stack is converted.
    objects : Mapping[str, GeoObject]
        Object lookup resolving each polygon layer ID to its Polygon.
    points : Mapping[str, Point]
        Point lookup resolving every vertex ID.

    Returns
    -------
    list[list[numpy.ndarray]]
        Faces, each a list of ``(3,)`` vertex arrays.

    Raises
    ------
    ValueError
        If a lateral band joins polygons of differing vertex counts.
    """
    caps, laterals = _solid_brep(solid, objects, points)
    return caps + laterals


def _solid_brep(
    solid: Solid,
    objects: Mapping[str, GeoObject],
    points: Mapping[str, Point],
) -> tuple[list[list[np.ndarray]], list[list[np.ndarray]]]:
    """Return ``(cap_faces, lateral_faces)`` of a Solid's closed B-rep.

    Raises
    ------
    ValueError
        If ``solid`` is a convex-hull facet shell rather than a cross-section
        stack (see :func:`_ensure_solid_is_stack`). The function also asserts
        at least two layers, but this is belt-and-suspenders:
        :meth:`Solid.__post_init__` already rejects a 0- or 1-layer Solid at
        construction, so a real Solid can never reach that guard.
    """
    _ensure_solid_is_stack(solid, objects)
    rings = _solid_layer_rings(solid, objects, points)
    if len(rings) < 2:
        raise ValueError(
            f"Solid B-rep requires at least 2 layers; got {len(rings)} "
            f"(a 0- or 1-layer Solid has no cap/lateral structure)"
        )
    caps: list[list[np.ndarray]] = []
    first_is_pt, first = rings[0]
    last_is_pt, last = rings[-1]
    if not first_is_pt:
        caps.append(list(reversed(first)))  # bottom cap: outward normal points down
    if not last_is_pt:
        caps.append(list(last))  # top cap: outward normal points up
    laterals: list[list[np.ndarray]] = []
    for lower, upper in zip(rings, rings[1:]):
        laterals.extend(_lateral_faces(lower, upper))
    return caps, laterals


def _face_area_vector(face: Sequence[np.ndarray]) -> np.ndarray:
    """Newell area vector of a planar polygon face (½·Σ vᵢ × vᵢ₊₁)."""
    total = np.zeros(3, dtype=np.float64)
    n = len(face)
    for i in range(n):
        total += np.cross(face[i], face[(i + 1) % n])
    return 0.5 * total


def _face_area(face: Sequence[np.ndarray]) -> np.float64:
    """Area of a planar polygon face."""
    return np.float64(np.linalg.norm(_face_area_vector(face)))


def solid_volume_centroid(
    solid: Solid,
    objects: Mapping[str, GeoObject],
    points: Mapping[str, Point],
) -> tuple[np.float64, np.ndarray]:
    """Volume and centroid of a Solid (Mirtich 1996 polyhedral mass properties).

    Builds the closed B-rep via :func:`solid_faces`, fan-triangulates each
    face, and accumulates the signed-tetrahedron decomposition — the
    divergence-theorem surface integral underlying Mirtich's method. The
    volume is ``Σ (p₀ · (p₁ × p₂)) / 6`` over the triangles; the centroid is the
    volume-weighted mean of the tetra centroids ``(p₀+p₁+p₂)/4``.

    The tetra/centroid sum is accumulated in a frame shifted by a reference
    vertex (the first vertex of the first face), not the absolute UTM origin.
    Mirtich's decomposition is translation-invariant in the volume and the
    centroid simply translates by the same offset, so this is exact — but it
    avoids the catastrophic cancellation that would otherwise lose ~5 significant
    digits: at UTM magnitudes (E~5e5, N~4e6) the unshifted tetra products are
    ~1e17 and the volume emerges as their tiny difference. The reference offset
    is added back to the returned centroid; the volume needs no correction.

    Because every face is consistently wound (:func:`solid_faces`), the signed
    volume's global sign is uniform: the reported volume is its magnitude, and
    the centroid ``ΣC / ΣV`` is correct regardless of whether the shell is
    globally inward- or outward-oriented (both numerator and denominator share
    the sign).

    A degenerate (coplanar, zero-extent) Solid returns volume ``0.0`` paired
    with a **nan-filled centroid** (``np.full(3, nan)``), not a fabricated
    ``(0, 0, 0)``: in UTM metres the origin is hundreds of kilometres from any
    real geometry, so returning it would silently plant the centroid in the
    ocean and could not be told apart from a flat solid whose
    inconsistently-wound faces happen to cancel to ~0. A ``nan`` centroid is the
    honest "undefined" signal; callers gate on volume via
    :func:`geometry.services.validation.validate_solid_non_degenerate` against
    :data:`~geometry.utils.constants.EPS_VOLUME`. The volume agrees with the
    Wuttke (2021) Eq. 22 form-factor cross-check ``(1/3)·Σ Ar(face)·r_perp``.

    Parameters
    ----------
    solid : Solid
        The solid to measure.
    objects : Mapping[str, GeoObject]
        Object lookup resolving polygon layers.
    points : Mapping[str, Point]
        Point lookup resolving vertices.

    Returns
    -------
    tuple[numpy.float64, numpy.ndarray]
        ``(volume, centroid)`` — non-negative volume in cubic metres and the
        ``(easting, northing, altitude)`` centroid, shape ``(3,)``. A
        zero-volume (or non-finite) Solid returns ``(0.0, np.full(3, nan))``:
        the centroid is undefined, not the UTM origin.

    Raises
    ------
    ValueError
        If ``solid`` is a convex-hull facet shell rather than a cross-section
        stack (propagated from :func:`solid_faces`). The underlying B-rep also
        asserts at least two layers, but :meth:`Solid.__post_init__` already
        rejects a 0- or 1-layer Solid at construction, so a real Solid can
        never trigger that path.
    """
    faces = solid_faces(solid, objects, points)
    # Anchor the accumulation at the first vertex to keep the tetra products in a
    # small local frame; see the docstring for the UTM-cancellation rationale.
    ref = faces[0][0] if faces else np.zeros(3, dtype=np.float64)
    signed_v = np.float64(0.0)
    moment = np.zeros(3, dtype=np.float64)
    for face in faces:
        v0 = face[0] - ref
        for i in range(1, len(face) - 1):
            v1 = face[i] - ref
            v2 = face[i + 1] - ref
            tetra = float(np.dot(v0, np.cross(v1, v2))) / 6.0
            signed_v += tetra
            moment += tetra * (v0 + v1 + v2) / 4.0
    # A non-finite signed volume (from a nan/inf vertex) must not slip past the
    # degeneracy gate: ``nan < EPS_VOLUME`` is False, so without this branch the
    # function would return ``(nan, moment/nan)``. Treat non-finite as degenerate
    # alongside the genuine zero-extent case.
    if not math.isfinite(float(signed_v)) or abs(signed_v) < EPS_VOLUME:
        return np.float64(0.0), np.full(3, np.nan, dtype=np.float64)
    # Centroid was computed in the shifted frame; translate it back by ``ref``.
    return np.float64(abs(signed_v)), moment / signed_v + ref


def solid_lateral_surface_area(
    solid: Solid,
    objects: Mapping[str, GeoObject],
    points: Mapping[str, Point],
) -> np.float64:
    """Total area of a Solid's lateral faces (the bands between layers).

    Raises
    ------
    ValueError
        If ``solid`` is a convex-hull facet shell rather than a cross-section
        stack, or its layers yield bands with differing vertex counts
        (propagated from :func:`_solid_brep`). The underlying B-rep also
        asserts at least two layers, but :meth:`Solid.__post_init__` already
        rejects a 0- or 1-layer Solid at construction, so a real Solid can
        never trigger that path.
    """
    _, laterals = _solid_brep(solid, objects, points)
    return np.float64(sum(_face_area(f) for f in laterals))


def solid_total_surface_area(
    solid: Solid,
    objects: Mapping[str, GeoObject],
    points: Mapping[str, Point],
) -> np.float64:
    """Total surface area of a Solid: lateral bands plus the cap faces.

    Raises
    ------
    ValueError
        If ``solid`` is a convex-hull facet shell rather than a cross-section
        stack, or its layers yield bands with differing vertex counts
        (propagated from :func:`_solid_brep`). The underlying B-rep also
        asserts at least two layers, but :meth:`Solid.__post_init__` already
        rejects a 0- or 1-layer Solid at construction, so a real Solid can
        never trigger that path.
    """
    caps, laterals = _solid_brep(solid, objects, points)
    return np.float64(sum(_face_area(f) for f in caps + laterals))
