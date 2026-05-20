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

# pylint: disable=duplicate-code
from dataclasses import dataclass, field

from geometry.models.common import DirectionMode, DirectionUnits, GeoObject


@dataclass
class Vector(GeoObject):
    """A vector with a fixed origin, direction, and length.

    Endpoint formula (azimuth convention):
        endpoint = (origin_e + length * sin(az), origin_n + length * cos(az))

    The ``endpoint_id`` field is ``None`` when the vector was created via the
    Length + Direction tab; it is set to a Point ID when the vector was created
    via the Origin + Endpoint tab (so both authoring modes round-trip cleanly).

    ``fill_color`` is stored for schema consistency but is not rendered for
    this 1-D object.

    Fields
    ------
    origin_id : str
        ID of the origin point.
    direction : float
        Direction in radians (internal storage only).
    direction_mode : DirectionMode
        Whether ``direction`` represents an azimuth or a standard math angle.
    direction_units : DirectionUnits
        Whether the user-facing representation is in radians or degrees.
    length : float
        Magnitude of the vector in metres.
    endpoint_id : str | None
        ID of the explicit endpoint point, or ``None`` for Length+Direction mode.
    line_color : str
        Hex colour string for the stroke.
    fill_color : str
        Hex colour string for fill (stored but not rendered for vectors).
    """

    origin_id: str
    direction: float
    direction_mode: DirectionMode
    direction_units: DirectionUnits
    length: float
    endpoint_id: str | None
    line_color: str
    fill_color: str
    type: str = field(init=False, default="vector")
