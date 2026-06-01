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

from dataclasses import dataclass, field

from geometry.models.common import ElevatedObject


@dataclass
class Vector(ElevatedObject):
    """A vector with a fixed origin, direction, length, and elevation.

    Inherits ``direction``, ``elevation``, ``direction_mode``, and
    ``direction_units`` from ``ElevatedObject``.

    Endpoint formula (azimuth + elevation convention):
        E = origin.easting  + length * sin(az) * cos(el)
        N = origin.northing + length * cos(az) * cos(el)
        Z = origin.altitude + length * sin(el)

    The ``endpoint_id`` field is ``None`` when the vector was created via the
    Length + Direction tab; it is set to a Point ID when the vector was created
    via the Origin + Endpoint tab (so both authoring modes round-trip cleanly).

    ``fill_color`` is stored for schema consistency but is not rendered for
    this 1-D object.

    Fields
    ------
    origin_id : str
        ID of the origin point.
    length : float
        Magnitude of the vector in metres.
    endpoint_id : str | None
        ID of the explicit endpoint point, or ``None`` for Length+Direction mode.
    line_color : str
        Hex colour string for the stroke.
    fill_color : str
        Hex colour string for fill (stored but not rendered for vectors).

    See Also
    --------
    geometry.models.common.GeoObject : Shared envelope fields (``id``, ``name``,
        ``type``, ``alpha``, ``visibility``) inherited by every concrete model.
    geometry.models.common.ElevatedObject : Direction and elevation metadata
        (``direction``, ``elevation``, ``direction_mode``, ``direction_units``)
        inherited by all four direction-bearing types (Line, Ray, Vector, Tangent).
    """

    origin_id: str
    length: float
    endpoint_id: str | None
    line_color: str
    fill_color: str
    type: str = field(init=False, default="vector")
