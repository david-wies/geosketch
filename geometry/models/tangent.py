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
class Tangent(GeoObject):
    """A tangent line at a point on a circle's circumference, perpendicular to the radius.

    The canonical direction is the azimuth of the tangent:
        direction = (radius_azimuth + π/2) mod 2π

    Direction is always stored internally in radians.  ``fill_color`` is
    stored for schema consistency but is not rendered for this 1-D object.

    Fields
    ------
    circle_id : str
        ID of the target circle.
    point_id : str
        ID of the point on the circumference where the tangent is drawn.
    direction : float
        Tangent direction in radians (canonical: ``(radius_azimuth + π/2) mod 2π``).
    direction_mode : DirectionMode
        Whether ``direction`` represents an azimuth or a standard math angle.
    direction_units : DirectionUnits
        Whether the user-facing representation is in radians or degrees.
    line_color : str
        Hex colour string for the stroke.
    fill_color : str
        Hex colour string for fill (stored but not rendered for tangents).
    """

    circle_id: str
    point_id: str
    direction: float
    direction_mode: DirectionMode
    direction_units: DirectionUnits
    line_color: str
    fill_color: str
    type: str = field(init=False, default="tangent")
