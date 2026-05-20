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
class Circle(GeoObject):
    """A circle defined by a centre point and a radius.

    Fields
    ------
    center_id : str
        ID of the centre point.
    radius : float
        Radius in metres.
    line_color : str
        Hex colour string for the outline stroke.
    fill_color : str
        Hex colour string for the interior fill.
    """

    center_id: str
    radius: float
    line_color: str
    fill_color: str
    type: str = field(init=False, default="circle")
