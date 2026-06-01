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


@dataclass
class SlicePlane:
    """Cutting plane definition for the Slice view tab.

    ``SlicePlane`` is **not** a ``GeoObject``. It is ephemeral UI state and
    is **never persisted** to the project file.

    The plane equation is ``a·E + b·N + c·Z = d`` where the coefficients
    ``(a, b, c)`` form a unit normal vector for the three axis-aligned
    presets. For Custom mode the UI must normalise before constructing this
    object (see ``EPS_ALTITUDE`` contract in ``spec/MVP.md``).

    Inclusion test: ``|a·E + b·N + c·Z - d| ≤ EPS_ALTITUDE + thickness``.

    Fields
    ------
    mode : str
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

    Preset encodings
    ----------------
    Horizontal Z=v  →  a=0, b=0, c=1, d=v
    Easting E=v     →  a=1, b=0, c=0, d=v
    Northing N=v    →  a=0, b=1, c=0, d=v
    Custom          →  UI normalises so sqrt(a²+b²+c²)=1, then d is offset.
    """

    mode: str
    a: float
    b: float
    c: float
    d: float
    thickness: float = field(default=0.0)
