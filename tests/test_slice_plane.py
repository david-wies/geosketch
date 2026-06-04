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

"""Tests for the ephemeral SlicePlane data class (never a GeoObject)."""

import math

import pytest

from geometry.models import GeoObject, SlicePlane


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
    # vector is unit-length (the UI normalises before constructing).
    unit = 1.0 / math.sqrt(3.0)
    sp = SlicePlane(mode="custom", a=unit, b=unit, c=unit, d=50.0)
    assert sp.mode == "custom"
    assert sp.thickness == 0.0


def test_slice_plane_custom_rejects_non_unit_normal():
    # A non-unit normal silently changes the effective slab thickness, so the
    # Custom-mode inclusion test requires a unit normal.
    with pytest.raises(ValueError, match="unit-length"):
        SlicePlane(mode="custom", a=1.0, b=1.0, c=1.0, d=50.0)


def test_slice_plane_rejects_invalid_mode():
    with pytest.raises(ValueError, match="mode"):
        SlicePlane(mode="diagonal", a=0.0, b=0.0, c=1.0, d=0.0)


def test_slice_plane_rejects_negative_thickness():
    with pytest.raises(ValueError, match="thickness"):
        SlicePlane(mode="horizontal", a=0.0, b=0.0, c=1.0, d=0.0, thickness=-1.0)


def test_slice_plane_rejects_zero_normal():
    with pytest.raises(ValueError, match="zero vector"):
        SlicePlane(mode="custom", a=0.0, b=0.0, c=0.0, d=0.0)


def test_slice_plane_rejects_non_finite_coefficients():
    # nan/inf slip past ``< 0`` and the magnitude check, silently degrading the
    # inclusion test to all-excluded or all-included — they must raise instead.
    for field_name in ("a", "b", "c", "d"):
        for bad in (math.nan, math.inf, -math.inf):
            kwargs = {"mode": "horizontal", "a": 0.0, "b": 0.0, "c": 1.0, "d": 10.0}
            kwargs[field_name] = bad
            with pytest.raises(ValueError, match=field_name):
                SlicePlane(**kwargs)


def test_slice_plane_rejects_non_finite_thickness():
    for bad in (math.nan, math.inf):
        with pytest.raises(ValueError, match="thickness"):
            SlicePlane(mode="horizontal", a=0.0, b=0.0, c=1.0, d=0.0, thickness=bad)
