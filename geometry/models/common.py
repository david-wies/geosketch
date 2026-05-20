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

    ``GeoObject`` is not instantiable on its own — every concrete object must
    be one of the seven subclasses (Point, Line, Polygon, Ray, Vector, Circle,
    Tangent), each of which pins ``type`` to a canonical literal via
    ``field(init=False, default=...)``. The ``__post_init__`` guard below
    enforces this so service code cannot accidentally produce a base object
    with a bogus ``type`` string.

    Fields
    ------
    id : str
        Unique object identifier of the form ``<type>_NNN`` (e.g. ``pt_001``).
        References between objects use these strings, not memory pointers.
    name : str
        User-visible label.
    type : str
        Lowercase canonical type name (e.g. ``"point"``, ``"line"``,
        ``"polygon"``, ``"ray"``, ``"vector"``, ``"circle"``, ``"tangent"``).
        Distinct from the 2-letter ID prefix used in ``id`` (``pt`` for a
        Point, ``ln`` for a Line, etc.). Pinned at construction time via
        ``field(init=False, default=...)`` on every concrete subclass; treat
        it as a read-only class invariant after construction (post-init
        reassignment is technically legal because the dataclass is mutable,
        but no code outside of test fixtures should rely on that).
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

    def __post_init__(self) -> None:
        # `isinstance` would be True for every concrete subclass too, defeating
        # the guard — exact-type identity is the correct check here.
        if type(self) is GeoObject:  # pylint: disable=unidiomatic-typecheck
            raise TypeError(
                "GeoObject is an abstract base class and must not be "
                "instantiated directly; use one of the seven concrete "
                "subclasses (Point, Line, Polygon, Ray, Vector, Circle, "
                "Tangent)."
            )
