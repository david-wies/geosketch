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

"""Numerical tolerance constants used throughout the geometry engine.

The values below are the single source of truth for every floating-point
comparison in the codebase. Service-layer code must import these constants
rather than inline bare literals, both so the thresholds can be tuned in
one place and so that diffs to those thresholds are reviewable.

The reference values are documented in ``spec/MVP.md`` § "Numerical
Tolerances" and matched here. If the spec value changes, update both this
module and the spec in the same commit.

Constants
---------
EPS_DISTANCE : float
    1e-6 m. Used for "is point on circle?", "are segments coincident?",
    "do polygons touch?", and similar metric comparisons. Matches the
    precision of typical UTM surveying inputs.
EPS_ANGLE : float
    1e-9 rad. Used for "are lines parallel?" (zero-cross-product) and
    other angular tolerance checks where radians are the natural unit.
EPS_AREA : float
    1e-9 m**2. Used for the signed-area sign check that decides whether
    a polygon is degenerate (``|signed_area| < EPS_AREA`` rejects).
EPS_PARAM : float
    1e-9. Used for parametric ``t`` clipping on segment/line intersection
    where the parameter is dimensionless and lives roughly in [0, 1].
EPS_ALTITUDE : float
    1e-6 m. Forward-looking: will gate slice-plane membership once the slice
    service lands, via
    ``|aE+bN+cZ−d| / √(a²+b²+c²) ≤ EPS_ALTITUDE + thickness``. The denominator
    is 1 when the plane normal is unit-length (the three presets and a
    normalised Custom normal) but must be retained for a non-unit normal. No
    code consumes this constant yet.
EPS_VOLUME : float
    1e-9 m³. Forward-looking: will gate Solid/Ball/Cylinder degeneracy once
    volume measurement lands (``|volume| < EPS_VOLUME`` will reject), analogous
    to EPS_AREA for 2-D polygons. No code consumes this constant yet.
"""

EPS_DISTANCE: float = 1e-6
EPS_ANGLE: float = 1e-9
EPS_AREA: float = 1e-9
EPS_PARAM: float = 1e-9
EPS_ALTITUDE: float = 1e-6
EPS_VOLUME: float = 1e-9

__all__ = [
    "EPS_DISTANCE",
    "EPS_ANGLE",
    "EPS_AREA",
    "EPS_PARAM",
    "EPS_ALTITUDE",
    "EPS_VOLUME",
]
