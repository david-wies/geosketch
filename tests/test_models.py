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

"""Smoke tests for the geometry.models data-class layer."""

import ast
import dataclasses
import math
import pathlib

import pytest

from geometry.models import (
    Ball,
    Circle,
    Cylinder,
    ElevatedObject,
    DirectionMode,
    DirectionUnits,
    GeoObject,
    Line,
    Point,
    Polygon,
    Ray,
    Solid,
    Tangent,
    Vector,
)
from geometry.utils.constants import EPS_ANGLE, EPS_DISTANCE

SUBCLASS_TYPES = [
    (Point, "point"),
    (Line, "line"),
    (Polygon, "polygon"),
    (Ray, "ray"),
    (Vector, "vector"),
    (Circle, "circle"),
    (Ball, "ball"),
    (Cylinder, "cylinder"),
    (Solid, "solid"),
    (Tangent, "tangent"),
]


# ---------------------------------------------------------------------------
# Enum values
# ---------------------------------------------------------------------------


def test_direction_mode_values():
    assert DirectionMode.AZIMUTH.value == "azimuth"
    assert DirectionMode.ANGLE.value == "angle"


def test_direction_units_values():
    assert DirectionUnits.RADIANS.value == "radians"
    assert DirectionUnits.DEGREES.value == "degrees"


# ---------------------------------------------------------------------------
# GeoObject base
# ---------------------------------------------------------------------------


def test_geo_object_fields():
    field_names = {f.name for f in dataclasses.fields(GeoObject)}
    assert field_names == {"id", "name", "type", "alpha", "visibility"}


# ---------------------------------------------------------------------------
# Per-type: instantiation and auto-typed `type` field
# ---------------------------------------------------------------------------


def test_point_instantiation():
    pt = Point(
        id="pt_001",
        name="A",
        alpha=1.0,
        visibility=True,
        easting=100.0,
        northing=200.0,
        altitude=50.0,
        color="#ff0000",
    )
    assert pt.type == "point"
    assert pt.easting == 100.0
    assert pt.northing == 200.0
    assert pt.altitude == 50.0
    assert pt.color == "#ff0000"


@pytest.mark.parametrize(("cls", "expected_type"), SUBCLASS_TYPES)
def test_type_not_in_init(cls, expected_type):
    init_field_names = [f.name for f in dataclasses.fields(cls) if f.init]
    assert "type" not in init_field_names
    type_field = next(f for f in dataclasses.fields(cls) if f.name == "type")
    assert type_field.default == expected_type


@pytest.mark.parametrize(("cls", "_"), SUBCLASS_TYPES)
def test_subclass_inherits_geo_object(cls, _):
    assert issubclass(cls, GeoObject)


def test_geo_object_direct_instantiation_rejected():
    with pytest.raises(TypeError, match="abstract base class"):
        GeoObject(id="x_001", name="X", type="bogus", alpha=1.0, visibility=True)


def test_alpha_out_of_range_rejected_via_subclass():
    # alpha is documented as [0.0, 1.0]; the guard lives in GeoObject so every
    # concrete subclass inherits it. nan and out-of-range values must raise.
    for bad in (math.nan, -0.1, 1.1, math.inf):
        with pytest.raises(ValueError, match="alpha"):
            Point(
                id="pt_001",
                name="A",
                alpha=bad,
                visibility=True,
                easting=0.0,
                northing=0.0,
                color="#000000",
            )


def test_alpha_accepts_boundary_values():
    # 0.0 (fully transparent) and 1.0 (fully opaque) are both valid endpoints.
    for boundary in (0.0, 1.0):
        pt = Point(
            id="pt_001",
            name="A",
            alpha=boundary,
            visibility=True,
            easting=0.0,
            northing=0.0,
            color="#000000",
        )
        assert pt.alpha == boundary


def test_elevated_object_direct_instantiation_rejected():
    with pytest.raises(TypeError, match="abstract base class"):
        ElevatedObject(
            id="x_001",
            name="X",
            type="bogus",
            alpha=1.0,
            visibility=True,
            direction=0.0,
            elevation=0.0,
            direction_mode=DirectionMode.AZIMUTH,
            direction_units=DirectionUnits.RADIANS,
        )


def test_point_isinstance_geo_object():
    pt = Point(
        id="pt_001",
        name="A",
        alpha=1.0,
        visibility=True,
        easting=0.0,
        northing=0.0,
        altitude=0.0,
        color="#000000",
    )
    assert isinstance(pt, GeoObject)


def test_polygon_point_ids_defensively_copied():
    shared = ["pt_001", "pt_002", "pt_003"]
    pg = Polygon(
        id="pg_001",
        name="P",
        alpha=1.0,
        visibility=True,
        point_ids=shared,
        is_convex=True,
        line_color="#000000",
        fill_color="#ffffff",
    )
    assert pg.point_ids == shared
    assert pg.point_ids is not shared
    shared.append("pt_999")
    assert "pt_999" not in pg.point_ids


def test_line_instantiation():
    ln = Line(
        id="ln_001",
        name="AB",
        alpha=1.0,
        visibility=True,
        point_a_id="pt_001",
        point_b_id="pt_002",
        direction=0.785,
        elevation=0.0,
        direction_mode=DirectionMode.AZIMUTH,
        direction_units=DirectionUnits.RADIANS,
        line_color="#0000ff",
        fill_color="#0000ff",
    )
    assert ln.type == "line"
    assert ln.point_a_id == "pt_001"
    assert ln.elevation == 0.0


def test_polygon_instantiation():
    pg = Polygon(
        id="pg_001",
        name="Tri",
        alpha=0.8,
        visibility=True,
        point_ids=["pt_001", "pt_002", "pt_003"],
        is_convex=True,
        line_color="#ffff00",
        fill_color="#ffffcc",
    )
    assert pg.type == "polygon"
    assert pg.point_ids == ["pt_001", "pt_002", "pt_003"]
    assert pg.is_convex is True


def test_ray_instantiation():
    ry = Ray(
        id="ry_001",
        name="R",
        alpha=1.0,
        visibility=True,
        origin_id="pt_001",
        direction=1.571,
        elevation=0.0,
        direction_mode=DirectionMode.AZIMUTH,
        direction_units=DirectionUnits.RADIANS,
        line_color="#ff00ff",
        fill_color="#ff00ff",
    )
    assert ry.type == "ray"
    assert ry.origin_id == "pt_001"
    assert ry.elevation == 0.0


def test_vector_instantiation_length_direction():
    vc = Vector(
        id="vc_001",
        name="V",
        alpha=1.0,
        visibility=True,
        origin_id="pt_001",
        direction=0.785,
        elevation=0.0,
        direction_mode=DirectionMode.AZIMUTH,
        direction_units=DirectionUnits.RADIANS,
        length=100.0,
        endpoint_id=None,
        line_color="#00ffff",
        fill_color="#00ffff",
    )
    assert vc.type == "vector"
    assert vc.endpoint_id is None
    assert vc.length == 100.0
    assert vc.elevation == 0.0


def test_vector_instantiation_origin_endpoint():
    vc = Vector(
        id="vc_002",
        name="V2",
        alpha=1.0,
        visibility=True,
        origin_id="pt_001",
        direction=0.785,
        elevation=0.3,
        direction_mode=DirectionMode.AZIMUTH,
        direction_units=DirectionUnits.RADIANS,
        length=50.0,
        endpoint_id="pt_002",
        line_color="#00ffff",
        fill_color="#00ffff",
    )
    assert vc.endpoint_id == "pt_002"
    assert vc.elevation == 0.3


def test_circle_instantiation():
    ci = Circle(
        id="ci_001",
        name="C",
        alpha=1.0,
        visibility=True,
        center_id="pt_001",
        radius=50.0,
        line_color="#ff6600",
        fill_color="#ffd699",
    )
    assert ci.type == "circle"
    assert ci.radius == 50.0


def test_tangent_instantiation_circle():
    tg = Tangent(
        id="tg_001",
        name="T",
        alpha=1.0,
        visibility=True,
        shape_id="ci_001",
        shape_type="circle",
        point_id="pt_004",
        direction=2.356,
        elevation=0.0,
        direction_mode=DirectionMode.AZIMUTH,
        direction_units=DirectionUnits.RADIANS,
        line_color="#00ff66",
        fill_color="#00ff66",
    )
    assert tg.type == "tangent"
    assert tg.shape_id == "ci_001"
    assert tg.shape_type == "circle"
    assert tg.point_id == "pt_004"
    assert tg.elevation == 0.0


def test_tangent_instantiation_ball():
    tg = Tangent(
        id="tg_002",
        name="T2",
        alpha=1.0,
        visibility=True,
        shape_id="ba_001",
        shape_type="ball",
        point_id="pt_005",
        direction=1.0,
        elevation=0.5,
        direction_mode=DirectionMode.AZIMUTH,
        direction_units=DirectionUnits.RADIANS,
        line_color="#00ff66",
        fill_color="#00ff66",
    )
    assert tg.type == "tangent"
    assert tg.shape_id == "ba_001"
    assert tg.shape_type == "ball"
    assert tg.elevation == 0.5


# ---------------------------------------------------------------------------
# New 3D types: Ball, Cylinder, Solid
# ---------------------------------------------------------------------------


def test_ball_instantiation():
    ba = Ball(
        id="ba_001",
        name="B",
        alpha=1.0,
        visibility=True,
        center_id="pt_001",
        radius=25.0,
        line_color="#ff6600",
        fill_color="#ffd699",
    )
    assert ba.type == "ball"
    assert ba.center_id == "pt_001"
    assert ba.radius == 25.0


def test_cylinder_instantiation():
    cy = Cylinder(
        id="cy_001",
        name="C",
        alpha=1.0,
        visibility=True,
        base_center_id="pt_001",
        radius=10.0,
        height=50.0,
        axis_mode="vertical",
        axis_azimuth=0.0,
        axis_elevation=math.pi / 2,
        direction_mode=DirectionMode.AZIMUTH,
        direction_units=DirectionUnits.RADIANS,
        line_color="#336699",
        fill_color="#99bbdd",
    )
    assert cy.type == "cylinder"
    assert cy.base_center_id == "pt_001"
    assert cy.axis_mode == "vertical"
    assert cy.axis_elevation == math.pi / 2


def test_cylinder_inclined():
    cy = Cylinder(
        id="cy_002",
        name="CI",
        alpha=0.8,
        visibility=True,
        base_center_id="pt_002",
        radius=5.0,
        height=20.0,
        axis_mode="inclined",
        axis_azimuth=0.785,
        axis_elevation=0.3,
        direction_mode=DirectionMode.AZIMUTH,
        direction_units=DirectionUnits.RADIANS,
        line_color="#336699",
        fill_color="#99bbdd",
    )
    assert cy.type == "cylinder"
    assert cy.axis_mode == "inclined"
    assert cy.axis_azimuth == 0.785


def test_solid_instantiation():
    so = Solid(
        id="so_001",
        name="S",
        alpha=0.9,
        visibility=True,
        layers=["pg_001", "pg_002", "pg_003"],
        line_color="#993300",
        fill_color="#cc9966",
    )
    assert so.type == "solid"
    assert so.layers == ("pg_001", "pg_002", "pg_003")


def test_solid_layers_defensively_copied():
    shared = ["pg_001", "pg_002"]
    so = Solid(
        id="so_002",
        name="S2",
        alpha=1.0,
        visibility=True,
        layers=shared,
        line_color="#000000",
        fill_color="#ffffff",
    )
    assert so.layers == tuple(shared)
    assert so.layers is not shared
    shared.append("pg_999")
    assert "pg_999" not in so.layers


def test_solid_apex_layer():
    so = Solid(
        id="so_003",
        name="Pyramid",
        alpha=1.0,
        visibility=True,
        layers=["pg_001", "pt_010"],
        line_color="#000000",
        fill_color="#aaaaaa",
    )
    assert so.layers[-1] == "pt_010"


# ---------------------------------------------------------------------------
# Validation: Ball, Cylinder, Solid, ElevatedObject
# ---------------------------------------------------------------------------


def _ball_kwargs(**overrides) -> dict:
    base = {
        "id": "ba_001",
        "name": "B",
        "alpha": 1.0,
        "visibility": True,
        "center_id": "pt_001",
        "radius": 10.0,
        "line_color": "#000000",
        "fill_color": "#ffffff",
    }
    base.update(overrides)
    return base


def _cylinder_kwargs(**overrides) -> dict:
    base = {
        "id": "cy_001",
        "name": "C",
        "alpha": 1.0,
        "visibility": True,
        "base_center_id": "pt_001",
        "radius": 5.0,
        "height": 10.0,
        "axis_mode": "vertical",
        "axis_azimuth": 0.0,
        "axis_elevation": math.pi / 2,
        "direction_mode": DirectionMode.AZIMUTH,
        "direction_units": DirectionUnits.RADIANS,
        "line_color": "#000000",
        "fill_color": "#ffffff",
    }
    base.update(overrides)
    return base


def _solid_kwargs(**overrides) -> dict:
    base = {
        "id": "so_001",
        "name": "S",
        "alpha": 1.0,
        "visibility": True,
        "layers": ["pg_001", "pg_002"],
        "line_color": "#000000",
        "fill_color": "#ffffff",
    }
    base.update(overrides)
    return base


def _line_kwargs(**overrides) -> dict:
    base = {
        "id": "ln_001",
        "name": "L",
        "alpha": 1.0,
        "visibility": True,
        "point_a_id": "pt_001",
        "point_b_id": "pt_002",
        "direction": 0.0,
        "elevation": 0.0,
        "direction_mode": DirectionMode.AZIMUTH,
        "direction_units": DirectionUnits.RADIANS,
        "line_color": "#000000",
        "fill_color": "#ffffff",
    }
    base.update(overrides)
    return base


def _tangent_kwargs(**overrides) -> dict:
    base = {
        "id": "tg_001",
        "name": "T",
        "alpha": 1.0,
        "visibility": True,
        "shape_id": "ci_001",
        "shape_type": "circle",
        "point_id": "pt_004",
        "direction": 2.356,
        "elevation": 0.0,
        "direction_mode": DirectionMode.AZIMUTH,
        "direction_units": DirectionUnits.RADIANS,
        "line_color": "#00ff66",
        "fill_color": "#00ff66",
    }
    base.update(overrides)
    return base


def test_ball_rejects_non_positive_radius():
    with pytest.raises(ValueError, match="radius"):
        Ball(**_ball_kwargs(radius=0.0))
    with pytest.raises(ValueError, match="radius"):
        Ball(**_ball_kwargs(radius=-5.0))


def test_cylinder_rejects_non_positive_radius():
    with pytest.raises(ValueError, match="radius"):
        Cylinder(**_cylinder_kwargs(radius=0.0))
    with pytest.raises(ValueError, match="radius"):
        Cylinder(**_cylinder_kwargs(radius=-1.0))


def test_cylinder_rejects_non_positive_height():
    with pytest.raises(ValueError, match="height"):
        Cylinder(**_cylinder_kwargs(height=0.0))
    with pytest.raises(ValueError, match="height"):
        Cylinder(**_cylinder_kwargs(height=-10.0))


def test_cylinder_inclined_rejects_out_of_range_axis_elevation():
    # Inclined mode with elevation = 0 is a flat disk — rejected.
    with pytest.raises(ValueError, match="axis_elevation"):
        Cylinder(**_cylinder_kwargs(axis_mode="inclined", axis_elevation=0.0))
    # Elevation > π/2 is beyond vertical — rejected.
    with pytest.raises(ValueError, match="axis_elevation"):
        Cylinder(**_cylinder_kwargs(axis_mode="inclined", axis_elevation=math.pi))


def test_solid_rejects_fewer_than_two_layers():
    with pytest.raises(ValueError, match="2"):
        Solid(**_solid_kwargs(layers=["pg_001"]))
    with pytest.raises(ValueError, match="2"):
        Solid(**_solid_kwargs(layers=[]))


def test_elevated_object_rejects_non_finite_elevation():
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="finite"):
            Line(**_line_kwargs(elevation=bad))


def test_elevated_object_rejects_out_of_range_elevation():
    # Elevation outside [-π/2, π/2] must be rejected.
    with pytest.raises(ValueError, match="π/2"):
        Line(**_line_kwargs(elevation=math.pi))
    with pytest.raises(ValueError, match="π/2"):
        Line(**_line_kwargs(elevation=-math.pi))


def test_elevated_object_accepts_elevation_boundaries():
    # ±π/2 ("straight up"/"straight down") are valid — guards a fence-post
    # change from <= to < silently rejecting vertical directions.
    for boundary in (math.pi / 2, -math.pi / 2):
        line = Line(**_line_kwargs(elevation=boundary))
        assert line.elevation == boundary


def test_elevated_object_rejects_non_finite_direction():
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="direction"):
            Line(**_line_kwargs(direction=bad))


def test_elevated_object_rejects_raw_string_direction_mode():
    # The wire format uses lowercase strings ("azimuth"); the deserialiser must
    # map them to DirectionMode before construction. A raw string must raise.
    with pytest.raises(ValueError, match="direction_mode"):
        Line(**_line_kwargs(direction_mode="azimuth"))


def test_elevated_object_rejects_raw_string_direction_units():
    with pytest.raises(ValueError, match="direction_units"):
        Line(**_line_kwargs(direction_units="radians"))


# ---------------------------------------------------------------------------
# ElevatedObject: azimuth normalization
# ---------------------------------------------------------------------------


def test_azimuth_mode_normalizes_direction_above_two_pi():
    # 3π mod 2π = π — a value one full turn past π wraps back to π.
    ln = Line(**_line_kwargs(direction=3 * math.pi, direction_mode=DirectionMode.AZIMUTH))
    assert ln.direction == pytest.approx(math.pi)


def test_azimuth_mode_normalizes_negative_direction():
    # -π/2 mod 2π = 3π/2 — negative azimuths wrap into [0, 2π).
    ln = Line(**_line_kwargs(direction=-math.pi / 2, direction_mode=DirectionMode.AZIMUTH))
    assert ln.direction == pytest.approx(3 * math.pi / 2)


def test_angle_mode_normalizes_direction_above_two_pi():
    # Angle mode applies the same [0, 2π) normalization as azimuth mode.
    # 3π mod 2π = π — a value one full turn past π wraps back to π.
    ln = Line(**_line_kwargs(direction=3 * math.pi, direction_mode=DirectionMode.ANGLE))
    assert ln.direction == pytest.approx(math.pi)


def test_ball_rejects_non_finite_radius():
    for bad in (math.inf, math.nan):
        with pytest.raises(ValueError, match="radius"):
            Ball(**_ball_kwargs(radius=bad))


def test_ball_rejects_radius_at_distance_floor():
    # radius must be strictly greater than the linear tolerance EPS_DISTANCE.
    with pytest.raises(ValueError, match="radius"):
        Ball(**_ball_kwargs(radius=EPS_DISTANCE))


def test_cylinder_rejects_non_finite_radius_and_height():
    for bad in (math.inf, math.nan):
        with pytest.raises(ValueError, match="radius"):
            Cylinder(**_cylinder_kwargs(radius=bad))
        with pytest.raises(ValueError, match="height"):
            Cylinder(**_cylinder_kwargs(height=bad))


def test_cylinder_rejects_radius_at_distance_floor():
    with pytest.raises(ValueError, match="radius"):
        Cylinder(**_cylinder_kwargs(radius=EPS_DISTANCE))


def test_cylinder_rejects_invalid_axis_mode():
    with pytest.raises(ValueError, match="axis_mode"):
        Cylinder(**_cylinder_kwargs(axis_mode="diagonal"))


def test_cylinder_vertical_rejects_wrong_axis_elevation():
    # A vertical cylinder must store axis_elevation = π/2 exactly.
    with pytest.raises(ValueError, match="axis_elevation"):
        Cylinder(**_cylinder_kwargs(axis_mode="vertical", axis_elevation=0.0))


def test_cylinder_vertical_rejects_nonzero_axis_azimuth():
    with pytest.raises(ValueError, match="axis_azimuth"):
        Cylinder(
            **_cylinder_kwargs(axis_mode="vertical", axis_azimuth=1.0, axis_elevation=math.pi / 2)
        )


def test_cylinder_inclined_rejects_axis_elevation_at_vertical():
    # axis_elevation = π/2 with axis_mode='inclined' is ambiguous: axis_azimuth
    # would be meaningless for a vertical axis. The correct form is
    # axis_mode='vertical'. Verify that the check catches the exact value and
    # a value within EPS_ANGLE of π/2.
    with pytest.raises(ValueError, match="vertical"):
        Cylinder(**_cylinder_kwargs(axis_mode="inclined", axis_elevation=math.pi / 2))
    with pytest.raises(ValueError, match="vertical"):
        Cylinder(
            **_cylinder_kwargs(axis_mode="inclined", axis_elevation=math.pi / 2 - EPS_ANGLE / 2)
        )


def test_tangent_rejects_invalid_shape_type():
    with pytest.raises(ValueError, match="shape_type"):
        Tangent(**_tangent_kwargs(shape_type="polygon"))


def test_tangent_circle_rejects_nonzero_elevation():
    # Circle tangents are always horizontal; a non-zero elevation is rejected.
    with pytest.raises(ValueError, match="elevation"):
        Tangent(**_tangent_kwargs(shape_type="circle", elevation=0.5))


def test_tangent_circle_accepts_near_zero_elevation_within_tolerance():
    # The horizontal check uses the angular tolerance, so a value 1 ULP off 0.0
    # (e.g. from radians(0.0) round-trips) must not be wrongly rejected.
    tg = Tangent(**_tangent_kwargs(shape_type="circle", elevation=EPS_ANGLE / 2))
    assert tg.shape_type == "circle"


# ---------------------------------------------------------------------------
# Point: altitude default and coordinate finiteness
# ---------------------------------------------------------------------------


def test_point_altitude_defaults_to_zero():
    # Spec §1: altitude defaults to 0.0 when omitted, so the loader need not
    # inject it before construction.
    pt = Point(
        id="pt_001",
        name="A",
        alpha=1.0,
        visibility=True,
        easting=1.0,
        northing=2.0,
        color="#000000",
    )
    assert pt.altitude == 0.0


def test_point_rejects_non_finite_coordinates():
    for field_name in ("easting", "northing", "altitude"):
        for bad in (math.nan, math.inf, -math.inf):
            kwargs = {
                "id": "pt_001",
                "name": "A",
                "alpha": 1.0,
                "visibility": True,
                "easting": 1.0,
                "northing": 2.0,
                "altitude": 3.0,
                "color": "#000000",
            }
            kwargs[field_name] = bad
            with pytest.raises(ValueError, match=field_name):
                Point(**kwargs)


# ---------------------------------------------------------------------------
# Circle: radius validation parity with Ball/Cylinder
# ---------------------------------------------------------------------------


def _circle_kwargs(**overrides) -> dict:
    base = {
        "id": "ci_001",
        "name": "C",
        "alpha": 1.0,
        "visibility": True,
        "center_id": "pt_001",
        "radius": 10.0,
        "line_color": "#000000",
        "fill_color": "#ffffff",
    }
    base.update(overrides)
    return base


def test_circle_rejects_non_positive_radius():
    with pytest.raises(ValueError, match="radius"):
        Circle(**_circle_kwargs(radius=0.0))
    with pytest.raises(ValueError, match="radius"):
        Circle(**_circle_kwargs(radius=-5.0))


def test_circle_rejects_non_finite_radius():
    for bad in (math.inf, math.nan):
        with pytest.raises(ValueError, match="radius"):
            Circle(**_circle_kwargs(radius=bad))


def test_circle_rejects_radius_at_distance_floor():
    with pytest.raises(ValueError, match="radius"):
        Circle(**_circle_kwargs(radius=EPS_DISTANCE))


# ---------------------------------------------------------------------------
# Cylinder: axis-angle finiteness, tolerance, and inclined range additions
# ---------------------------------------------------------------------------


def test_cylinder_inclined_rejects_non_finite_axis_azimuth():
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="axis_azimuth"):
            Cylinder(**_cylinder_kwargs(axis_mode="inclined", axis_azimuth=bad, axis_elevation=0.5))


def test_cylinder_inclined_rejects_negative_axis_elevation():
    # The lower side of the (0, π/2) inclined range was previously unexercised.
    with pytest.raises(ValueError, match="axis_elevation"):
        Cylinder(**_cylinder_kwargs(axis_mode="inclined", axis_elevation=-0.1))


def test_cylinder_rejects_raw_string_direction_mode():
    with pytest.raises(ValueError, match="direction_mode"):
        Cylinder(**_cylinder_kwargs(direction_mode="azimuth"))


def test_cylinder_rejects_raw_string_direction_units():
    with pytest.raises(ValueError, match="direction_units"):
        Cylinder(**_cylinder_kwargs(direction_units="radians"))


def test_cylinder_inclined_normalizes_axis_azimuth():
    # Inclined-mode axis_azimuth is normalized into [0, 2π) for canonical
    # storage, mirroring ElevatedObject.direction. 3π wraps to π.
    cy = Cylinder(
        **_cylinder_kwargs(axis_mode="inclined", axis_azimuth=3 * math.pi, axis_elevation=0.3)
    )
    assert cy.axis_azimuth == pytest.approx(math.pi)
    assert 0.0 <= cy.axis_azimuth < 2 * math.pi


def test_cylinder_inclined_normalizes_negative_axis_azimuth():
    cy = Cylinder(
        **_cylinder_kwargs(axis_mode="inclined", axis_azimuth=-math.pi / 2, axis_elevation=0.3)
    )
    assert cy.axis_azimuth == pytest.approx(3 * math.pi / 2)


def test_cylinder_vertical_accepts_axis_angles_within_tolerance():
    # A vertical cylinder whose axis_elevation/axis_azimuth land within EPS_ANGLE
    # of π/2 and 0.0 (e.g. from radians(90.0)) must construct, not be rejected.
    cy = Cylinder(
        **_cylinder_kwargs(
            axis_mode="vertical",
            axis_azimuth=EPS_ANGLE / 2,
            axis_elevation=math.pi / 2 - EPS_ANGLE / 2,
        )
    )
    assert cy.axis_mode == "vertical"


# ---------------------------------------------------------------------------
# Solid: Point-ID layer rule (spec §10)
# ---------------------------------------------------------------------------


def test_solid_rejects_multiple_point_layers():
    with pytest.raises(ValueError, match="at most one Point ID"):
        Solid(**_solid_kwargs(layers=["pt_001", "pg_001", "pt_002"]))


def test_solid_rejects_interior_point_layer():
    with pytest.raises(ValueError, match="first or last"):
        Solid(**_solid_kwargs(layers=["pg_001", "pt_001", "pg_002"]))


def test_solid_accepts_point_as_first_or_last_layer():
    first = Solid(**_solid_kwargs(layers=["pt_001", "pg_001", "pg_002"]))
    assert first.layers[0] == "pt_001"
    last = Solid(**_solid_kwargs(layers=["pg_001", "pg_002", "pt_001"]))
    assert last.layers[-1] == "pt_001"


def test_solid_rejects_mis_prefixed_layer():
    # A layer must be a Polygon ('pg_') or Point ('pt_') ID. Anything else
    # (a Circle ID, a typo, an empty string) was previously accepted silently
    # as a polygon layer; it must now be rejected at construction.
    for bad in ("ci_001", "polygon_1", ""):
        with pytest.raises(ValueError, match="mis-prefixed"):
            Solid(**_solid_kwargs(layers=["pg_001", bad]))


# ---------------------------------------------------------------------------
# Vector: length validation
# ---------------------------------------------------------------------------


def _vector_kwargs(**overrides) -> dict:
    base = {
        "id": "vc_001",
        "name": "V",
        "alpha": 1.0,
        "visibility": True,
        "origin_id": "pt_001",
        "direction": 0.785,
        "elevation": 0.0,
        "direction_mode": DirectionMode.AZIMUTH,
        "direction_units": DirectionUnits.RADIANS,
        "length": 100.0,
        "endpoint_id": None,
        "line_color": "#000000",
        "fill_color": "#ffffff",
    }
    base.update(overrides)
    return base


def test_cylinder_rejects_height_at_distance_floor():
    # Mirror of test_cylinder_rejects_radius_at_distance_floor for height.
    with pytest.raises(ValueError, match="height"):
        Cylinder(**_cylinder_kwargs(height=EPS_DISTANCE))


def test_cylinder_inclined_accepts_small_positive_axis_elevation():
    # A small positive elevation well below EPS_ANGLE of π/2 must be accepted
    # for inclined mode, pinning the strict lower bound from the acceptance side.
    cy = Cylinder(
        **_cylinder_kwargs(
            axis_mode="inclined",
            axis_azimuth=0.785,
            axis_elevation=0.01,
        )
    )
    assert cy.axis_mode == "inclined"
    assert cy.axis_elevation == pytest.approx(0.01)


def test_tangent_circle_accepts_elevation_at_exact_tolerance_boundary():
    # elevation = EPS_ANGLE: the check is ``abs(elevation) > EPS_ANGLE``, so the
    # exact boundary value is accepted (strict >), not rejected. This pins the
    # strict inequality so a future change to >= would fail loud.
    tg = Tangent(**_tangent_kwargs(shape_type="circle", elevation=EPS_ANGLE))
    assert tg.shape_type == "circle"
    assert tg.elevation == EPS_ANGLE


# ---------------------------------------------------------------------------
# Layer discipline: no forbidden imports in models
# ---------------------------------------------------------------------------


def test_no_forbidden_imports():
    """Verify no model file imports from services, canvas, ui, or persistence."""
    # Models must not reach into any layer above utils/. ``geometry.project``
    # sits above services in the layer stack (see docs/geo-sketch-design.md
    # §Layer rules) so it is forbidden too — preventative even though no
    # current model imports it.
    forbidden = {
        "geometry.services",
        "geometry.canvas",
        "geometry.ui",
        "geometry.persistence",
        "geometry.project",
    }
    models_dir = pathlib.Path(__file__).parent.parent / "geometry" / "models"

    for py_file in models_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            for module in modules:
                for bad in forbidden:
                    assert not module.startswith(bad), (
                        f"{py_file.name} imports from forbidden layer: {module}"
                    )
