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
    SlicePlane,
    Solid,
    Tangent,
    Vector,
)

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
    assert so.layers == ["pg_001", "pg_002", "pg_003"]


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
    assert so.layers == shared
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


# ---------------------------------------------------------------------------
# SlicePlane (ephemeral, not a GeoObject)
# ---------------------------------------------------------------------------


def test_slice_plane_horizontal():
    sp = SlicePlane(mode="horizontal", a=0.0, b=0.0, c=1.0, d=100.0)
    assert sp.mode == "horizontal"
    assert sp.c == 1.0
    assert sp.d == 100.0
    assert sp.thickness == 0.0


def test_slice_plane_easting():
    sp = SlicePlane(mode="easting", a=1.0, b=0.0, c=0.0, d=500000.0)
    assert sp.a == 1.0
    assert sp.thickness == 0.0


def test_slice_plane_with_thickness():
    sp = SlicePlane(mode="horizontal", a=0.0, b=0.0, c=1.0, d=50.0, thickness=2.5)
    assert sp.thickness == 2.5


def test_slice_plane_not_geo_object():
    sp = SlicePlane(mode="northing", a=0.0, b=1.0, c=0.0, d=0.0)
    assert not isinstance(sp, GeoObject)


def test_slice_plane_custom_mode():
    # The fourth mode ("custom") must construct without error when the normal
    # vector is non-zero.
    sp = SlicePlane(mode="custom", a=1.0, b=1.0, c=1.0, d=50.0)
    assert sp.mode == "custom"
    assert sp.thickness == 0.0


def test_slice_plane_rejects_invalid_mode():
    with pytest.raises(ValueError, match="mode"):
        SlicePlane(mode="diagonal", a=0.0, b=0.0, c=1.0, d=0.0)


def test_slice_plane_rejects_negative_thickness():
    with pytest.raises(ValueError, match="thickness"):
        SlicePlane(mode="horizontal", a=0.0, b=0.0, c=1.0, d=0.0, thickness=-1.0)


def test_slice_plane_rejects_zero_normal():
    with pytest.raises(ValueError, match="zero vector"):
        SlicePlane(mode="custom", a=0.0, b=0.0, c=0.0, d=0.0)


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
