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

import math
from dataclasses import dataclass, field

from geometry.models.common import GeoObject


@dataclass
class Point(GeoObject):
    """A UTM point with easting, northing, and altitude coordinates.

    Coordinates are in meters. Easting comes first in tuples (UTM convention).
    ``altitude`` carries a Python default of 0.0, matching the spec rule that
    altitude defaults to 0.0 when absent or null in the JSON file; the UI form
    pre-fills 0.0. The serializer always writes ``altitude`` explicitly.

    Fields
    ------
    easting : float
        UTM easting in metres. Must be finite.
    northing : float
        UTM northing in metres. Must be finite.
    color : str
        Hex colour string for the marker (e.g. ``"#FF0000"``).
    altitude : float
        Elevation above datum in metres; must be finite. Defaults to 0.0 for
        2-D-only use. Declared after ``color`` so it can carry the spec's 0.0
        default — a dataclass forbids a defaulted field before the
        non-default ``color``.

    See Also
    --------
    geometry.models.common.GeoObject : Shared envelope fields (``id``, ``name``,
        ``type``, ``alpha``, ``visibility``) inherited by every concrete model.
    """

    easting: float
    northing: float
    color: str
    altitude: float = 0.0
    type: str = field(init=False, default="point")

    def __post_init__(self) -> None:
        super().__post_init__()
        if not math.isfinite(self.easting):
            raise ValueError(f"Point.easting must be finite; got {self.easting!r}")
        if not math.isfinite(self.northing):
            raise ValueError(f"Point.northing must be finite; got {self.northing!r}")
        if not math.isfinite(self.altitude):
            raise ValueError(f"Point.altitude must be finite; got {self.altitude!r}")
