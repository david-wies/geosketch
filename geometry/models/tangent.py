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

from geometry.models.common import DirectedObject


@dataclass
class Tangent(DirectedObject):
    """A tangent line at a point on a circle's circumference, perpendicular to the radius.

    Inherits ``direction``, ``direction_mode``, and ``direction_units`` from
    ``DirectedObject``.  ``fill_color`` is stored for schema consistency but
    is not rendered for this 1-D object.

    The canonical direction formula relating ``direction`` to the underlying
    circle/point geometry lives in ``services/geometry.py``; the model layer
    just stores whatever radians value it is given.

    Fields
    ------
    circle_id : str
        ID of the target circle.
    point_id : str
        ID of the point on the circumference where the tangent is drawn.
    line_color : str
        Hex colour string for the stroke.
    fill_color : str
        Hex colour string for fill (stored but not rendered for tangents).

    See Also
    --------
    geometry.models.common.GeoObject : Shared envelope fields (``id``, ``name``,
        ``type``, ``alpha``, ``visibility``) inherited by every concrete model.
    """

    circle_id: str
    point_id: str
    line_color: str
    fill_color: str
    type: str = field(init=False, default="tangent")
