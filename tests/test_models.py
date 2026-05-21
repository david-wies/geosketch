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
import pathlib

import pytest

from geometry.models import (
    Circle,
    DirectedObject,
    DirectionMode,
    DirectionUnits,
    GeoObject,
    Line,
    Point,
    Polygon,
    Ray,
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
        color="#ff0000",
    )
    assert pt.type == "point"
    assert pt.easting == 100.0
    assert pt.northing == 200.0
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


def test_directed_object_direct_instantiation_rejected():
    with pytest.raises(TypeError, match="abstract base class"):
        DirectedObject(
            id="x_001",
            name="X",
            type="bogus",
            alpha=1.0,
            visibility=True,
            direction=0.0,
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
        direction_mode=DirectionMode.AZIMUTH,
        direction_units=DirectionUnits.RADIANS,
        line_color="#0000ff",
        fill_color="#0000ff",
    )
    assert ln.type == "line"
    assert ln.point_a_id == "pt_001"


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
        direction_mode=DirectionMode.AZIMUTH,
        direction_units=DirectionUnits.RADIANS,
        line_color="#ff00ff",
        fill_color="#ff00ff",
    )
    assert ry.type == "ray"
    assert ry.origin_id == "pt_001"


def test_vector_instantiation_length_direction():
    vc = Vector(
        id="vc_001",
        name="V",
        alpha=1.0,
        visibility=True,
        origin_id="pt_001",
        direction=0.785,
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


def test_vector_instantiation_origin_endpoint():
    vc = Vector(
        id="vc_002",
        name="V2",
        alpha=1.0,
        visibility=True,
        origin_id="pt_001",
        direction=0.785,
        direction_mode=DirectionMode.AZIMUTH,
        direction_units=DirectionUnits.RADIANS,
        length=50.0,
        endpoint_id="pt_002",
        line_color="#00ffff",
        fill_color="#00ffff",
    )
    assert vc.endpoint_id == "pt_002"


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


def test_tangent_instantiation():
    tg = Tangent(
        id="tg_001",
        name="T",
        alpha=1.0,
        visibility=True,
        circle_id="ci_001",
        point_id="pt_004",
        direction=2.356,
        direction_mode=DirectionMode.AZIMUTH,
        direction_units=DirectionUnits.RADIANS,
        line_color="#00ff66",
        fill_color="#00ff66",
    )
    assert tg.type == "tangent"
    assert tg.circle_id == "ci_001"
    assert tg.point_id == "pt_004"


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
