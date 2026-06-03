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
from typing import Literal

from geometry.models.common import DirectionMode, DirectionUnits, GeoObject
from geometry.utils.constants import EPS_ANGLE, EPS_DISTANCE

_VALID_AXIS_MODES = frozenset({"vertical", "inclined"})


@dataclass
class Cylinder(GeoObject):
    """A 3D cylinder defined by a base-center Point, radius, height, and axis orientation.

    ``axis_mode`` controls whether the axis is vertical (axis points straight
    up; azimuth and elevation are stored as 0.0 and π/2 respectively) or
    inclined (azimuth and elevation are user-supplied).

    ``Cylinder`` intentionally does **not** extend ``ElevatedObject``: its
    ``axis_azimuth``/``axis_elevation`` are named geometry parameters, not the
    generic ``direction``/``elevation`` of a directed line.

    Fields
    ------
    base_center_id : str
        ID of the Point at the center of the base circular face.
    radius : float
        Radius in metres; must be finite and greater than ``EPS_DISTANCE``
        (a linear dimension, so the linear tolerance applies).
    height : float
        Length of the cylinder along its axis in metres; must be finite and
        greater than ``EPS_DISTANCE``.
    axis_mode : str
        ``"vertical"`` or ``"inclined"``. A vertical cylinder must store
        ``axis_azimuth = 0.0`` and ``axis_elevation = π/2``.
    axis_azimuth : float
        Horizontal bearing of the axis in radians (stored as 0.0 when vertical).
    axis_elevation : float
        Angle of the axis above the horizontal plane in radians; range
        ``(0, π/2]``. π/2 = vertical. Must be > 0 (0 = flat disk, rejected
        by validation).
    direction_mode : DirectionMode
        Controls display of ``axis_azimuth``.
    direction_units : DirectionUnits
        Controls display of both ``axis_azimuth`` and ``axis_elevation``.
    line_color : str
        Edge/stroke color.
    fill_color : str
        Face fill color (rendered in 3D and Slice views).

    See Also
    --------
    geometry.models.common.GeoObject : Shared envelope fields (``id``, ``name``,
        ``type``, ``alpha``, ``visibility``) inherited by every concrete model.
    """

    base_center_id: str
    radius: float
    height: float
    axis_mode: Literal["vertical", "inclined"]
    axis_azimuth: float
    axis_elevation: float
    direction_mode: DirectionMode
    direction_units: DirectionUnits
    line_color: str
    fill_color: str
    type: str = field(init=False, default="cylinder")

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.axis_mode not in _VALID_AXIS_MODES:
            raise ValueError(
                f"Cylinder.axis_mode must be 'vertical' or 'inclined'; got {self.axis_mode!r}"
            )
        if not math.isfinite(self.radius) or self.radius <= EPS_DISTANCE:
            raise ValueError(
                f"Cylinder.radius must be finite and > {EPS_DISTANCE}; got {self.radius!r}"
            )
        if not math.isfinite(self.height) or self.height <= EPS_DISTANCE:
            raise ValueError(
                f"Cylinder.height must be finite and > {EPS_DISTANCE}; got {self.height!r}"
            )
        # Guard both axis angles for finiteness before the mode-specific range
        # checks, mirroring ElevatedObject's treatment of direction/elevation.
        if not math.isfinite(self.axis_azimuth):
            raise ValueError(f"Cylinder.axis_azimuth must be finite; got {self.axis_azimuth!r}")
        if not math.isfinite(self.axis_elevation):
            raise ValueError(f"Cylinder.axis_elevation must be finite; got {self.axis_elevation!r}")
        if self.axis_mode == "inclined" and not 0.0 < self.axis_elevation <= math.pi / 2:
            raise ValueError(
                f"Cylinder.axis_elevation must be in (0, π/2] for an inclined "
                f"cylinder; got {self.axis_elevation!r}"
            )
        if self.axis_mode == "vertical" and abs(self.axis_elevation - math.pi / 2) > EPS_ANGLE:
            raise ValueError(
                f"Cylinder.axis_elevation must be π/2 for a vertical cylinder; "
                f"got {self.axis_elevation!r}"
            )
        if self.axis_mode == "vertical" and abs(self.axis_azimuth) > EPS_ANGLE:
            raise ValueError(
                f"Cylinder.axis_azimuth must be 0.0 for a vertical cylinder; "
                f"got {self.axis_azimuth!r}"
            )
