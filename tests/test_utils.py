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

"""Tests for the geometry.utils package.

Covers the four modules required by issue #11:

* ``constants`` — the four EPS tolerance values match the spec.
* ``angles`` — radians/degrees and azimuth/angle round-trip cleanly,
  ``normalize_to_2pi`` handles negatives, and ``to_radians`` accepts
  both the enum and the case-insensitive string form.
* ``id_factory`` — :class:`IDFactory.next_id` zero-pads to three digits,
  per-prefix counters are independent, and :meth:`reseed` sets the
  counter above the maximum integer suffix in the input.
* ``events`` — the seven defined events are exposed as constants;
  :class:`EventBus` is synchronous, supports subscribe/unsubscribe,
  de-duplicates subscriptions, and tolerates handler-list mutation
  mid-fire.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from geometry.models.common import DirectionUnits
from geometry.utils import (
    CANVAS_STALE,
    DEFINED_EVENTS,
    EPS_ANGLE,
    EPS_AREA,
    EPS_DISTANCE,
    EPS_PARAM,
    HISTORY_CHANGED,
    OBJECT_CREATED,
    OBJECT_DELETED,
    OBJECT_MODIFIED,
    PROJECT_LOADED,
    SELECTION_CHANGED,
    EventBus,
    IDFactory,
    angle_to_azimuth,
    azimuth_to_angle,
    normalize_to_2pi,
    to_degrees,
    to_radians,
)

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------


def test_eps_constants_match_spec():
    # The MVP spec pins these literal values in spec/MVP.md
    # § "Numerical Tolerances"; the issue's acceptance criteria
    # repeat them. Hard-code them in the test so a silent drift
    # in constants.py shows up here.
    assert EPS_DISTANCE == 1e-6
    assert EPS_ANGLE == 1e-9
    assert EPS_AREA == 1e-9
    assert EPS_PARAM == 1e-9


# ---------------------------------------------------------------------------
# angles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [0.0, 0.1, 1.0, math.pi / 4, math.pi / 2, math.pi, 1.5 * math.pi, 2 * math.pi - 1e-3],
)
def test_azimuth_angle_roundtrip(value: float):
    """``angle_to_azimuth(azimuth_to_angle(x)) == x`` for ``x`` in [0, 2π)."""
    roundtripped = angle_to_azimuth(azimuth_to_angle(value))
    assert isinstance(roundtripped, np.float64)
    assert math.isclose(float(roundtripped), value, abs_tol=1e-12)


def test_azimuth_to_angle_known_values():
    # Azimuth 0 (due North) corresponds to math angle π/2 (positive Y axis).
    assert math.isclose(float(azimuth_to_angle(0.0)), math.pi / 2, abs_tol=1e-12)
    # Azimuth π/2 (due East) corresponds to math angle 0.
    assert math.isclose(float(azimuth_to_angle(math.pi / 2)), 0.0, abs_tol=1e-12)
    # Azimuth π (due South) corresponds to math angle 3π/2 (negative Y, mod 2π).
    assert math.isclose(float(azimuth_to_angle(math.pi)), 1.5 * math.pi, abs_tol=1e-12)


def test_angle_to_azimuth_known_values():
    assert math.isclose(float(angle_to_azimuth(0.0)), math.pi / 2, abs_tol=1e-12)
    assert math.isclose(float(angle_to_azimuth(math.pi / 2)), 0.0, abs_tol=1e-12)


def test_azimuth_to_angle_normalises_negative_input():
    # -π/2 reduced into [0, 2π) is 3π/2; converted to angle that's 0 - 3π/2 + π/2 = -π
    # then mod 2π = π. Spot-check the result lies in [0, 2π) and is finite.
    out = azimuth_to_angle(-math.pi / 2)
    assert 0.0 <= float(out) < 2 * math.pi
    assert math.isclose(float(out), math.pi, abs_tol=1e-12)


def test_to_radians_radians_passthrough():
    assert to_radians(1.234, DirectionUnits.RADIANS) == np.float64(1.234)


def test_to_radians_degrees_conversion():
    assert math.isclose(float(to_radians(180.0, DirectionUnits.DEGREES)), math.pi, abs_tol=1e-12)
    assert math.isclose(float(to_radians(90.0, DirectionUnits.DEGREES)), math.pi / 2, abs_tol=1e-12)


def test_to_radians_accepts_lowercase_string():
    assert math.isclose(float(to_radians(180.0, "degrees")), math.pi, abs_tol=1e-12)
    assert to_radians(1.0, "radians") == np.float64(1.0)


def test_to_radians_string_is_case_insensitive():
    # The spec mandates case-insensitive deserialisation of enum strings.
    assert math.isclose(float(to_radians(180.0, "DEGREES")), math.pi, abs_tol=1e-12)
    assert math.isclose(float(to_radians(180.0, "Degrees")), math.pi, abs_tol=1e-12)


def test_to_radians_rejects_unknown_units():
    with pytest.raises(ValueError, match="Unknown direction units"):
        to_radians(1.0, "grads")
    with pytest.raises(ValueError, match="Unknown direction units"):
        to_radians(1.0, 42)  # type: ignore[arg-type]


def test_to_degrees_returns_float64():
    out = to_degrees(math.pi)
    assert isinstance(out, np.float64)
    assert math.isclose(float(out), 180.0, abs_tol=1e-12)


def test_to_radians_to_degrees_roundtrip():
    for deg in (0.0, 1.0, 45.0, 90.0, 180.0, 270.0, 359.999):
        rad = to_radians(deg, DirectionUnits.DEGREES)
        back = to_degrees(rad)
        assert math.isclose(float(back), deg, abs_tol=1e-9)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.0, 0.0),
        (math.pi, math.pi),
        (2 * math.pi, 0.0),
        (-math.pi / 2, 1.5 * math.pi),
        (3 * math.pi, math.pi),  # 3π mod 2π = π
        (-3 * math.pi, math.pi),
    ],
)
def test_normalize_to_2pi(value: float, expected: float):
    out = normalize_to_2pi(value)
    assert isinstance(out, np.float64)
    assert math.isclose(float(out), expected, abs_tol=1e-12)
    assert 0.0 <= float(out) < 2 * math.pi or math.isclose(float(out), 0.0, abs_tol=1e-12)


def test_all_angle_helpers_return_float64():
    # Reference precision is NumPy float64 per spec/MVP.md.
    assert isinstance(azimuth_to_angle(1.0), np.float64)
    assert isinstance(angle_to_azimuth(1.0), np.float64)
    assert isinstance(to_radians(1.0, "radians"), np.float64)
    assert isinstance(to_degrees(1.0), np.float64)
    assert isinstance(normalize_to_2pi(1.0), np.float64)


# ---------------------------------------------------------------------------
# id_factory
# ---------------------------------------------------------------------------


def test_next_id_zero_pads_three_digits():
    factory = IDFactory()
    assert factory.next_id("pt") == "pt_001"
    assert factory.next_id("pt") == "pt_002"
    assert factory.next_id("ln") == "ln_001"


def test_next_id_counters_are_per_prefix():
    factory = IDFactory()
    assert factory.next_id("pt") == "pt_001"
    assert factory.next_id("ln") == "ln_001"
    assert factory.next_id("pt") == "pt_002"
    assert factory.next_id("ln") == "ln_002"


def test_next_id_grows_beyond_three_digits():
    factory = IDFactory()
    factory.reseed(["pt_999"])
    assert factory.next_id("pt") == "pt_1000"
    assert factory.next_id("pt") == "pt_1001"


def test_next_id_rejects_invalid_prefix():
    factory = IDFactory()
    for bad in ("", "PT", "pt1", "p_t", "pt ", " pt", "pté"):
        with pytest.raises(ValueError, match="prefix"):
            factory.next_id(bad)


def test_reseed_sets_counter_above_max():
    """After reseed, next_id returns max(existing) + 1 per prefix."""
    factory = IDFactory()
    factory.reseed(["pt_001", "pt_005", "pt_003", "ln_002"])
    assert factory.next_id("pt") == "pt_006"
    assert factory.next_id("ln") == "ln_003"


def test_reseed_ignores_unmentioned_prefix():
    """Reseed does not touch prefixes absent from the input."""
    factory = IDFactory()
    factory.next_id("pt")  # advance pt to 1
    factory.next_id("pt")  # advance pt to 2
    factory.reseed(["ln_007"])
    # ln got reseeded; pt is untouched.
    assert factory.next_id("ln") == "ln_008"
    assert factory.next_id("pt") == "pt_003"


def test_reseed_is_monotonic():
    """Reseeding with a lower max does not lower the existing counter."""
    factory = IDFactory()
    factory.reseed(["pt_010"])
    factory.reseed(["pt_005"])  # lower max — should be ignored
    assert factory.next_id("pt") == "pt_011"


def test_reseed_handles_all_seven_geosketch_prefixes():
    """End-to-end check: every spec-defined ID prefix is parsed correctly."""
    factory = IDFactory()
    factory.reseed(
        [
            "pt_004",  # Point
            "ln_002",  # Line
            "pg_007",  # Polygon
            "ry_001",  # Ray
            "vc_003",  # Vector
            "ci_005",  # Circle
            "tg_009",  # Tangent
        ]
    )
    assert factory.next_id("pt") == "pt_005"
    assert factory.next_id("ln") == "ln_003"
    assert factory.next_id("pg") == "pg_008"
    assert factory.next_id("ry") == "ry_002"
    assert factory.next_id("vc") == "vc_004"
    assert factory.next_id("ci") == "ci_006"
    assert factory.next_id("tg") == "tg_010"


def test_reseed_empty_list_is_noop():
    factory = IDFactory()
    factory.reseed([])
    assert factory.next_id("pt") == "pt_001"


def test_reseed_rejects_malformed_ids():
    factory = IDFactory()
    for bad in ("pt001", "PT_001", "pt_", "pt_-1", "pt_001a", "_001", "pt 001", ""):
        with pytest.raises(ValueError):
            factory.reseed([bad])


def test_reseed_rejects_zero_suffix():
    """Suffix must be a positive integer (>= 1) per MVP § ID Allocation."""
    factory = IDFactory()
    with pytest.raises(ValueError):
        factory.reseed(["pt_000"])


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------


def test_defined_event_constants_match_design_doc():
    """The seven event names in docs/geo-sketch-design.md are exposed."""
    assert OBJECT_CREATED == "object_created"
    assert OBJECT_MODIFIED == "object_modified"
    assert OBJECT_DELETED == "object_deleted"
    assert SELECTION_CHANGED == "selection_changed"
    assert CANVAS_STALE == "canvas_stale"
    assert PROJECT_LOADED == "project_loaded"
    assert HISTORY_CHANGED == "history_changed"


def test_defined_events_frozenset_complete():
    assert DEFINED_EVENTS == frozenset(
        {
            "object_created",
            "object_modified",
            "object_deleted",
            "selection_changed",
            "canvas_stale",
            "project_loaded",
            "history_changed",
        }
    )


def test_subscribe_and_fire_invokes_handler():
    bus = EventBus()
    received: list[str] = []

    def handler(obj_id: str) -> None:
        received.append(obj_id)

    bus.subscribe(OBJECT_CREATED, handler)
    bus.fire(OBJECT_CREATED, obj_id="pt_001")
    assert received == ["pt_001"]


def test_fire_with_no_subscribers_is_noop():
    bus = EventBus()
    # Must not raise even when nobody subscribes.
    bus.fire(CANVAS_STALE)


def test_fire_with_no_payload_passes_no_kwargs():
    bus = EventBus()
    called: list[bool] = []

    def handler() -> None:
        called.append(True)

    bus.subscribe(CANVAS_STALE, handler)
    bus.fire(CANVAS_STALE)
    assert called == [True]


def test_fire_passes_multiple_payload_fields():
    bus = EventBus()
    received: list[tuple[bool, bool]] = []

    def handler(can_undo: bool, can_redo: bool) -> None:
        received.append((can_undo, can_redo))

    bus.subscribe(HISTORY_CHANGED, handler)
    bus.fire(HISTORY_CHANGED, can_undo=True, can_redo=False)
    assert received == [(True, False)]


def test_subscribe_dedupes_duplicate_handler():
    """The same (event, handler) pair registers exactly once."""
    bus = EventBus()
    received: list[str] = []

    def handler(obj_id: str) -> None:
        received.append(obj_id)

    bus.subscribe(OBJECT_CREATED, handler)
    bus.subscribe(OBJECT_CREATED, handler)  # duplicate
    bus.fire(OBJECT_CREATED, obj_id="pt_001")
    assert received == ["pt_001"]


def test_unsubscribe_removes_handler():
    bus = EventBus()
    received: list[str] = []

    def handler(obj_id: str) -> None:
        received.append(obj_id)

    bus.subscribe(OBJECT_CREATED, handler)
    bus.unsubscribe(OBJECT_CREATED, handler)
    bus.fire(OBJECT_CREATED, obj_id="pt_001")
    assert not received


def test_unsubscribe_unknown_handler_is_noop():
    bus = EventBus()

    def handler() -> None:
        pass

    # Neither subscribed event nor known handler → must not raise.
    bus.unsubscribe(CANVAS_STALE, handler)


def test_subscribers_invoked_in_subscription_order():
    bus = EventBus()
    order: list[int] = []

    bus.subscribe(CANVAS_STALE, lambda: order.append(1))
    bus.subscribe(CANVAS_STALE, lambda: order.append(2))
    bus.subscribe(CANVAS_STALE, lambda: order.append(3))
    bus.fire(CANVAS_STALE)
    assert order == [1, 2, 3]


def test_handler_exception_propagates():
    bus = EventBus()

    def bad_handler() -> None:
        raise RuntimeError("boom")

    bus.subscribe(CANVAS_STALE, bad_handler)
    with pytest.raises(RuntimeError, match="boom"):
        bus.fire(CANVAS_STALE)


def test_handler_mutating_subscribers_during_fire_does_not_break_iteration():
    """A handler that unsubscribes itself mid-fire must not raise."""
    bus = EventBus()
    received: list[str] = []

    def handler_a() -> None:
        received.append("a")
        bus.unsubscribe(CANVAS_STALE, handler_a)

    def handler_b() -> None:
        received.append("b")

    bus.subscribe(CANVAS_STALE, handler_a)
    bus.subscribe(CANVAS_STALE, handler_b)
    bus.fire(CANVAS_STALE)
    assert received == ["a", "b"]

    received.clear()
    bus.fire(CANVAS_STALE)
    # handler_a is gone; only handler_b runs on the next fire.
    assert received == ["b"]


def test_synchronous_dispatch():
    """fire() returns only after every handler has run."""
    bus = EventBus()
    log: list[str] = []

    def slow_handler() -> None:
        log.append("during")

    bus.subscribe(CANVAS_STALE, slow_handler)
    log.append("before")
    bus.fire(CANVAS_STALE)
    log.append("after")
    assert log == ["before", "during", "after"]
