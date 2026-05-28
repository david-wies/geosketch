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

"""Shared utilities for GeoSketch: tolerances, angle math, IDs, events.

Each helper here has zero geometry semantics, zero tkinter imports, and
zero matplotlib imports — they sit at the bottom of the layering rule
documented in ``docs/geo-sketch-design.md`` and may be imported freely
by every layer above.
"""

from geometry.utils.angles import (
    angle_to_azimuth,
    azimuth_to_angle,
    normalize_to_2pi,
    to_degrees,
    to_radians,
)
from geometry.utils.constants import EPS_ANGLE, EPS_AREA, EPS_DISTANCE, EPS_PARAM
from geometry.utils.events import (
    CANVAS_STALE,
    DEFINED_EVENTS,
    HISTORY_CHANGED,
    OBJECT_CREATED,
    OBJECT_DELETED,
    OBJECT_MODIFIED,
    PROJECT_LOADED,
    SELECTION_CHANGED,
    EventBus,
    EventHandler,
)
from geometry.utils.id_factory import IDFactory

__all__ = [
    # constants
    "EPS_ANGLE",
    "EPS_AREA",
    "EPS_DISTANCE",
    "EPS_PARAM",
    # angles
    "angle_to_azimuth",
    "azimuth_to_angle",
    "normalize_to_2pi",
    "to_degrees",
    "to_radians",
    # id factory
    "IDFactory",
    # events
    "CANVAS_STALE",
    "DEFINED_EVENTS",
    "EventBus",
    "EventHandler",
    "HISTORY_CHANGED",
    "OBJECT_CREATED",
    "OBJECT_DELETED",
    "OBJECT_MODIFIED",
    "PROJECT_LOADED",
    "SELECTION_CHANGED",
]
