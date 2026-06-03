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
from geometry.utils.constants import EPS_DISTANCE


@dataclass
class Circle(GeoObject):
    """A circle defined by a centre point and a radius.

    Fields
    ------
    center_id : str
        ID of the centre point.
    radius : float
        Radius in metres; must be finite and greater than ``EPS_DISTANCE``
        (a linear dimension, matching the ``Ball``/``Cylinder`` guard).
    line_color : str
        Hex colour string for the outline stroke.
    fill_color : str
        Hex colour string for the interior fill.

    See Also
    --------
    geometry.models.common.GeoObject : Shared envelope fields (``id``, ``name``,
        ``type``, ``alpha``, ``visibility``) inherited by every concrete model.
    """

    center_id: str
    radius: float
    line_color: str
    fill_color: str
    type: str = field(init=False, default="circle")

    def __post_init__(self) -> None:
        super().__post_init__()
        if not math.isfinite(self.radius) or self.radius <= EPS_DISTANCE:
            raise ValueError(
                f"Circle.radius must be finite and > {EPS_DISTANCE}; got {self.radius!r}"
            )
