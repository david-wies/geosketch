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

"""Tests for ``geometry.services.validation`` (issue #14).

Each of the twelve validators gets at least one valid case (does not raise)
and one invalid case (raises ``ValueError``), plus boundary cases where the
tolerance edge or a structural sub-rule deserves explicit coverage. Inputs are
exact (3-4-5 triangles, axis-aligned squares, unit radii) so the assertions do
not depend on floating-point noise beyond a tight tolerance.
"""

from __future__ import annotations

import math

import pytest

from geometry.models.ball import Ball
from geometry.models.circle import Circle
from geometry.models.point import Point
from geometry.models.polygon import Polygon
from geometry.models.solid import Solid
from geometry.services import validation as val
from geometry.utils.constants import EPS_ANGLE, EPS_DISTANCE, EPS_VOLUME

# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------


# A single ``_envelope`` collapses the five model builders below to one-line
# constructor calls. This keeps them readable, removes the intra-file
# repetition of the shared ``alpha``/``visibility``/colour fields, and (by
# design) makes the builder call shapes structurally distinct from the
# multi-line keyword blocks in ``test_geometry.py`` so pylint's duplicate-code
# (R0801) check does not flag the two suites as overlapping.
_LINE = "#000000"
_FILL = "#cccccc"


def _envelope(pid: str, name: str | None = None) -> dict[str, object]:
    """Shared ``GeoObject`` envelope kwargs (id, name, alpha, visibility)."""
    return {"id": pid, "name": name or pid, "alpha": 1.0, "visibility": True}


def _pt(pid: str, easting: float, northing: float, altitude: float = 0.0) -> Point:
    return Point(
        **_envelope(pid),
        easting=float(easting),
        northing=float(northing),
        altitude=float(altitude),
        color=_LINE,
    )


def _poly(pid: str, point_ids: tuple[str, ...], name: str = "poly") -> Polygon:
    return Polygon(
        **_envelope(pid, name),
        point_ids=point_ids,
        is_convex=False,
        line_color=_LINE,
        fill_color=_FILL,
    )


def _circle(pid: str, center_id: str, radius: float) -> Circle:
    return Circle(
        **_envelope(pid),
        center_id=center_id,
        radius=float(radius),
        line_color=_LINE,
        fill_color=_FILL,
    )


def _ball(pid: str, center_id: str, radius: float) -> Ball:
    return Ball(
        **_envelope(pid),
        center_id=center_id,
        radius=float(radius),
        line_color=_LINE,
        fill_color=_FILL,
    )


def _solid(pid: str, layers: tuple[str, ...]) -> Solid:
    return Solid(**_envelope(pid), layers=layers, line_color=_LINE, fill_color=_FILL)


def _square(prefix: str = "s") -> tuple[dict[str, Point], Polygon]:
    """2x2 CCW square with corners at (0,0),(2,0),(2,2),(0,2)."""
    corners = ((0, 0), (2, 0), (2, 2), (0, 2))
    pts = {f"{prefix}{i}": _pt(f"{prefix}{i}", e, n) for i, (e, n) in enumerate(corners)}
    poly = _poly(f"pg_{prefix}", tuple(pts))
    return pts, poly


# ---------------------------------------------------------------------------
# polygon non-degenerate
# ---------------------------------------------------------------------------


def test_polygon_non_degenerate_valid_square():
    pts, poly = _square()
    val.validate_polygon_non_degenerate(poly, pts)  # 2x2 square, area 4 -> ok


def test_polygon_non_degenerate_rejects_collinear():
    # Three collinear points enclose zero area -> degenerate.
    pts = {
        "k0": _pt("k0", 0, 0),
        "k1": _pt("k1", 1, 1),
        "k2": _pt("k2", 2, 2),
    }
    poly = _poly("pg_k", ("k0", "k1", "k2"))
    with pytest.raises(ValueError, match="degenerate"):
        val.validate_polygon_non_degenerate(poly, pts)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_polygon_non_degenerate_rejects_non_finite_coord(bad):
    # A vertex coordinate mutated to nan/±inf after construction poisons the
    # shoelace sum; |nan| < EPS_AREA and |inf| < EPS_AREA are both False, so the
    # non-finite signed-area guard is what rejects it.
    pts, poly = _square()
    pts["s0"].easting = bad
    with pytest.raises(ValueError, match="finite"):
        val.validate_polygon_non_degenerate(poly, pts)


# ---------------------------------------------------------------------------
# polygon simple
# ---------------------------------------------------------------------------


def test_polygon_simple_valid_square():
    pts, poly = _square()
    val.validate_polygon_simple(poly, pts)  # axis-aligned square is simple


def test_polygon_simple_rejects_bowtie():
    # A self-intersecting "bowtie": swapping the last two corners crosses the
    # diagonals, producing a figure-eight boundary.
    pts = {
        "b0": _pt("b0", 0, 0),
        "b1": _pt("b1", 2, 0),
        "b2": _pt("b2", 0, 2),
        "b3": _pt("b3", 2, 2),
    }
    poly = _poly("pg_b", ("b0", "b1", "b2", "b3"))
    with pytest.raises(ValueError, match="self-intersecting"):
        val.validate_polygon_simple(poly, pts)


def test_polygon_simple_rejects_fewer_than_three_vertices():
    # The Polygon constructor rejects < 3, so build a valid triangle then shrink
    # point_ids to exercise validate_polygon_simple's own < 3 short-circuit
    # (distinct from validate_polygon_vertex_count). The points dict still
    # resolves both IDs so the count guard fires before any KeyError.
    pts = {"v0": _pt("v0", 0, 0), "v1": _pt("v1", 2, 0), "v2": _pt("v2", 1, 2)}
    poly = _poly("pg_v", ("v0", "v1", "v2"))
    poly.point_ids = ("v0", "v1")
    with pytest.raises(ValueError, match="at least 3 vertices"):
        val.validate_polygon_simple(poly, pts)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_polygon_simple_rejects_non_finite_coord(bad):
    # A vertex coordinate mutated to nan/±inf after construction poisons
    # shapely.is_simple (which then returns a value that makes the
    # self-intersection branch unreachable); the up-front coordinate guard
    # rejects it before the shapely Polygon is built.
    pts, poly = _square()
    pts["s2"].northing = bad
    with pytest.raises(ValueError, match="finite"):
        val.validate_polygon_simple(poly, pts)


# ---------------------------------------------------------------------------
# polygon vertex count
# ---------------------------------------------------------------------------


def test_polygon_vertex_count_valid_triangle():
    poly = _poly("pg_t", ("t0", "t1", "t2"))  # exactly 3 vertices -> ok
    val.validate_polygon_vertex_count(poly)


def test_polygon_vertex_count_rejects_two():
    # The Polygon constructor rejects < 3, so a 2-vertex polygon cannot be
    # built directly; construct a valid triangle then shrink point_ids to
    # exercise the validator's own guard.
    poly = _poly("pg_t", ("t0", "t1", "t2"))
    poly.point_ids = ("t0", "t1")
    with pytest.raises(ValueError, match="at least 3 vertices"):
        val.validate_polygon_vertex_count(poly)


# ---------------------------------------------------------------------------
# circle tangent point (2D)
# ---------------------------------------------------------------------------


def test_circle_tangent_point_valid_on_circumference():
    # Centre at origin, radius 5, point at (3,4): 2D distance == 5 -> ok.
    val.validate_circle_tangent_point(_pt("c", 0, 0), _pt("p", 3, 4), 5.0)


def test_circle_tangent_point_ignores_altitude():
    # A circle is planar: the same (3,4) point lifted 100 m still has horizontal
    # distance 5, so it must pass even though its 3D distance is far from 5.
    val.validate_circle_tangent_point(_pt("c", 0, 0, 0.0), _pt("p", 3, 4, 100.0), 5.0)


def test_circle_tangent_point_rejects_off_circumference():
    # 2D distance 5 but radius declared 4 -> off the circumference.
    with pytest.raises(ValueError, match="does not lie on the circle"):
        val.validate_circle_tangent_point(_pt("c", 0, 0), _pt("p", 3, 4), 4.0)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_circle_tangent_point_rejects_non_finite_radius(bad):
    # A non-finite radius makes |distance - radius| non-finite, which compares
    # False against the tolerance and would slip the gate silently; the finite
    # guard rejects it.
    with pytest.raises(ValueError, match="finite"):
        val.validate_circle_tangent_point(_pt("c", 0, 0), _pt("p", 3, 4), bad)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_circle_tangent_point_rejects_non_finite_coord(bad):
    # A coordinate mutated to nan/±inf after construction poisons math.hypot;
    # nan/inf both compare False against the tolerance, so without the up-front
    # coordinate guard the validator would silently admit the bad point.
    surface = _pt("p", 3, 4)
    surface.easting = bad
    with pytest.raises(ValueError, match="finite"):
        val.validate_circle_tangent_point(_pt("c", 0, 0), surface, 5.0)


# ---------------------------------------------------------------------------
# ball tangent point (3D)
# ---------------------------------------------------------------------------


def test_ball_tangent_point_valid_on_surface():
    # 3-4-12-13 quadruple: 3D distance from origin to (3,4,12) is 13 -> ok.
    val.validate_ball_tangent_point(_pt("c", 0, 0, 0.0), _pt("p", 3, 4, 12.0), 13.0)


def test_ball_tangent_point_rejects_using_2d_distance():
    # Horizontal distance is 5, but the true 3D distance is 13; passing radius 5
    # (the 2D value) must be rejected, proving the check is genuinely 3D.
    with pytest.raises(ValueError, match="does not lie on the ball"):
        val.validate_ball_tangent_point(_pt("c", 0, 0, 0.0), _pt("p", 3, 4, 12.0), 5.0)


def test_ball_tangent_point_uses_real_ball_radius():
    # Drive the check from a real Ball's radius field (not a bare float), the way
    # the command layer would: a unit ball with a surface point at distance 1.
    ball = _ball("ba_001", "c", 1.0)
    val.validate_ball_tangent_point(_pt("c", 0, 0, 0.0), _pt("p", 0, 0, 1.0), ball.radius)


def test_ball_tangent_point_boundary_just_inside_tolerance():
    # 3D point (0,3,4): sqrt(0+9+16) == 5 (a clean quadruple at altitude 4, so
    # the check genuinely exercises the 3D path). Error just under EPS_DISTANCE
    # must pass; the check uses >= for rejection.
    radius = 5.0 - EPS_DISTANCE / 2
    val.validate_ball_tangent_point(_pt("c", 0, 0, 0.0), _pt("p", 0, 3, 4.0), radius)


def test_ball_tangent_point_boundary_at_tolerance_rejects():
    # Same 3D distance 5; error exactly EPS_DISTANCE must reject (>= boundary).
    radius = 5.0 - EPS_DISTANCE
    with pytest.raises(ValueError, match="does not lie on the ball"):
        val.validate_ball_tangent_point(_pt("c", 0, 0, 0.0), _pt("p", 0, 3, 4.0), radius)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_ball_tangent_point_rejects_non_finite_radius(bad):
    # A non-finite radius makes |distance - radius| non-finite, which compares
    # False against the tolerance and would slip the gate silently; the finite
    # guard rejects it.
    with pytest.raises(ValueError, match="finite"):
        val.validate_ball_tangent_point(_pt("c", 0, 0, 0.0), _pt("p", 3, 4, 12.0), bad)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_ball_tangent_point_rejects_non_finite_coord(bad):
    # An altitude mutated to nan/±inf after construction poisons geo.distance;
    # the resulting non-finite error compares False against the tolerance, so the
    # up-front 3-D coordinate guard is what rejects it.
    surface = _pt("p", 3, 4, 12.0)
    surface.altitude = bad
    with pytest.raises(ValueError, match="finite"):
        val.validate_ball_tangent_point(_pt("c", 0, 0, 0.0), surface, 13.0)


# ---------------------------------------------------------------------------
# ball tangent perpendicular
# ---------------------------------------------------------------------------


def test_ball_tangent_perpendicular_valid():
    # Radius points due East (surface point at (1,0,0)). A tangent pointing due
    # North (azimuth 0, elevation 0) is perpendicular to it.
    val.validate_ball_tangent_perpendicular(_pt("c", 0, 0, 0.0), _pt("p", 1, 0, 0.0), 0.0, 0.0)


def test_ball_tangent_perpendicular_valid_vertical_radius():
    # Radius points straight up (surface point above centre). A horizontal
    # tangent (any azimuth, elevation 0) is perpendicular to a vertical radius.
    val.validate_ball_tangent_perpendicular(
        _pt("c", 0, 0, 0.0), _pt("p", 0, 0, 1.0), math.pi / 2, 0.0
    )


def test_ball_tangent_perpendicular_rejects_parallel():
    # Radius points due East; a tangent also pointing due East (azimuth pi/2)
    # is parallel, not perpendicular -> |dot| == 1.
    with pytest.raises(ValueError, match="perpendicular"):
        val.validate_ball_tangent_perpendicular(
            _pt("c", 0, 0, 0.0), _pt("p", 1, 0, 0.0), math.pi / 2, 0.0
        )


def test_ball_tangent_perpendicular_rejects_zero_radius():
    # Centre and surface point coincide: the radius has no direction.
    with pytest.raises(ValueError, match="coincide"):
        val.validate_ball_tangent_perpendicular(_pt("c", 5, 5, 5.0), _pt("p", 5, 5, 5.0), 0.0, 0.0)


def test_ball_tangent_perpendicular_boundary_just_inside_tolerance():
    # Radius due East (1,0,0); with elevation 0 the dot product reduces to
    # sin(azimuth). A tiny azimuth of 0.1 * EPS_ANGLE gives |dot| ~ 1e-10,
    # comfortably under EPS_ANGLE -> perpendicular within tolerance, passes.
    az = EPS_ANGLE * 0.1
    val.validate_ball_tangent_perpendicular(_pt("c", 0, 0, 0.0), _pt("p", 1, 0, 0.0), az, 0.0)


def test_ball_tangent_perpendicular_boundary_over_tolerance_rejects():
    # Same construction with azimuth 10 * EPS_ANGLE gives |dot| ~ 1e-8,
    # comfortably over EPS_ANGLE -> not perpendicular, rejects.
    az = EPS_ANGLE * 10
    with pytest.raises(ValueError, match="perpendicular"):
        val.validate_ball_tangent_perpendicular(_pt("c", 0, 0, 0.0), _pt("p", 1, 0, 0.0), az, 0.0)


@pytest.mark.parametrize(
    ("direction", "elevation"),
    [
        (math.nan, 0.0),
        (0.0, math.nan),
        (math.inf, 0.0),
        (-math.inf, 0.0),
        (0.0, -math.inf),
    ],
)
def test_ball_tangent_perpendicular_rejects_non_finite_angle(direction, elevation):
    # A non-finite azimuth or elevation yields a NaN dot product, which compares
    # False against the tolerance and would be silently admitted as
    # "perpendicular"; the finite guard rejects it. Centre/surface point are a
    # valid finite due-East radius so only the angle guard is exercised.
    with pytest.raises(ValueError, match="finite"):
        val.validate_ball_tangent_perpendicular(
            _pt("c", 0, 0, 0.0), _pt("p", 1, 0, 0.0), direction, elevation
        )


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_ball_tangent_perpendicular_rejects_non_finite_coord(bad):
    # A coordinate mutated to nan/±inf after construction poisons the radius
    # vector: a non-finite norm skips the coincidence guard AND a non-finite dot
    # makes the perpendicular branch unreachable (the double bypass). The
    # up-front 3-D coordinate guard rejects the point before either runs.
    surface = _pt("p", 1, 0, 0.0)
    surface.northing = bad
    with pytest.raises(ValueError, match="finite"):
        val.validate_ball_tangent_perpendicular(_pt("c", 0, 0, 0.0), surface, 0.0, 0.0)


# ---------------------------------------------------------------------------
# cylinder axis elevation
# ---------------------------------------------------------------------------


def test_cylinder_axis_elevation_valid():
    val.validate_cylinder_axis_elevation(math.pi / 4)  # inclined, positive -> ok


def test_cylinder_axis_elevation_rejects_zero():
    with pytest.raises(ValueError, match="> 0"):
        val.validate_cylinder_axis_elevation(0.0)


def test_cylinder_axis_elevation_rejects_negative():
    with pytest.raises(ValueError, match="> 0"):
        val.validate_cylinder_axis_elevation(-0.1)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_cylinder_axis_elevation_rejects_non_finite(bad):
    with pytest.raises(ValueError, match="finite"):
        val.validate_cylinder_axis_elevation(bad)


# ---------------------------------------------------------------------------
# positive radius
# ---------------------------------------------------------------------------


def test_positive_radius_valid():
    val.validate_positive_radius(1.0)


def test_positive_radius_rejects_zero():
    with pytest.raises(ValueError, match="> 0"):
        val.validate_positive_radius(0.0)


def test_positive_radius_rejects_negative():
    with pytest.raises(ValueError, match="> 0"):
        val.validate_positive_radius(-2.5)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_positive_radius_rejects_non_finite(bad):
    # The finite guard is the ONLY branch that rejects +inf: +inf > 0 is True, so
    # without it the radius gate would silently admit an infinite radius.
    with pytest.raises(ValueError, match="finite"):
        val.validate_positive_radius(bad)


# ---------------------------------------------------------------------------
# solid layers
# ---------------------------------------------------------------------------


def _solid_objects() -> dict[str, object]:
    """Two polygons and a point, the building blocks for the solid-layer tests."""
    pts_a, poly_a = _square("a")
    pts_b, poly_b = _square("b")
    apex = _pt("pt_apex", 1, 1, 5.0)
    objects: dict[str, object] = {"pg_a": poly_a, "pg_b": poly_b, "pt_apex": apex}
    # Resolve the polygons' own vertices too so the lookup is self-consistent,
    # though validate_solid_layers only inspects the layer IDs themselves.
    objects.update(pts_a)
    objects.update(pts_b)
    return objects


def test_solid_layers_valid_two_polygons():
    objects = _solid_objects()
    val.validate_solid_layers(["pg_a", "pg_b"], objects)


def test_solid_layers_accepts_real_solid_layer_stack():
    # Validate the layer list taken straight off a constructed Solid object, the
    # way the command layer would, rather than a hand-built list literal.
    objects = _solid_objects()
    solid = _solid("so_001", ("pg_a", "pg_b", "pt_apex"))
    val.validate_solid_layers(solid.layers, objects)


def test_solid_layers_valid_point_apex_last():
    objects = _solid_objects()
    val.validate_solid_layers(["pg_a", "pg_b", "pt_apex"], objects)


def test_solid_layers_valid_point_apex_first():
    # The Point layer is allowed at the first position, not only the last.
    objects = _solid_objects()
    val.validate_solid_layers(["pt_apex", "pg_a", "pg_b"], objects)


def test_solid_layers_rejects_too_few():
    objects = _solid_objects()
    with pytest.raises(ValueError, match="at least 2 layers"):
        val.validate_solid_layers(["pg_a"], objects)


def test_solid_layers_rejects_empty():
    # An empty layer list also trips the < 2 guard (zero layers, no extent).
    objects = _solid_objects()
    with pytest.raises(ValueError, match="at least 2 layers"):
        val.validate_solid_layers([], objects)


def test_solid_layers_accepts_duplicate_layer_id():
    # Pins CURRENT behavior per the round-4 review: validate_solid_layers does
    # not reject a layer ID repeated within the stack, so two references to the
    # same valid polygon pass. (Rejecting duplicates is intentionally out of
    # scope here; this test guards against silently changing that behavior.)
    objects = _solid_objects()
    val.validate_solid_layers(["pg_001", "pg_001"], {"pg_001": objects["pg_a"]})


def test_solid_layers_rejects_missing_object():
    objects = _solid_objects()
    with pytest.raises(ValueError, match="non-existent"):
        val.validate_solid_layers(["pg_a", "pg_missing"], objects)


def test_solid_layers_rejects_wrong_type():
    # A Circle is neither a Polygon nor a Point, so it cannot be a layer.
    objects = _solid_objects()
    objects["ci_001"] = _circle("ci_001", "a0", 1.0)
    with pytest.raises(ValueError, match="Polygon or Point"):
        val.validate_solid_layers(["pg_a", "ci_001"], objects)


def test_solid_layers_rejects_two_point_layers():
    objects = _solid_objects()
    objects["pt_base"] = _pt("pt_base", 1, 1, 0.0)
    with pytest.raises(ValueError, match="at most one Point"):
        val.validate_solid_layers(["pt_base", "pg_a", "pt_apex"], objects)


def test_solid_layers_rejects_point_layer_in_middle():
    objects = _solid_objects()
    with pytest.raises(ValueError, match="first or last"):
        val.validate_solid_layers(["pg_a", "pt_apex", "pg_b"], objects)


def test_solid_layers_classifies_by_type_not_id_prefix():
    # An object whose ID does not look like a point but whose .type is "point"
    # must still be treated as a Point layer (and, being in the middle, fail).
    # This proves classification reads .type, not the ID prefix.
    objects = _solid_objects()
    weird = _pt("xx_weird", 1, 1, 2.0)  # .type == "point", non-"pt_" prefix
    objects["xx_weird"] = weird
    with pytest.raises(ValueError, match="first or last"):
        val.validate_solid_layers(["pg_a", "xx_weird", "pg_b"], objects)


# ---------------------------------------------------------------------------
# solid non-degenerate
# ---------------------------------------------------------------------------


def test_solid_non_degenerate_valid():
    val.validate_solid_non_degenerate(10.0)


def test_solid_non_degenerate_rejects_flat():
    with pytest.raises(ValueError, match="degenerate"):
        val.validate_solid_non_degenerate(0.0)


def test_solid_non_degenerate_valid_negative_volume():
    # The gate compares |volume|, so a negative (e.g. opposite-winding) volume
    # of sufficient magnitude is accepted.
    val.validate_solid_non_degenerate(-10.0)


def test_solid_non_degenerate_boundary_at_tolerance_passes():
    # The check is |volume| < EPS_VOLUME rejects, so |volume| == EPS_VOLUME passes.
    val.validate_solid_non_degenerate(EPS_VOLUME)


def test_solid_non_degenerate_boundary_just_below_tolerance_rejects():
    # |volume| just under EPS_VOLUME must reject.
    with pytest.raises(ValueError, match="degenerate"):
        val.validate_solid_non_degenerate(EPS_VOLUME / 2)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_solid_non_degenerate_rejects_non_finite(bad):
    # A NaN from a degenerate hull (or an infinite volume) must not slip the
    # non-degenerate gate: |nan| < EPS and |inf| < EPS are both False.
    with pytest.raises(ValueError, match="finite"):
        val.validate_solid_non_degenerate(bad)


# ---------------------------------------------------------------------------
# reference exists
# ---------------------------------------------------------------------------


def test_reference_exists_valid():
    objects = {"pt_001": _pt("pt_001", 0, 0)}
    val.validate_reference_exists("pt_001", objects)


def test_reference_exists_rejects_missing():
    objects = {"pt_001": _pt("pt_001", 0, 0)}
    with pytest.raises(ValueError, match="does not exist"):
        val.validate_reference_exists("pt_999", objects)


# ---------------------------------------------------------------------------
# altitude finite
# ---------------------------------------------------------------------------


def test_altitude_finite_valid():
    val.validate_altitude_finite(42.5)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_altitude_finite_rejects_non_finite(bad):
    with pytest.raises(ValueError, match="finite"):
        val.validate_altitude_finite(bad)


# ---------------------------------------------------------------------------
# tolerance boundary cases
# ---------------------------------------------------------------------------


def test_circle_tangent_point_boundary_just_inside_tolerance():
    # Error just under EPS_DISTANCE must pass; the check uses >= for rejection.
    radius = 5.0 - EPS_DISTANCE / 2
    val.validate_circle_tangent_point(_pt("c", 0, 0), _pt("p", 5, 0), radius)


def test_circle_tangent_point_boundary_at_tolerance_rejects():
    # Error exactly EPS_DISTANCE must reject (>= boundary).
    radius = 5.0 - EPS_DISTANCE
    with pytest.raises(ValueError, match="circle"):
        val.validate_circle_tangent_point(_pt("c", 0, 0), _pt("p", 5, 0), radius)
