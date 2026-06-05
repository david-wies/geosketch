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

from geometry.models import GeoObject

__all__ = ["DependencyGraph"]


class DependencyGraph:
    """Reverse-reference graph for O(|affected|) cascade operations.

    Forward edges record what each object depends on; reverse edges record what
    depends on each object. ``dependents_of`` walks the reverse edges to collect
    the full transitive closure of objects affected by a delete or point-move,
    without scanning the entire object store.

    Fields
    ------
    _deps : dict[str, set[str]]
        Forward edges: ``obj_id`` -> set of IDs it depends on.
    _rdeps : dict[str, set[str]]
        Reverse edges: ``obj_id`` -> set of IDs that depend on it.
    """

    def __init__(self) -> None:
        self._deps: dict[str, set[str]] = {}
        self._rdeps: dict[str, set[str]] = {}

    def register(self, obj_id: str, dep_ids: set[str]) -> None:
        """Record that ``obj_id`` depends on every id in ``dep_ids``.

        Safe to call repeatedly: any previously registered edges for ``obj_id``
        are removed first, so re-registration replaces rather than accumulates.
        An empty ``dep_ids`` (e.g. a Point) records the object with no edges.
        """
        # Drop stale forward edges before re-adding, so re-registration with a
        # changed dependency set does not leave orphaned reverse edges behind.
        for old_dep in self._deps.get(obj_id, set()):
            reverse = self._rdeps.get(old_dep)
            if reverse is not None:
                reverse.discard(obj_id)
                if not reverse:
                    del self._rdeps[old_dep]

        self._deps[obj_id] = set(dep_ids)
        for dep_id in dep_ids:
            self._rdeps.setdefault(dep_id, set()).add(obj_id)

    def unregister(self, obj_id: str) -> None:
        """Remove ``obj_id`` from both maps and prune every edge involving it.

        No-op if ``obj_id`` was never registered. Both the object's own forward
        edges and any reverse edges pointing at it are removed, so a later
        ``dependents_of`` never surfaces a deleted object.
        """
        # Remove forward edges out of obj_id and their mirrored reverse edges.
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
                forward.discard(obj_id)

    def dependents_of(self, obj_id: str) -> set[str]:
        """Return the transitive closure of objects that depend on ``obj_id``.

        Breadth-first walk over the reverse edges. The result never includes
        ``obj_id`` itself, and is empty for an unknown id or a leaf that nothing
        references.
        """
        result: set[str] = set()
        queue: deque[str] = deque(self._rdeps.get(obj_id, set()))
        while queue:
            current = queue.popleft()
            if current in result:
                continue
            result.add(current)
            queue.extend(self._rdeps.get(current, set()))
        return result

    def deps_for_type(self, obj: GeoObject) -> set[str]:
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
        solid        ``set(layers)``
        tangent      ``{shape_id, point_id}``
        ===========  ===================================================

        Raises
        ------
        ValueError
            If ``obj.type`` is not one of the ten known object types.
        """
        deps: set[str]
        match obj.type:
            case "point":
                deps = set()
            case "line":
                deps = {obj.point_a_id, obj.point_b_id}
            case "polygon":
                deps = set(obj.point_ids)
            case "ray":
                deps = {obj.origin_id}
            case "vector":
                deps = {obj.origin_id}
                if obj.endpoint_id is not None:
                    deps.add(obj.endpoint_id)
            case "circle" | "ball":
                deps = {obj.center_id}
            case "cylinder":
                deps = {obj.base_center_id}
            case "solid":
                deps = set(obj.layers)
            case "tangent":
                deps = {obj.shape_id, obj.point_id}
            case _:
                raise ValueError(f"deps_for_type: unknown object type {obj.type!r}")
        return deps
