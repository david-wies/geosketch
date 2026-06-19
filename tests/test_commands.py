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

"""Unit tests for :mod:`geometry.services.commands`.

Three concerns are exercised here:

* :class:`CommandHistory` mechanics — undo/redo round-trips, the bounded
  ring-buffer overflow, redo-stack invalidation on a fresh push, the
  :data:`HISTORY_CHANGED` event payload, and clearing (explicit and on
  :data:`PROJECT_LOADED`);
* each of the six command classes — do/undo/redo against a live object store
  and dependency graph, asserting the store and graph return to their
  pre-command state on undo and re-reach the post-command state on redo; and
* the point-move recompute rules — that a dependent Line's
  ``direction``/``elevation``, an endpoint Vector's ``length``, and a Polygon's
  cached ``is_convex`` actually change on the move and are restored on undo.

The model builders below intentionally use small explicit factory functions
(one per type that a test needs) rather than the spread-dict style, so each test
reads as a self-contained scene.
"""

import math

import pytest

from geometry.models import (
    Circle,
    DirectionMode,
    DirectionUnits,
    Line,
    Point,
    Polygon,
    Ray,
    Tangent,
    Vector,
)
from geometry.services.commands import (
    MAX_HISTORY,
    BulkImportCommand,
    CascadeDeleteCommand,
    Command,
    CommandHistory,
    CreateObjectCommand,
    ModifyObjectCommand,
    ModifyPolygonVerticesCommand,
    MovePointCommand,
)
from geometry.services.dep_graph import DependencyGraph
from geometry.utils.events import (
    HISTORY_CHANGED,
    OBJECT_CREATED,
    OBJECT_DELETED,
    OBJECT_MODIFIED,
    PROJECT_LOADED,
    EventBus,
)

# ---------------------------------------------------------------------------
# Model builders. Each factory fills the display envelope and direction
# metadata with valid-but-arbitrary values; only the geometry-relevant
# arguments are exposed as parameters.
# ---------------------------------------------------------------------------

_LINE_HEX = "#101010"
_FILL_HEX = "#f0f0f0"


def make_point(pid: str, easting: float, northing: float, altitude: float = 0.0) -> Point:
    """Build a Point with the given coordinates and an arbitrary marker colour."""
    return Point(
        id=pid,
        name=pid,
        alpha=1.0,
        visibility=True,
        easting=easting,
        northing=northing,
        altitude=altitude,
        color="#abcdef",
    )


def make_line(
    pid: str,
    point_a_id: str,
    point_b_id: str,
    mode: DirectionMode = DirectionMode.AZIMUTH,
) -> Line:
    """Build a Line between two point IDs with a placeholder direction/elevation."""
    return Line(
        id=pid,
        name=pid,
        alpha=1.0,
        visibility=True,
        direction=0.0,
        elevation=0.0,
        direction_mode=mode,
        direction_units=DirectionUnits.RADIANS,
        point_a_id=point_a_id,
        point_b_id=point_b_id,
        line_color=_LINE_HEX,
        fill_color=_FILL_HEX,
    )


def make_ray(pid: str, origin_id: str) -> Ray:
    """Build a Ray from an origin point with a fixed intrinsic direction."""
    return Ray(
        id=pid,
        name=pid,
        alpha=1.0,
        visibility=True,
        direction=1.0,
        elevation=0.25,
        direction_mode=DirectionMode.AZIMUTH,
        direction_units=DirectionUnits.RADIANS,
        origin_id=origin_id,
        line_color=_LINE_HEX,
        fill_color=_FILL_HEX,
    )


def make_vector(pid: str, origin_id: str, length: float, endpoint_id: str | None) -> Vector:
    """Build a Vector, either Length+Direction (no endpoint) or Origin+Endpoint."""
    return Vector(
        id=pid,
        name=pid,
        alpha=1.0,
        visibility=True,
        direction=0.0,
        elevation=0.0,
        direction_mode=DirectionMode.AZIMUTH,
        direction_units=DirectionUnits.RADIANS,
        origin_id=origin_id,
        length=length,
        endpoint_id=endpoint_id,
        line_color=_LINE_HEX,
        fill_color=_FILL_HEX,
    )


def make_circle(pid: str, center_id: str, radius: float = 5.0) -> Circle:
    """Build a Circle around a centre point."""
    return Circle(
        id=pid,
        name=pid,
        alpha=1.0,
        visibility=True,
        center_id=center_id,
        radius=radius,
        line_color=_LINE_HEX,
        fill_color=_FILL_HEX,
    )


def make_tangent(pid: str, shape_id: str, point_id: str) -> Tangent:
    """Build a Circle Tangent (elevation 0.0) at a surface point."""
    return Tangent(
        id=pid,
        name=pid,
        alpha=1.0,
        visibility=True,
        direction=0.0,
        elevation=0.0,
        direction_mode=DirectionMode.AZIMUTH,
        direction_units=DirectionUnits.RADIANS,
        shape_id=shape_id,
        shape_type="circle",
        point_id=point_id,
        line_color=_LINE_HEX,
        fill_color=_FILL_HEX,
    )


def make_polygon(pid: str, point_ids: tuple[str, ...], is_convex: bool = True) -> Polygon:
    """Build a Polygon over the given vertex IDs."""
    return Polygon(
        id=pid,
        name=pid,
        alpha=1.0,
        visibility=True,
        point_ids=point_ids,
        is_convex=is_convex,
        line_color=_LINE_HEX,
        fill_color=_FILL_HEX,
    )


class _HistoryRecorder:
    """Records every :data:`HISTORY_CHANGED` payload for assertions."""

    def __init__(self) -> None:
        self.events: list[tuple[bool, bool]] = []

    def __call__(self, *, can_undo: bool, can_redo: bool) -> None:
        self.events.append((can_undo, can_redo))


class _EventCounter:
    """Counts fired events by name with their payloads for assertions."""

    def __init__(self) -> None:
        self.created: list[str] = []
        self.deleted: list[list[str]] = []
        self.modified: list[str] = []

    def on_created(self, *, obj_id: str) -> None:
        self.created.append(obj_id)

    def on_deleted(self, *, obj_ids: list[str]) -> None:
        self.deleted.append(obj_ids)

    def on_modified(self, *, obj_id: str) -> None:
        self.modified.append(obj_id)

    def subscribe_all(self, bus: EventBus) -> None:
        bus.subscribe(OBJECT_CREATED, self.on_created)
        bus.subscribe(OBJECT_DELETED, self.on_deleted)
        bus.subscribe(OBJECT_MODIFIED, self.on_modified)


class _NoOpCommand:
    """Minimal :class:`Command` for history-mechanics tests.

    Tracks how many times it was applied and reversed so ordering assertions
    can verify the buffer replays commands in the right sequence.
    """

    def __init__(self, label: str, log: list[str]) -> None:
        self.description = label
        self._log = log

    def do(self) -> None:
        self._log.append(f"do:{self.description}")

    def undo(self) -> None:
        self._log.append(f"undo:{self.description}")


# ---------------------------------------------------------------------------
# CommandHistory mechanics
# ---------------------------------------------------------------------------


def test_noop_command_satisfies_protocol():
    assert isinstance(_NoOpCommand("x", []), Command)


def test_push_applies_command_and_enables_undo():
    log: list[str] = []
    history = CommandHistory()
    history.push(_NoOpCommand("a", log))
    assert log == ["do:a"]
    assert history.can_undo
    assert not history.can_redo


def test_undo_then_redo_round_trip():
    log: list[str] = []
    history = CommandHistory()
    history.push(_NoOpCommand("a", log))
    history.undo()
    assert history.can_redo
    assert not history.can_undo
    history.redo()
    assert log == ["do:a", "undo:a", "do:a"]
    assert history.can_undo
    assert not history.can_redo


def test_undo_on_empty_history_returns_none():
    history = CommandHistory()
    assert history.undo() is None


def test_redo_on_empty_stack_returns_none():
    history = CommandHistory()
    assert history.redo() is None


def test_new_push_discards_redo_stack():
    log: list[str] = []
    history = CommandHistory()
    history.push(_NoOpCommand("a", log))
    history.undo()
    assert history.can_redo
    history.push(_NoOpCommand("b", log))
    # The redo branch must be unreachable after a fresh action.
    assert not history.can_redo


def test_ring_buffer_drops_oldest_at_overflow():
    log: list[str] = []
    history = CommandHistory()
    # Push one more than the cap; the first command must be evicted.
    for i in range(MAX_HISTORY + 1):
        history.push(_NoOpCommand(f"c{i}", log))
    # Undo every retained command: there must be exactly MAX_HISTORY of them,
    # and they must replay newest-first down to c1 (c0 was evicted).
    undone = []
    while history.can_undo:
        cmd = history.undo()
        undone.append(cmd.description)
    assert len(undone) == MAX_HISTORY
    assert undone[0] == f"c{MAX_HISTORY}"
    assert undone[-1] == "c1"
    assert "c0" not in undone


def test_history_changed_fires_with_correct_flags():
    bus = EventBus()
    recorder = _HistoryRecorder()
    bus.subscribe(HISTORY_CHANGED, recorder)
    history = CommandHistory(bus)
    log: list[str] = []
    history.push(_NoOpCommand("a", log))  # (can_undo=True, can_redo=False)
    history.undo()  # (False, True)
    history.redo()  # (True, False)
    assert recorder.events == [(True, False), (False, True), (True, False)]


def test_clear_empties_both_stacks_and_fires():
    bus = EventBus()
    recorder = _HistoryRecorder()
    history = CommandHistory(bus)
    log: list[str] = []
    history.push(_NoOpCommand("a", log))
    history.undo()
    bus.subscribe(HISTORY_CHANGED, recorder)
    history.clear()
    assert not history.can_undo
    assert not history.can_redo
    assert recorder.events == [(False, False)]


def test_project_loaded_clears_history():
    bus = EventBus()
    history = CommandHistory(bus)
    log: list[str] = []
    history.push(_NoOpCommand("a", log))
    assert history.can_undo
    bus.fire(PROJECT_LOADED)
    assert not history.can_undo
    assert not history.can_redo


# ---------------------------------------------------------------------------
# CreateObjectCommand
# ---------------------------------------------------------------------------


def test_create_object_round_trip():
    objects: dict = {}
    graph = DependencyGraph()
    bus = EventBus()
    counter = _EventCounter()
    counter.subscribe_all(bus)
    point = make_point("pt_001", 0.0, 0.0)
    history = CommandHistory(bus)

    history.push(CreateObjectCommand(objects, graph, bus, point))
    assert objects == {"pt_001": point}
    assert graph.is_registered("pt_001")
    assert counter.created == ["pt_001"]

    history.undo()
    assert objects == {}
    assert not graph.is_registered("pt_001")
    assert counter.deleted == [["pt_001"]]

    history.redo()
    assert objects == {"pt_001": point}
    assert graph.is_registered("pt_001")


def test_create_object_description():
    objects: dict = {}
    cmd = CreateObjectCommand(
        objects, DependencyGraph(), EventBus(), make_point("pt_001", 1.0, 2.0)
    )
    assert cmd.description == "Create point 'pt_001'"


def test_create_line_registers_edges_to_both_points():
    objects: dict = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "pt_002": make_point("pt_002", 10.0, 0.0),
    }
    graph = DependencyGraph()
    graph.add(objects["pt_001"])
    graph.add(objects["pt_002"])
    bus = EventBus()
    line = make_line("ln_001", "pt_001", "pt_002")

    cmd = CreateObjectCommand(objects, graph, bus, line)
    cmd.do()
    assert graph.dependents_of("pt_001") == {"ln_001"}
    assert graph.dependents_of("pt_002") == {"ln_001"}
    cmd.undo()
    assert graph.dependents_of("pt_001") == set()
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


# ---------------------------------------------------------------------------
# CascadeDeleteCommand
# ---------------------------------------------------------------------------


def _point_line_polygon_scene() -> tuple[dict, DependencyGraph]:
    """Build pt_001/pt_002/pt_003, a line on the first two, a polygon on all three."""
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "pt_002": make_point("pt_002", 10.0, 0.0),
        "pt_003": make_point("pt_003", 0.0, 10.0),
        "ln_001": make_line("ln_001", "pt_001", "pt_002"),
        "pg_001": make_polygon("pg_001", ("pt_001", "pt_002", "pt_003")),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    return objects, graph


def test_cascade_delete_removes_full_closure_and_restores():
    objects, graph = _point_line_polygon_scene()
    bus = EventBus()
    counter = _EventCounter()
    counter.subscribe_all(bus)
    history = CommandHistory(bus)

    history.push(CascadeDeleteCommand(objects, graph, bus, "pt_001"))
    # pt_001 feeds both the line and the polygon, so all three go.
    assert "pt_001" not in objects
    assert "ln_001" not in objects
    assert "pg_001" not in objects
    assert not graph.is_registered("pt_001")
    assert not graph.is_registered("ln_001")
    assert not graph.is_registered("pg_001")
    # Unaffected points survive.
    assert "pt_002" in objects
    assert "pt_003" in objects
    assert len(counter.deleted) == 1
    assert set(counter.deleted[0]) == {"pt_001", "ln_001", "pg_001"}

    history.undo()
    assert set(objects) == {"pt_001", "pt_002", "pt_003", "ln_001", "pg_001"}
    assert graph.dependents_of("pt_001") == {"ln_001", "pg_001"}
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


def test_cascade_delete_redo_recomputes_same_closure():
    objects, graph = _point_line_polygon_scene()
    bus = EventBus()
    history = CommandHistory(bus)
    cmd = CascadeDeleteCommand(objects, graph, bus, "pt_001")
    history.push(cmd)
    history.undo()
    history.redo()
    assert "pt_001" not in objects
    assert "ln_001" not in objects
    assert "pg_001" not in objects
    assert "pt_002" in objects


def test_cascade_delete_leaf_removes_only_itself():
    objects, graph = _point_line_polygon_scene()
    bus = EventBus()
    cmd = CascadeDeleteCommand(objects, graph, bus, "ln_001")
    cmd.do()
    assert "ln_001" not in objects
    assert "pt_001" in objects  # the line's endpoints are untouched
    assert "pg_001" in objects
    cmd.undo()
    assert "ln_001" in objects


def test_cascade_delete_description_captured_before_do():
    objects, graph = _point_line_polygon_scene()
    cmd = CascadeDeleteCommand(objects, graph, EventBus(), "pg_001")
    cmd.do()
    # Even though pg_001 is gone from the store, the label survives.
    assert cmd.description == "Delete polygon 'pg_001'"


# ---------------------------------------------------------------------------
# ModifyObjectCommand
# ---------------------------------------------------------------------------


def test_modify_object_round_trip_does_not_touch_graph():
    objects = {"pt_001": make_point("pt_001", 0.0, 0.0)}
    graph = DependencyGraph()
    graph.add(objects["pt_001"])
    bus = EventBus()
    counter = _EventCounter()
    counter.subscribe_all(bus)
    history = CommandHistory(bus)

    history.push(
        ModifyObjectCommand(objects, graph, bus, "pt_001", {"name": "renamed", "alpha": 0.5})
    )
    assert objects["pt_001"].name == "renamed"
    assert objects["pt_001"].alpha == 0.5
    assert counter.modified == ["pt_001"]
    # Graph membership is unchanged by an envelope edit.
    assert graph.is_registered("pt_001")

    history.undo()
    assert objects["pt_001"].name == "pt_001"
    assert objects["pt_001"].alpha == 1.0

    history.redo()
    assert objects["pt_001"].name == "renamed"


def test_modify_object_leaves_original_instance_untouched():
    original = make_point("pt_001", 0.0, 0.0)
    objects = {"pt_001": original}
    cmd = ModifyObjectCommand(objects, DependencyGraph(), EventBus(), "pt_001", {"name": "x"})
    cmd.do()
    # The command swaps in a deep copy; the caller's original is not mutated.
    assert original.name == "pt_001"
    assert objects["pt_001"] is not original


# ---------------------------------------------------------------------------
# MovePointCommand
# ---------------------------------------------------------------------------


def test_move_point_updates_coordinates_round_trip():
    objects = {"pt_001": make_point("pt_001", 1.0, 2.0, 3.0)}
    graph = DependencyGraph()
    graph.add(objects["pt_001"])
    bus = EventBus()
    history = CommandHistory(bus)

    history.push(
        MovePointCommand(objects, graph, bus, "pt_001", easting=5.0, northing=6.0, altitude=7.0)
    )
    moved = objects["pt_001"]
    assert (moved.easting, moved.northing, moved.altitude) == (5.0, 6.0, 7.0)

    history.undo()
    restored = objects["pt_001"]
    assert (restored.easting, restored.northing, restored.altitude) == (1.0, 2.0, 3.0)

    history.redo()
    assert objects["pt_001"].easting == 5.0


def test_move_point_without_altitude_preserves_altitude():
    objects = {"pt_001": make_point("pt_001", 0.0, 0.0, 9.0)}
    graph = DependencyGraph()
    graph.add(objects["pt_001"])
    cmd = MovePointCommand(objects, graph, EventBus(), "pt_001", easting=1.0, northing=1.0)
    cmd.do()
    assert objects["pt_001"].altitude == 9.0


def test_move_point_recomputes_dependent_line_direction_and_elevation():
    # Line pt_001 -> pt_002 starts pointing due East (azimuth π/2), flat.
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0, 0.0),
        "pt_002": make_point("pt_002", 10.0, 0.0, 0.0),
        "ln_001": make_line("ln_001", "pt_001", "pt_002"),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    bus = EventBus()
    history = CommandHistory(bus)

    before_dir = objects["ln_001"].direction  # placeholder 0.0 from the builder
    before_el = objects["ln_001"].elevation

    # Move pt_002 due East and up: azimuth becomes π/2, elevation positive.
    history.push(
        MovePointCommand(objects, graph, bus, "pt_002", easting=10.0, northing=0.0, altitude=10.0)
    )
    line = objects["ln_001"]
    assert line.direction == pytest.approx(math.pi / 2)  # azimuth due East
    assert line.elevation == pytest.approx(math.atan2(10.0, 10.0))
    assert line.direction != before_dir
    assert line.elevation != before_el

    history.undo()
    assert objects["ln_001"].direction == pytest.approx(before_dir)
    assert objects["ln_001"].elevation == pytest.approx(before_el)


def test_move_point_recomputes_line_direction_in_angle_mode():
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "pt_002": make_point("pt_002", 10.0, 0.0),
        "ln_001": make_line("ln_001", "pt_001", "pt_002", mode=DirectionMode.ANGLE),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    cmd = MovePointCommand(objects, graph, EventBus(), "pt_002", easting=0.0, northing=10.0)
    cmd.do()
    # Due North is azimuth 0 -> math angle π/2 (CCW from East).
    assert objects["ln_001"].direction == pytest.approx(math.pi / 2)


def test_move_point_recomputes_endpoint_vector_length():
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0, 0.0),
        "pt_002": make_point("pt_002", 3.0, 4.0, 0.0),
        "vc_001": make_vector("vc_001", "pt_001", length=5.0, endpoint_id="pt_002"),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    bus = EventBus()
    history = CommandHistory(bus)
    assert objects["vc_001"].length == pytest.approx(5.0)

    # Move endpoint so the 3-4-5 triangle becomes a pure 12-unit vertical climb.
    history.push(
        MovePointCommand(objects, graph, bus, "pt_002", easting=0.0, northing=0.0, altitude=12.0)
    )
    assert objects["vc_001"].length == pytest.approx(12.0)
    assert objects["vc_001"].elevation == pytest.approx(math.pi / 2)

    history.undo()
    assert objects["vc_001"].length == pytest.approx(5.0)


def test_move_point_does_not_recompute_length_direction_vector():
    # A Length+Direction vector (endpoint_id None) translates with its origin;
    # nothing point-derived is stored, so length stays put.
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "vc_001": make_vector("vc_001", "pt_001", length=7.5, endpoint_id=None),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    cmd = MovePointCommand(objects, graph, EventBus(), "pt_001", easting=99.0, northing=99.0)
    cmd.do()
    assert objects["vc_001"].length == pytest.approx(7.5)


def test_move_point_recomputes_tangent_direction():
    # Circle centred at pt_001; tangent at surface point pt_002 due East.
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "pt_002": make_point("pt_002", 5.0, 0.0),
        "ci_001": make_circle("ci_001", "pt_001"),
        "tg_001": make_tangent("tg_001", "ci_001", "pt_002"),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    bus = EventBus()
    history = CommandHistory(bus)
    before_dir = objects["tg_001"].direction

    # Move the surface point due North; the tangent azimuth rotates by 90°.
    history.push(MovePointCommand(objects, graph, bus, "pt_002", easting=0.0, northing=5.0))
    after_dir = objects["tg_001"].direction
    assert after_dir != before_dir
    # Circle tangents stay horizontal.
    assert objects["tg_001"].elevation == 0.0

    history.undo()
    assert objects["tg_001"].direction == pytest.approx(before_dir)


def test_move_point_recomputes_dependent_ray_is_noop():
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "ry_001": make_ray("ry_001", "pt_001"),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    before_dir = objects["ry_001"].direction
    before_el = objects["ry_001"].elevation
    cmd = MovePointCommand(objects, graph, EventBus(), "pt_001", easting=50.0, northing=50.0)
    cmd.do()
    # The ray's intrinsic direction/elevation are untouched by an origin move.
    assert objects["ry_001"].direction == before_dir
    assert objects["ry_001"].elevation == before_el


def test_move_point_flips_polygon_convexity_and_restores():
    # A convex square; moving one vertex inward makes it concave.
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "pt_002": make_point("pt_002", 10.0, 0.0),
        "pt_003": make_point("pt_003", 10.0, 10.0),
        "pt_004": make_point("pt_004", 0.0, 10.0),
        "pg_001": make_polygon("pg_001", ("pt_001", "pt_002", "pt_003", "pt_004")),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    bus = EventBus()
    history = CommandHistory(bus)
    assert objects["pg_001"].is_convex is True

    # Pull pt_003 into the interior, creating a reflex (concave) vertex.
    history.push(MovePointCommand(objects, graph, bus, "pt_003", easting=4.0, northing=4.0))
    assert objects["pg_001"].is_convex is False

    history.undo()
    assert objects["pg_001"].is_convex is True


def test_move_point_fires_modified_for_point_and_dependents():
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "pt_002": make_point("pt_002", 10.0, 0.0),
        "ln_001": make_line("ln_001", "pt_001", "pt_002"),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    bus = EventBus()
    counter = _EventCounter()
    counter.subscribe_all(bus)
    cmd = MovePointCommand(objects, graph, bus, "pt_001", easting=1.0, northing=1.0)
    cmd.do()
    assert set(counter.modified) == {"pt_001", "ln_001"}
    # The moved point fires before its dependents.
    assert counter.modified[0] == "pt_001"


# ---------------------------------------------------------------------------
# ModifyPolygonVerticesCommand
# ---------------------------------------------------------------------------


def test_modify_polygon_vertices_round_trip_updates_graph_and_convexity():
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "pt_002": make_point("pt_002", 10.0, 0.0),
        "pt_003": make_point("pt_003", 10.0, 10.0),
        "pt_004": make_point("pt_004", 0.0, 10.0),
        # Start as a degenerate-ish concave triangle subset flagged convex=False.
        "pg_001": make_polygon("pg_001", ("pt_001", "pt_002", "pt_003"), is_convex=False),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    bus = EventBus()
    counter = _EventCounter()
    counter.subscribe_all(bus)
    history = CommandHistory(bus)

    history.push(
        ModifyPolygonVerticesCommand(
            objects, graph, bus, "pg_001", ("pt_001", "pt_002", "pt_003", "pt_004")
        )
    )
    poly = objects["pg_001"]
    assert poly.point_ids == ("pt_001", "pt_002", "pt_003", "pt_004")
    assert poly.is_convex is True  # the full square is convex
    assert graph.dependents_of("pt_004") == {"pg_001"}  # new edge registered
    assert counter.modified == ["pg_001"]

    history.undo()
    restored = objects["pg_001"]
    assert restored.point_ids == ("pt_001", "pt_002", "pt_003")
    assert restored.is_convex is False
    assert graph.dependents_of("pt_004") == set()  # old edge set restored
    graph._test_only_assert_consistent()  # pylint: disable=protected-access

    history.redo()
    assert objects["pg_001"].point_ids == ("pt_001", "pt_002", "pt_003", "pt_004")
    assert graph.dependents_of("pt_004") == {"pg_001"}


# ---------------------------------------------------------------------------
# BulkImportCommand
# ---------------------------------------------------------------------------


def test_bulk_import_round_trip():
    objects: dict = {}
    graph = DependencyGraph()
    bus = EventBus()
    counter = _EventCounter()
    counter.subscribe_all(bus)
    history = CommandHistory(bus)
    points = [make_point(f"pt_{i:03d}", float(i), 0.0) for i in range(1, 4)]

    history.push(BulkImportCommand(objects, graph, bus, points))
    assert set(objects) == {"pt_001", "pt_002", "pt_003"}
    assert all(graph.is_registered(pid) for pid in objects)
    assert counter.created == ["pt_001", "pt_002", "pt_003"]

    history.undo()
    assert objects == {}
    # Undo reverses import order: last created is deleted first.
    assert counter.deleted == [["pt_003"], ["pt_002"], ["pt_001"]]

    history.redo()
    assert set(objects) == {"pt_001", "pt_002", "pt_003"}


def test_bulk_import_default_description():
    points = [make_point("pt_001", 0.0, 0.0), make_point("pt_002", 1.0, 0.0)]
    cmd = BulkImportCommand({}, DependencyGraph(), EventBus(), points)
    assert cmd.description == "Import 2 object(s)"


def test_bulk_import_custom_description():
    cmd = BulkImportCommand({}, DependencyGraph(), EventBus(), [], description="Load survey")
    assert cmd.description == "Load survey"
