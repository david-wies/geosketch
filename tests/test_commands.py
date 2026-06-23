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
  :data:`HISTORY_CHANGED` event payload, clearing (explicit and on
  :data:`PROJECT_LOADED`), and the peek-apply-then-move contract that keeps a
  command recoverable when its ``do``/``undo`` raises;
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
# The command suite exercises six command classes plus history mechanics, a
# ten-type parametrized create round-trip, and per-type recompute rules, so it
# legitimately exceeds pylint's default module-length cap; splitting it would
# scatter the shared builders/fault-injection fixtures across modules.
# pylint: disable=too-many-lines

import math

import pytest

from geometry.models import (
    Ball,
    Circle,
    Cylinder,
    DirectionMode,
    DirectionUnits,
    GeoObject,
    Line,
    Point,
    Polygon,
    Ray,
    Solid,
    Tangent,
    Vector,
)
from geometry.services.commands import (
    MAX_HISTORY,
    REFERENCE_FIELDS,
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


def _env(pid: str) -> dict:
    """Display-envelope kwargs (id/name/alpha/visibility) shared by every builder."""
    return {"id": pid, "name": pid, "alpha": 1.0, "visibility": True}


def _bearing(
    mode: DirectionMode = DirectionMode.AZIMUTH,
    direction: float = 0.0,
    elevation: float = 0.0,
) -> dict:
    """Direction-metadata kwargs for the four ElevatedObject subclasses."""
    return {
        "direction": direction,
        "elevation": elevation,
        "direction_mode": mode,
        "direction_units": DirectionUnits.RADIANS,
    }


def _colors() -> dict:
    """Line/fill colour kwargs for the nine non-Point types."""
    return {"line_color": _LINE_HEX, "fill_color": _FILL_HEX}


def make_point(pid: str, easting: float, northing: float, altitude: float = 0.0) -> Point:
    """Build a Point with the given coordinates and an arbitrary marker colour."""
    return Point(
        **_env(pid), easting=easting, northing=northing, altitude=altitude, color="#abcdef"
    )


def make_line(
    pid: str,
    point_a_id: str,
    point_b_id: str,
    mode: DirectionMode = DirectionMode.AZIMUTH,
) -> Line:
    """Build a Line between two point IDs with a placeholder direction/elevation."""
    return Line(
        **_env(pid),
        **_bearing(mode),
        point_a_id=point_a_id,
        point_b_id=point_b_id,
        **_colors(),
    )


def make_ray(pid: str, origin_id: str) -> Ray:
    """Build a Ray from an origin point with a fixed intrinsic direction."""
    return Ray(
        **_env(pid), **_bearing(direction=1.0, elevation=0.25), origin_id=origin_id, **_colors()
    )


def make_vector(pid: str, origin_id: str, length: float, endpoint_id: str | None) -> Vector:
    """Build a Vector, either Length+Direction (no endpoint) or Origin+Endpoint."""
    return Vector(
        **_env(pid),
        **_bearing(),
        origin_id=origin_id,
        length=length,
        endpoint_id=endpoint_id,
        **_colors(),
    )


def make_circle(pid: str, center_id: str, radius: float = 5.0) -> Circle:
    """Build a Circle around a centre point."""
    return Circle(**_env(pid), center_id=center_id, radius=radius, **_colors())


def make_tangent(pid: str, shape_id: str, point_id: str) -> Tangent:
    """Build a Circle Tangent (elevation 0.0) at a surface point."""
    return Tangent(
        **_env(pid),
        **_bearing(),
        shape_id=shape_id,
        shape_type="circle",
        point_id=point_id,
        **_colors(),
    )


def make_ball(pid: str, center_id: str, radius: float = 5.0) -> Ball:
    """Build a Ball around a centre point."""
    return Ball(**_env(pid), center_id=center_id, radius=radius, **_colors())


def make_ball_tangent(pid: str, shape_id: str, point_id: str, elevation: float) -> Tangent:
    """Build a Ball Tangent carrying a user-supplied (non-zero) elevation."""
    return Tangent(
        **_env(pid),
        **_bearing(elevation=elevation),
        shape_id=shape_id,
        shape_type="ball",
        point_id=point_id,
        **_colors(),
    )


def make_cylinder(pid: str, base_center_id: str) -> Cylinder:
    """Build a vertical Cylinder anchored at a base-centre point.

    The axis/direction kwargs are assembled in a local dict (rather than spelled
    out as consecutive call keywords) so this builder does not duplicate the
    constructor-call block in ``test_models``'s cylinder test.
    """
    axis = {"axis_mode": "vertical", "axis_azimuth": 0.0, "axis_elevation": math.pi / 2}
    bearing = {"direction_mode": DirectionMode.AZIMUTH, "direction_units": DirectionUnits.RADIANS}
    return Cylinder(
        **_env(pid),
        base_center_id=base_center_id,
        radius=5.0,
        height=10.0,
        **axis,
        **bearing,
        **_colors(),
    )


def make_solid(pid: str, layers: tuple[str, ...]) -> Solid:
    """Build a Solid over an ordered layer stack (polygons and/or one apex point)."""
    return Solid(**_env(pid), layers=layers, **_colors())


def make_polygon(pid: str, point_ids: tuple[str, ...], is_convex: bool = True) -> Polygon:
    """Build a Polygon over the given vertex IDs."""
    return Polygon(**_env(pid), point_ids=point_ids, is_convex=is_convex, **_colors())


class _HistoryRecorder:  # pylint: disable=too-few-public-methods
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


class _RaisingCommand:
    """A :class:`Command` whose :meth:`do`/:meth:`undo` can be armed to raise.

    Used to exercise the peek-apply-then-move contract of
    :meth:`CommandHistory.undo`/:meth:`CommandHistory.redo`: when the applied
    side raises, the command must stay on its originating stack and
    :data:`HISTORY_CHANGED` must not fire for the failed transition.
    """

    def __init__(self, label: str = "raiser") -> None:
        self.description = label
        self.raise_on_do = False
        self.raise_on_undo = False

    def do(self) -> None:
        if self.raise_on_do:
            raise RuntimeError("do failed on purpose")

    def undo(self) -> None:
        if self.raise_on_undo:
            raise RuntimeError("undo failed on purpose")


class _FailingUnregisterGraph(DependencyGraph):
    """A graph whose :meth:`unregister` raises once it reaches a chosen ID.

    Used to induce a mid-cascade failure in
    :meth:`CascadeDeleteCommand.do` and verify the rollback restores both the
    store and the graph exactly to their pre-``do`` state.
    """

    def __init__(self, fail_id: str) -> None:
        super().__init__()
        self._fail_id = fail_id

    def unregister(self, obj_id: str, *, strict: bool = False) -> None:
        if obj_id == self._fail_id:
            raise RuntimeError(f"induced unregister failure for {obj_id!r}")
        super().unregister(obj_id, strict=strict)


class _FaultInjectGraph(DependencyGraph):
    """A graph that can be armed to raise from :meth:`unregister` and :meth:`add`.

    ``unregister_fail_id`` raises a ``RuntimeError`` the first time that id is
    unregistered (the *primary* fault that triggers a rollback). ``add_fail_id``
    raises a ``RuntimeError`` the first time that id is (re-)added, simulating a
    *rollback step* that itself fails. Both fire at most once, so the rollback
    can still make progress on its remaining steps and the original exception is
    the one that must surface.

    Used to prove the rollback loops in :class:`CascadeDeleteCommand` are
    fault-tolerant: an exception thrown by one rollback step neither aborts the
    remaining steps nor replaces the original (primary) exception.
    """

    def __init__(self, *, unregister_fail_id: str | None = None, add_fail_id: str | None = None):
        super().__init__()
        self._unregister_fail_id = unregister_fail_id
        self._add_fail_id = add_fail_id
        self.add_attempts: list[str] = []

    def unregister(self, obj_id: str, *, strict: bool = False) -> None:
        if obj_id == self._unregister_fail_id:
            self._unregister_fail_id = None  # fire once
            raise RuntimeError(f"induced unregister failure for {obj_id!r}")
        super().unregister(obj_id, strict=strict)

    def add(self, obj) -> None:  # noqa: ANN001 - GeoObject, matches base signature
        self.add_attempts.append(obj.id)
        if obj.id == self._add_fail_id:
            self._add_fail_id = None  # fire once
            raise RuntimeError(f"induced add failure for {obj.id!r}")
        super().add(obj)


class _RaisingUndoCreate:
    """A wrapped-create stand-in whose :meth:`do`/:meth:`undo` can be armed to raise.

    Mirrors :class:`CreateObjectCommand`'s ``do``/``undo`` contract closely
    enough for :class:`BulkImportCommand` to drive it, while letting a test arm
    a specific call to raise. ``log`` records every ``do``/``undo`` so the test
    can assert which rollback steps actually ran.
    """

    def __init__(self, label: str, log: list[str]) -> None:
        self.description = f"Create {label}"
        self._label = label
        self._log = log
        self.raise_on_do = False
        self.raise_on_undo = False

    def do(self) -> None:
        self._log.append(f"do:{self._label}")
        if self.raise_on_do:
            raise RuntimeError(f"do failed for {self._label}")

    def undo(self) -> None:
        self._log.append(f"undo:{self._label}")
        if self.raise_on_undo:
            raise RuntimeError(f"undo failed for {self._label}")


# ---------------------------------------------------------------------------
# CommandHistory mechanics
# ---------------------------------------------------------------------------


def test_noop_command_satisfies_protocol():
    assert isinstance(_NoOpCommand("x", []), Command)


def test_push_applies_command_and_enables_undo():
    log: list[str] = []
    history = CommandHistory(EventBus())
    history.push(_NoOpCommand("a", log))
    assert log == ["do:a"]
    assert history.can_undo
    assert not history.can_redo


def test_undo_then_redo_round_trip():
    log: list[str] = []
    history = CommandHistory(EventBus())
    history.push(_NoOpCommand("a", log))
    history.undo()
    assert history.can_redo
    assert not history.can_undo
    history.redo()
    assert log == ["do:a", "undo:a", "do:a"]
    assert history.can_undo
    assert not history.can_redo


def test_undo_on_empty_history_returns_none():
    history = CommandHistory(EventBus())
    assert history.undo() is None


def test_redo_on_empty_stack_returns_none():
    history = CommandHistory(EventBus())
    assert history.redo() is None


def test_new_push_discards_redo_stack():
    log: list[str] = []
    history = CommandHistory(EventBus())
    history.push(_NoOpCommand("a", log))
    history.undo()
    assert history.can_redo
    history.push(_NoOpCommand("b", log))
    # The redo branch must be unreachable after a fresh action.
    assert not history.can_redo


def test_ring_buffer_drops_oldest_at_overflow():
    log: list[str] = []
    history = CommandHistory(EventBus())
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


def test_close_unsubscribes_from_project_loaded():
    # CommandHistory subscribes to PROJECT_LOADED in __init__, and the bus holds
    # subscribers by strong reference. close() must unsubscribe that handler so a
    # later PROJECT_LOADED no longer reaches (and clears) the closed history.
    bus = EventBus()
    history = CommandHistory(bus)
    log: list[str] = []
    history.push(_NoOpCommand("a", log))
    assert history.can_undo

    history.close()
    # After close the history detaches from the bus: firing PROJECT_LOADED must
    # not invoke the (now-unsubscribed) handler. close() itself cleared the
    # stacks, so push a fresh command to prove the firing is a true no-op.
    history.push(_NoOpCommand("b", log))
    bus.fire(PROJECT_LOADED)
    assert history.can_undo  # not cleared — the handler is gone


def test_close_is_idempotent():
    bus = EventBus()
    history = CommandHistory(bus)
    history.close()
    history.close()  # second call is a no-op (handler already absent)
    assert not history.can_undo


def test_project_loaded_clears_history():
    bus = EventBus()
    history = CommandHistory(bus)
    log: list[str] = []
    history.push(_NoOpCommand("a", log))
    assert history.can_undo
    bus.fire(PROJECT_LOADED)
    assert not history.can_undo
    assert not history.can_redo


def test_push_does_not_enter_history_when_do_raises():
    # push() calls cmd.do() first, so a command that raises mid-apply must never
    # be recorded: the buffers stay consistent with the (unchanged) store. After
    # a failed push the history must be exactly as empty as before — not undoable.
    bus = EventBus()
    recorder = _HistoryRecorder()
    bus.subscribe(HISTORY_CHANGED, recorder)
    history = CommandHistory(bus)
    cmd = _RaisingCommand()
    cmd.raise_on_do = True

    with pytest.raises(RuntimeError, match="do failed on purpose"):
        history.push(cmd)
    # The failed command never entered the undo buffer and no HISTORY_CHANGED
    # fired for the aborted push.
    assert not history.can_undo
    assert not history.can_redo
    assert not recorder.events


def test_redo_keeps_command_when_do_raises():
    # A failed redo (do() raises) must leave the command recoverable on the redo
    # stack and must NOT fire HISTORY_CHANGED for the aborted transition.
    bus = EventBus()
    recorder = _HistoryRecorder()
    history = CommandHistory(bus)
    cmd = _RaisingCommand()
    history.push(cmd)  # (True, False)
    history.undo()  # (False, True) — cmd now on the redo stack
    assert history.can_redo

    bus.subscribe(HISTORY_CHANGED, recorder)
    cmd.raise_on_do = True
    with pytest.raises(RuntimeError, match="do failed on purpose"):
        history.redo()
    # Command stays recoverable; no HISTORY_CHANGED for the failed transition.
    assert history.can_redo
    assert not history.can_undo
    assert not recorder.events

    # Once the fault clears, redo succeeds and the command moves across.
    cmd.raise_on_do = False
    history.redo()
    assert history.can_undo
    assert not history.can_redo


def test_undo_keeps_command_when_undo_raises():
    # The symmetric case: a failed undo must leave the command on the undo stack.
    bus = EventBus()
    recorder = _HistoryRecorder()
    history = CommandHistory(bus)
    cmd = _RaisingCommand()
    history.push(cmd)
    assert history.can_undo

    bus.subscribe(HISTORY_CHANGED, recorder)
    cmd.raise_on_undo = True
    with pytest.raises(RuntimeError, match="undo failed on purpose"):
        history.undo()
    assert history.can_undo
    assert not history.can_redo
    assert not recorder.events


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
    assert not objects
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


def test_create_object_do_rolls_back_store_when_graph_add_raises():
    # Test gap: a direct CreateObjectCommand.do whose graph.add raises must
    # remove the just-inserted store entry before the exception propagates, so a
    # failed create never leaves an orphan in the store with no graph edges.
    objects: dict = {}
    graph = _FaultInjectGraph(add_fail_id="pt_001")
    point = make_point("pt_001", 0.0, 0.0)
    cmd = CreateObjectCommand(objects, graph, EventBus(), point)
    with pytest.raises(RuntimeError, match="induced add failure"):
        cmd.do()
    assert "pt_001" not in objects  # the inserted entry was rolled back


def test_create_object_undo_unregisters_even_when_already_absent():
    # H4: when the object is already absent from the store, undo must still call
    # graph.unregister (idempotent) so store and graph stay consistent — no
    # stale graph edge is left behind — and it must NOT fire OBJECT_DELETED
    # (nothing was removed from the store).
    objects: dict = {}
    graph = DependencyGraph()
    point = make_point("pt_001", 0.0, 0.0)
    bus = EventBus()
    counter = _EventCounter()
    counter.subscribe_all(bus)
    cmd = CreateObjectCommand(objects, graph, bus, point)
    cmd.do()  # inserts pt_001 and registers its edge
    del objects["pt_001"]  # remove out-of-band; graph edge now stale

    unregistered: list[str] = []
    original_unregister = graph.unregister

    def _spy(obj_id: str, *, strict: bool = False) -> None:
        unregistered.append(obj_id)
        original_unregister(obj_id, strict=strict)

    graph.unregister = _spy  # type: ignore[method-assign]
    counter.deleted.clear()

    cmd.undo()
    assert unregistered == ["pt_001"]  # idempotent unregister still called
    assert not graph.is_registered("pt_001")  # store and graph back in sync
    assert not counter.deleted  # no OBJECT_DELETED for the no-op branch


def _create_round_trip_scene(kind: str) -> tuple[list[GeoObject], GeoObject, frozenset[str]]:
    """Build the prerequisites and target object for a create round-trip.

    Returns ``(prereqs, target, expected_edges)``: ``prereqs`` are the
    already-created objects ``target`` references, ``target`` is the object whose
    ``CreateObjectCommand`` is under test, and ``expected_edges`` is the exact
    forward-edge set ``deps_for_type`` should derive for ``target`` (asserted
    independently so a per-type edge-extraction regression surfaces here).
    """
    pts = [make_point(f"pt_{i:03d}", float(i), 0.0) for i in range(1, 5)]
    p1, p2, p3, p4 = (p.id for p in pts)
    polygon = make_polygon("pg_001", (p1, p2, p3))
    circle = make_circle("ci_001", p1)
    # Each entry: prerequisite objects, target object, expected forward edges.
    table: dict[str, tuple[list[GeoObject], GeoObject, set[str]]] = {
        "point": ([], make_point("pt_001", 0.0, 0.0), set()),
        "line": (pts[:2], make_line("ln_001", p1, p2), {p1, p2}),
        "polygon": (pts[:3], polygon, {p1, p2, p3}),
        "ray": (pts[:1], make_ray("ry_001", p1), {p1}),
        "vector": (pts[:2], make_vector("vc_001", p1, 10.0, p2), {p1, p2}),
        "circle": (pts[:1], make_circle("ci_001", p1), {p1}),
        "ball": (pts[:1], make_ball("ba_001", p1), {p1}),
        "cylinder": (pts[:1], make_cylinder("cy_001", p1), {p1}),
        "solid": ([*pts, polygon], make_solid("so_001", ("pg_001", p4)), {"pg_001", p4}),
        "tangent": ([pts[0], pts[1], circle], make_tangent("tg_001", "ci_001", p2), {"ci_001", p2}),
    }
    prereqs, target, edges = table[kind]
    return prereqs, target, frozenset(edges)


_ALL_KINDS = (
    "point",
    "line",
    "polygon",
    "ray",
    "vector",
    "circle",
    "ball",
    "cylinder",
    "solid",
    "tangent",
)


@pytest.mark.parametrize("kind", _ALL_KINDS)
def test_create_object_round_trip_all_types(kind: str):
    # Round-trip CreateObjectCommand for every one of the ten object types:
    # create installs the object and registers its exact dependency edges; undo
    # removes it and unregisters those edges; redo restores both. The asserted
    # edge set mirrors deps_for_type, so a type-specific edge-extraction bug
    # surfaces here rather than silently in a later cascade.
    prereqs, target, expected_edges = _create_round_trip_scene(kind)
    objects: dict = {obj.id: obj for obj in prereqs}
    graph = DependencyGraph()
    for obj in prereqs:
        graph.add(obj)
    bus = EventBus()
    history = CommandHistory(bus)

    history.push(CreateObjectCommand(objects, graph, bus, target))
    assert objects[target.id] is target
    assert graph.is_registered(target.id)
    # Forward edges: exactly the dependency set deps_for_type derives.
    assert graph._test_only_dep_ids_of(target.id) == expected_edges  # pylint: disable=protected-access
    # Reverse edges: the target is a dependent of each id it references.
    for dep_id in expected_edges:
        assert target.id in graph.dependents_of(dep_id)
    graph._test_only_assert_consistent()  # pylint: disable=protected-access

    history.undo()
    assert target.id not in objects
    assert not graph.is_registered(target.id)
    for dep_id in expected_edges:
        assert target.id not in graph.dependents_of(dep_id)
    graph._test_only_assert_consistent()  # pylint: disable=protected-access

    history.redo()
    assert objects[target.id] is target
    assert graph.is_registered(target.id)
    assert graph._test_only_dep_ids_of(target.id) == expected_edges  # pylint: disable=protected-access
    for dep_id in expected_edges:
        assert target.id in graph.dependents_of(dep_id)
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


@pytest.mark.parametrize(
    ("axis", "kwargs"),
    [
        ("easting", {"easting": float("nan"), "northing": 1.0}),
        ("northing", {"easting": 1.0, "northing": float("inf")}),
        ("altitude", {"easting": 1.0, "northing": 1.0, "altitude": float("nan")}),
    ],
)
def test_move_point_rejects_non_finite_coordinate(axis: str, kwargs: dict):
    # do() installs the moved point via deep copy + attribute writes, which
    # bypasses Point.__post_init__'s finiteness check, so a NaN/inf coordinate
    # would silently install a corrupt Point. __init__ must reject it up front
    # (before any snapshot/mutation), naming the axis and the point id.
    objects = {"pt_001": make_point("pt_001", 0.0, 0.0)}
    graph = DependencyGraph()
    graph.add(objects["pt_001"])
    with pytest.raises(ValueError, match=rf"{axis} must be finite.*pt_001"):
        MovePointCommand(objects, graph, EventBus(), "pt_001", **kwargs)
    # Construction raised before any mutation: the point is unmoved.
    assert (objects["pt_001"].easting, objects["pt_001"].northing) == (0.0, 0.0)


def test_move_point_rejects_non_point_target():
    # The models are unslotted dataclasses, so a wrong-type target would let the
    # coordinate writes graft stray easting/northing onto a non-Point. __init__
    # must reject it with a clear TypeError naming the id and expected type.
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "ln_001": make_line("ln_001", "pt_001", "pt_001"),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    with pytest.raises(TypeError, match=r"ln_001.*not a Point"):
        MovePointCommand(objects, graph, EventBus(), "ln_001", easting=1.0, northing=1.0)


def test_move_point_missing_id_raises_contextual_key_error():
    # A missing point id must raise a KeyError whose message names the command
    # and the missing id (via the shared _require helper), not a bare KeyError
    # carrying only the key.
    graph = DependencyGraph()
    with pytest.raises(KeyError, match=r"MovePointCommand.*pt_404"):
        MovePointCommand({}, graph, EventBus(), "pt_404", easting=1.0, northing=1.0)


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

    # Move pt_002 to a genuinely new horizontal position (north-east) and up, so
    # both the azimuth (now π/4, NE) and the elevation change for real — not
    # merely the altitude. A move that kept (easting, northing) would leave the
    # azimuth unchanged and make ``direction != before_dir`` pass by accident.
    history.push(
        MovePointCommand(objects, graph, bus, "pt_002", easting=10.0, northing=10.0, altitude=10.0)
    )
    line = objects["ln_001"]
    assert line.direction == pytest.approx(math.pi / 4)  # azimuth NE
    # Horizontal reach is √(10²+10²); the climb is 10, so elevation = atan2(10, √200).
    assert line.elevation == pytest.approx(math.atan2(10.0, math.hypot(10.0, 10.0)))
    assert line.direction != before_dir
    assert line.elevation != before_el

    history.undo()
    assert objects["ln_001"].direction == pytest.approx(before_dir)
    assert objects["ln_001"].elevation == pytest.approx(before_el)

    # Redo must reinstate the recomputed DEPENDENT geometry, not just the moved
    # point's coordinates: the line's direction/elevation return to the moved
    # values, proving the after-snapshot carries the recomputed dependent.
    history.redo()
    assert objects["pt_002"].easting == 10.0
    assert objects["ln_001"].direction == pytest.approx(math.pi / 4)
    assert objects["ln_001"].elevation == pytest.approx(math.atan2(10.0, math.hypot(10.0, 10.0)))


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


def test_move_point_recomputes_endpoint_vector_direction_in_angle_mode():
    # _directed_value's DirectionMode.ANGLE branch (azimuth_to_angle) was only
    # covered for Line. Exercise it for an Origin+Endpoint Vector: move the
    # endpoint due East of the origin so the azimuth is π/2; under ANGLE mode the
    # stored direction is azimuth_to_angle(π/2) == π/2 - π/2 == 0.0 (East is
    # math-angle 0). Pin the exact converted value.
    origin = make_point("pt_001", 0.0, 0.0, 0.0)
    endpoint = make_point("pt_002", 0.0, 5.0, 0.0)  # starts due North
    vec = Vector(
        **_env("vc_001"),
        **_bearing(mode=DirectionMode.ANGLE),
        origin_id="pt_001",
        length=5.0,
        endpoint_id="pt_002",
        **_colors(),
    )
    objects = {"pt_001": origin, "pt_002": endpoint, "vc_001": vec}
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)

    # Move the endpoint due East of the origin: azimuth π/2 -> math angle 0.0.
    cmd = MovePointCommand(objects, graph, EventBus(), "pt_002", easting=10.0, northing=0.0)
    cmd.do()
    assert objects["vc_001"].direction == pytest.approx(0.0)


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

    # Move the surface point due North; the radius (center -> point) now points
    # due North (azimuth 0), so the tangent azimuth is 0 + π/2 == π/2. Under
    # AZIMUTH mode the value is stored directly. Pin the exact expected azimuth
    # rather than asserting only that it changed.
    history.push(MovePointCommand(objects, graph, bus, "pt_002", easting=0.0, northing=5.0))
    after_dir = objects["tg_001"].direction
    assert after_dir != before_dir
    assert after_dir == pytest.approx(math.pi / 2)
    # Circle tangents stay horizontal.
    assert objects["tg_001"].elevation == 0.0

    history.undo()
    assert objects["tg_001"].direction == pytest.approx(before_dir)


def test_move_point_recomputes_tangent_direction_in_angle_mode():
    # _directed_value's DirectionMode.ANGLE branch (azimuth_to_angle) was only
    # covered for Line. Exercise it for a Tangent: with the circle centred at the
    # origin and the surface point moved due East, the radius azimuth is π/2 so
    # the tangent azimuth is π/2 + π/2 == π; under ANGLE mode the stored direction
    # is azimuth_to_angle(π) == π/2 - π == -π/2 -> 3π/2 after normalisation. Pin
    # the exact converted value.
    tangent = Tangent(
        **_env("tg_001"),
        **_bearing(mode=DirectionMode.ANGLE),
        shape_id="ci_001",
        shape_type="circle",
        point_id="pt_002",
        **_colors(),
    )
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),  # circle center
        "pt_002": make_point("pt_002", 0.0, 5.0),  # surface point, starts due North
        "ci_001": make_circle("ci_001", "pt_001"),
        "tg_001": tangent,
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)

    # Move the surface point due East of the center: radius azimuth π/2, tangent
    # azimuth π, math angle 3π/2.
    cmd = MovePointCommand(objects, graph, EventBus(), "pt_002", easting=5.0, northing=0.0)
    cmd.do()
    assert objects["tg_001"].direction == pytest.approx(3.0 * math.pi / 2.0)


def test_move_circle_center_recomputes_tangent_direction_transitively():
    # The tangent depends on the circle (and its surface point); the circle
    # depends on its center point. Moving the CENTER is a *transitive*
    # dependency hop through the circle, so the tangent must still recompute.
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),  # circle center
        "pt_002": make_point("pt_002", 5.0, 0.0),  # surface point
        "ci_001": make_circle("ci_001", "pt_001"),
        "tg_001": make_tangent("tg_001", "ci_001", "pt_002"),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    bus = EventBus()
    history = CommandHistory(bus)
    before_dir = objects["tg_001"].direction

    # Move the center so the radius arm (center -> surface) rotates; the tangent
    # azimuth, derived from that arm, must change even though only the center
    # (a transitive dependency) moved.
    history.push(MovePointCommand(objects, graph, bus, "pt_001", easting=0.0, northing=-5.0))
    assert objects["tg_001"].direction != before_dir

    history.undo()
    assert objects["tg_001"].direction == pytest.approx(before_dir)


def test_move_point_preserves_nonzero_ball_tangent_elevation():
    # A Ball tangent carries a user-supplied, non-zero elevation that the move
    # recompute must leave untouched (only the azimuth direction is refreshed).
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0, 0.0),  # ball center
        "pt_002": make_point("pt_002", 3.0, 0.0, 4.0),  # surface point (r = 5)
        "ba_001": make_ball("ba_001", "pt_001"),
        "tg_001": make_ball_tangent("tg_001", "ba_001", "pt_002", elevation=0.3),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    bus = EventBus()
    history = CommandHistory(bus)
    before_dir = objects["tg_001"].direction

    history.push(MovePointCommand(objects, graph, bus, "pt_002", easting=0.0, northing=3.0))
    tangent = objects["tg_001"]
    assert tangent.direction != before_dir  # azimuth refreshed
    assert tangent.elevation == pytest.approx(0.3)  # user elevation preserved


def test_move_point_ball_dependent_is_noop_but_fires_modified():
    # A Ball stores no point-derived scalar, so a center move returns it
    # unchanged — yet it is a dependent and must still fire OBJECT_MODIFIED.
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "ba_001": make_ball("ba_001", "pt_001", radius=5.0),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    bus = EventBus()
    counter = _EventCounter()
    counter.subscribe_all(bus)
    cmd = MovePointCommand(objects, graph, bus, "pt_001", easting=20.0, northing=20.0)
    cmd.do()
    assert objects["ba_001"].radius == pytest.approx(5.0)  # unchanged
    assert objects["ba_001"].center_id == "pt_001"
    assert set(counter.modified) == {"pt_001", "ba_001"}


def test_move_point_cylinder_dependent_is_noop_but_fires_modified():
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "cy_001": make_cylinder("cy_001", "pt_001"),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    bus = EventBus()
    counter = _EventCounter()
    counter.subscribe_all(bus)
    cmd = MovePointCommand(objects, graph, bus, "pt_001", easting=7.0, northing=8.0)
    cmd.do()
    assert objects["cy_001"].radius == pytest.approx(5.0)  # unchanged
    assert objects["cy_001"].height == pytest.approx(10.0)
    assert set(counter.modified) == {"pt_001", "cy_001"}


def test_move_point_solid_dependent_is_noop_but_fires_modified():
    # A Solid stacks a base polygon and an apex point; moving a shared base
    # vertex leaves the solid's stored fields unchanged but it is a dependent
    # (via the polygon and via the apex point) and must fire OBJECT_MODIFIED.
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "pt_002": make_point("pt_002", 10.0, 0.0),
        "pt_003": make_point("pt_003", 0.0, 10.0),
        "pt_004": make_point("pt_004", 3.0, 3.0, 10.0),  # apex
        "pg_001": make_polygon("pg_001", ("pt_001", "pt_002", "pt_003")),
        "so_001": make_solid("so_001", ("pg_001", "pt_004")),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    bus = EventBus()
    counter = _EventCounter()
    counter.subscribe_all(bus)
    cmd = MovePointCommand(objects, graph, bus, "pt_001", easting=-2.0, northing=-2.0)
    cmd.do()
    assert objects["so_001"].layers == ("pg_001", "pt_004")  # unchanged
    assert "so_001" in counter.modified


def test_move_point_rejected_when_it_invalidates_tangent():
    # Moving the circle CENTER onto the tangent's surface point horizontally
    # makes the radius zero, so tangent_direction raises; the move must be
    # rejected in __init__ with a contextual ValueError and the store/graph
    # left untouched (the command never applies).
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0, 0.0),  # circle center
        "pt_002": make_point("pt_002", 5.0, 0.0, 0.0),  # surface point
        "ci_001": make_circle("ci_001", "pt_001"),
        "tg_001": make_tangent("tg_001", "ci_001", "pt_002"),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    before = {k: (v.easting, v.northing) for k, v in objects.items() if isinstance(v, Point)}

    with pytest.raises(ValueError, match=r"pt_001.*tg_001.*rejected"):
        # Move the center onto the surface point horizontally (same E/N): the
        # radius collapses to zero in the horizontal plane.
        MovePointCommand(objects, graph, EventBus(), "pt_001", easting=5.0, northing=0.0)

    # Nothing moved: __init__ raised before any mutation.
    after = {k: (v.easting, v.northing) for k, v in objects.items() if isinstance(v, Point)}
    assert after == before
    assert graph.dependents_of("pt_001") == {"ci_001", "tg_001"}


def test_move_point_dangling_dependent_reference_raises_runtime_error():
    # H5: a dependent referencing a missing store id makes ``_recompute_dependent``
    # raise a KeyError (not a ValueError). The move must surface a contextual
    # RuntimeError naming the moved point and the offending dependent, chained
    # from the original KeyError — rather than letting a bare KeyError escape.
    line = make_line("ln_001", "pt_001", "pt_missing")
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "ln_001": line,
    }
    graph = DependencyGraph()
    graph.add(objects["pt_001"])
    # Register the line manually so it is a dependent of pt_001 even though its
    # other endpoint (pt_missing) is absent from the store.
    graph.add(line)

    with pytest.raises(RuntimeError, match=r"pt_001.*ln_001") as excinfo:
        MovePointCommand(objects, graph, EventBus(), "pt_001", easting=1.0, northing=1.0)
    assert isinstance(excinfo.value.__cause__, (KeyError, AttributeError))


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


def test_move_point_fires_modified_in_deterministic_sorted_order():
    # With several dependents, OBJECT_MODIFIED must fire point-first then the
    # dependents in sorted id order on BOTH do and undo — a stable, reproducible
    # fan-out independent of the graph's (unordered) reverse-edge set. The
    # dependents are registered out of sorted order to prove the command sorts.
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),  # shared origin/center
        "pt_002": make_point("pt_002", 10.0, 0.0),
        "ln_002": make_line("ln_002", "pt_001", "pt_002"),
        "ci_001": make_circle("ci_001", "pt_001"),
        "ln_001": make_line("ln_001", "pt_001", "pt_002"),
    }
    graph = DependencyGraph()
    # Register in a deliberately non-sorted dependent order.
    for obj in objects.values():
        graph.add(obj)
    bus = EventBus()
    counter = _EventCounter()
    counter.subscribe_all(bus)
    history = CommandHistory(bus)

    expected_order = ["pt_001", "ci_001", "ln_001", "ln_002"]  # point first, then sorted
    history.push(MovePointCommand(objects, graph, bus, "pt_001", easting=1.0, northing=1.0))
    assert counter.modified == expected_order

    counter.modified.clear()
    history.undo()
    assert counter.modified == expected_order


def test_move_point_dependent_typeerror_surfaces_runtime_error():
    # A dependent whose recompute raises TypeError (structural inconsistency, not
    # invalid geometry) must surface as the contextual RuntimeError naming the
    # moved point and the offending dependent, chained from the TypeError —
    # rather than letting a bare TypeError escape from __init__.
    endpoint = make_point("pt_002", 10.0, 0.0)
    # Corrupt the endpoint's easting to a non-numeric value: the line's recompute
    # feeds it to ``azimuth`` -> ``np.arctan2``, which raises TypeError on a str.
    object.__setattr__(endpoint, "easting", "not-a-number")
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "pt_002": endpoint,
        "ln_001": make_line("ln_001", "pt_001", "pt_002"),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)

    with pytest.raises(RuntimeError, match=r"structurally inconsistent") as excinfo:
        MovePointCommand(objects, graph, EventBus(), "pt_001", easting=1.0, northing=1.0)
    assert "pt_001" in str(excinfo.value)
    assert "ln_001" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, TypeError)


# ---------------------------------------------------------------------------
# ModifyPolygonVerticesCommand
# ---------------------------------------------------------------------------


def test_modify_polygon_vertices_rejects_non_polygon_target():
    # A wrong-type target would let the point_ids/is_convex writes graft stray
    # attributes onto a non-Polygon (unslotted dataclass). __init__ must reject
    # it with a clear TypeError naming the id and expected type.
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "ln_001": make_line("ln_001", "pt_001", "pt_001"),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    with pytest.raises(TypeError, match=r"ln_001.*not a Polygon"):
        ModifyPolygonVerticesCommand(objects, graph, EventBus(), "ln_001", ("pt_001",))


def test_modify_polygon_vertices_missing_id_raises_contextual_key_error():
    graph = DependencyGraph()
    with pytest.raises(KeyError, match=r"ModifyPolygonVerticesCommand.*pg_404"):
        ModifyPolygonVerticesCommand(
            {}, graph, EventBus(), "pg_404", ("pt_001", "pt_002", "pt_003")
        )


def test_cascade_delete_missing_root_raises_contextual_key_error():
    graph = DependencyGraph()
    with pytest.raises(KeyError, match=r"CascadeDeleteCommand.*pt_404"):
        CascadeDeleteCommand({}, graph, EventBus(), "pt_404")


def test_modify_object_missing_id_raises_contextual_key_error():
    graph = DependencyGraph()
    with pytest.raises(KeyError, match=r"ModifyObjectCommand.*pt_404"):
        ModifyObjectCommand({}, graph, EventBus(), "pt_404", {"name": "x"})


def test_modify_polygon_vertices_round_trip_updates_graph_and_convexity():
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "pt_002": make_point("pt_002", 10.0, 0.0),
        "pt_003": make_point("pt_003", 10.0, 10.0),
        "pt_004": make_point("pt_004", 0.0, 10.0),
        # Start as a valid right triangle on three of the square's corners,
        # arranged with is_convex=False so the round-trip can assert the command
        # recomputes it to True (every triangle is convex). The flag is a
        # deliberately-wrong starting value, not a real concave/degenerate ring.
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
    assert not objects
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


def test_bulk_import_rolls_back_on_mid_batch_failure():
    # A graph whose unregister never fails, but a duplicate id in the batch makes
    # the second create overwrite the first; instead we force a failure by having
    # one create target a graph that rejects it. Simpler: a create whose object
    # has a non-str reference makes DependencyGraph.add raise mid-batch.
    objects: dict = {}
    graph = DependencyGraph()
    bus = EventBus()
    good = make_point("pt_001", 0.0, 0.0)
    # A line with a non-str point reference makes graph.add raise TypeError when
    # its CreateObjectCommand.do registers edges.
    bad_line = make_line("ln_bad", "pt_001", "pt_002")
    object.__setattr__(bad_line, "point_b_id", 123)  # corrupt to force add() failure
    with pytest.raises(TypeError):
        BulkImportCommand(objects, graph, bus, [good, bad_line]).do()
    # The good point created before the failure was rolled back.
    assert not objects
    assert not graph.is_registered("pt_001")


def test_bulk_import_do_rollback_is_fault_tolerant():
    # H1: a wrapped create fails mid-batch, triggering the rollback, and a
    # rollback ``undo()`` of an already-applied create ALSO raises. The ORIGINAL
    # exception must propagate (not the rollback one) and every remaining
    # rollback step must still run.
    log: list[str] = []
    cmd = BulkImportCommand({}, DependencyGraph(), EventBus(), [])
    a = _RaisingUndoCreate("a", log)
    b = _RaisingUndoCreate("b", log)
    c = _RaisingUndoCreate("c", log)
    c.raise_on_do = True  # the batch fails on c's create
    a.raise_on_undo = True  # and a's rollback undo ALSO raises
    cmd._commands = [a, b, c]  # pylint: disable=protected-access

    with pytest.raises(RuntimeError, match="do failed for c"):
        cmd.do()
    # a and b were applied, c failed; rollback runs newest-first over the
    # applied set (b then a) and still attempts a's undo despite it raising.
    assert log == ["do:a", "do:b", "do:c", "undo:b", "undo:a"]


def test_bulk_import_undo_rollback_is_fault_tolerant():
    # Test gap: a wrapped ``undo`` fails mid-batch during BulkImport.undo, and
    # the restoring ``do()`` ALSO raises. The ORIGINAL exception must propagate
    # and restoration must be attempted for every already-reversed command.
    log: list[str] = []
    cmd = BulkImportCommand({}, DependencyGraph(), EventBus(), [])
    a = _RaisingUndoCreate("a", log)
    b = _RaisingUndoCreate("b", log)
    c = _RaisingUndoCreate("c", log)
    # undo iterates newest-first: c, b, a. Make a's undo fail (the batch fault);
    # then restoration redoes the already-reversed c and b — make c's do raise.
    a.raise_on_undo = True
    c.raise_on_do = True
    cmd._commands = [a, b, c]  # pylint: disable=protected-access

    with pytest.raises(RuntimeError, match="undo failed for a"):
        cmd.undo()
    # undo order c, b, a (a raises). reversed_so_far == [c, b]; restoration runs
    # newest-first (b then c) and still attempts c's do despite it raising.
    assert log == ["undo:c", "undo:b", "undo:a", "do:b", "do:c"]


# ---------------------------------------------------------------------------
# CascadeDeleteCommand atomicity (rollback on mid-cascade failure)
# ---------------------------------------------------------------------------


def test_cascade_delete_rolls_back_on_mid_cascade_failure():
    objects, _ = _point_line_polygon_scene()
    # Rebuild the graph with one whose unregister raises on a chosen dependent.
    graph = _FailingUnregisterGraph(fail_id="ln_001")
    for obj in objects.values():
        graph.add(obj)
    before_objects = dict(objects)
    bus = EventBus()
    counter = _EventCounter()
    counter.subscribe_all(bus)

    cmd = CascadeDeleteCommand(objects, graph, bus, "pt_001")
    with pytest.raises(RuntimeError, match="induced unregister failure"):
        cmd.do()

    # Full rollback: store is exactly as before, and every object is still
    # registered (graph restored). No delete event fired for the failed cascade.
    assert objects == before_objects
    assert graph.is_registered("pt_001")
    assert graph.is_registered("ln_001")
    assert graph.is_registered("pg_001")
    assert graph.dependents_of("pt_001") == {"ln_001", "pg_001"}
    assert not counter.deleted
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


def test_cascade_delete_do_rollback_is_fault_tolerant():
    # H1: a primary mid-cascade unregister failure triggers the rollback, and a
    # rollback-step ``add`` ALSO raises once. The ORIGINAL exception must still
    # propagate (not the rollback one), every remaining rollback ``add`` must
    # still run, and ``_snapshot`` must end empty so a later undo cannot re-apply
    # a failed delete.
    objects, _ = _point_line_polygon_scene()
    graph = _FaultInjectGraph(unregister_fail_id="ln_001")
    for obj in objects.values():
        graph.add(obj)
    graph.add_attempts.clear()
    # Arm the rollback-step failure only after the initial registration, so it
    # fires during the rollback's re-add rather than during setup.
    graph._add_fail_id = "pt_001"  # pylint: disable=protected-access
    bus = EventBus()

    cmd = CascadeDeleteCommand(objects, graph, bus, "pt_001")
    with pytest.raises(RuntimeError, match="induced unregister failure"):
        cmd.do()

    # The rollback attempted to re-add every snapshot object despite pt_001's add
    # raising — the closure is {pt_001, ln_001, pg_001}.
    assert set(graph.add_attempts) >= {"pt_001", "ln_001", "pg_001"}
    # Snapshot is cleared even though a rollback step failed: a later undo must
    # not re-apply the failed delete.
    assert not cmd._snapshot  # pylint: disable=protected-access


def test_cascade_delete_undo_rolls_back_partial_restore():
    # H2: ``undo`` re-inserts each snapshot object and calls ``graph.add``. If an
    # ``add`` raises mid-restore, the partial restore must be rolled back (the
    # just-re-inserted store entries removed, their edges unregistered) and the
    # ORIGINAL exception must propagate. Mirroring ``do``'s contract, ``_snapshot``
    # is cleared on any restore failure so a later undo/redo never re-applies this
    # failed restore against a now-inconsistent store.
    objects, _ = _point_line_polygon_scene()
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    bus = EventBus()

    cmd = CascadeDeleteCommand(objects, graph, bus, "pt_001")
    cmd.do()  # removes pt_001, ln_001, pg_001 cleanly
    snapshot_ids = set(cmd._snapshot)  # pylint: disable=protected-access
    assert snapshot_ids == {"pt_001", "ln_001", "pg_001"}

    # Arm one snapshot object's re-add to fail during undo.
    fail_id = next(iter(snapshot_ids))
    graph_fault = _FaultInjectGraph(add_fail_id=fail_id)
    # Re-register the survivors so the fault graph mirrors the real one's state.
    for obj in objects.values():
        graph_fault.add(obj)
    cmd._graph = graph_fault  # pylint: disable=protected-access

    with pytest.raises(RuntimeError, match="induced add failure"):
        cmd.undo()

    # Partial restore was rolled back: none of the snapshot ids leaked into the
    # store, and the snapshot was cleared (do()'s contract) so a failed restore
    # cannot be re-applied by a later undo/redo.
    for oid in snapshot_ids:
        assert oid not in objects
    assert not cmd._snapshot  # pylint: disable=protected-access


def test_cascade_delete_undo_rollback_failure_chains_runtime_error():
    # When undo's mid-restore ``add`` raises AND a rollback step's ``unregister``
    # of an already-restored object ALSO raises, undo must surface a contextual
    # RuntimeError whose ``__cause__`` is the ORIGINAL mid-restore exception. The
    # message names "rollback" and the root id.
    objects, _ = _point_line_polygon_scene()
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    bus = EventBus()

    cmd = CascadeDeleteCommand(objects, graph, bus, "pt_001")
    cmd.do()  # removes pt_001, ln_001, pg_001 cleanly
    snapshot_order = list(cmd._snapshot)  # pylint: disable=protected-access
    # The first snapshot object restores cleanly; the second's re-add raises
    # (the primary mid-restore fault), then the rollback's unregister of the
    # first (already-restored) object ALSO raises.
    first_restored, second_added = snapshot_order[0], snapshot_order[1]
    graph_fault = _FaultInjectGraph(unregister_fail_id=first_restored, add_fail_id=second_added)
    # Mirror the real graph's surviving state into the fault graph.
    for obj in objects.values():
        graph_fault.add(obj)
    cmd._graph = graph_fault  # pylint: disable=protected-access

    with pytest.raises(RuntimeError, match="rollback") as excinfo:
        cmd.undo()
    # The contextual RuntimeError names the root and chains the original fault.
    assert "pt_001" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert "induced add failure" in str(excinfo.value.__cause__)


# ---------------------------------------------------------------------------
# Multi-hop transitive cascade-delete closure
# ---------------------------------------------------------------------------


def test_cascade_delete_multi_hop_transitive_closure_round_trip():
    # Deleting a point cascades through a 2+ hop chain:
    #   pt_001 -> pg_001 (polygon vertex) -> so_001 (solid layer on the polygon).
    # The full transitive closure {pg_001, so_001} plus the root must be deleted
    # on do and fully restored (with edges re-registered) on undo.
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "pt_002": make_point("pt_002", 10.0, 0.0),
        "pt_003": make_point("pt_003", 0.0, 10.0),
        "pt_004": make_point("pt_004", 3.0, 3.0, 10.0),  # solid apex
        "pg_001": make_polygon("pg_001", ("pt_001", "pt_002", "pt_003")),
        "so_001": make_solid("so_001", ("pg_001", "pt_004")),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    bus = EventBus()
    counter = _EventCounter()
    counter.subscribe_all(bus)
    history = CommandHistory(bus)

    # pt_001 -> pg_001 -> so_001 is a two-hop chain through the graph.
    assert graph.dependents_of("pt_001") == {"pg_001", "so_001"}

    history.push(CascadeDeleteCommand(objects, graph, bus, "pt_001"))
    # The whole transitive closure (root + both hops) is removed.
    for oid in ("pt_001", "pg_001", "so_001"):
        assert oid not in objects
        assert not graph.is_registered(oid)
    # Unrelated points and the apex (a solid dep, not a pt_001 dependent) survive.
    for oid in ("pt_002", "pt_003", "pt_004"):
        assert oid in objects
    assert len(counter.deleted) == 1
    assert set(counter.deleted[0]) == {"pt_001", "pg_001", "so_001"}

    history.undo()
    assert set(objects) == {"pt_001", "pt_002", "pt_003", "pt_004", "pg_001", "so_001"}
    # Edges re-registered: the two-hop closure resolves again.
    assert graph.dependents_of("pt_001") == {"pg_001", "so_001"}
    assert graph.dependents_of("pg_001") == {"so_001"}
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


# ---------------------------------------------------------------------------
# ModifyObjectCommand field validation (S2)
# ---------------------------------------------------------------------------


def test_modify_object_rejects_unknown_field():
    objects = {"pt_001": make_point("pt_001", 0.0, 0.0)}
    graph = DependencyGraph()
    graph.add(objects["pt_001"])
    with pytest.raises(ValueError, match=r"unknown field 'colour'"):
        ModifyObjectCommand(objects, graph, EventBus(), "pt_001", {"colour": "#ff0000"})
    # Construction raised before any mutation: the store is unchanged.
    assert objects["pt_001"].color == "#abcdef"


def test_reference_fields_set_matches_expected():
    # Pin the exported set so a drift between REFERENCE_FIELDS and
    # deps_for_type's reference fields is caught here. The set is the union of
    # every inter-object reference field the dependency graph consumes. Written
    # as a whitespace-split string to avoid duplicating commands.py's frozenset
    # block (which would otherwise trip pylint's duplicate-code check).
    expected = (
        "point_a_id point_b_id point_ids origin_id endpoint_id "
        "center_id base_center_id shape_id point_id layers"
    )
    assert REFERENCE_FIELDS == frozenset(expected.split())


def _line_scene_for_modify() -> tuple[dict, DependencyGraph]:
    """Two points plus a line on them, all registered — for ModifyObject tests."""
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "pt_002": make_point("pt_002", 10.0, 0.0),
        "ln_001": make_line("ln_001", "pt_001", "pt_002"),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    return objects, graph


def test_modify_object_rejects_identity_field_id():
    objects, graph = _line_scene_for_modify()
    with pytest.raises(ValueError, match="cannot change identity field"):
        ModifyObjectCommand(objects, graph, EventBus(), "ln_001", {"id": "ln_999"})
    assert objects["ln_001"].id == "ln_001"


def test_modify_object_rejects_identity_field_type():
    objects, graph = _line_scene_for_modify()
    with pytest.raises(ValueError, match="cannot change identity field"):
        ModifyObjectCommand(objects, graph, EventBus(), "ln_001", {"type": "ray"})
    assert objects["ln_001"].type == "line"


@pytest.mark.parametrize(
    ("obj_id", "changes"),
    [
        ("ln_001", {"point_a_id": "pt_002"}),
        ("pg_001", {"point_ids": ("pt_001", "pt_002", "pt_003")}),
        ("ci_001", {"center_id": "pt_002"}),
    ],
)
def test_modify_object_rejects_reference_field(obj_id: str, changes: dict):
    # Mutating a reference field would change which objects this one depends on,
    # but ModifyObjectCommand never touches the graph, so it rejects the edit.
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "pt_002": make_point("pt_002", 10.0, 0.0),
        "pt_003": make_point("pt_003", 0.0, 10.0),
        "ln_001": make_line("ln_001", "pt_001", "pt_002"),
        "pg_001": make_polygon("pg_001", ("pt_001", "pt_002", "pt_003")),
        "ci_001": make_circle("ci_001", "pt_001"),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    with pytest.raises(ValueError, match="cannot change reference field"):
        ModifyObjectCommand(objects, graph, EventBus(), obj_id, changes)


@pytest.mark.parametrize("bad_alpha", [-0.1, 1.5, True, float("nan")])
def test_modify_object_rejects_bad_alpha(bad_alpha: object):
    # alpha must be a real number in [0, 1]: a bool, a NaN, or an out-of-range
    # value is rejected before the deep-copy setattr can install it.
    objects = {"pt_001": make_point("pt_001", 0.0, 0.0)}
    graph = DependencyGraph()
    graph.add(objects["pt_001"])
    with pytest.raises(ValueError, match="alpha must be"):
        ModifyObjectCommand(objects, graph, EventBus(), "pt_001", {"alpha": bad_alpha})
    assert objects["pt_001"].alpha == 1.0


def test_modify_object_rejects_non_bool_visibility():
    objects = {"pt_001": make_point("pt_001", 0.0, 0.0)}
    graph = DependencyGraph()
    graph.add(objects["pt_001"])
    with pytest.raises(ValueError, match="visibility must be a bool"):
        ModifyObjectCommand(objects, graph, EventBus(), "pt_001", {"visibility": "yes"})
    assert objects["pt_001"].visibility is True


def test_modify_object_valid_envelope_change_leaves_graph_untouched():
    # A valid envelope edit (name + alpha + visibility) round-trips do/undo and
    # never mutates the dependency graph — the line's edges are invariant.
    objects, graph = _line_scene_for_modify()
    before_edges = graph._test_only_dep_ids_of("ln_001")  # pylint: disable=protected-access
    before_deps_a = graph.dependents_of("pt_001")
    bus = EventBus()
    history = CommandHistory(bus)

    history.push(
        ModifyObjectCommand(
            objects,
            graph,
            bus,
            "ln_001",
            {"name": "renamed", "alpha": 0.5, "visibility": False},
        )
    )
    edited = objects["ln_001"]
    assert (edited.name, edited.alpha, edited.visibility) == ("renamed", 0.5, False)
    # Graph edges unchanged by the envelope edit.
    assert graph._test_only_dep_ids_of("ln_001") == before_edges  # pylint: disable=protected-access
    assert graph.dependents_of("pt_001") == before_deps_a

    history.undo()
    restored = objects["ln_001"]
    assert (restored.name, restored.alpha, restored.visibility) == ("ln_001", 1.0, True)
    assert graph._test_only_dep_ids_of("ln_001") == before_edges  # pylint: disable=protected-access
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


# ---------------------------------------------------------------------------
# ModifyPolygonVerticesCommand: CCW reorder + simplicity/degeneracy validation
# ---------------------------------------------------------------------------


def _square_scene() -> tuple[dict, DependencyGraph]:
    """Four corner points of a unit-ish square plus a triangle polygon on three."""
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "pt_002": make_point("pt_002", 10.0, 0.0),
        "pt_003": make_point("pt_003", 10.0, 10.0),
        "pt_004": make_point("pt_004", 0.0, 10.0),
        "pg_001": make_polygon("pg_001", ("pt_001", "pt_002", "pt_003")),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    return objects, graph


def test_modify_polygon_vertices_reorders_cw_input_to_ccw():
    objects, graph = _square_scene()
    # Clockwise order of the square (negative signed area) must be stored CCW
    # (reversed) by the command.
    cw_order = ("pt_001", "pt_004", "pt_003", "pt_002")
    cmd = ModifyPolygonVerticesCommand(objects, graph, EventBus(), "pg_001", cw_order)
    cmd.do()
    assert objects["pg_001"].point_ids == tuple(reversed(cw_order))
    assert objects["pg_001"].is_convex is True


def test_modify_polygon_vertices_keeps_ccw_input():
    objects, graph = _square_scene()
    ccw_order = ("pt_001", "pt_002", "pt_003", "pt_004")
    cmd = ModifyPolygonVerticesCommand(objects, graph, EventBus(), "pg_001", ccw_order)
    cmd.do()
    # Already CCW (positive signed area): order is preserved.
    assert objects["pg_001"].point_ids == ccw_order


def test_modify_polygon_vertices_rejects_self_intersecting_bowtie():
    # An asymmetric corner set whose bowtie ordering is non-simple yet
    # non-degenerate (|signed area| = 30 > EPS_AREA), so the simplicity check —
    # not the degeneracy check — is what rejects it.
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "pt_002": make_point("pt_002", 10.0, 2.0),
        "pt_003": make_point("pt_003", 10.0, 0.0),
        "pt_004": make_point("pt_004", 0.0, 8.0),
        "pg_001": make_polygon("pg_001", ("pt_001", "pt_003", "pt_002", "pt_004")),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    before_ids = objects["pg_001"].point_ids
    before_deps = graph.dependents_of("pt_004")
    # The (pt_001, pt_002, pt_003, pt_004) ordering crosses itself (a bowtie).
    bowtie = ("pt_001", "pt_002", "pt_003", "pt_004")
    with pytest.raises(ValueError, match="simple"):
        ModifyPolygonVerticesCommand(objects, graph, EventBus(), "pg_001", bowtie)
    # Construction raised before any mutation: store and graph are unchanged.
    assert objects["pg_001"].point_ids == before_ids
    assert graph.dependents_of("pt_004") == before_deps


def test_modify_polygon_vertices_rejects_degenerate_collinear():
    objects = {
        "pt_001": make_point("pt_001", 0.0, 0.0),
        "pt_002": make_point("pt_002", 5.0, 0.0),
        "pt_003": make_point("pt_003", 10.0, 0.0),  # all three collinear
        "pg_001": make_polygon("pg_001", ("pt_001", "pt_002", "pt_003"), is_convex=False),
    }
    graph = DependencyGraph()
    for obj in objects.values():
        graph.add(obj)
    before_ids = objects["pg_001"].point_ids
    with pytest.raises(ValueError, match="degenerate"):
        ModifyPolygonVerticesCommand(
            objects, graph, EventBus(), "pg_001", ("pt_001", "pt_002", "pt_003")
        )
    assert objects["pg_001"].point_ids == before_ids
