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

from geometry.utils.constants import EPS_DISTANCE

_VALID_MODES = frozenset({"horizontal", "easting", "northing", "custom"})

# Squared-magnitude floor below which the normal (a, b, c) is treated as the
# degenerate zero vector. Expressed via the linear metric tolerance so it stays
# in lockstep with the rest of the engine rather than a bare literal.
_EPS_NORMAL_SQ: float = EPS_DISTANCE**2

# Tolerance on |‖(a, b, c)‖² − 1| for the Custom-mode unit-normal check.
# This is a *dimensionless* numerical tolerance: the quantity (a²+b²+c²) − 1
# has no units regardless of the units of the plane coefficients. The value
# EPS_DISTANCE (1e-6) is reused here for numeric consistency with the rest of
# the engine, not because the units match. For a nearly-unit vector,
# |‖n‖² − 1| ≈ 2·|‖n‖ − 1|, so this threshold corresponds to a magnitude
# error of roughly EPS_DISTANCE / 2 ≈ 5e-7 — tight enough for any
# floating-point input the UI will produce.
_EPS_UNIT_NORMAL: float = EPS_DISTANCE


@dataclass
class SlicePlane:
    """Cutting plane definition for the Slice view tab.

    ``SlicePlane`` is **not** a ``GeoObject``. It is ephemeral UI state and
    is **never persisted** to the project file.

    The plane equation is ``a·E + b·N + c·Z = d`` where the coefficients
    ``(a, b, c)`` form a unit normal vector for the three axis-aligned
    presets. For Custom mode the UI must normalise before constructing this
    object (see ``EPS_ALTITUDE`` contract in ``spec/MVP.md``).

    Inclusion test:
    ``|a·E + b·N + c·Z - d| / √(a²+b²+c²) ≤ EPS_ALTITUDE + thickness``.
    The ``√(a²+b²+c²)`` denominator is 1 for the three axis-aligned presets and
    for any correctly normalised Custom normal, but a slice-service implementer
    must keep it to stay metric under a non-unit Custom normal.

    Fields
    ------
    mode : Literal["horizontal", "easting", "northing", "custom"]
        One of ``"horizontal"``, ``"easting"``, ``"northing"``, ``"custom"``.
    a : float
        Coefficient of Easting in the plane equation.
    b : float
        Coefficient of Northing.
    c : float
        Coefficient of Altitude.
    d : float
        Right-hand-side constant (offset from origin along the normal).
    thickness : float
        Half-thickness of the slab in metres (default 0.0 = exact plane).
        Points within ±``thickness`` of the plane are included.

    All four modes require ``(a, b, c)`` to be a unit normal
    (``|‖n‖² − 1| ≤ _EPS_UNIT_NORMAL``). The three axis-aligned presets use
    canonical unit coefficients; Custom mode requires the caller to normalise
    before constructing. Construction raises ``ValueError`` for any mode if the
    normal is not unit-length.

    Preset encodings
    ----------------
    Horizontal Z=v  →  a=0, b=0, c=1, d=v
    Easting E=v     →  a=1, b=0, c=0, d=v
    Northing N=v    →  a=0, b=1, c=0, d=v
    Custom          →  UI normalises so sqrt(a²+b²+c²)=1, then d is offset.
    """

    mode: Literal["horizontal", "easting", "northing", "custom"]
    a: float
    b: float
    c: float
    d: float
    thickness: float = field(default=0.0)

    def __post_init__(self) -> None:
        if self.mode not in _VALID_MODES:
            raise ValueError(
                f"SlicePlane.mode must be one of the four documented modes; got {self.mode!r}"
            )
        # Guard finiteness before the magnitude/thickness comparisons: nan and
        # inf slip past ``< 0`` (both ``inf < 0`` and ``nan < 0`` are False) and
        # would silently degrade the inclusion test to all-excluded or
        # all-included rather than raising.
        for name, value in (("a", self.a), ("b", self.b), ("c", self.c), ("d", self.d)):
            if not math.isfinite(value):
                raise ValueError(f"SlicePlane.{name} must be finite; got {value!r}")
        if not math.isfinite(self.thickness):
            raise ValueError(f"SlicePlane.thickness must be finite; got {self.thickness!r}")
        if self.thickness < 0:
            raise ValueError(f"SlicePlane.thickness must be >= 0; got {self.thickness!r}")
        mag_sq = self.a**2 + self.b**2 + self.c**2
        if mag_sq < _EPS_NORMAL_SQ:
            raise ValueError("SlicePlane normal (a, b, c) must not be the zero vector")
        if abs(mag_sq - 1.0) > _EPS_UNIT_NORMAL:
            raise ValueError(
                f"SlicePlane normal (a, b, c) must be unit-length for {self.mode!r} mode; "
                f"got magnitude {math.sqrt(mag_sq):.6f}"
            )
