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
from geometry.services.dep_graph import DependencyGraph, deps_for_type


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
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


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
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


def test_reregister_to_empty_deps_removes_all_rdep_entries():
    # Re-registering an object with an empty dep set must remove every former
    # reverse edge. A stale _rdeps entry from the old registration would be
    # invisible to dependents_of but would break the asymmetric invariant.
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001", "pt_002"})
    graph.register("ln_001", set())
    assert graph.dependents_of("pt_001") == frozenset()
    assert graph.dependents_of("pt_002") == frozenset()
    assert not graph.has_dependents("pt_001")
    assert not graph.has_dependents("pt_002")
    assert graph.is_registered("ln_001")
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


def test_reregister_with_smaller_dep_set_removes_only_dropped_edges():
    # Re-registering with a subset of original deps must drop only the removed
    # edges; edges to deps still in the set must be preserved.
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001", "pt_002"})
    graph.register("ln_001", {"pt_001"})
    assert graph.dependents_of("pt_001") == {"ln_001"}
    assert graph.dependents_of("pt_002") == frozenset()
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


def test_register_dependent_before_dependency_is_legal():
    # Registering a dependent before its dependency is legal: the dependency
    # appears only as an _rdeps key (not yet in _deps) until it registers.
    graph = DependencyGraph()
    graph.register("ci_001", {"pt_001"})  # pt_001 not yet registered
    graph._test_only_assert_consistent()  # pylint: disable=protected-access
    graph.register("pt_001", set())
    assert graph.dependents_of("pt_001") == {"ci_001"}
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


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
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


def test_unregister_invariant_violation_logs_and_raises(caplog):
    graph = DependencyGraph()
    graph._rdeps["pt_001"] = {"ci_001"}  # pylint: disable=protected-access

    with caplog.at_level("ERROR"), pytest.raises(RuntimeError, match="invariant"):
        graph.unregister("pt_001")

    assert "ci_001" in caplog.text
    assert "pt_001" in caplog.text


def test_unregister_invariant_violation_reverse_direction_logs_and_raises(caplog):
    graph = DependencyGraph()
    # pt_001 lists ci_001 as dependency, but pt_001 is not in _rdeps["ci_001"]
    graph._deps["pt_001"] = {"ci_001"}  # pylint: disable=protected-access

    with caplog.at_level("ERROR"), pytest.raises(RuntimeError, match="invariant"):
        graph.unregister("pt_001")

    assert "ci_001" in caplog.text
    assert "pt_001" in caplog.text


def test_unregister_forward_is_none_backstop_logs_and_raises(caplog):
    # Out-of-band corruption: a dependent listed in _rdeps[obj_id] has a _deps
    # KEY (so the pre-check passes) whose VALUE is None (not a set). The
    # reverse-edge cleanup loop's ``forward is None`` backstop must route this
    # through RuntimeError rather than letting ``None.discard`` raise a bare
    # AttributeError, so cascade callers' error handlers fire.
    graph = DependencyGraph()
    # pt_001 has no forward deps; ci_001 "depends on" pt_001 via _rdeps only,
    # and its _deps entry is corrupted to None.
    graph._deps["pt_001"] = set()  # pylint: disable=protected-access
    graph._deps["ci_001"] = None  # type: ignore[assignment]  # pylint: disable=protected-access
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
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


def test_register_rejects_self_edge():
    # The domain has no self-referential objects, so an obj_id depending on
    # itself is always a programming error. The guard fires before any mutation,
    # so a rejected call (whether self-edge alone or mixed with real deps) leaves
    # both maps empty.
    graph = DependencyGraph()
    with pytest.raises(ValueError, match="self-edge"):
        graph.register("pt_001", {"pt_001"})
    with pytest.raises(ValueError, match="self-edge"):
        graph.register("ln_001", {"pt_001", "ln_001"})
    assert not graph._deps  # pylint: disable=protected-access
    assert not graph._rdeps  # pylint: disable=protected-access


def test_register_with_none_deps_value_raises_runtime_error(caplog):
    # Out-of-band corruption: an object's _deps value is a present key bound to
    # None (not a set). The stale-edge cleanup loop would iterate None and
    # escape as a bare TypeError; the pre-mutation None guard must surface it as
    # a RuntimeError instead, mirroring unregister's guarantee.
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001"})
    graph._deps["ln_001"] = None  # type: ignore[assignment]  # pylint: disable=protected-access

    with caplog.at_level("ERROR"), pytest.raises(RuntimeError, match="invariant"):
        graph.register("ln_001", {"pt_002"})

    assert "ln_001" in caplog.text
    assert "_deps" in caplog.text


def test_register_bare_str_dep_ids_raises_and_leaves_graph_unmutated():
    # A bare str is Iterable[str], so without the guard set("pt_001") would
    # shatter into single-character "deps" and corrupt the graph.
    graph = DependencyGraph()
    with pytest.raises(TypeError, match="bare str"):
        graph.register("ln_001", "pt_001")
    assert not graph.is_registered("ln_001")
    # No mutation at all: both maps must still be empty.
    assert not graph._deps  # pylint: disable=protected-access
    assert not graph._rdeps  # pylint: disable=protected-access


def test_register_unhashable_dep_element_raises_and_leaves_graph_unmutated():
    # A list nested inside the iterable is unhashable, so set() raises a
    # TypeError. It must be reworded to the clear "must contain only str"
    # message (mentioning the unhashable element), and leave no partial mutation.
    graph = DependencyGraph()
    with pytest.raises(TypeError, match="must contain only str"):
        graph.register("ln_001", ["pt_001", ["x"]])
    assert not graph.is_registered("ln_001")
    assert not graph._deps  # pylint: disable=protected-access
    assert not graph._rdeps  # pylint: disable=protected-access


@pytest.mark.parametrize("dep_ids", [42, None, 3.14])
def test_register_non_iterable_dep_ids_raises_accurate_message(dep_ids):
    # A non-iterable dep_ids must NOT be mislabeled as an "unhashable element":
    # that wording actively misdirects debugging. The message must instead make
    # clear the argument is not iterable, and no mutation may occur.
    graph = DependencyGraph()
    with pytest.raises(TypeError, match="iterable") as exc_info:
        graph.register("ln_001", dep_ids)
    assert "unhashable" not in str(exc_info.value)
    assert not graph.is_registered("ln_001")
    assert not graph._deps  # pylint: disable=protected-access
    assert not graph._rdeps  # pylint: disable=protected-access


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


def test_has_dependents_empty_obj_id_raises():
    graph = DependencyGraph()
    with pytest.raises(ValueError, match="non-empty"):
        graph.has_dependents("")


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
    # in a cycle, which is expected and impossible in production. register() now
    # rejects a self-edge, so the self-loop can only be reached by corrupting the
    # private maps directly (the BFS only ever reads _rdeps, so seeding it alone
    # is enough to exercise the visited-guard against an infinite loop).
    graph = DependencyGraph()
    graph._rdeps["x"] = {"x"}  # pylint: disable=protected-access
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
    assert not graph.has_dependents("pt_001")


def test_unregister_prunes_rdeps_entry_for_former_deps():
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001"})
    graph.unregister("ln_001")
    assert not graph.has_dependents("pt_001")


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
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


def test_unregister_bidirectional_cleanup():
    graph = DependencyGraph()
    graph.register("pt_001", set())
    graph.register("ci_001", {"pt_001"})
    graph.register("tg_001", {"ci_001"})
    graph.unregister("ci_001")
    assert graph.dependents_of("pt_001") == set()
    assert graph.dependents_of("tg_001") == set()
    assert graph.dependents_of("ci_001") == set()
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


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
    assert "ci_001" not in graph._test_only_dep_ids_of("tg_001")  # pylint: disable=protected-access
    assert "ci_001" not in graph._test_only_dep_ids_of("tg_002")  # pylint: disable=protected-access
    assert graph.is_registered("tg_001")
    assert graph.is_registered("tg_002")
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


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
        point_ids=["pt_001", "pt_002", "pt_003"],
        is_convex=True,
        **_colors(),
    )
    deps = graph.deps_for_type(pg)
    deps.add("bogus")
    assert graph.deps_for_type(pg) == {"pt_001", "pt_002", "pt_003"}


def test_module_level_deps_for_type_export_matches_static_alias():
    # __all__ exports the module-level deps_for_type, but every other test reaches
    # it through the DependencyGraph.deps_for_type alias. Exercise the bare import
    # here so the export contract is pinned and the alias stays a pass-through.
    ln = Line(
        **_env("ln"),
        point_a_id="pt_001",
        point_b_id="pt_002",
        **_BEARING,
        **_colors(),
    )
    assert deps_for_type(ln) == {"pt_001", "pt_002"}
    assert deps_for_type(ln) == DependencyGraph.deps_for_type(ln)


def test_deps_for_type_solid_with_duplicate_layers_collapses():
    # set(obj.layers) silently collapses duplicate IDs. Pin the intent so the
    # collapse is documented rather than accidental.
    so = Solid(**_env("so"), layers=["pg_001", "pg_001", "pt_010"], **_colors())
    assert DependencyGraph.deps_for_type(so) == {"pg_001", "pt_010"}


def test_deps_for_type_polygon_with_duplicate_points_collapses():
    pg = Polygon(
        **_env("pg"),
        point_ids=["pt_001", "pt_002", "pt_001"],
        is_convex=True,
        **_colors(),
    )
    assert DependencyGraph.deps_for_type(pg) == {"pt_001", "pt_002"}


# ---------------------------------------------------------------------------
# deps_for_type — empty-reference rejection, one test per raise path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("point_a_id", "point_b_id"),
    [("", "pt_002"), ("pt_001", ""), ("", "")],
    ids=["a-empty", "b-empty", "both-empty"],
)
def test_deps_for_type_line_with_empty_point_reference_raises(point_a_id, point_b_id):
    ln = Line(
        **_env("ln"),
        point_a_id=point_a_id,
        point_b_id=point_b_id,
        **_BEARING,
        **_colors(),
    )
    with pytest.raises(ValueError, match="line 'ln_001' has empty point reference"):
        DependencyGraph.deps_for_type(ln)


def test_deps_for_type_polygon_with_empty_point_reference_raises():
    # An empty string inside a non-empty point_ids list — distinct from the
    # empty-list case below, which has its own message.
    pg = Polygon(
        **_env("pg"),
        point_ids=["pt_001", "", "pt_003"],
        is_convex=True,
        **_colors(),
    )
    with pytest.raises(ValueError, match="polygon 'pg_001' has empty point reference"):
        DependencyGraph.deps_for_type(pg)


def test_deps_for_type_polygon_with_none_point_reference_raises():
    # None in point_ids must raise TypeError — consistent with the non-str
    # scalar-field guards (e.g. line.point_a_id). The "" guard alone passes for
    # None (None != ""), so the non-str element check is what fires here; raising
    # TypeError (not ValueError) keeps command code that catches TypeError to
    # detect model corruption from silently missing the polygon case.
    pg = Polygon(
        **_env("pg"), point_ids=["pt_001", "pt_002", "pt_003"], is_convex=True, **_colors()
    )
    object.__setattr__(pg, "point_ids", ["pt_001", None])
    with pytest.raises(TypeError, match="polygon 'pg_001' has non-str point reference"):
        DependencyGraph.deps_for_type(pg)


def test_add_polygon_with_none_point_id_raises_type_error():
    # Regression: None in point_ids must escape add() as TypeError (wrapped with
    # object context). deps_for_type raises TypeError for the non-str element,
    # and add()'s except TypeError branch re-raises it with the object id/type so
    # command code catching TypeError to detect corruption sees the polygon case.
    graph = DependencyGraph()
    pg = Polygon(
        **_env("pg"), point_ids=["pt_001", "pt_002", "pt_003"], is_convex=True, **_colors()
    )
    object.__setattr__(pg, "point_ids", ["pt_001", None])
    with pytest.raises(TypeError, match="pg_001"):
        graph.add(pg)


def test_deps_for_type_polygon_with_no_points_raises():
    # Polygon.__post_init__ now rejects fewer than three vertices, so an empty
    # list can no longer be constructed normally; bypass the constructor (as the
    # solid empty-layers test does) to reach deps_for_type's own guard, which
    # must reject it rather than silently registering an edgeless polygon.
    pg = Polygon(
        **_env("pg"), point_ids=["pt_001", "pt_002", "pt_003"], is_convex=True, **_colors()
    )
    object.__setattr__(pg, "point_ids", [])
    with pytest.raises(ValueError, match="polygon 'pg_001' has no point references"):
        DependencyGraph.deps_for_type(pg)


def test_deps_for_type_ray_with_empty_origin_reference_raises():
    ry = Ray(**_env("ry"), origin_id="", **_BEARING, **_colors())
    with pytest.raises(ValueError, match="ray 'ry_001' has empty origin reference"):
        DependencyGraph.deps_for_type(ry)


def test_deps_for_type_vector_with_empty_origin_reference_raises():
    vc = Vector(
        **_env("vc"),
        origin_id="",
        length=10.0,
        endpoint_id=None,
        **_BEARING,
        **_colors(),
    )
    with pytest.raises(ValueError, match="vector 'vc_001' has empty origin reference"):
        DependencyGraph.deps_for_type(vc)


def test_deps_for_type_vector_with_empty_endpoint_reference_raises():
    # endpoint_id="" is NOT the no-endpoint case (that is endpoint_id=None,
    # which is legal); an empty string is a corrupt reference and must raise.
    vc = Vector(
        **_env("vc"),
        origin_id="pt_001",
        length=10.0,
        endpoint_id="",
        **_BEARING,
        **_colors(),
    )
    with pytest.raises(ValueError, match="vector 'vc_001' has empty endpoint reference"):
        DependencyGraph.deps_for_type(vc)


def test_deps_for_type_circle_with_empty_center_reference_raises():
    ci = Circle(**_env("ci"), center_id="", radius=5.0, **_colors())
    with pytest.raises(ValueError, match="circle 'ci_001' has empty center reference"):
        DependencyGraph.deps_for_type(ci)


def test_deps_for_type_ball_with_empty_center_reference_raises():
    ba = Ball(**_env("ba"), center_id="", radius=5.0, **_colors())
    with pytest.raises(ValueError, match="ball 'ba_001' has empty center reference"):
        DependencyGraph.deps_for_type(ba)


def test_deps_for_type_cylinder_with_empty_base_center_reference_raises():
    cy = Cylinder(
        **_env("cy"),
        base_center_id="",
        radius=5.0,
        height=10.0,
        axis_mode="vertical",
        axis_azimuth=0.0,
        axis_elevation=1.5707963267948966,
        direction_mode=DirectionMode.AZIMUTH,
        direction_units=DirectionUnits.RADIANS,
        **_colors(),
    )
    with pytest.raises(ValueError, match="cylinder 'cy_001' has empty base center reference"):
        DependencyGraph.deps_for_type(cy)


def test_deps_for_type_solid_with_empty_layer_reference_raises():
    # Solid.__post_init__ already rejects an empty string at construction (the
    # prefix rule), so bypass it — the same way the unknown-type tests rewrite
    # ``type`` — to reach deps_for_type's own empty-string guard, which defends
    # against instances built outside the dataclass constructor.
    so = Solid(**_env("so"), layers=["pg_001", "pg_002"], **_colors())
    object.__setattr__(so, "layers", ("pg_001", ""))
    with pytest.raises(ValueError, match="solid 'so_001' has empty layer reference"):
        DependencyGraph.deps_for_type(so)


def test_deps_for_type_solid_with_empty_layers_raises():
    # Solid.__post_init__ rejects too-few layers, so bypass construction-time
    # validation to pin deps_for_type's own guard against malformed instances.
    so = Solid(**_env("so"), layers=["pg_001", "pg_002"], **_colors())
    object.__setattr__(so, "layers", ())
    with pytest.raises(ValueError, match="solid 'so_001' has no layer references"):
        DependencyGraph.deps_for_type(so)


def test_deps_for_type_solid_with_none_layer_reference_raises():
    # Same pattern as the polygon None test: the "" guard alone passes for None,
    # so the non-str check is what fires. It raises TypeError (consistent with
    # the non-str scalar-field guards) so command code catching TypeError sees
    # the solid case too.
    so = Solid(**_env("so"), layers=["pg_001", "pg_002"], **_colors())
    object.__setattr__(so, "layers", ("pg_001", None))
    with pytest.raises(TypeError, match="solid 'so_001' has non-str layer reference"):
        DependencyGraph.deps_for_type(so)


@pytest.mark.parametrize(
    ("shape_id", "point_id"),
    [("", "pt_001"), ("ci_001", ""), ("", "")],
    ids=["shape-empty", "point-empty", "both-empty"],
)
def test_deps_for_type_tangent_with_empty_reference_raises(shape_id, point_id):
    tg = Tangent(
        **_env("tg"),
        shape_id=shape_id,
        shape_type="circle",
        point_id=point_id,
        **_BEARING,
        **_colors(),
    )
    with pytest.raises(ValueError, match="tangent 'tg_001' has empty reference"):
        DependencyGraph.deps_for_type(tg)


# ---------------------------------------------------------------------------
# deps_for_type — non-str scalar reference rejection (TypeError), one per arm.
# A truthy non-str (e.g. 42) passes the empty-reference guard, so the dedicated
# non-str check is what must fire. object.__setattr__ bypasses the dataclass
# constructor to exercise the deps_for_type guard directly.
# ---------------------------------------------------------------------------


def test_deps_for_type_line_with_non_str_point_a_id_raises_type_error():
    ln = Line(
        **_env("ln"),
        point_a_id="pt_001",
        point_b_id="pt_002",
        **_BEARING,
        **_colors(),
    )
    object.__setattr__(ln, "point_a_id", 42)
    with pytest.raises(TypeError, match="line 'ln_001' has non-str point_a_id"):
        DependencyGraph.deps_for_type(ln)


def test_deps_for_type_line_with_non_str_point_b_id_raises_type_error():
    ln = Line(
        **_env("ln"),
        point_a_id="pt_001",
        point_b_id="pt_002",
        **_BEARING,
        **_colors(),
    )
    object.__setattr__(ln, "point_b_id", 42)
    with pytest.raises(TypeError, match="line 'ln_001' has non-str point_b_id"):
        DependencyGraph.deps_for_type(ln)


def test_deps_for_type_ray_with_non_str_origin_raises_type_error():
    ry = Ray(**_env("ry"), origin_id="pt_001", **_BEARING, **_colors())
    object.__setattr__(ry, "origin_id", 42)
    with pytest.raises(TypeError, match="ray 'ry_001' has non-str origin_id=42"):
        DependencyGraph.deps_for_type(ry)


def test_deps_for_type_vector_with_non_str_origin_raises_type_error():
    vc = Vector(
        **_env("vc"),
        origin_id="pt_001",
        length=10.0,
        endpoint_id=None,
        **_BEARING,
        **_colors(),
    )
    object.__setattr__(vc, "origin_id", 42)
    with pytest.raises(TypeError, match="vector 'vc_001' has non-str origin_id=42"):
        DependencyGraph.deps_for_type(vc)


def test_deps_for_type_vector_with_non_str_endpoint_raises_type_error():
    vc = Vector(
        **_env("vc"),
        origin_id="pt_001",
        length=10.0,
        endpoint_id="pt_002",
        **_BEARING,
        **_colors(),
    )
    object.__setattr__(vc, "endpoint_id", 42)
    with pytest.raises(TypeError, match="vector 'vc_001' has non-str endpoint_id=42"):
        DependencyGraph.deps_for_type(vc)


def test_deps_for_type_circle_with_non_str_center_raises_type_error():
    ci = Circle(**_env("ci"), center_id="pt_001", radius=5.0, **_colors())
    object.__setattr__(ci, "center_id", 42)
    with pytest.raises(TypeError, match="circle 'ci_001' has non-str center_id=42"):
        DependencyGraph.deps_for_type(ci)


def test_deps_for_type_ball_with_non_str_center_raises_type_error():
    ba = Ball(**_env("ba"), center_id="pt_001", radius=5.0, **_colors())
    object.__setattr__(ba, "center_id", 42)
    with pytest.raises(TypeError, match="ball 'ba_001' has non-str center_id=42"):
        DependencyGraph.deps_for_type(ba)


def test_deps_for_type_cylinder_with_non_str_base_center_raises_type_error():
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
    object.__setattr__(cy, "base_center_id", 42)
    with pytest.raises(TypeError, match="cylinder 'cy_001' has non-str base_center_id=42"):
        DependencyGraph.deps_for_type(cy)


def test_deps_for_type_tangent_with_non_str_shape_raises_type_error():
    tg = Tangent(
        **_env("tg"),
        shape_id="ci_001",
        shape_type="circle",
        point_id="pt_001",
        **_BEARING,
        **_colors(),
    )
    object.__setattr__(tg, "shape_id", 42)
    with pytest.raises(TypeError, match="tangent 'tg_001' has non-str shape_id=42"):
        DependencyGraph.deps_for_type(tg)


def test_deps_for_type_tangent_with_non_str_point_raises_type_error():
    tg = Tangent(
        **_env("tg"),
        shape_id="ci_001",
        shape_type="circle",
        point_id="pt_001",
        **_BEARING,
        **_colors(),
    )
    object.__setattr__(tg, "point_id", 42)
    with pytest.raises(TypeError, match="tangent 'tg_001' has non-str point_id=42"):
        DependencyGraph.deps_for_type(tg)


def test_deps_for_type_polygon_with_non_str_element_raises_type_error():
    # A non-str element in a non-empty point_ids list raises TypeError (Item 2),
    # consistent with the scalar-field guards.
    pg = Polygon(
        **_env("pg"), point_ids=["pt_001", "pt_002", "pt_003"], is_convex=True, **_colors()
    )
    object.__setattr__(pg, "point_ids", ["pt_001", 42])
    with pytest.raises(TypeError, match="polygon 'pg_001' has non-str point reference"):
        DependencyGraph.deps_for_type(pg)


def test_deps_for_type_solid_with_non_str_element_raises_type_error():
    so = Solid(**_env("so"), layers=["pg_001", "pg_002"], **_colors())
    object.__setattr__(so, "layers", ("pg_001", 42))
    with pytest.raises(TypeError, match="solid 'so_001' has non-str layer reference"):
        DependencyGraph.deps_for_type(so)


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
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


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
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


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
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


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


def test_add_none_id_raises_type_error_naming_add():
    # add() validates obj.id itself so the TypeError blames add, not the
    # internal delegation to register.
    graph = DependencyGraph()
    pt = Point(**_env("pt"), easting=0.0, northing=0.0, altitude=0.0, color="#ff0000")
    object.__setattr__(pt, "id", None)
    with pytest.raises(TypeError, match=r"DependencyGraph\.add"):
        graph.add(pt)


def test_add_line_with_truthy_non_str_reference_type_error_includes_object_context():
    # A truthy scalar like 42 passes line's empty-reference guard; add() must
    # still wrap the register TypeError so callers see the failing object.
    graph = DependencyGraph()
    ln = Line(
        **_env("ln"),
        point_a_id="pt_001",
        point_b_id="pt_002",
        **_BEARING,
        **_colors(),
    )
    object.__setattr__(ln, "point_a_id", 42)
    with pytest.raises(TypeError) as exc_info:
        graph.add(ln)
    message = str(exc_info.value)
    assert "DependencyGraph.add" in message
    assert "ln_001" in message
    assert "line" in message
    assert "point_a_id=42" in message


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


def test_full_cascade_delete_multi_branch():
    graph = DependencyGraph()
    # Shared root pt_001
    # Branch 1: circle + tangent
    # Branch 2: line + polygon
    graph.register("pt_001", set())
    graph.register("ci_001", {"pt_001"})
    graph.register("tg_001", {"ci_001"})
    graph.register("ln_001", {"pt_001"})
    graph.register("pg_001", {"ln_001"})

    # cascade_unregister returns ALL unregistered IDs, including obj_id itself.
    affected = graph.cascade_unregister("pt_001")
    assert affected == {"pt_001", "ci_001", "tg_001", "ln_001", "pg_001"}

    assert not graph.is_registered("pt_001")
    assert not graph.is_registered("ci_001")
    assert not graph.is_registered("tg_001")
    assert not graph.is_registered("ln_001")
    assert not graph.is_registered("pg_001")
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


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
    graph._test_only_assert_consistent()  # pylint: disable=protected-access
    assert not graph._deps  # pylint: disable=protected-access
    assert not graph._rdeps  # pylint: disable=protected-access


# ---------------------------------------------------------------------------
# cascade_unregister — convenience method
# ---------------------------------------------------------------------------


def test_cascade_unregister_returns_frozenset_including_root():
    # cascade_unregister must return ALL unregistered IDs including obj_id.
    graph = DependencyGraph()
    graph.register("pt_001", set())
    graph.register("ci_001", {"pt_001"})
    result = graph.cascade_unregister("pt_001")
    assert isinstance(result, frozenset)
    assert result == frozenset({"pt_001", "ci_001"})


def test_cascade_unregister_removes_all_from_graph():
    # Every ID in the returned set must no longer be registered.
    graph = DependencyGraph()
    graph.register("pt_001", set())
    graph.register("ci_001", {"pt_001"})
    graph.register("tg_001", {"ci_001"})
    result = graph.cascade_unregister("pt_001")
    for obj_id in result:
        assert not graph.is_registered(obj_id)
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


def test_cascade_unregister_graph_is_empty_when_all_objects_removed():
    graph = DependencyGraph()
    graph.register("pt_001", set())
    graph.register("ci_001", {"pt_001"})
    graph.cascade_unregister("pt_001")
    assert not graph._deps  # pylint: disable=protected-access
    assert not graph._rdeps  # pylint: disable=protected-access


def test_cascade_unregister_leaf_only_removes_itself():
    # A leaf with no dependents: return set contains only the root.
    graph = DependencyGraph()
    graph.register("pt_001", set())
    graph.register("ci_001", {"pt_001"})
    result = graph.cascade_unregister("ci_001")
    assert result == frozenset({"ci_001"})
    assert not graph.is_registered("ci_001")
    # pt_001 is unaffected.
    assert graph.is_registered("pt_001")
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


def test_cascade_unregister_unknown_id_returns_empty_frozenset():
    # A completely unknown obj_id: nothing was unregistered, so the return
    # set is empty and the graph is left untouched.
    graph = DependencyGraph()
    graph.register("pt_001", set())
    graph.register("ci_001", {"pt_001"})
    result = graph.cascade_unregister("pt_999")
    assert result == frozenset()
    assert graph.is_registered("pt_001")
    assert graph.is_registered("ci_001")
    assert graph.dependents_of("pt_001") == {"ci_001"}
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


def test_cascade_unregister_unregistered_root_with_dependents_returns_dependents_only():
    # pt_001 never registered itself, but ln_001 was registered naming it
    # (a legal forward reference). The cascade removes the dependents and
    # returns only them — the root is excluded because it had no _deps entry
    # to remove.
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001"})  # pt_001 itself never registered
    result = graph.cascade_unregister("pt_001")
    assert result == frozenset({"ln_001"})
    assert not graph.is_registered("ln_001")
    assert not graph.has_dependents("pt_001")
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


def test_cascade_unregister_unregistered_root_with_transitive_dependents():
    # pt_x never registered itself, but a transitive chain hangs off it via
    # forward references: ln_1 depends on pt_x, and tg_1 depends on ln_1. The
    # cascade must return the FULL transitive closure (both dependents), with
    # the unregistered root excluded because it had no _deps entry to remove.
    graph = DependencyGraph()
    graph.register("ln_1", {"pt_x"})  # pt_x itself never registered
    graph.register("tg_1", {"ln_1"})
    result = graph.cascade_unregister("pt_x")
    assert result == frozenset({"ln_1", "tg_1"})
    assert not graph.is_registered("ln_1")
    assert not graph.is_registered("tg_1")
    assert not graph.has_dependents("pt_x")
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


def test_cascade_unregister_diamond_returns_all_four_and_empties_graph():
    # Diamond: pt_001 feeds ln_001 and ln_002, both feeding pg_001. The
    # cascade must return all four IDs exactly once and leave both internal
    # maps completely empty.
    graph = DependencyGraph()
    graph.register("pt_001", set())
    graph.register("ln_001", {"pt_001"})
    graph.register("ln_002", {"pt_001"})
    graph.register("pg_001", {"ln_001", "ln_002"})
    result = graph.cascade_unregister("pt_001")
    assert result == frozenset({"pt_001", "ln_001", "ln_002", "pg_001"})
    assert not graph._deps  # pylint: disable=protected-access
    assert not graph._rdeps  # pylint: disable=protected-access
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


def test_cascade_unregister_empty_id_raises():
    graph = DependencyGraph()
    with pytest.raises(ValueError, match="non-empty"):
        graph.cascade_unregister("")


def test_cascade_unregister_preserves_unrelated_objects():
    # Objects not in the transitive closure of obj_id must remain registered.
    graph = DependencyGraph()
    graph.register("pt_001", set())
    graph.register("pt_002", set())
    graph.register("ci_001", {"pt_001"})
    graph.cascade_unregister("ci_001")
    assert graph.is_registered("pt_001")
    assert graph.is_registered("pt_002")
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


def test_add_then_cascade_unregister_real_vector_and_cylinder_objects():
    graph = DependencyGraph()
    pt_001 = Point(**_env("pt"), easting=0.0, northing=0.0, altitude=0.0, color="#ff0000")
    pt_002 = Point(**_env("pt", 2), easting=1.0, northing=0.0, altitude=0.0, color="#00ff00")
    pt_003 = Point(**_env("pt", 3), easting=2.0, northing=0.0, altitude=0.0, color="#0000ff")
    vc = Vector(
        **_env("vc"),
        origin_id="pt_001",
        length=10.0,
        endpoint_id="pt_002",
        **_BEARING,
        **_colors(),
    )
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
    ci = Circle(**_env("ci"), center_id="pt_003", radius=5.0, **_colors())

    for obj in (pt_001, pt_002, pt_003, vc, cy, ci):
        graph.add(obj)

    result = graph.cascade_unregister("pt_001")
    assert result == frozenset({"pt_001", "vc_001", "cy_001"})
    assert not graph.is_registered("pt_001")
    assert not graph.is_registered("vc_001")
    assert not graph.is_registered("cy_001")
    assert graph.is_registered("pt_002")
    assert graph.is_registered("pt_003")
    assert graph.is_registered("ci_001")
    assert graph.dependents_of("pt_002") == frozenset()
    assert graph.dependents_of("pt_003") == frozenset({"ci_001"})
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


def test_cascade_unregister_line_cleans_sibling_dependency_rdeps_entry():
    graph = DependencyGraph()
    graph.register("pt_001", set())
    graph.register("pt_002", set())
    graph.register("ln_001", {"pt_001", "pt_002"})

    result = graph.cascade_unregister("pt_001")

    assert result == frozenset({"pt_001", "ln_001"})
    assert graph.is_registered("pt_002")
    assert graph.dependents_of("pt_002") == frozenset()
    assert not graph.has_dependents("pt_002")
    graph._test_only_assert_consistent()  # pylint: disable=protected-access


def test_cascade_unregister_invariant_violation_logs_cascade_context_and_raises(caplog):
    # Out-of-band corruption surfaced during the cascade must route through
    # cascade_unregister's RuntimeError handler, which logs cascade context
    # before re-raising. pt_001 lists ci_001 as a dependency with no matching
    # back-edge (Direction-2 pre-check violation); nothing depends on pt_001, so
    # the cascade proceeds straight to unregister(pt_001) and trips the check.
    graph = DependencyGraph()
    graph._deps["pt_001"] = {"ci_001"}  # pylint: disable=protected-access

    with caplog.at_level("ERROR"), pytest.raises(RuntimeError, match="invariant"):
        graph.cascade_unregister("pt_001")

    assert "cascade_unregister" in caplog.text
    assert "pt_001" in caplog.text


def test_cascade_unregister_none_valued_dependent_deps_raises_runtime_error(caplog):
    # Out-of-band corruption: a registered dependent's _deps entry is a present
    # key bound to None (not a missing key). When cascade_unregister processes
    # this dependent FIRST, unregister's Direction-2 pre-check loop would iterate
    # None and escape as a bare TypeError, bypassing the RuntimeError guarantee
    # and the cascade's except-RuntimeError handler. The pre-mutation None guard
    # must surface it as a RuntimeError and the cascade context must be logged.
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001"})
    graph._deps["ln_001"] = None  # type: ignore[assignment]  # pylint: disable=protected-access

    with caplog.at_level("ERROR"), pytest.raises(RuntimeError, match="invariant"):
        graph.cascade_unregister("pt_001")

    assert "cascade_unregister" in caplog.text
    assert "ln_001" in caplog.text


def test_cascade_unregister_partial_mutation_has_no_rollback(caplog):
    # The cascade unregisters in turn with no transaction, so a RuntimeError
    # mid-cascade leaves the graph partially mutated ("no rollback" per the
    # docstring). Deterministic because dependents are always processed before
    # the root: clean ln_001 is removed first, then the root pt_001 — whose _deps
    # is corrupted to None — trips unregister's pre-mutation guard. ln_001 must
    # stay removed; a future change adding rollback would restore it and fail.
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001"})
    # pt_001 registered-but-corrupted (present key bound to None); _rdeps[pt_001]
    # is left intact so the cascade reaches the corrupted root.
    graph._deps["pt_001"] = None  # type: ignore[assignment]  # pylint: disable=protected-access

    with caplog.at_level("ERROR"), pytest.raises(RuntimeError, match="invariant"):
        graph.cascade_unregister("pt_001")

    assert not graph.is_registered("ln_001")  # removed, not rolled back
    assert graph.is_registered("pt_001")  # cascade aborted before clearing root
    assert "cascade_unregister" in caplog.text
    assert "ln_001" in caplog.text


def test_unregister_none_valued_deps_entry_raises_runtime_error(caplog):
    # Direct unregister on an obj_id whose own _deps value is None must raise
    # RuntimeError (not a bare TypeError) from the pre-mutation None guard.
    graph = DependencyGraph()
    graph._deps["ln_001"] = None  # type: ignore[assignment]  # pylint: disable=protected-access

    with caplog.at_level("ERROR"), pytest.raises(RuntimeError, match="invariant"):
        graph.unregister("ln_001")

    assert "ln_001" in caplog.text
    assert "_deps" in caplog.text


def test_unregister_none_valued_rdeps_entry_raises_runtime_error(caplog):
    # Direct unregister on an obj_id whose own _rdeps value is None must raise
    # RuntimeError (not a bare TypeError) from the pre-mutation None guard.
    graph = DependencyGraph()
    graph._deps["pt_001"] = set()  # pylint: disable=protected-access
    graph._rdeps["pt_001"] = None  # type: ignore[assignment]  # pylint: disable=protected-access

    with caplog.at_level("ERROR"), pytest.raises(RuntimeError, match="invariant"):
        graph.unregister("pt_001")

    assert "pt_001" in caplog.text
    assert "_rdeps" in caplog.text


# ---------------------------------------------------------------------------
# None guards — TypeError fires before the empty-string ValueError, on every
# public method that takes an obj_id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("register", (None, set())),
        ("unregister", (None,)),
        ("dependents_of", (None,)),
        ("is_registered", (None,)),
        ("cascade_unregister", (None,)),
        ("has_dependents", (None,)),
    ],
)
def test_none_obj_id_raises_type_error(method, args):
    graph = DependencyGraph()
    with pytest.raises(TypeError, match="obj_id must be a str"):
        getattr(graph, method)(*args)


def test_register_none_dep_id_raises_type_error_and_does_not_register():
    graph = DependencyGraph()
    with pytest.raises(TypeError, match="dep_ids must contain only str"):
        graph.register("ln_001", {"pt_001", None})
    # validate-before-mutate: nothing was registered, no edges were created.
    assert not graph.is_registered("ln_001")
    assert not graph._deps  # pylint: disable=protected-access
    assert not graph._rdeps  # pylint: disable=protected-access


def test_register_unhashable_dep_id_raises_type_error_with_clear_message():
    # An unhashable element (e.g. a list) makes set(dep_ids) raise a TypeError
    # about unhashability; register() must re-raise it with the same
    # "must contain only str" wording the per-element guard uses.
    graph = DependencyGraph()
    with pytest.raises(TypeError, match="dep_ids must contain only str"):
        graph.register("ln_001", ["pt_001", ["nested"]])
    assert not graph.is_registered("ln_001")
    assert not graph._deps  # pylint: disable=protected-access
    assert not graph._rdeps  # pylint: disable=protected-access


def test_register_none_dep_id_on_reregister_leaves_graph_consistent():
    # Re-registering with a dep_ids set containing None must validate before
    # mutating, exactly like the empty-string case: the TypeError fires, the
    # prior registration is preserved intact, and the invariant still holds.
    graph = DependencyGraph()
    graph.register("ln_001", {"pt_001"})
    with pytest.raises(TypeError, match="dep_ids must contain only str"):
        graph.register("ln_001", {"pt_002", None})
    assert graph.is_registered("ln_001")
    assert graph.dependents_of("pt_001") == {"ln_001"}
    assert graph.dependents_of("pt_002") == frozenset()
    graph._test_only_assert_consistent()  # pylint: disable=protected-access
