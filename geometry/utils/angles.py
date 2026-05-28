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

"""Angle conversions between the two coordinate conventions GeoSketch uses.

GeoSketch interleaves two distinct angle conventions throughout the model
and the UI, and silent mix-ups between them are the single largest source
of geometry bugs. These helpers are the *only* sanctioned conversion path;
no service or model code should re-derive the formulas inline.

The two conventions:

* **Azimuth** — measured **clockwise from North**, range ``[0, 2π)``.
  Native to surveying, UTM, and the user-facing form fields.
* **Angle** — standard mathematical angle, measured **counter-clockwise
  from East**, range ``[0, 2π)``. Native to ``atan2`` and the rendering
  layer.

The relationship between them is ``angle = π/2 - azimuth`` (and vice
versa), both reduced into ``[0, 2π)``. All helpers in this module return
``numpy.float64`` so the value can be inserted directly into NumPy
expressions without an implicit cast.

Public functions
----------------
azimuth_to_angle(rad)
    Convert an azimuth (radians, CW from N) to a math angle
    (radians, CCW from E), normalised into ``[0, 2π)``.
angle_to_azimuth(rad)
    Inverse of ``azimuth_to_angle``.
to_radians(value, units)
    Convert a user-facing direction value to radians, accepting either
    ``"radians"``/``"degrees"`` as a (case-insensitive) string or a
    :class:`DirectionUnits` enum member.
to_degrees(rad)
    Convert radians to degrees.
normalize_to_2pi(rad)
    Reduce any real-valued radian measure into ``[0, 2π)``. Behaves
    correctly for negative inputs (Python's ``%`` already does the
    right thing for ``float`` operands; documented here so callers are
    not tempted to "fix" it).
"""

from __future__ import annotations

import numpy as np

from geometry.models.common import DirectionUnits

_TWO_PI: np.float64 = np.float64(2.0) * np.float64(np.pi)
_HALF_PI: np.float64 = np.float64(np.pi) / np.float64(2.0)


def normalize_to_2pi(rad: float) -> np.float64:
    """Reduce ``rad`` into the half-open interval ``[0, 2π)``.

    Python's ``%`` operator on floats already returns a non-negative
    result whose sign matches the divisor, so ``-0.5 % (2π)`` yields
    ``2π - 0.5`` as desired. The reduction is performed in ``float64``
    to match the project's reference precision.

    Parameters
    ----------
    rad : float
        Any real-valued radian measure (may be negative or > 2π).

    Returns
    -------
    numpy.float64
        The reduced value in ``[0, 2π)``.
    """
    return np.float64(rad) % _TWO_PI


def azimuth_to_angle(rad: float) -> np.float64:
    """Convert an azimuth in radians to a math angle in radians.

    Azimuth is measured clockwise from North; the math angle is measured
    counter-clockwise from East. The conversion is ``angle = π/2 - az``
    (mod 2π).

    Parameters
    ----------
    rad : float
        Azimuth in radians. Need not be pre-normalised; values outside
        ``[0, 2π)`` are accepted and the result is normalised.

    Returns
    -------
    numpy.float64
        Math angle in radians, normalised to ``[0, 2π)``.
    """
    return normalize_to_2pi(_HALF_PI - np.float64(rad))


def angle_to_azimuth(rad: float) -> np.float64:
    """Convert a math angle in radians to an azimuth in radians.

    Inverse of :func:`azimuth_to_angle`; the formula
    ``az = π/2 - angle`` (mod 2π) is its own inverse modulo ``2π``.

    Parameters
    ----------
    rad : float
        Math angle in radians. Need not be pre-normalised.

    Returns
    -------
    numpy.float64
        Azimuth in radians, normalised to ``[0, 2π)``.
    """
    return normalize_to_2pi(_HALF_PI - np.float64(rad))


def to_radians(value: float, units: DirectionUnits | str) -> np.float64:
    """Convert a user-facing direction value to radians.

    The MVP spec stores ``direction`` internally in radians but allows
    the UI to capture it in either radians or degrees. This helper
    normalises that input. It accepts either a :class:`DirectionUnits`
    enum member (in-memory form) or a string (case-insensitive
    deserialization form), matching the spec's "deserialisation MUST be
    case-insensitive" rule.

    Parameters
    ----------
    value : float
        Direction in the requested units.
    units : DirectionUnits or str
        ``DirectionUnits.RADIANS``/``DirectionUnits.DEGREES`` or the
        string ``"radians"``/``"degrees"`` (case-insensitive).

    Returns
    -------
    numpy.float64
        ``value`` expressed in radians.

    Raises
    ------
    ValueError
        If ``units`` is a string that does not name a known unit.
    """
    resolved = _resolve_units(units)
    val = np.float64(value)
    if resolved is DirectionUnits.RADIANS:
        return val
    return np.deg2rad(val)


def to_degrees(rad: float) -> np.float64:
    """Convert radians to degrees as ``float64``.

    Parameters
    ----------
    rad : float
        Angle in radians.

    Returns
    -------
    numpy.float64
        Angle in degrees.
    """
    return np.rad2deg(np.float64(rad))


def _resolve_units(units: DirectionUnits | str) -> DirectionUnits:
    """Coerce a units identifier into the canonical enum member.

    Accepts either a :class:`DirectionUnits` instance (passed through)
    or a case-insensitive string matching one of the enum values
    (``"radians"`` / ``"degrees"``). Centralised here so call sites need
    not duplicate the case-folding logic.
    """
    if isinstance(units, DirectionUnits):
        return units
    if isinstance(units, str):
        normalised = units.strip().lower()
        for member in DirectionUnits:
            if member.value == normalised:
                return member
    raise ValueError(
        f"Unknown direction units {units!r}; expected one of "
        f"{[m.value for m in DirectionUnits]} or a DirectionUnits member."
    )


__all__ = [
    "azimuth_to_angle",
    "angle_to_azimuth",
    "to_radians",
    "to_degrees",
    "normalize_to_2pi",
]
