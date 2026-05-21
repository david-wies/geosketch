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
class Line(DirectedObject):
    """A directed line segment defined by two point IDs.

    Inherits ``direction``, ``direction_mode``, and ``direction_units`` from
    ``DirectedObject``.  ``fill_color`` is present in the schema for
    consistency but is ignored at render time for this 1-D object.

    Fields
    ------
    point_a_id : str
        ID of the first endpoint point.
    point_b_id : str
        ID of the second endpoint point.
    line_color : str
        Hex colour string for the stroke.
    fill_color : str
        Hex colour string for fill (stored but not rendered for lines).

    See Also
    --------
    geometry.models.common.GeoObject : Shared envelope fields (``id``, ``name``,
        ``type``, ``alpha``, ``visibility``) inherited by every concrete model.
    """

    point_a_id: str
    point_b_id: str
    line_color: str
    fill_color: str
    type: str = field(init=False, default="line")
