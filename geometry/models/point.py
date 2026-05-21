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

from geometry.models.common import GeoObject


@dataclass
class Point(GeoObject):
    """A UTM point with easting and northing coordinates.

    Coordinates are in meters. Easting comes first in tuples (UTM convention).

    Fields
    ------
    easting : float
        UTM easting in metres.
    northing : float
        UTM northing in metres.
    color : str
        Hex colour string for the marker (e.g. ``"#FF0000"``).

    See Also
    --------
    geometry.models.common.GeoObject : Shared envelope fields (``id``, ``name``,
        ``type``, ``alpha``, ``visibility``) inherited by every concrete model.
    """

    easting: float
    northing: float
    color: str
    type: str = field(init=False, default="point")
