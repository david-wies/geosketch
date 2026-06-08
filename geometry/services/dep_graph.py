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

"""Reverse-reference dependency graph for cascade delete and point-move recompute.

References between objects are ID strings (``pt_001`` depends on nothing; a
``Line`` depends on its two endpoint points; a ``Tangent`` depends on its shape
and its point; and so on — see :meth:`DependencyGraph.deps_for_type`). When a
point moves or is deleted, every object that transitively references it must be
recomputed or removed. Scanning the whole object store for each such operation
is O(|all objects|); this graph reduces it to O(|affected|) by maintaining the
reverse edges explicitly and walking them with a breadth-first traversal.

The graph stores only IDs — it never holds model instances — so it cannot leak
references and stays valid across save/load as long as the create/delete
commands keep it in sync via :meth:`register` and :meth:`unregister`. It
imports only the model dataclasses (:mod:`geometry.models`); no ``tkinter`` or
``matplotlib``.
"""

from collections import deque
from collections.abc import Iterable

from geometry.models import GeoObject

__all__ = ["DependencyGraph"]

_EMPTY: frozenset[str] = frozenset()


class DependencyGraph:
    """Reverse-reference graph for O(|affected|) cascade operations.

    Forward edges record what each object depends on; reverse edges record what
    depends on each object. ``dependents_of`` walks the reverse edges to collect
    the full transitive closure of objects affected by a delete or point-move,
    without scanning the entire object store.

    Not thread-safe; callers must serialise mutations. This is intentional for
    a single-threaded desktop application.

    Fields
    ------
    _deps : dict[str, set[str]]
        Forward edges: ``obj_id`` -> set of IDs it depends on. A registered
        object always keeps an entry here, even when its set is empty (a Point,
        or an object whose every dependency has since been unregistered): the
        empty set is a deliberate presence marker, not noise.
    _rdeps : dict[str, set[str]]
        Reverse edges: ``obj_id`` -> set of IDs that depend on it. Empty sets
        are never retained here — a key is dropped the moment its last reverse
        edge is pruned — so the two maps are intentionally asymmetric. Only
        ``_rdeps`` is walked by :meth:`dependents_of`, so its emptiness is what
        matters for query results.
    """

    def __init__(self) -> None:
        self._deps: dict[str, set[str]] = {}
        self._rdeps: dict[str, set[str]] = {}

    def add(self, obj: GeoObject) -> None:
        """Register ``obj`` using the dependency set derived from its own type.

        Convenience wrapper that couples :meth:`register` to
        :meth:`deps_for_type`, so a caller cannot accidentally register an
        incomplete edge set (which would cause a cascade delete triggered from
        a missing dependency to silently skip this object). Command code should
        prefer this over calling :meth:`register` directly; :meth:`register`
        stays available for tests and for callers that already hold a
        precomputed dependency set.
        """
        self.register(obj.id, self.deps_for_type(obj))

    def register(self, obj_id: str, dep_ids: Iterable[str]) -> None:
        """Record that ``obj_id`` depends on every id in ``dep_ids``.

        Safe to call repeatedly: any previously registered edges for ``obj_id``
        are removed first, so re-registration replaces rather than accumulates.
        An empty ``dep_ids`` (e.g. a Point) records the object with no edges.

        Prefer :meth:`add` over calling this directly unless you already hold a
        precomputed dependency set — ``add`` derives the correct edge set from
        the object's type so a partial manual set cannot be accidentally passed.
        """
        # Drop stale forward edges before re-adding, so re-registration with a
        # changed dependency set does not leave orphaned reverse edges behind.
        for old_dep in self._deps.get(obj_id, set()):
            reverse = self._rdeps.get(old_dep)
            if reverse is not None:
                reverse.discard(obj_id)
                if not reverse:
                    del self._rdeps[old_dep]

        dep_set = set(dep_ids)
        self._deps[obj_id] = dep_set
        for dep_id in dep_set:
            self._rdeps.setdefault(dep_id, set()).add(obj_id)

    def unregister(self, obj_id: str) -> None:
        """Remove ``obj_id`` from both maps and prune every edge involving it.

        No-op if ``obj_id`` was never registered. Both the object's own forward
        edges and any reverse edges pointing at it are removed, so a later
        ``dependents_of`` never surfaces a deleted object.

        Callers running a cascade delete should unregister every object returned
        by ``dependents_of`` as well, so their forward edges stay consistent
        with the remaining graph state.

        Callers that guarantee exactly-once unregister should treat a no-op
        here as a sign of a double-delete bug; consider adding an assertion or
        logging at the call site.
        """
        # Remove forward edges out of obj_id and their mirrored reverse edges.
        # No-op if obj_id was never registered (pop returns the empty default).
        # TODO(commands): production callers that guarantee exactly-once delete
        # should assert obj_id in _deps before this call — a silent no-op here
        # signals a double-delete bug at the command layer.
        for dep_id in self._deps.pop(obj_id, set()):
            reverse = self._rdeps.get(dep_id)
            if reverse is not None:
                reverse.discard(obj_id)
                if not reverse:
                    del self._rdeps[dep_id]

        # Remove reverse edges into obj_id and their mirrored forward edges.
        for dependent in self._rdeps.pop(obj_id, set()):
            forward = self._deps.get(dependent)
            if forward is not None:
                # Intentionally do NOT delete an emptied forward set: a
                # dependent that loses its last edge is still a registered
                # object, and an empty ``_deps`` entry is its presence marker
                # (identical to a freshly registered Point). ``_rdeps`` is the
                # map that must stay free of empty sets; see the class docstring.
                forward.discard(obj_id)

    def dependents_of(self, obj_id: str) -> set[str]:
        """Return the transitive closure of objects that depend on ``obj_id``.

        Breadth-first walk over the reverse edges. The result is empty for an
        unknown id or a leaf that nothing references. To distinguish an unknown
        id from a registered leaf with no dependents, use :meth:`is_registered`.
        In the well-formed DAG that the real domain always produces, ``obj_id``
        itself will not appear in the result. In a pathological cycle,
        ``obj_id`` may appear because the BFS seeds ``result`` from the
        first-wave dependents only; ``obj_id`` is never pre-placed into the
        visited set, so a reverse path that leads back to it will collect it.
        The BFS terminates regardless because the visited-guard prevents
        re-enqueueing any already-collected node.
        """
        result: set[str] = set()
        queue: deque[str] = deque()
        for node in self._rdeps.get(obj_id, _EMPTY):
            if node not in result:
                result.add(node)
                queue.append(node)
        while queue:
            current = queue.popleft()
            for node in self._rdeps.get(current, _EMPTY):
                if node not in result:
                    result.add(node)
                    queue.append(node)
        return result

    def is_registered(self, obj_id: str) -> bool:
        """Return whether ``obj_id`` is currently tracked by the graph.

        Exposes the presence-marker invariant: every registered object has a
        ``_deps`` entry, even if its dependency set is empty (e.g. a Point).
        The command layer can use this to check graph state after load without
        exposing ``_deps`` directly.
        """
        return obj_id in self._deps

    def _assert_consistent(self) -> None:
        """Assert the bidirectional mirror invariant holds on both maps.

        Every forward edge ``(obj_id, dep_id)`` in ``_deps`` must have a
        matching reverse edge in ``_rdeps``, and vice versa. ``_rdeps`` must
        never contain an empty set. Call this at the end of mutation-heavy
        test scenarios to catch any regression that silently breaks the mirror.

        **Note on ``_rdeps`` keys:** A key in ``_rdeps`` need not be a
        registered object (in ``_deps``) — callers may register a dependent
        before its dependency (forward reference). The pruning logic in
        :meth:`unregister` ensures no stale ``_rdeps`` entries survive a
        properly ordered cascade delete, so asserting presence in ``_deps``
        would flag valid forward references, not actual bugs.

        **Warning:** This method uses ``assert`` statements and is silently
        inert when Python is run with ``-O`` or ``-OO``. It is for test-time
        invariant verification only; do not call it as a production guard.
        """
        for obj_id, fwd in self._deps.items():
            for dep_id in fwd:
                assert obj_id in self._rdeps.get(dep_id, set()), (
                    f"forward edge {obj_id!r}→{dep_id!r} has no matching reverse edge"
                )
        for dep_id, rev in self._rdeps.items():
            assert rev, f"_rdeps must not contain empty sets; found key {dep_id!r}"
            for obj_id in rev:
                assert dep_id in self._deps.get(obj_id, set()), (
                    f"reverse edge {dep_id!r}→{obj_id!r} has no matching forward edge"
                )

    @staticmethod
    def deps_for_type(obj: GeoObject) -> set[str]:
        """Derive the forward-edge set (direct dependencies) for any object.

        Centralises the per-type edge table so command code never has to
        pattern-match on type names. The table, keyed on ``obj.type``:

        ===========  ===================================================
        Type         Direct dependencies
        ===========  ===================================================
        point        none
        line         ``{point_a_id, point_b_id}``
        polygon      ``set(point_ids)``
        ray          ``{origin_id}``
        vector       ``{origin_id}`` plus ``{endpoint_id}`` when set
        circle       ``{center_id}``
        ball         ``{center_id}``
        cylinder     ``{base_center_id}``
        solid        ``set(layers)`` — ``layers`` is a sequence of Polygon or
                     Point ids.
        tangent      ``{shape_id, point_id}`` — ``shape_id`` is the id of a
                     Circle or Ball.
        ===========  ===================================================

        Raises
        ------
        ValueError
            If ``obj.type`` is not one of the ten known object types.
        AttributeError
            If a correct type string reaches the wrong match arm (e.g. the
            model instance is missing the expected attribute).
        """
        # Dispatch on the string discriminant ``obj.type`` — the same
        # discriminated-union key used by the JSON wire format — rather than
        # ``isinstance``. Deliberate trade-off: a static checker cannot verify
        # the subtype-only attribute reads in each arm, so the exhaustive
        # per-type tests plus the ``case _`` guard are the safety net.
        try:
            match obj.type:
                case "point":
                    return set()
                case "line":
                    return {obj.point_a_id, obj.point_b_id}
                case "polygon":
                    return set(obj.point_ids)
                case "ray":
                    return {obj.origin_id}
                case "vector":
                    deps = {obj.origin_id}
                    if obj.endpoint_id is not None:
                        deps.add(obj.endpoint_id)
                    return deps
                case "circle" | "ball":
                    return {obj.center_id}
                case "cylinder":
                    return {obj.base_center_id}
                case "solid":
                    return set(obj.layers)
                case "tangent":
                    return {obj.shape_id, obj.point_id}
                case _:
                    raise ValueError(f"deps_for_type: unknown object type {obj.type!r}")
        except AttributeError as exc:
            raise AttributeError(
                f"deps_for_type: object {obj.id!r} has type={obj.type!r} but is "
                f"missing an expected attribute — likely a type/class mismatch: {exc}"
            ) from exc
