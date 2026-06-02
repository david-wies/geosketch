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
from geometry.utils.constants import EPS_VOLUME


@dataclass
class Ball(GeoObject):
    """A 3D sphere defined by a center Point and radius.

    Fields
    ------
    center_id : str
        ID of the Point at the geometric center of the sphere.
    radius : float
        Radius in metres; must be > 0.
    line_color : str
        Wireframe/stroke color.
    fill_color : str
        Interior fill color (rendered in 3D and Slice views; projected circle
        in 2D flat view).

    See Also
    --------
    geometry.models.common.GeoObject : Shared envelope fields (``id``, ``name``,
        ``type``, ``alpha``, ``visibility``) inherited by every concrete model.
    """

    center_id: str
    radius: float
    line_color: str
    fill_color: str
    type: str = field(init=False, default="ball")

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.radius <= EPS_VOLUME:
            raise ValueError(f"Ball.radius must be > 0; got {self.radius!r}")
