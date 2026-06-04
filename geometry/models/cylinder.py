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

# ``axis_mode`` is typed ``Literal["vertical", "inclined"]``, but Python does
# not enforce ``Literal`` at runtime, so this frozenset is the actual guard
# against bogus wire values — do not delete it as "redundant" with the type.
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
        Horizontal bearing of the axis in radians. When ``axis_mode='vertical'``
        it must be 0.0 within ``EPS_ANGLE`` (a vertical axis has no meaningful
        bearing). When ``axis_mode='inclined'`` it is normalized into ``[0, 2π)``
        at construction via modulo arithmetic, mirroring
        ``ElevatedObject.direction``, so callers need not pre-range it.
    axis_elevation : float
        Angle of the axis above the horizontal plane in radians; range
        ``(0, π/2)`` strictly open for ``axis_mode='inclined'``. Must be > 0
        (0 = flat disk, rejected by validation). Values within ``EPS_ANGLE``
        of π/2 are also rejected for inclined mode — use ``axis_mode='vertical'``
        for a vertical axis so that ``axis_azimuth`` is always meaningful.
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
        # Reject raw wire strings that bypass the enum, mirroring ElevatedObject:
        # the deserialiser must map "azimuth"/"radians" to the enum members.
        if not isinstance(self.direction_mode, DirectionMode):
            raise ValueError(
                f"Cylinder.direction_mode must be a DirectionMode member; "
                f"got {self.direction_mode!r}"
            )
        if not isinstance(self.direction_units, DirectionUnits):
            raise ValueError(
                f"Cylinder.direction_units must be a DirectionUnits member; "
                f"got {self.direction_units!r}"
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
        if self.axis_mode == "inclined":
            # Normalize the bearing into [0, 2π) for canonical storage, matching
            # ElevatedObject.direction. Done only for inclined mode: vertical mode
            # forces axis_azimuth ≈ 0.0, which is already canonical.
            self.axis_azimuth = self.axis_azimuth % (2 * math.pi)
            # Check the near-vertical case first so that values within EPS_ANGLE
            # of π/2 get the actionable "use axis_mode='vertical'" message instead
            # of the generic range message (the range check uses strict <, so
            # values at or above π/2 would otherwise hit the range error first).
            if abs(self.axis_elevation - math.pi / 2) < EPS_ANGLE:
                raise ValueError(
                    f"Cylinder.axis_elevation = π/2 (or within EPS_ANGLE) is vertical; "
                    f"use axis_mode='vertical' instead; got {self.axis_elevation!r}"
                )
            if not 0.0 < self.axis_elevation < math.pi / 2:
                raise ValueError(
                    f"Cylinder.axis_elevation must be strictly in (0, π/2) for an "
                    f"inclined cylinder; got {self.axis_elevation!r}"
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
