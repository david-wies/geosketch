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

"""Unit tests for :mod:`geometry.services.dep_graph`.

Two concerns are exercised here:

* the bare graph mechanics (``register`` / ``unregister`` / ``dependents_of``),
  including transitive closure, diamond de-duplication and edge pruning, using
  plain string IDs so the traversal is tested in isolation; and
* :meth:`DependencyGraph.deps_for_type`, the per-type edge table, against real
  model instances so the forward-edge sets match the design spec for all ten
  object types.
"""

import dataclasses

import pytest

from geometry.models import (
    Ball,
    Circle,
    Cylinder,
    DirectionMode,
    DirectionUnits,
    Line,
    Point,
    Polygon,
    Ray,
    Solid,
    Tangent,
    Vector,
)
from geometry.services.dep_graph import DependencyGraph


# ---------------------------------------------------------------------------
# Compact model builders. Only the reference fields matter for deps_for_type;
# the rest are filled with valid-but-arbitrary envelope values.
# ---------------------------------------------------------------------------

_BEARING = {
    "direction": 0.0,
    "elevation": 0.0,
    "direction_mode": DirectionMode.AZIMUTH,
    "direction_units": DirectionUnits.RADIANS,
}


def _env(prefix: str, idx: int = 1) -> dict:
    return {
        "id": f"{prefix}_{idx:03d}",
        "name": f"{prefix}{idx}",
        "alpha": 1.0,
        "visibility": True,
    }


def _colors() -> dict:
    return {"line_color": "#000000", "fill_color": "#ffffff"}


# ---------------------------------------------------------------------------
# Bare graph mechanics
# ---------------------------------------------------------------------------


def test_register_then_dependents_of_returns_direct_dependent():
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001", "pt_002"})
    assert graph.dependents_of("pt_001") == {"ln_001"}
    assert graph.dependents_of("pt_002") == {"ln_001"}


def test_dependents_of_leaf_with_no_dependents_is_empty():
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001"})
    # The line itself is a leaf — nothing depends on it.
    assert graph.dependents_of("ln_001") == set()


def test_dependents_of_unknown_id_is_empty():
    graph = DependencyGraph()
    assert graph.dependents_of("pt_999") == set()


def test_dependents_of_excludes_the_queried_node_itself():
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001"})
    graph.register("pg_001", {"pt_001"})
    assert "pt_001" not in graph.dependents_of("pt_001")


def test_dependents_of_collects_transitive_closure():
    graph = DependencyGraph()
    # pt_001 <- ci_001 <- tg_001  (tangent depends on circle depends on point)
    graph.register("ci_001", {"pt_001"})
    graph.register("tg_001", {"ci_001"})
    assert graph.dependents_of("pt_001") == {"ci_001", "tg_001"}


def test_dependents_of_collects_three_hop_transitive_closure():
    graph = DependencyGraph()
    graph.register("ci_001", {"pt_001"})
    graph.register("tg_001", {"ci_001"})
    graph.register("so_001", {"tg_001"})
    assert graph.dependents_of("pt_001") == {"ci_001", "tg_001", "so_001"}


def test_dependents_of_fan_out_multiple_direct_dependents():
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001"})
    graph.register("ry_001", {"pt_001"})
    graph.register("ci_001", {"pt_001"})
    assert graph.dependents_of("pt_001") == {"ln_001", "ry_001", "ci_001"}


def test_dependents_of_diamond_deduplicates():
    graph = DependencyGraph()
    # Arbitrary ids for topology testing: pt_001 feeds ln_001 and ln_002;
    # pg_001 depends on both lines.
    graph.register("ln_001", {"pt_001"})
    graph.register("ln_002", {"pt_001"})
    graph.register("pg_001", {"ln_001", "ln_002"})
    assert graph.dependents_of("pt_001") == {"ln_001", "ln_002", "pg_001"}


def test_register_with_empty_deps_creates_no_edges():
    graph = DependencyGraph()
    graph.register("pt_001", set())
    assert graph.dependents_of("pt_001") == set()


def test_reregister_replaces_old_edges():
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001", "pt_002"})
    graph.register("ln_001", {"pt_002", "pt_003"})
    # pt_001 is no longer a dependency of ln_001 after re-registration.
    assert graph.dependents_of("pt_001") == set()
    assert graph.dependents_of("pt_002") == {"ln_001"}
    assert graph.dependents_of("pt_003") == {"ln_001"}
    graph._assert_consistent()  # pylint: disable=protected-access


def test_reregister_empty_deps_node_does_not_break_rdep_pointing_at_it():
    # Re-registering a leaf (empty deps) while something still depends on it
    # must not accidentally clear the reverse edge pointing at it. The prune
    # loop in register() exits immediately for empty dep sets, but pin the
    # invariant explicitly so a refactor that clears _rdeps during re-registration
    # fails here rather than passing silently.
    graph = DependencyGraph()
    graph.register("pt_001", set())
    graph.register("ln_001", {"pt_001"})
    graph.register("pt_001", set())  # re-register with same empty deps
    assert graph.dependents_of("pt_001") == {"ln_001"}
    graph._assert_consistent()  # pylint: disable=protected-access


def test_reregister_to_empty_deps_removes_all_rdep_entries():
    # Re-registering an object with an empty dep set must remove every former
    # reverse edge. A stale _rdeps entry from the old registration would be
    # invisible to dependents_of but would break the asymmetric invariant.
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001", "pt_002"})
    graph.register("ln_001", set())
    assert graph.dependents_of("pt_001") == frozenset()
    assert graph.dependents_of("pt_002") == frozenset()
    assert "pt_001" not in graph._rdeps  # pylint: disable=protected-access
    assert "pt_002" not in graph._rdeps  # pylint: disable=protected-access
    assert graph.is_registered("ln_001")
    graph._assert_consistent()  # pylint: disable=protected-access


def test_reregister_with_smaller_dep_set_removes_only_dropped_edges():
    # Re-registering with a subset of original deps must drop only the removed
    # edges; edges to deps still in the set must be preserved.
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001", "pt_002"})
    graph.register("ln_001", {"pt_001"})
    assert graph.dependents_of("pt_001") == {"ln_001"}
    assert graph.dependents_of("pt_002") == frozenset()
    graph._assert_consistent()  # pylint: disable=protected-access


def test_register_dependent_before_dependency_is_legal():
    # Registering a dependent before its dependency is legal: the dependency
    # appears only as an _rdeps key (not yet in _deps) until it registers.
    graph = DependencyGraph()
    graph.register("ci_001", {"pt_001"})  # pt_001 not yet registered
    graph._assert_consistent()  # pylint: disable=protected-access
    graph.register("pt_001", set())
    assert graph.dependents_of("pt_001") == {"ci_001"}
    graph._assert_consistent()  # pylint: disable=protected-access


def test_unregister_removes_node_as_a_dependent():
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001"})
    graph.unregister("ln_001")
    assert graph.dependents_of("pt_001") == set()


def test_unregister_prunes_node_from_transitive_closure():
    graph = DependencyGraph()
    graph.register("ci_001", {"pt_001"})
    graph.register("tg_001", {"ci_001"})
    graph.unregister("ci_001")
    # With the circle gone, the point no longer transitively reaches anything.
    assert graph.dependents_of("pt_001") == set()


def test_unregister_unknown_id_is_noop():
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001"})
    graph.unregister("pt_999")
    assert graph.dependents_of("pt_001") == {"ln_001"}


def test_unregister_strict_raises_for_unregistered_id():
    graph = DependencyGraph()
    with pytest.raises(KeyError):
        graph.unregister("pt_999", strict=True)


def test_unregister_strict_succeeds_for_registered_id():
    graph = DependencyGraph()
    graph.register("pt_001", set())
    graph.unregister("pt_001", strict=True)
    assert not graph.is_registered("pt_001")


def test_unregister_strict_cleans_up_edges():
    # strict=True is recommended in the cascade-delete path where nodes have
    # edges; unregistering a non-leaf must prune both directions cleanly.
    graph = DependencyGraph()
    graph.register("pt_001", set())
    graph.register("ci_001", {"pt_001"})
    graph.unregister("ci_001", strict=True)
    assert not graph.is_registered("ci_001")
    assert graph.dependents_of("pt_001") == frozenset()
    graph._assert_consistent()  # pylint: disable=protected-access


def test_unregister_invariant_violation_logs_and_raises(caplog):
    graph = DependencyGraph()
    graph._rdeps["pt_001"] = {"ci_001"}  # pylint: disable=protected-access

    with caplog.at_level("ERROR"), pytest.raises(RuntimeError, match="invariant"):
        graph.unregister("pt_001")

    assert "ci_001" in caplog.text
    assert "pt_001" in caplog.text


def test_register_empty_obj_id_raises():
    graph = DependencyGraph()
    with pytest.raises(ValueError, match="non-empty"):
        graph.register("", {"pt_001"})


def test_register_empty_dep_id_raises():
    graph = DependencyGraph()
    with pytest.raises(ValueError, match="dep_ids"):
        graph.register("ln_001", {"pt_001", ""})


def test_register_empty_dep_id_on_reregister_leaves_graph_consistent():
    # Re-registering with a dep_ids set containing "" must validate before
    # mutating: the ValueError fires, the prior registration is preserved
    # intact, and the bidirectional invariant still holds.
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001"})
    with pytest.raises(ValueError, match="dep_ids"):
        graph.register("ln_001", {"pt_002", ""})
    assert graph.is_registered("ln_001")
    # The original edge survived; the bad re-registration was fully rejected.
    assert graph.dependents_of("pt_001") == {"ln_001"}
    assert graph.dependents_of("pt_002") == frozenset()
    graph._assert_consistent()  # pylint: disable=protected-access


def test_unregister_empty_obj_id_raises():
    graph = DependencyGraph()
    with pytest.raises(ValueError, match="non-empty"):
        graph.unregister("")


def test_dependents_of_empty_obj_id_raises():
    graph = DependencyGraph()
    with pytest.raises(ValueError, match="non-empty"):
        graph.dependents_of("")


def test_is_registered_empty_obj_id_raises():
    graph = DependencyGraph()
    with pytest.raises(ValueError, match="non-empty"):
        graph.is_registered("")


def test_dependents_of_terminates_on_a_two_node_cycle():
    # The real domain is a DAG, but the BFS visited-guard is the only thing
    # preventing an infinite loop should a cyclic reverse edge ever exist.
    # Pin the termination contract so a refactor that drops the guard fails
    # here (by hanging) rather than passing silently.
    # Note: in a cycle the queried node may appear in the result — this tests termination only.
    graph = DependencyGraph()
    graph.register("a", {"b"})
    graph.register("b", {"a"})
    assert graph.dependents_of("a") == {"a", "b"}
    assert graph.dependents_of("b") == {"a", "b"}


def test_dependents_of_terminates_on_a_self_loop():
    # Pin termination contract only — the queried node appears in the result
    # in a cycle, which is expected and impossible in production.
    graph = DependencyGraph()
    graph.register("x", {"x"})
    assert graph.dependents_of("x") == {"x"}


def test_dependents_of_returns_a_fresh_frozenset():
    # The returned frozenset is an immutable snapshot; it cannot be mutated
    # and does not share state with the graph's internals.
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001"})
    result = graph.dependents_of("pt_001")
    assert isinstance(result, frozenset)
    assert result == {"ln_001"}
    # A second call returns a separate frozenset, not the same object.
    assert graph.dependents_of("pt_001") is not result


def test_register_copies_its_input_set():
    # A caller mutating the set it passed to register must not alter the graph.
    graph = DependencyGraph()
    deps = {"pt_001"}
    graph.register("ln_001", deps)
    deps.add("pt_002")
    assert graph.dependents_of("pt_002") == set()
    assert graph.dependents_of("pt_001") == {"ln_001"}


def test_reregister_prunes_stale_rdeps_entry():
    # Directly verify the _rdeps key is removed, not just that query results
    # are empty — a stale empty set in _rdeps would be invisible to
    # dependents_of but would break the asymmetric invariant.
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001"})
    graph.register("ln_001", {"pt_002"})  # replaces pt_001
    assert "pt_001" not in graph._rdeps  # pylint: disable=protected-access


def test_unregister_prunes_rdeps_entry_for_former_deps():
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001"})
    graph.unregister("ln_001")
    assert "pt_001" not in graph._rdeps  # pylint: disable=protected-access


def test_unregister_middle_node_preserves_orphaned_dependent_presence():
    # After unregistering ci_001, tg_001 loses its forward edge but must
    # remain a registered object (empty _deps entry = presence marker).
    graph = DependencyGraph()
    graph.register("ci_001", {"pt_001"})
    graph.register("tg_001", {"ci_001"})
    graph.unregister("ci_001")
    assert graph.dependents_of("tg_001") == set()
    # Re-registering must not accumulate stale edges from before unregister.
    graph.register("tg_001", {"pt_002"})
    assert graph.dependents_of("pt_002") == {"tg_001"}
    assert graph.dependents_of("pt_001") == set()
    graph._assert_consistent()  # pylint: disable=protected-access


def test_unregister_bidirectional_cleanup():
    graph = DependencyGraph()
    graph.register("pt_001", set())
    graph.register("ci_001", {"pt_001"})
    graph.register("tg_001", {"ci_001"})
    graph.unregister("ci_001")
    assert graph.dependents_of("pt_001") == set()
    assert graph.dependents_of("tg_001") == set()
    assert graph.dependents_of("ci_001") == set()
    graph._assert_consistent()  # pylint: disable=protected-access


def test_unregister_node_with_multiple_dependents_prunes_all_forward_edges():
    # Verify that unregistering a node whose _rdeps entry lists several
    # dependents correctly prunes every dependent's forward edge. A bug
    # that only prunes the first entry would pass the single-dependent
    # test above.
    graph = DependencyGraph()
    graph.register("ci_001", {"pt_001"})
    graph.register("tg_001", {"ci_001"})
    graph.register("tg_002", {"ci_001"})
    graph.unregister("ci_001")
    assert "ci_001" not in graph._deps.get("tg_001", set())  # pylint: disable=protected-access
    assert "ci_001" not in graph._deps.get("tg_002", set())  # pylint: disable=protected-access
    assert graph.is_registered("tg_001")
    assert graph.is_registered("tg_002")
    graph._assert_consistent()  # pylint: disable=protected-access


# ---------------------------------------------------------------------------
# deps_for_type — the per-type forward-edge table
# ---------------------------------------------------------------------------


def test_deps_for_type_point_is_empty():
    pt = Point(**_env("pt"), easting=0.0, northing=0.0, altitude=0.0, color="#ff0000")
    assert DependencyGraph().deps_for_type(pt) == set()


def test_deps_for_type_line():
    ln = Line(
        **_env("ln"),
        point_a_id="pt_001",
        point_b_id="pt_002",
        **_BEARING,
        **_colors(),
    )
    assert DependencyGraph().deps_for_type(ln) == {"pt_001", "pt_002"}


def test_deps_for_type_polygon():
    pg = Polygon(
        **_env("pg"),
        point_ids=["pt_001", "pt_002", "pt_003"],
        is_convex=True,
        **_colors(),
    )
    assert DependencyGraph().deps_for_type(pg) == {"pt_001", "pt_002", "pt_003"}


def test_deps_for_type_ray():
    ry = Ray(**_env("ry"), origin_id="pt_001", **_BEARING, **_colors())
    assert DependencyGraph().deps_for_type(ry) == {"pt_001"}


def test_deps_for_type_vector_without_endpoint():
    vc = Vector(
        **_env("vc"),
        origin_id="pt_001",
        length=10.0,
        endpoint_id=None,
        **_BEARING,
        **_colors(),
    )
    assert DependencyGraph().deps_for_type(vc) == {"pt_001"}


def test_deps_for_type_vector_with_endpoint():
    vc = Vector(
        **_env("vc"),
        origin_id="pt_001",
        length=10.0,
        endpoint_id="pt_002",
        **_BEARING,
        **_colors(),
    )
    assert DependencyGraph().deps_for_type(vc) == {"pt_001", "pt_002"}


def test_deps_for_type_circle():
    ci = Circle(**_env("ci"), center_id="pt_001", radius=5.0, **_colors())
    assert DependencyGraph().deps_for_type(ci) == {"pt_001"}


def test_deps_for_type_ball():
    ba = Ball(**_env("ba"), center_id="pt_001", radius=5.0, **_colors())
    assert DependencyGraph().deps_for_type(ba) == {"pt_001"}


def test_deps_for_type_cylinder():
    cy = Cylinder(
        **_env("cy"),
        base_center_id="pt_001",
        radius=5.0,
        height=10.0,
        axis_mode="vertical",
        axis_azimuth=0.0,
        axis_elevation=1.5707963267948966,
        direction_mode=DirectionMode.AZIMUTH,
        direction_units=DirectionUnits.RADIANS,
        **_colors(),
    )
    assert DependencyGraph().deps_for_type(cy) == {"pt_001"}


def test_deps_for_type_solid():
    so = Solid(**_env("so"), layers=["pg_001", "pg_002", "pt_010"], **_colors())
    assert DependencyGraph().deps_for_type(so) == {"pg_001", "pg_002", "pt_010"}


def test_deps_for_type_tangent_on_circle():
    tg = Tangent(
        **_env("tg"),
        shape_id="ci_001",
        shape_type="circle",
        point_id="pt_001",
        **_BEARING,
        **_colors(),
    )
    assert DependencyGraph().deps_for_type(tg) == {"ci_001", "pt_001"}


def test_deps_for_type_tangent_on_ball():
    tg = Tangent(
        **_env("tg"),
        shape_id="ba_001",
        shape_type="ball",
        point_id="pt_001",
        **_BEARING,
        **_colors(),
    )
    assert DependencyGraph().deps_for_type(tg) == {"ba_001", "pt_001"}


def test_deps_for_type_line_with_identical_endpoints_collapses():
    # A degenerate Line whose two endpoint ids coincide yields a one-element
    # set. Pin the intent so the collapse is documented, not accidental.
    ln = Line(
        **_env("ln"),
        point_a_id="pt_001",
        point_b_id="pt_001",
        **_BEARING,
        **_colors(),
    )
    assert DependencyGraph().deps_for_type(ln) == {"pt_001"}


def test_deps_for_type_tangent_with_identical_shape_and_point_collapses():
    tg = Tangent(
        **_env("tg"),
        shape_id="x_001",
        shape_type="circle",
        point_id="x_001",
        **_BEARING,
        **_colors(),
    )
    assert DependencyGraph().deps_for_type(tg) == {"x_001"}


def test_deps_for_type_returns_a_fresh_set_callers_cannot_corrupt():
    # The returned set must be independent of any internal state, so mutating
    # it cannot affect a later register/deps_for_type call.
    graph = DependencyGraph()
    pg = Polygon(
        **_env("pg"),
        point_ids=["pt_001", "pt_002"],
        is_convex=True,
        **_colors(),
    )
    deps = graph.deps_for_type(pg)
    deps.add("bogus")
    assert graph.deps_for_type(pg) == {"pt_001", "pt_002"}


def test_deps_for_type_solid_with_duplicate_layers_collapses():
    # set(obj.layers) silently collapses duplicate IDs. Pin the intent so the
    # collapse is documented rather than accidental.
    so = Solid(**_env("so"), layers=["pg_001", "pg_001", "pt_010"], **_colors())
    assert DependencyGraph.deps_for_type(so) == {"pg_001", "pt_010"}


# ---------------------------------------------------------------------------
# Integration: deps_for_type feeding register, then a multi-hop cascade query
# ---------------------------------------------------------------------------


def test_cascade_point_circle_tangent_via_deps_for_type():
    graph = DependencyGraph()
    ci = Circle(**_env("ci"), center_id="pt_001", radius=5.0, **_colors())
    tg = Tangent(
        **_env("tg"),
        shape_id="ci_001",
        shape_type="circle",
        point_id="pt_002",
        **_BEARING,
        **_colors(),
    )
    graph.register(ci.id, graph.deps_for_type(ci))
    graph.register(tg.id, graph.deps_for_type(tg))
    # Deleting the centre point cascades to the circle and onward to the tangent.
    assert graph.dependents_of("pt_001") == {"ci_001", "tg_001"}
    # The tangent's own point only reaches the tangent.
    assert graph.dependents_of("pt_002") == {"tg_001"}
    graph._assert_consistent()  # pylint: disable=protected-access


def test_deps_for_type_unknown_type_raises():
    graph = DependencyGraph()
    pt = Point(**_env("pt"), easting=0.0, northing=0.0, altitude=0.0, color="#ff0000")
    object.__setattr__(pt, "type", "bogus")
    with pytest.raises(ValueError):
        graph.deps_for_type(pt)


# ---------------------------------------------------------------------------
# add — convenience wrapper that couples register to deps_for_type
# ---------------------------------------------------------------------------


def test_add_registers_object_with_its_derived_dependency_set():
    graph = DependencyGraph()
    ci = Circle(**_env("ci"), center_id="pt_001", radius=5.0, **_colors())
    graph.add(ci)
    assert graph.is_registered(ci.id)
    # add() must record exactly what deps_for_type derives — no caller can omit
    # an edge the way a hand-rolled register() call could.
    assert graph.dependents_of("pt_001") == {"ci_001"}


def test_add_matches_register_with_deps_for_type():
    obj = Line(
        **_env("ln"),
        point_a_id="pt_001",
        point_b_id="pt_002",
        **_BEARING,
        **_colors(),
    )
    via_add = DependencyGraph()
    via_add.add(obj)
    via_register = DependencyGraph()
    via_register.register(obj.id, via_register.deps_for_type(obj))
    assert via_add.dependents_of("pt_001") == via_register.dependents_of("pt_001")
    assert via_add.dependents_of("pt_002") == via_register.dependents_of("pt_002")


def test_add_point_creates_presence_entry_with_no_edges():
    graph = DependencyGraph()
    pt = Point(**_env("pt"), easting=0.0, northing=0.0, altitude=0.0, color="#ff0000")
    graph.add(pt)
    assert graph.dependents_of("pt_001") == set()


def test_add_cascade_point_circle_tangent():
    graph = DependencyGraph()
    ci = Circle(**_env("ci"), center_id="pt_001", radius=5.0, **_colors())
    tg = Tangent(
        **_env("tg"),
        shape_id="ci_001",
        shape_type="circle",
        point_id="pt_002",
        **_BEARING,
        **_colors(),
    )
    graph.add(ci)
    graph.add(tg)
    assert graph.dependents_of("pt_001") == {"ci_001", "tg_001"}
    graph._assert_consistent()  # pylint: disable=protected-access


def test_add_replaces_old_edges_on_readd():
    # Verify that add() (not just register()) replaces rather than accumulates
    # when an already-registered object is re-added with a changed dependency.
    graph = DependencyGraph()
    ci = Circle(**_env("ci"), center_id="pt_001", radius=5.0, **_colors())
    graph.add(ci)
    ci_edited = dataclasses.replace(ci, center_id="pt_002")
    graph.add(ci_edited)
    assert graph.dependents_of("pt_001") == set()
    assert graph.dependents_of("pt_002") == {"ci_001"}
    graph._assert_consistent()  # pylint: disable=protected-access


def test_add_unknown_type_raises():
    # add() must propagate the ValueError from deps_for_type rather than
    # silently registering with a wrong edge set, and it must include object
    # context just like the AttributeError path.
    graph = DependencyGraph()
    pt = Point(**_env("pt"), easting=0.0, northing=0.0, altitude=0.0, color="#ff0000")
    object.__setattr__(pt, "type", "bogus")
    with pytest.raises(ValueError) as exc_info:
        graph.add(pt)
    assert "pt_001" in str(exc_info.value)
    assert "bogus" in str(exc_info.value)


def test_add_attribute_error_includes_object_context():
    # When deps_for_type raises AttributeError (mismatched type/class),
    # add() must re-raise with the object id and type in the message.
    graph = DependencyGraph()
    pt = Point(**_env("pt"), easting=0.0, northing=0.0, altitude=0.0, color="#ff0000")
    object.__setattr__(pt, "type", "line")  # line arm reads point_a_id which Point lacks
    with pytest.raises(AttributeError, match="pt_001"):
        graph.add(pt)


# ---------------------------------------------------------------------------
# is_registered — presence-marker invariant
# ---------------------------------------------------------------------------


def test_is_registered_true_for_point_with_empty_deps():
    graph = DependencyGraph()
    graph.register("pt_001", set())
    assert graph.is_registered("pt_001")


def test_is_registered_false_for_never_registered_id():
    graph = DependencyGraph()
    assert not graph.is_registered("pt_999")


def test_is_registered_false_after_unregister():
    graph = DependencyGraph()
    graph.register("pt_001", set())
    graph.unregister("pt_001")
    assert not graph.is_registered("pt_001")


def test_is_registered_true_for_dependent_whose_dependency_was_unregistered():
    # When a dependency is unregistered, the dependent object loses its forward
    # edge but remains a registered object (empty _deps entry = presence marker).
    graph = DependencyGraph()
    graph.register("pt_001", set())
    graph.register("ci_001", {"pt_001"})
    graph.unregister("pt_001")
    assert not graph.is_registered("pt_001")
    assert graph.is_registered("ci_001")  # ci_001 still registered, just orphaned


# ---------------------------------------------------------------------------
# Full cascade delete workflow
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "order",
    [["ci_001", "tg_001"], ["tg_001", "ci_001"]],
    ids=["circle-first", "tangent-first"],
)
def test_full_cascade_delete_leaves_graph_clean(order):
    # Pin the three-step pattern: dependents_of → unregister each dependent →
    # unregister root. Parametrised over both unregistration orderings to
    # confirm no order-sensitivity in the cascade.
    graph = DependencyGraph()
    graph.register("pt_001", set())
    graph.register("ci_001", {"pt_001"})
    graph.register("tg_001", {"ci_001"})

    affected = graph.dependents_of("pt_001")
    assert affected == {"ci_001", "tg_001"}
    for obj_id in order:
        graph.unregister(obj_id)
    graph.unregister("pt_001")

    assert not graph.is_registered("pt_001")
    assert not graph.is_registered("ci_001")
    assert not graph.is_registered("tg_001")
    graph._assert_consistent()  # pylint: disable=protected-access
    assert not graph._deps  # pylint: disable=protected-access
    assert not graph._rdeps  # pylint: disable=protected-access
