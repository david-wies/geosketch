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

from __future__ import annotations

from dataclasses import dataclass

from geometry.models.common import DirectionMode, DirectionUnits, GeoObject


@dataclass
class Line(GeoObject):
    """A directed line segment defined by two point IDs.

    The direction is always stored internally in radians regardless of
    ``direction_units``.  ``direction_mode`` and ``direction_units`` record
    how the user originally expressed the direction, so the UI can round-trip
    the value without silent unit conversion.

    ``fill_color`` is present in the schema for consistency but is ignored
    at render time for this 1-D object.

    Fields
    ------
    point_a_id : str
        ID of the first endpoint point.
    point_b_id : str
        ID of the second endpoint point.
    direction : float
        Direction in radians (internal storage only).
    direction_mode : DirectionMode
        Whether ``direction`` represents an azimuth or a standard math angle.
    direction_units : DirectionUnits
        Whether the user-facing representation is in radians or degrees.
    line_color : str
        Hex colour string for the stroke.
    fill_color : str
        Hex colour string for fill (stored but not rendered for lines).
    """

    point_a_id: str
    point_b_id: str
    direction: float
    direction_mode: DirectionMode
    direction_units: DirectionUnits
    line_color: str
    fill_color: str
