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

from __future__ import annotations

from dataclasses import dataclass

from geometry.models.common import GeoObject


@dataclass
class Polygon(GeoObject):
    """A polygon defined by an ordered list of point IDs.

    Vertex order is CCW — the services layer enforces winding order on
    creation and modification; this model stores the result as-is.

    ``is_convex`` is set by the services layer (using the cross-product
    method) on creation and after any modification.

    Fields
    ------
    point_ids : list[str]
        Ordered point IDs in CCW winding order.
    is_convex : bool
        True if the polygon is convex; cached by the services layer.
    line_color : str
        Hex colour string for the outline stroke.
    fill_color : str
        Hex colour string for the interior fill.
    """

    point_ids: list[str]
    is_convex: bool
    line_color: str
    fill_color: str
