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

import enum
from dataclasses import dataclass


class DirectionMode(enum.Enum):
    """Whether a direction is expressed as an azimuth (CW from North) or a
    standard math angle (CCW from East)."""

    AZIMUTH = "azimuth"
    ANGLE = "angle"


class DirectionUnits(enum.Enum):
    """Whether a direction value is in radians or degrees."""

    RADIANS = "radians"
    DEGREES = "degrees"


@dataclass
class GeoObject:
    """Base data class shared by all seven geometry object types.

    Fields
    ------
    id : str
        Unique object identifier of the form ``<type>_NNN`` (e.g. ``pt_001``).
        References between objects use these strings, not memory pointers.
    name : str
        User-visible label.
    type : str
        Lowercase type tag matching the ID prefix (e.g. ``"pt"``, ``"ln"``).
    alpha : float
        Opacity in [0.0, 1.0].
    visibility : bool
        Whether the object is rendered on the canvas.
    """

    id: str
    name: str
    type: str
    alpha: float
    visibility: bool
