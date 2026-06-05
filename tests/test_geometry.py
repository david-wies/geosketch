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

"""Tests for ``geometry.services.geometry`` (issue #13).

Every formula in the acceptance criteria gets a known-input/known-output
test: direction (azimuth), Euclidean distance, convexity, convex hull,
signed area, the four intersection types, the two polygon distances, the
tangent direction, and the vector endpoint. Inputs are chosen so the
expected results are exact (axis-aligned squares, 3-4-5 triangles) and can
be asserted without depending on floating-point noise beyond a tight
tolerance.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.spatial import QhullError  # pylint: disable=no-name-in-module

from geometry.models.common import DirectionMode, DirectionUnits
from geometry.models.line import Line
from geometry.models.point import Point
from geometry.models.polygon import Polygon
from geometry.models.ray import Ray
from geometry.services import geometry as geo
from geometry.utils.constants import EPS_DISTANCE

# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------


def _pt(pid: str, easting: float, northing: float, altitude: float = 0.0) -> Point:
    return Point(
        id=pid,
        name=pid,
        alpha=1.0,
        visibility=True,
        easting=float(easting),
        northing=float(northing),
        altitude=float(altitude),
        color="#000000",
    )


def _poly(pid: str, point_ids: list[str], name: str = "poly") -> Polygon:
    return Polygon(
        id=pid,
        name=name,
        alpha=1.0,
        visibility=True,
        point_ids=point_ids,
        is_convex=False,
        line_color="#000000",
        fill_color="#cccccc",
    )


def _elevated_kwargs(direction: float = 0.0, mode: DirectionMode = DirectionMode.AZIMUTH) -> dict:
    """Common envelope + direction kwargs shared by the elevated-object builders."""
    return {
        "alpha": 1.0,
        "visibility": True,
        "direction": float(direction),
        "elevation": 0.0,
        "direction_mode": mode,
        "direction_units": DirectionUnits.RADIANS,
        "line_color": "#000000",
        "fill_color": "#cccccc",
    }


def _line(pid: str, a_id: str, b_id: str) -> Line:
    return Line(id=pid, name=pid, point_a_id=a_id, point_b_id=b_id, **_elevated_kwargs())


def _ray(
    pid: str,
    origin_id: str,
    direction: float,
    mode: DirectionMode = DirectionMode.AZIMUTH,
) -> Ray:
    return Ray(id=pid, name=pid, origin_id=origin_id, **_elevated_kwargs(direction, mode))


def _unit_square(prefix: str = "s") -> tuple[dict[str, Point], Polygon]:
    """CCW unit-ish square with corners at (0,0),(2,0),(2,2),(0,2)."""
    pts = {
        f"{prefix}0": _pt(f"{prefix}0", 0, 0),
        f"{prefix}1": _pt(f"{prefix}1", 2, 0),
        f"{prefix}2": _pt(f"{prefix}2", 2, 2),
        f"{prefix}3": _pt(f"{prefix}3", 0, 2),
    }
    poly = _poly(f"pg_{prefix}", [f"{prefix}0", f"{prefix}1", f"{prefix}2", f"{prefix}3"])
    return pts, poly


# ---------------------------------------------------------------------------
# direction / distance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("east", "north", "expected"),
    [
        (0.0, 1.0, 0.0),  # due North
        (1.0, 0.0, math.pi / 2),  # due East
        (0.0, -1.0, math.pi),  # due South
        (-1.0, 0.0, 3 * math.pi / 2),  # due West
    ],
)
def test_azimuth_cardinal_directions(east, north, expected):
    a = _pt("a", 0, 0)
    b = _pt("b", east, north)
    result = geo.azimuth(a, b)
    assert isinstance(result, np.float64)
    assert result == pytest.approx(expected)


def test_azimuth_normalized_to_2pi():
    # Due West would be atan2(-1, 0) = -pi/2; must normalize to 3pi/2, not stay negative.
    result = geo.azimuth(_pt("a", 0, 0), _pt("b", -1, 0))
    assert 0.0 <= result < 2 * math.pi


def test_distance_3_4_5():
    result = geo.distance(_pt("a", 0, 0), _pt("b", 3, 4))
    assert isinstance(result, np.float64)
    assert result == pytest.approx(5.0)


def test_distance_zero_for_coincident_points():
    assert geo.distance(_pt("a", 7, 7), _pt("b", 7, 7)) == pytest.approx(0.0)


def test_distance_3d_altitude_component():
    # Pure vertical separation: only altitude differs, so distance == |Δz|.
    result = geo.distance(_pt("a", 0, 0, 0.0), _pt("b", 0, 0, 5.0))
    assert isinstance(result, np.float64)
    assert result == pytest.approx(5.0)


def test_distance_3d_pythagorean_quadruple():
    # 3-4-12-13 Pythagorean quadruple: sqrt(3²+4²+12²) = sqrt(9+16+144) = 13.
    result = geo.distance(_pt("a", 0, 0, 0.0), _pt("b", 3, 4, 12.0))
    assert result == pytest.approx(13.0)


# ---------------------------------------------------------------------------
# horizontal unit vector (both modes)
# ---------------------------------------------------------------------------


def test_horizontal_unit_vector_azimuth_east():
    # Azimuth pi/2 is due East => unit vector (1, 0) in (easting, northing).
    ray = _ray("ry", "o", math.pi / 2, DirectionMode.AZIMUTH)
    vec = geo.horizontal_unit_vector(ray)
    assert vec.shape == (2,)
    assert vec.dtype == np.float64
    assert vec[0] == pytest.approx(1.0)
    assert vec[1] == pytest.approx(0.0)


def test_horizontal_unit_vector_angle_east():
    # Math angle 0 is due East => (cos 0, sin 0) = (1, 0).
    ray = _ray("ry", "o", 0.0, DirectionMode.ANGLE)
    vec = geo.horizontal_unit_vector(ray)
    assert vec[0] == pytest.approx(1.0)
    assert vec[1] == pytest.approx(0.0)


def test_horizontal_unit_vector_angle_north():
    # Math angle pi/2 is due North => (cos, sin) = (0, 1).
    ray = _ray("ry", "o", math.pi / 2, DirectionMode.ANGLE)
    vec = geo.horizontal_unit_vector(ray)
    assert vec[0] == pytest.approx(0.0)
    assert vec[1] == pytest.approx(1.0)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_horizontal_unit_vector_rejects_non_finite_direction(bad):
    # A corrupted (e.g. malformed-JSON) direction must fail loud here rather
    # than propagate a [nan, nan] vector that silently poisons callers. The
    # model now rejects a non-finite direction at construction, so bypass the
    # constructor to exercise the function's own defense-in-depth guard.
    ray = _ray("ry", "o", 0.0)
    ray.direction = bad
    with pytest.raises(ValueError, match="finite"):
        geo.horizontal_unit_vector(ray)


# ---------------------------------------------------------------------------
# signed area
# ---------------------------------------------------------------------------


def test_signed_area_ccw_is_positive():
    pts, poly = _unit_square()
    area = geo.signed_area(poly, pts)
    assert isinstance(area, np.float64)
    assert area == pytest.approx(4.0)  # 2x2 square


def test_signed_area_cw_is_negative():
    pts, poly = _unit_square()
    poly.point_ids = list(reversed(poly.point_ids))
    assert geo.signed_area(poly, pts) == pytest.approx(-4.0)


# ---------------------------------------------------------------------------
# convexity
# ---------------------------------------------------------------------------


def test_is_convex_true_for_square():
    pts, poly = _unit_square()
    assert geo.is_convex(poly, pts) is True


def test_is_convex_false_for_concave_arrow():
    # Classic concave "arrowhead": the notch vertex creates a reflex angle.
    pts = {
        "c0": _pt("c0", 0, 0),
        "c1": _pt("c1", 4, 0),
        "c2": _pt("c2", 2, 2),  # reflex notch pulled inward
        "c3": _pt("c3", 4, 4),
        "c4": _pt("c4", 0, 4),
    }
    poly = _poly("pg_c", ["c0", "c1", "c2", "c3", "c4"])
    assert geo.is_convex(poly, pts) is False


def test_is_convex_false_for_concave_with_duplicate_at_reflex_vertex():
    # A duplicated vertex at the reflex notch creates a zero-length edge that
    # straddles the reflex turn. Pairing turns by raw index would mask that
    # turn and wrongly report convex; compacting degenerate edges first keeps
    # the polygon correctly classified as concave.
    pts = {
        "c0": _pt("c0", 0, 0),
        "c1": _pt("c1", 4, 0),
        "c2": _pt("c2", 2, 2),  # reflex notch
        "c2b": _pt("c2b", 2, 2),  # exact duplicate of the notch vertex
        "c3": _pt("c3", 4, 4),
        "c4": _pt("c4", 0, 4),
    }
    poly = _poly("pg_cd", ["c0", "c1", "c2", "c2b", "c3", "c4"])
    assert geo.is_convex(poly, pts) is False


def test_is_convex_true_for_square_with_duplicate_vertex():
    # A redundant duplicated vertex on a convex polygon must not flip the
    # result to concave — the compaction drops the zero-length edge cleanly.
    pts = {
        "s0": _pt("s0", 0, 0),
        "s1": _pt("s1", 2, 0),
        "s1b": _pt("s1b", 2, 0),  # duplicate, mid-boundary
        "s2": _pt("s2", 2, 2),
        "s3": _pt("s3", 0, 2),
    }
    poly = _poly("pg_sd", ["s0", "s1", "s1b", "s2", "s3"])
    assert geo.is_convex(poly, pts) is True


def test_is_convex_false_for_cw_wound_concave():
    # Same arrowhead, but wound clockwise (reversed order). The sign of the
    # turns flips wholesale, yet a reflex vertex still produces a mixed sign,
    # so it must remain concave. Guards the CW branch the creation path can
    # transiently see before signed-area reversal.
    pts = {
        "c0": _pt("c0", 0, 0),
        "c1": _pt("c1", 4, 0),
        "c2": _pt("c2", 2, 2),  # reflex notch
        "c3": _pt("c3", 4, 4),
        "c4": _pt("c4", 0, 4),
    }
    poly = _poly("pg_c", list(reversed(["c0", "c1", "c2", "c3", "c4"])))
    assert geo.is_convex(poly, pts) is False


# ---------------------------------------------------------------------------
# convex hull
# ---------------------------------------------------------------------------


def test_convex_hull_drops_interior_point():
    pts, _ = _unit_square()
    pts["s4"] = _pt("s4", 1, 1)  # interior point
    poly = _poly("pg_h", ["s0", "s1", "s2", "s3", "s4"], name="myshape")

    hull = geo.convex_hull(poly, pts, "pg_999")

    assert isinstance(hull, Polygon)
    assert hull.id == "pg_999"
    assert hull.name == "myshape_convex_hull"
    assert hull.is_convex is True
    assert "s4" not in hull.point_ids
    assert set(hull.point_ids) == {"s0", "s1", "s2", "s3"}


def test_convex_hull_is_ccw():
    pts, _ = _unit_square()
    pts["s4"] = _pt("s4", 1, 1)
    poly = _poly("pg_h", ["s0", "s1", "s2", "s3", "s4"], name="shape")
    hull = geo.convex_hull(poly, pts, "pg_999")
    # CCW winding => positive signed area.
    assert geo.signed_area(hull, pts) > 0


def test_convex_hull_raises_on_collinear():
    # Three collinear points are degenerate for hull construction. Unlike the
    # intersection/distance helpers, convex_hull propagates QhullError.
    pts = {
        "k0": _pt("k0", 0, 0),
        "k1": _pt("k1", 1, 1),
        "k2": _pt("k2", 2, 2),
    }
    poly = _poly("pg_k", ["k0", "k1", "k2"])
    with pytest.raises(QhullError):
        geo.convex_hull(poly, pts, "pg_999")


# ---------------------------------------------------------------------------
# line-line intersection
# ---------------------------------------------------------------------------


def test_line_intersection_crossing():
    pts = {
        "a0": _pt("a0", 0, 0),
        "a1": _pt("a1", 2, 0),  # horizontal line y=0
        "b0": _pt("b0", 1, -1),
        "b1": _pt("b1", 1, 1),  # vertical line x=1
    }
    la = _line("ln_a", "a0", "a1")
    lb = _line("ln_b", "b0", "b1")
    result = geo.line_intersection(la, lb, pts)
    assert result is not None
    assert result[0] == pytest.approx(1.0)
    assert result[1] == pytest.approx(0.0)


def test_line_intersection_small_scale_not_falsely_parallel():
    # Genuinely perpendicular lines at sub-millimetre scale. The raw
    # (non-normalized) cross product is |d1||d2|·sin θ, so the tiny |d|
    # factors drag it below EPS_ANGLE and the lines were wrongly judged
    # parallel. Normalizing the directions first makes EPS_ANGLE a true
    # angular tolerance, so a real 90° crossing is always detected.
    s = 2e-5
    pts = {
        "a0": _pt("a0", 0, 0),
        "a1": _pt("a1", s, 0),  # horizontal
        "b0": _pt("b0", 0, -s),
        "b1": _pt("b1", 0, s),  # vertical
    }
    la = _line("ln_a", "a0", "a1")
    lb = _line("ln_b", "b0", "b1")
    result = geo.line_intersection(la, lb, pts)
    assert result is not None
    assert result[0] == pytest.approx(0.0)
    assert result[1] == pytest.approx(0.0)


def test_line_intersection_parallel_returns_none():
    pts = {
        "a0": _pt("a0", 0, 0),
        "a1": _pt("a1", 2, 0),  # y=0
        "b0": _pt("b0", 0, 1),
        "b1": _pt("b1", 2, 1),  # y=1, parallel
    }
    la = _line("ln_a", "a0", "a1")
    lb = _line("ln_b", "b0", "b1")
    assert geo.line_intersection(la, lb, pts) is None


def test_line_intersection_zero_length_line_returns_none():
    # One "line" has coincident defining points, so its direction is zero-length.
    # _unit returns None for it, _are_parallel treats it as parallel to
    # everything, and the function degrades to None rather than dividing by a
    # singular matrix.
    pts = {
        "a0": _pt("a0", 1, 1),
        "a1": _pt("a1", 1, 1),  # coincident => zero-length direction
        "b0": _pt("b0", 0, 0),
        "b1": _pt("b1", 2, 0),
    }
    la = _line("ln_a", "a0", "a1")
    lb = _line("ln_b", "b0", "b1")
    assert geo.line_intersection(la, lb, pts) is None


def test_line_intersection_collinear_returns_none():
    # Two lines on the same infinite line y=0 are collinear: no unique
    # intersection, so the parallel branch returns None.
    pts = {
        "a0": _pt("a0", 0, 0),
        "a1": _pt("a1", 2, 0),
        "b0": _pt("b0", 3, 0),
        "b1": _pt("b1", 5, 0),
    }
    la = _line("ln_a", "a0", "a1")
    lb = _line("ln_b", "b0", "b1")
    assert geo.line_intersection(la, lb, pts) is None


# ---------------------------------------------------------------------------
# line-polygon intersection
# ---------------------------------------------------------------------------


def test_line_polygon_intersections_ordered_along_line():
    pts, poly = _unit_square()
    # Horizontal line y=1 crossing the square left-to-right.
    pts["l0"] = _pt("l0", -1, 1)
    pts["l1"] = _pt("l1", 3, 1)
    line = _line("ln", "l0", "l1")

    result = geo.line_polygon_intersections(line, poly, pts)
    assert len(result) == 2
    # Ordered along the line direction (left to right): (0,1) then (2,1).
    assert result[0][0] == pytest.approx(0.0)
    assert result[0][1] == pytest.approx(1.0)
    assert result[1][0] == pytest.approx(2.0)
    assert result[1][1] == pytest.approx(1.0)


def test_line_polygon_no_intersection():
    pts, poly = _unit_square()
    pts["l0"] = _pt("l0", -1, 5)
    pts["l1"] = _pt("l1", 3, 5)  # y=5, well above the square
    line = _line("ln", "l0", "l1")
    assert not geo.line_polygon_intersections(line, poly, pts)


def test_line_polygon_through_vertices_dedups_to_two():
    # Diagonal through the square's opposite corners (0,0) and (2,2). Each
    # corner lies on two adjacent edges, so the raw crossings are 4; dedup
    # must collapse them to exactly the 2 corner points.
    pts, poly = _unit_square()
    pts["d0"] = _pt("d0", 0, 0)
    pts["d1"] = _pt("d1", 2, 2)
    line = _line("ln", "d0", "d1")

    result = geo.line_polygon_intersections(line, poly, pts)
    assert len(result) == 2
    # Ordered along the line (0,0) -> (2,2).
    assert result[0][0] == pytest.approx(0.0)
    assert result[0][1] == pytest.approx(0.0)
    assert result[1][0] == pytest.approx(2.0)
    assert result[1][1] == pytest.approx(2.0)


def test_line_polygon_collinear_with_edge_returns_overlap_endpoints():
    # Line collinear with the bottom edge y=0 of the square. The extended line
    # overlaps that edge, so shapely returns a LineString; _collect_points must
    # keep the shared edge endpoints (0,0) and (2,0), deduped.
    pts, poly = _unit_square()
    pts["e0"] = _pt("e0", -1, 0)
    pts["e1"] = _pt("e1", 3, 0)
    line = _line("ln", "e0", "e1")

    result = geo.line_polygon_intersections(line, poly, pts)
    coords = sorted((round(float(p[0]), 6), round(float(p[1]), 6)) for p in result)
    assert coords == [(0.0, 0.0), (2.0, 0.0)]


def test_line_polygon_intersections_non_convex_multiple_crossings():
    # A non-convex "W" polygon: a zig-zag bottom edge under a flat top. A
    # horizontal line y=2 crosses the two left/right walls plus all four
    # zig-zag legs, giving 6 ordered crossings — exercising the >2-crossing
    # path that a convex polygon can never produce.
    pts = {
        "w0": _pt("w0", 0, 0),
        "w1": _pt("w1", 2, 4),
        "w2": _pt("w2", 4, 0),
        "w3": _pt("w3", 6, 4),
        "w4": _pt("w4", 8, 0),
        "w5": _pt("w5", 8, 5),
        "w6": _pt("w6", 0, 5),
    }
    poly = _poly("pg_w", ["w0", "w1", "w2", "w3", "w4", "w5", "w6"])
    pts["l0"] = _pt("l0", -1, 2)
    pts["l1"] = _pt("l1", 9, 2)
    line = _line("ln", "l0", "l1")

    result = geo.line_polygon_intersections(line, poly, pts)
    eastings = [round(float(p[0]), 6) for p in result]
    assert all(round(float(p[1]), 6) == 2.0 for p in result)
    assert eastings == [0.0, 1.0, 3.0, 5.0, 7.0, 8.0]


def test_line_polygon_zero_length_line_returns_empty():
    # Coincident endpoints give a zero-length direction; the _unit/norm guard
    # short-circuits to an empty result rather than dividing by zero.
    pts, poly = _unit_square()
    pts["z0"] = _pt("z0", 1, 1)
    pts["z1"] = _pt("z1", 1, 1)
    line = _line("ln", "z0", "z1")
    assert not geo.line_polygon_intersections(line, poly, pts)


# ---------------------------------------------------------------------------
# polygon-polygon intersection
# ---------------------------------------------------------------------------


def test_polygon_polygon_intersections():
    pts_a, poly_a = _unit_square("a")  # corners (0,0)-(2,2)
    pts_b = {
        "b0": _pt("b0", 1, 1),
        "b1": _pt("b1", 3, 1),
        "b2": _pt("b2", 3, 3),
        "b3": _pt("b3", 1, 3),
    }
    poly_b = _poly("pg_b", ["b0", "b1", "b2", "b3"])
    pts = {**pts_a, **pts_b}

    result = geo.polygon_polygon_intersections(poly_a, poly_b, pts)
    # The function already returns lexicographic (easting, northing) order;
    # assert against the result directly (no re-sort) so the ordering contract
    # is actually exercised.
    coords = [(round(float(p[0]), 6), round(float(p[1]), 6)) for p in result]
    assert coords == [(1.0, 2.0), (2.0, 1.0)]


def test_polygon_polygon_intersections_secondary_northing_sort():
    # A plus-sign overlap: a vertical bar and a horizontal bar cross at four
    # points that pair up on shared eastings — (1,1),(1,3) and (3,1),(3,3).
    # Lexicographic ordering must use the northing as the tie-breaker, which
    # the (1,2),(2,1) case in the test above never exercises.
    pts = {
        # vertical bar x in [1,3], y in [0,4]
        "v0": _pt("v0", 1, 0),
        "v1": _pt("v1", 3, 0),
        "v2": _pt("v2", 3, 4),
        "v3": _pt("v3", 1, 4),
        # horizontal bar x in [0,4], y in [1,3]
        "h0": _pt("h0", 0, 1),
        "h1": _pt("h1", 4, 1),
        "h2": _pt("h2", 4, 3),
        "h3": _pt("h3", 0, 3),
    }
    vert = _poly("pg_v", ["v0", "v1", "v2", "v3"])
    horiz = _poly("pg_h", ["h0", "h1", "h2", "h3"])

    result = geo.polygon_polygon_intersections(vert, horiz, pts)
    coords = [(round(float(p[0]), 6), round(float(p[1]), 6)) for p in result]
    assert coords == [(1.0, 1.0), (1.0, 3.0), (3.0, 1.0), (3.0, 3.0)]


def test_polygon_polygon_intersections_nested_returns_empty():
    # poly_b strictly inside poly_a with no boundary crossing => no points.
    pts_a, poly_a = _unit_square("a")  # (0,0)-(2,2)
    pts_b = {
        "b0": _pt("b0", 0.5, 0.5),
        "b1": _pt("b1", 1.5, 0.5),
        "b2": _pt("b2", 1.5, 1.5),
        "b3": _pt("b3", 0.5, 1.5),
    }
    poly_b = _poly("pg_b", ["b0", "b1", "b2", "b3"])
    pts = {**pts_a, **pts_b}
    assert not geo.polygon_polygon_intersections(poly_a, poly_b, pts)


# ---------------------------------------------------------------------------
# ray-polygon distance
# ---------------------------------------------------------------------------


def test_ray_polygon_distance_hits():
    pts, poly = _unit_square()
    pts["o"] = _pt("o", -1, 1)
    ray = _ray("ry", "o", math.pi / 2)  # azimuth East => +easting
    result = geo.ray_polygon_distance(ray, poly, pts)
    assert result == pytest.approx(1.0)  # origin x=-1, first hit x=0


def test_ray_polygon_distance_misses_is_infinity():
    pts, poly = _unit_square()
    pts["o"] = _pt("o", -1, 1)
    ray = _ray("ry", "o", 3 * math.pi / 2)  # azimuth West => away from square
    assert math.isinf(geo.ray_polygon_distance(ray, poly, pts))


def test_ray_polygon_distance_origin_inside():
    # Origin at the square's center (1,1) firing East. The nearest forward exit
    # edge is x=2, so the distance is 1.0.
    pts, poly = _unit_square()
    pts["o"] = _pt("o", 1, 1)
    ray = _ray("ry", "o", math.pi / 2)  # azimuth East
    assert geo.ray_polygon_distance(ray, poly, pts) == pytest.approx(1.0)


def test_ray_polygon_distance_near_boundary_does_not_return_negative():
    # Origin a sub-tolerance step (EPS_DISTANCE/2) west of the left edge x=0,
    # firing West. The backward graze of the left edge lands in the snap zone
    # t in [-EPS_DISTANCE, 0), which must clamp to 0.0 — never a negative
    # distance — so the "distance or +inf" (non-negative) contract holds and a
    # caller's `d == inf` miss-check is never fooled by a small negative value.
    pts, poly = _unit_square()
    pts["o"] = _pt("o", -EPS_DISTANCE / 2, 1)
    ray = _ray("ry", "o", 3 * math.pi / 2)  # azimuth West
    d = geo.ray_polygon_distance(ray, poly, pts)
    assert d >= 0.0
    assert d == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# point-polygon distance
# ---------------------------------------------------------------------------


def test_point_polygon_distance_inside_is_zero():
    pts, poly = _unit_square()
    assert geo.point_polygon_distance(_pt("p", 1, 1), poly, pts) == pytest.approx(0.0)


def test_point_polygon_distance_outside():
    pts, poly = _unit_square()
    # Point at (3,1): nearest edge is x=2, distance 1.
    assert geo.point_polygon_distance(_pt("p", 3, 1), poly, pts) == pytest.approx(1.0)


def test_point_polygon_distance_on_boundary_is_zero():
    # Point exactly on the bottom edge (1,0). shapely.contains is False for a
    # boundary point, so the distance branch runs — and must still yield 0.
    pts, poly = _unit_square()
    assert geo.point_polygon_distance(_pt("p", 1, 0), poly, pts) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# polygon-polygon distance
# ---------------------------------------------------------------------------


def test_polygon_polygon_distance_separated():
    pts_a, poly_a = _unit_square("a")  # (0,0)-(2,2)
    pts_b = {
        "b0": _pt("b0", 3, 0),
        "b1": _pt("b1", 5, 0),
        "b2": _pt("b2", 5, 2),
        "b3": _pt("b3", 3, 2),
    }
    poly_b = _poly("pg_b", ["b0", "b1", "b2", "b3"])
    pts = {**pts_a, **pts_b}
    assert geo.polygon_polygon_distance(poly_a, poly_b, pts) == pytest.approx(1.0)


def test_polygon_polygon_distance_nested_is_zero():
    # poly_b fully contained in poly_a (no boundary crossing). shapely.intersects
    # is True for containment, so the distance is 0 — not the min edge gap.
    pts_a, poly_a = _unit_square("a")  # (0,0)-(2,2)
    pts_b = {
        "b0": _pt("b0", 0.5, 0.5),
        "b1": _pt("b1", 1.5, 0.5),
        "b2": _pt("b2", 1.5, 1.5),
        "b3": _pt("b3", 0.5, 1.5),
    }
    poly_b = _poly("pg_b", ["b0", "b1", "b2", "b3"])
    pts = {**pts_a, **pts_b}
    assert geo.polygon_polygon_distance(poly_a, poly_b, pts) == pytest.approx(0.0)


def test_polygon_polygon_distance_touching_is_zero():
    pts_a, poly_a = _unit_square("a")  # (0,0)-(2,2)
    pts_b = {
        "b0": _pt("b0", 2, 0),
        "b1": _pt("b1", 4, 0),
        "b2": _pt("b2", 4, 2),
        "b3": _pt("b3", 2, 2),
    }
    poly_b = _poly("pg_b", ["b0", "b1", "b2", "b3"])  # shares edge x=2
    pts = {**pts_a, **pts_b}
    assert geo.polygon_polygon_distance(poly_a, poly_b, pts) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# tangent direction
# ---------------------------------------------------------------------------


def test_tangent_direction_north_point():
    # Point due North of center: radius azimuth 0 => tangent azimuth pi/2.
    center = _pt("c", 0, 0)
    point = _pt("p", 0, 1)
    result = geo.tangent_direction(center, point)
    assert isinstance(result, np.float64)
    assert result == pytest.approx(math.pi / 2)


def test_tangent_direction_east_point():
    # Point due East: radius azimuth pi/2 => tangent azimuth pi.
    result = geo.tangent_direction(_pt("c", 0, 0), _pt("p", 1, 0))
    assert result == pytest.approx(math.pi)


def test_tangent_direction_normalizes_negative_wrap():
    # Point SW of center: radius azimuth atan2(-1,-1) = -3pi/4, +pi/2 = -pi/4,
    # which must normalize into [0, 2pi) as 7pi/4. Guards the negative wrap.
    result = geo.tangent_direction(_pt("c", 0, 0), _pt("p", -1, -1))
    assert result == pytest.approx(7 * math.pi / 4)
    assert 0.0 <= result < 2 * math.pi


def test_tangent_direction_rejects_coincident_zero_radius():
    # center == point is a zero-radius circle: the radius has no direction, so
    # the tangent is undefined and must fail loud rather than report pi/2.
    coincident = _pt("p", 5, 5)
    with pytest.raises(ValueError, match="zero-radius"):
        geo.tangent_direction(_pt("c", 5, 5), coincident)


def test_tangent_direction_coincidence_is_altitude_invariant():
    # The coincidence test is purely horizontal (hypot of Δe, Δn): two points
    # sharing (E, N) but differing in altitude have no horizontal separation
    # and thus no defined azimuth, so they must still raise "zero-radius"
    # rather than slip through on the altitude gap.
    center = _pt("c", 5, 5, 0.0)
    same_en_higher = _pt("p", 5, 5, 100.0)
    with pytest.raises(ValueError, match="zero-radius"):
        geo.tangent_direction(center, same_en_higher)


# ---------------------------------------------------------------------------
# vector endpoint
# ---------------------------------------------------------------------------


def test_vector_endpoint_east():
    # Azimuth East (pi/2), zero elevation: endpoint = (L, 0, 0); shape is (3,).
    end = geo.vector_endpoint(_pt("o", 0, 0), 5.0, math.pi / 2)
    assert end.shape == (3,)
    assert end[0] == pytest.approx(5.0)
    assert end[1] == pytest.approx(0.0)
    assert end[2] == pytest.approx(0.0)


def test_vector_endpoint_north():
    # Azimuth North (0), zero elevation: endpoint = (0, L, 0).
    end = geo.vector_endpoint(_pt("o", 0, 0), 5.0, 0.0)
    assert end.shape == (3,)
    assert end[0] == pytest.approx(0.0)
    assert end[1] == pytest.approx(5.0)
    assert end[2] == pytest.approx(0.0)


def test_vector_endpoint_off_axis_azimuth_pins_sin_cos_convention():
    # Off-axis azimuth pi/6 (30 deg): sin != cos, so the intentional sin/cos
    # swap (easting uses sin, northing uses cos) is detectable. The cardinal
    # cases above use values in {0, 1} where a swap is invisible; this pins the
    # convention so a future "correction" to (cos, sin) fails loud.
    end = geo.vector_endpoint(_pt("o", 0, 0), 10.0, math.pi / 6)
    assert end[0] == pytest.approx(10.0 * math.sin(math.pi / 6))  # 5.0
    assert end[1] == pytest.approx(10.0 * math.cos(math.pi / 6))  # ~8.66
    assert end[2] == pytest.approx(0.0)


def test_vector_endpoint_elevation_shortens_horizontal_reach():
    # At el=pi/4, horizontal reach = L*cos(pi/4) = L/sqrt(2);
    # vertical component = L*sin(pi/4) = L/sqrt(2). Azimuth East to keep the
    # horizontal component purely in easting so the formula is easy to check.
    length = 10.0
    el = math.pi / 4
    end = geo.vector_endpoint(_pt("o", 0, 0), length, math.pi / 2, el)
    assert end.shape == (3,)
    assert end[0] == pytest.approx(length * math.cos(el))  # ~7.071 (not 10)
    assert end[1] == pytest.approx(0.0)
    assert end[2] == pytest.approx(length * math.sin(el))  # ~7.071


def test_vector_endpoint_adds_origin_offset_including_altitude():
    # Endpoint is the origin plus the displacement; a non-zero origin (with a
    # non-zero altitude) must shift all three components. Azimuth East at
    # el=pi/6 so easting and altitude both pick up the offset.
    origin = _pt("o", 100.0, 200.0, 30.0)
    length, el = 10.0, math.pi / 6
    end = geo.vector_endpoint(origin, length, math.pi / 2, el)
    assert end[0] == pytest.approx(100.0 + length * math.cos(el))
    assert end[1] == pytest.approx(200.0)
    assert end[2] == pytest.approx(30.0 + length * math.sin(el))


def test_vector_endpoint_negative_elevation_points_down():
    # A negative elevation must drive Z below the origin (guards against an
    # ``abs(sin(el))`` regression that would flip downward vectors upward).
    length, el = 10.0, -math.pi / 6
    end = geo.vector_endpoint(_pt("o", 0, 0, 5.0), length, math.pi / 2, el)
    assert end[2] == pytest.approx(5.0 + length * math.sin(el))
    assert end[2] < 5.0


def test_vector_endpoint_propagates_nan_silently():
    # vector_endpoint carries no finiteness guard by design — non-finite
    # arguments propagate into nan/inf components without raising. Callers
    # from untrusted sources must validate before calling (see docstring).
    end = geo.vector_endpoint(_pt("o", 0, 0), float("nan"), 0.0)
    assert any(math.isnan(v) for v in end)


def test_vector_endpoint_straight_up():
    # At elevation = π/2: cos(el)=0 so no horizontal movement, sin(el)=1 so
    # the full length goes into the Z component. Guards a future sin/cos
    # transposition in the formula.
    end = geo.vector_endpoint(_pt("o", 100.0, 200.0, 30.0), 10.0, math.pi / 2, math.pi / 2)
    assert end[0] == pytest.approx(100.0)
    assert end[1] == pytest.approx(200.0)
    assert end[2] == pytest.approx(40.0)


def test_horizontal_unit_vector_azimuth_north():
    # Azimuth 0.0 is due North. azimuth_to_angle should yield π/2, so the unit
    # vector should be (easting=0.0, northing=1.0). The existing tests cover East
    # via azimuth and North via angle, but not North via azimuth.
    ray = _ray("ry", "o", 0.0, DirectionMode.AZIMUTH)
    vec = geo.horizontal_unit_vector(ray)
    assert vec[0] == pytest.approx(0.0)
    assert vec[1] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# elevation angle
# ---------------------------------------------------------------------------


def test_elevation_horizontal_is_zero():
    # Two points at the same altitude: the elevation angle is 0 regardless of
    # horizontal separation.
    assert geo.elevation(_pt("a", 0, 0, 5.0), _pt("b", 30, 40, 5.0)) == pytest.approx(0.0)


def test_elevation_straight_up_is_half_pi():
    # Purely vertical, upward separation: elevation is +π/2.
    assert geo.elevation(_pt("a", 7, 7, 0.0), _pt("b", 7, 7, 12.0)) == pytest.approx(math.pi / 2)


def test_elevation_straight_down_is_negative_half_pi():
    # Purely vertical, downward separation: elevation is -π/2.
    assert geo.elevation(_pt("a", 7, 7, 12.0), _pt("b", 7, 7, 0.0)) == pytest.approx(-math.pi / 2)


def test_elevation_forty_five_degrees():
    # Δz equal to the horizontal reach gives a 45° (π/4) elevation. 3-4-5 in the
    # horizontal plane (reach 5) with Δz = 5.
    assert geo.elevation(_pt("a", 0, 0, 0.0), _pt("b", 3, 4, 5.0)) == pytest.approx(math.pi / 4)


def test_elevation_coincident_points_is_zero():
    # No separation at all: atan2(0, 0) is 0.0, not NaN.
    assert geo.elevation(_pt("a", 9, 9, 9.0), _pt("b", 9, 9, 9.0)) == pytest.approx(0.0)


def test_elevation_is_order_antisymmetric():
    # Swapping the endpoints negates the elevation.
    a, b = _pt("a", 0, 0, 0.0), _pt("b", 10, 0, 6.0)
    assert geo.elevation(a, b) == pytest.approx(-geo.elevation(b, a))


# ---------------------------------------------------------------------------
# three-point azimuth & elevation (angle at vertex B)
# ---------------------------------------------------------------------------


def test_three_point_azimuth_north_to_east_is_half_pi():
    # Vertex B at origin; arm B→A points North, arm B→C points East. The
    # directed horizontal turn from BA to BC is +π/2. Both arms are horizontal,
    # so elevation is 0.
    b = _pt("b", 0, 0, 0.0)
    a = _pt("a", 0, 10, 0.0)  # due North of B
    c = _pt("c", 10, 0, 0.0)  # due East of B
    az, el = geo.three_point_azimuth_elevation(a, b, c)
    assert az == pytest.approx(math.pi / 2)
    assert el == pytest.approx(0.0)


def test_three_point_azimuth_ignores_altitude():
    # Azimuth is purely horizontal: lifting C straight up must not change the
    # azimuth (still North→East = π/2), only the elevation.
    b = _pt("b", 0, 0, 0.0)
    a = _pt("a", 0, 10, 0.0)
    c = _pt("c", 10, 0, 100.0)
    az, _el = geo.three_point_azimuth_elevation(a, b, c)
    assert az == pytest.approx(math.pi / 2)


def test_three_point_elevation_is_arm_difference():
    # Arm B→A is horizontal (elev 0); arm B→C rises at 45° (Δz == reach). The
    # reported elevation is elev(BC) − elev(BA) = π/4 − 0.
    b = _pt("b", 0, 0, 0.0)
    a = _pt("a", 10, 0, 0.0)
    c = _pt("c", 5, 0, 5.0)  # East 5, up 5 → 45° elevation
    _az, el = geo.three_point_azimuth_elevation(a, b, c)
    assert el == pytest.approx(math.pi / 4)


def test_three_point_reversed_order_is_explementary_and_negated():
    # Reversing the ordered triple gives the explementary azimuth (2π − az) and
    # the negated elevation. Neutral local names (first/vertex/last) keep the
    # reversed call from tripping pylint's arguments-out-of-order heuristic.
    first = _pt("a", 0, 10, 0.0)
    vertex = _pt("b", 0, 0, 0.0)
    last = _pt("c", 10, 0, 8.0)
    az, el = geo.three_point_azimuth_elevation(first, vertex, last)
    az_rev, el_rev = geo.three_point_azimuth_elevation(last, vertex, first)
    assert az_rev == pytest.approx(2 * math.pi - az)
    assert el_rev == pytest.approx(-el)


def test_three_point_azimuth_none_for_vertical_arm():
    # Arm B→C is purely vertical (no horizontal extent): the azimuth is
    # undefined and returned as None, but the elevation is still computed
    # (straight up = +π/2 for the BC arm, BA arm horizontal).
    b = _pt("b", 0, 0, 0.0)
    a = _pt("a", 10, 0, 0.0)
    c = _pt("c", 0, 0, 5.0)  # directly above B
    az, el = geo.three_point_azimuth_elevation(a, b, c)
    assert az is None
    assert el == pytest.approx(math.pi / 2)


def test_three_point_raises_on_zero_length_arm():
    # An arm of zero 3-D length (A coincident with vertex B) leaves the angle
    # undefined and must raise.
    b = _pt("b", 5, 5, 5.0)
    a = _pt("a", 5, 5, 5.0)  # coincident with B
    c = _pt("c", 10, 5, 5.0)
    with pytest.raises(ValueError):
        geo.three_point_azimuth_elevation(a, b, c)


def test_three_point_raises_when_last_arm_zero_length():
    # The other half of the zero-length guard: C coincident with vertex B
    # exercises the ``distance(c, b)`` branch of the ``or`` condition. A is well
    # separated so only the BC arm is degenerate.
    b = _pt("b", 5, 5, 5.0)
    a = _pt("a", 10, 5, 5.0)
    c = _pt("c", 5, 5, 5.0)  # coincident with B
    with pytest.raises(ValueError):
        geo.three_point_azimuth_elevation(a, b, c)


def test_three_point_elevation_near_pi_when_arms_point_opposite_vertically():
    # Arm B→A plunges almost straight down, arm B→C climbs almost straight up,
    # each keeping a tiny horizontal reach so the azimuth stays defined. The
    # elevation el(BC) − el(BA) approaches +π, exercising the upper end of the
    # [-π, π] range the π/4 case never reaches.
    b = _pt("b", 0, 0, 0.0)
    a = _pt("a", 1, 0, -1000.0)  # reach 1 East, 1000 down
    c = _pt("c", 1, 0, 1000.0)  # reach 1 East, 1000 up
    az, el = geo.three_point_azimuth_elevation(a, b, c)
    # Both arms share the same horizontal bearing (due East), so the turn is 0.
    assert az == pytest.approx(0.0)
    expected = math.atan2(1000.0, 1.0) - math.atan2(-1000.0, 1.0)
    assert el == pytest.approx(expected)
    assert expected == pytest.approx(math.pi, abs=2e-3)


def test_three_point_both_arms_vertical_none_azimuth_and_negative_pi_elevation():
    # Both arms purely vertical (horizontal length < EPS): the undefined branch
    # fires only when BOTH hypots are below EPS, so the azimuth is None. With A
    # straight up (el +π/2) and C straight down (el −π/2), the elevation
    # el(BC) − el(BA) is exactly −π — the lower end of the [-π, π] range.
    b = _pt("b", 0, 0, 0.0)
    a = _pt("a", 0, 0, 10.0)  # directly above B
    c = _pt("c", 0, 0, -10.0)  # directly below B
    az, el = geo.three_point_azimuth_elevation(a, b, c)
    assert az is None
    assert el == pytest.approx(-math.pi)


def test_three_point_azimuth_wraps_negative_raw_difference():
    # When the raw az_BC − az_BA is negative it must wrap into [0, 2π). Arm B→A
    # points East (bearing π/2), arm B→C points North (bearing 0), so the raw
    # difference is 0 − π/2 = −π/2, which normalises to 3π/2.
    b = _pt("b", 0, 0, 0.0)
    a = _pt("a", 10, 0, 0.0)  # due East of B
    c = _pt("c", 0, 10, 0.0)  # due North of B
    az, el = geo.three_point_azimuth_elevation(a, b, c)
    assert az == pytest.approx(3 * math.pi / 2)
    assert el == pytest.approx(0.0)
