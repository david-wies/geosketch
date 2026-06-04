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
from typing import Literal

from geometry.models.common import ElevatedObject
from geometry.utils.constants import EPS_ANGLE

_VALID_SHAPE_TYPES = frozenset({"circle", "ball"})


@dataclass
class Tangent(ElevatedObject):
    """A tangent to a Circle or Ball at a point on its surface.

    Inherits ``direction``, ``elevation``, ``direction_mode``, and
    ``direction_units`` from ``ElevatedObject``.  ``fill_color`` is stored
    for schema consistency but is not rendered for this 1-D object.

    The canonical direction formula relating ``direction`` to the underlying
    shape/point geometry lives in ``services/geometry.py``; the model layer
    just stores whatever radians value it is given.

    ``shape_type`` drives dispatch: Circle tangents are always horizontal
    (``elevation = 0.0``); Ball tangents are 3-D and user-supplied.

    Fields
    ------
    shape_id : str
        ID of the target Circle or Ball.
    shape_type : str
        ``"circle"`` or ``"ball"``. Identifies which object ``shape_id`` refers to.
    point_id : str
        ID of the surface point where the tangent is drawn.
    line_color : str
        Hex colour string for the stroke.
    fill_color : str
        Hex colour string for fill (stored but not rendered for tangents).

    See Also
    --------
    geometry.models.common.GeoObject : Shared envelope fields (``id``, ``name``,
        ``type``, ``alpha``, ``visibility``) inherited by every concrete model.
    geometry.models.common.ElevatedObject : Direction and elevation metadata
        (``direction``, ``elevation``, ``direction_mode``, ``direction_units``)
        inherited by all four direction-bearing types (Line, Ray, Vector, Tangent).
    """

    # ``shape_id`` + ``shape_type`` replaced the pre-1.1 single ``circle_id``
    # field. When the persistence layer is implemented, the loader must map a
    # legacy ``circle_id`` key to ``shape_id = circle_id, shape_type = "circle"``
    # — see the JSON migration note in spec/MVP.md §9 (Tangent).
    shape_id: str
    shape_type: Literal["circle", "ball"]
    point_id: str
    line_color: str
    fill_color: str
    type: str = field(init=False, default="tangent")

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.shape_type not in _VALID_SHAPE_TYPES:
            raise ValueError(
                f"Tangent.shape_type must be 'circle' or 'ball'; got {self.shape_type!r}"
            )
        if self.shape_type == "circle" and abs(self.elevation) > EPS_ANGLE:
            raise ValueError(f"Tangent to a Circle must have elevation=0.0; got {self.elevation!r}")
