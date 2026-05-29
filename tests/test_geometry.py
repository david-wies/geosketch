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

from geometry.models.common import DirectionMode, DirectionUnits
from geometry.models.line import Line
from geometry.models.point import Point
from geometry.models.polygon import Polygon
from geometry.models.ray import Ray
from geometry.services import geometry as geo

# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------


def _pt(pid: str, easting: float, northing: float) -> Point:
    return Point(
        id=pid,
        name=pid,
        alpha=1.0,
        visibility=True,
        easting=float(easting),
        northing=float(northing),
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


def _directed_kwargs(direction: float = 0.0) -> dict:
    """Common envelope + direction kwargs shared by the directed-object builders."""
    return {
        "alpha": 1.0,
        "visibility": True,
        "direction": float(direction),
        "direction_mode": DirectionMode.AZIMUTH,
        "direction_units": DirectionUnits.RADIANS,
        "line_color": "#000000",
        "fill_color": "#cccccc",
    }


def _line(pid: str, a_id: str, b_id: str) -> Line:
    return Line(id=pid, name=pid, point_a_id=a_id, point_b_id=b_id, **_directed_kwargs())


def _ray(pid: str, origin_id: str, azimuth: float) -> Ray:
    return Ray(id=pid, name=pid, origin_id=origin_id, **_directed_kwargs(azimuth))


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
    coords = sorted((round(float(p[0]), 6), round(float(p[1]), 6)) for p in result)
    assert coords == [(1.0, 2.0), (2.0, 1.0)]


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


# ---------------------------------------------------------------------------
# vector endpoint
# ---------------------------------------------------------------------------


def test_vector_endpoint_east():
    # Azimuth East (pi/2): endpoint = (e + L*sin, n + L*cos) = (L, 0).
    end = geo.vector_endpoint(_pt("o", 0, 0), 5.0, math.pi / 2)
    assert end[0] == pytest.approx(5.0)
    assert end[1] == pytest.approx(0.0)


def test_vector_endpoint_north():
    # Azimuth North (0): endpoint = (0, L).
    end = geo.vector_endpoint(_pt("o", 0, 0), 5.0, 0.0)
    assert end[0] == pytest.approx(0.0)
    assert end[1] == pytest.approx(5.0)
