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
import math
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
    """Base data class shared by all ten geometry object types.

    ``GeoObject`` is not instantiable on its own — every concrete object must
    be one of the ten subclasses (Point, Line, Polygon, Ray, Vector, Circle,
    Ball, Cylinder, Solid, Tangent), each of which pins ``type`` to a
    canonical literal via ``field(init=False, default=...)``. The
    ``__post_init__`` guard below enforces this so service code cannot
    accidentally produce a base object with a bogus ``type`` string.

    Fields
    ------
    id : str
        Unique object identifier of the form ``<type>_NNN`` (e.g. ``pt_001``).
        References between objects use these strings, not memory pointers.
    name : str
        User-visible label.
    type : str
        Lowercase canonical type name (e.g. ``"point"``, ``"line"``,
        ``"polygon"``, ``"ray"``, ``"vector"``, ``"circle"``, ``"ball"``,
        ``"cylinder"``, ``"solid"``, ``"tangent"``).
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
                "instantiated directly; use one of the ten concrete "
                "subclasses (Point, Line, Polygon, Ray, Vector, Circle, "
                "Ball, Cylinder, Solid, Tangent)."
            )


@dataclass
class ElevatedObject(GeoObject):
    """Abstract intermediate base for the four direction-bearing geometry types.

    "Elevated" names the distinguishing trait of this base: beyond a horizontal
    ``direction``, each subclass also carries a vertical ``elevation`` angle, so
    its bearing can point out of the horizontal plane (renamed from
    ``DirectedObject`` to make that 3-D capability explicit). ``Line``, ``Ray``,
    ``Vector``, and ``Tangent`` are the four "direction-bearing" subclasses.

    ``ElevatedObject`` is not instantiable on its own — like ``GeoObject``,
    it is an abstract base whose only purpose is to share the four
    direction-metadata fields (``direction``, ``elevation``,
    ``direction_mode``, ``direction_units``) across the four concrete
    subclasses ``Line``, ``Ray``, ``Vector``, and ``Tangent``. ``Point``,
    ``Polygon``, ``Circle``, ``Ball``, ``Cylinder``, and ``Solid`` extend
    ``GeoObject`` directly because they have no generic direction bearing.
    The ``__post_init__`` guard below enforces this so service code cannot
    accidentally produce a bare ``ElevatedObject`` with a bogus ``type``.

    ``direction`` is always stored internally in radians; ``direction_mode``
    and ``direction_units`` record how the user originally expressed the
    direction so the UI can round-trip the value without silent unit
    conversion.

    Fields
    ------
    direction : float
        Horizontal bearing in radians (internal storage); must be finite.
    elevation : float
        Angle above the horizontal plane in radians, range ``[-π/2, π/2]``;
        0.0 = horizontal. Required at construction (forms/loader supply 0.0).
    direction_mode : DirectionMode
        Whether ``direction`` represents an azimuth (CW from North) or a
        standard math angle (CCW from East).
    direction_units : DirectionUnits
        Whether the user-facing representation is in radians or degrees.
        Applies to both ``direction`` and ``elevation`` display.
    """

    direction: float
    elevation: float
    direction_mode: DirectionMode
    direction_units: DirectionUnits

    def __post_init__(self) -> None:
        super().__post_init__()
        # `isinstance` would be True for every concrete subclass too,
        # defeating the guard — exact-type identity is the correct check.
        if type(self) is ElevatedObject:  # pylint: disable=unidiomatic-typecheck
            raise TypeError(
                "ElevatedObject is an abstract base class and must not be "
                "instantiated directly; use one of the four concrete "
                "subclasses (Line, Ray, Vector, Tangent)."
            )
        if not math.isfinite(self.direction):
            raise ValueError(f"ElevatedObject.direction must be finite; got {self.direction!r}")
        if not math.isfinite(self.elevation):
            raise ValueError(f"ElevatedObject.elevation must be finite; got {self.elevation!r}")
        if not -math.pi / 2 <= self.elevation <= math.pi / 2:
            raise ValueError(
                f"ElevatedObject.elevation must be in [-π/2, π/2]; got {self.elevation!r}"
            )
