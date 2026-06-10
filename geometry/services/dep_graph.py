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

The preferred entry point for command code is :meth:`DependencyGraph.add`, which
derives the correct dependency set from the object's type automatically. Call
:meth:`DependencyGraph.register` directly only when you have already called
:meth:`DependencyGraph.deps_for_type` yourself and are passing its result in.

The graph stores only IDs — it never holds model instances — so it cannot leak
references and stays valid across save/load as long as the create/delete
commands keep it in sync via :meth:`DependencyGraph.add` and
:meth:`DependencyGraph.unregister`. It imports only the model dataclasses
(:mod:`geometry.models`); no ``tkinter`` or ``matplotlib``.
"""

import logging
from collections import deque
from collections.abc import Iterable
from collections.abc import Set as AbstractSet

from geometry.models import GeoObject

__all__ = ["DependencyGraph"]

_logger = logging.getLogger(__name__)

_EMPTY: AbstractSet[str] = frozenset()


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
        Reverse edges: ``dep_id`` -> set of IDs that depend on it. Empty sets
        are never retained here — a key is dropped the moment its last reverse
        edge is pruned — so the two maps are intentionally asymmetric. Only
        ``_rdeps`` is walked by :meth:`dependents_of`, so its emptiness is what
        matters for query results.
    """

    def __init__(self) -> None:
        # key present iff registered; empty set = no deps (presence marker)
        self._deps: dict[str, set[str]] = {}
        # key present iff >=1 dependent; empty sets are never retained here
        self._rdeps: dict[str, set[str]] = {}

    @staticmethod
    def _validate_obj_id(obj_id: str, method: str) -> None:
        """Reject a non-``str`` or empty ``obj_id`` before any other work.

        Shared by every public method that takes an ``obj_id`` so the type
        guard (``TypeError``, covering ``None``) always fires before the
        empty-string guard (``ValueError``), with a message naming the
        calling method.

        Parameters
        ----------
        obj_id : str
            The candidate identifier to validate.
        method : str
            Public method name to embed in the error message.

        Raises
        ------
        TypeError
            If ``obj_id`` is not a ``str`` (including ``None``).
        ValueError
            If ``obj_id`` is an empty string.
        """
        if not isinstance(obj_id, str):
            raise TypeError(
                f"DependencyGraph.{method}: obj_id must be a str, got {type(obj_id).__name__}"
            )
        if not obj_id:
            raise ValueError(f"DependencyGraph.{method}: obj_id must be a non-empty string")

    def add(self, obj: GeoObject) -> None:
        """Register ``obj`` using the dependency set derived from its own type.

        Convenience wrapper that couples :meth:`register` to
        :meth:`deps_for_type`, so a caller cannot accidentally register an
        incomplete edge set (which would cause a cascade delete triggered from
        a missing dependency to silently skip this object). Command code should
        prefer this over calling :meth:`register` directly; :meth:`register`
        stays available for tests and for callers that already hold a result
        from :meth:`deps_for_type`.

        The inverse operation is :meth:`unregister` called with ``obj.id``;
        there is intentionally no ``remove(obj)`` method, since unregister only
        needs the id.

        Parameters
        ----------
        obj : GeoObject
            The object to register. ``obj.type`` and all type-specific reference
            fields must be set correctly; see :meth:`deps_for_type` for the
            per-type edge table.

        Raises
        ------
        ValueError
            If ``obj.type`` is not one of the ten known object types, or if
            ``obj.id`` is an empty string, any derived dependency id is an
            empty string, or ``deps_for_type`` raises for any other reason
            (propagated with context identifying the object id and type).
        AttributeError
            If ``obj.type`` is a known type but a required type-specific
            attribute is missing on the instance (model dataclass inconsistent
            with its type discriminant).
        """
        # Read type/id into locals before the try block: if obj lacks these
        # base attributes, evaluating them inside the except format string would
        # raise a second AttributeError inside the handler (double traceback).
        obj_type = obj.type
        obj_id = obj.id
        try:
            dep_ids = self.deps_for_type(obj)
            self.register(obj_id, dep_ids)
        except AttributeError as exc:
            raise AttributeError(
                f"DependencyGraph.add: expected attributes for type {obj_type!r} "
                f"missing on object {obj_id!r}: {exc}"
            ) from exc
        except ValueError as exc:
            raise ValueError(
                f"DependencyGraph.add: cannot register type {obj_type!r} "
                f"on object {obj_id!r}: {exc}"
            ) from exc

    def register(self, obj_id: str, dep_ids: Iterable[str]) -> None:
        """Record that ``obj_id`` depends on every id in ``dep_ids``.

        Safe to call repeatedly: any previously registered edges for ``obj_id``
        are removed first, so re-registration replaces rather than accumulates.
        An empty ``dep_ids`` (e.g. a Point) records the object with no edges.

        Prefer :meth:`add` over calling this directly unless you called
        :meth:`deps_for_type` yourself and are passing its result directly —
        ``add`` derives the correct edge set from the object's type so a
        partial manual set cannot be accidentally passed.

        Parameters
        ----------
        obj_id : str
            Non-empty string identifier of the object being registered.
        dep_ids : Iterable[str]
            IDs of objects that ``obj_id`` directly depends on. May be empty.

        Raises
        ------
        TypeError
            If ``obj_id`` is not a ``str`` (including ``None``), or if any
            element of ``dep_ids`` is not a ``str``.
        ValueError
            If ``obj_id`` is an empty string, or if any element of ``dep_ids``
            is an empty string.
        """
        # Materialise and FULLY validate the new dependency set BEFORE any
        # mutation, so a bad input (None/empty obj_id or None/empty dep id)
        # cannot leave the graph half-updated on a re-registration.
        self._validate_obj_id(obj_id, "register")
        dep_set = set(dep_ids)
        for dep_id in dep_set:
            if not isinstance(dep_id, str):
                raise TypeError(
                    f"DependencyGraph.register: dep_ids must contain only str, "
                    f"got {type(dep_id).__name__}"
                )
        if "" in dep_set:
            raise ValueError("DependencyGraph.register: dep_ids must not contain empty strings")

        # Drop stale forward edges before re-adding, so re-registration with a
        # changed dependency set does not leave orphaned reverse edges behind.
        for old_dep in self._deps.get(obj_id, _EMPTY):
            reverse = self._rdeps.get(old_dep)
            if reverse is not None:
                reverse.discard(obj_id)
                if not reverse:
                    del self._rdeps[old_dep]

        self._deps[obj_id] = dep_set
        for dep_id in dep_set:
            self._rdeps.setdefault(dep_id, set()).add(obj_id)

    def unregister(self, obj_id: str, *, strict: bool = False) -> None:
        """Remove ``obj_id`` from both maps and prune every edge involving it.

        Both the object's own forward edges and any reverse edges pointing at
        it are removed, so a later :meth:`dependents_of` never surfaces a
        deleted object. No-op if ``obj_id`` was never registered (unless
        ``strict`` is set).

        For cascade deletes, prefer :meth:`cascade_unregister` — it bundles
        the whole protocol (closure query, dependent removal, root removal)
        into one call and reports exactly what it removed. Note that
        :meth:`cascade_unregister` calls this method with ``strict=False``
        internally, so hand-rolling the protocol with ``strict=True`` is not
        equivalent: the strict variant raises ``KeyError`` on a double-delete
        that the convenience wrapper would silently absorb.

        See Also
        --------
        cascade_unregister : Preferred cascade-delete entry point.

        Notes
        -----
        Advanced path — callers hand-rolling a cascade delete must query
        :meth:`dependents_of`, unregister every returned dependent, and then
        unregister the root ``obj_id`` separately so all forward edges stay
        consistent with the remaining graph state.

        Parameters
        ----------
        obj_id : str
            The object to remove from the graph.
        strict : bool, optional
            If ``True`` and ``obj_id`` is not currently registered, raise
            ``KeyError`` instead of silently ignoring the call. Use
            ``strict=True`` to surface double-delete bugs rather than hiding
            them (but see above — :meth:`cascade_unregister` deliberately
            uses ``strict=False``). Default is ``False``.

        Raises
        ------
        TypeError
            If ``obj_id`` is not a ``str`` (including ``None``).
        ValueError
            If ``obj_id`` is an empty string.
        KeyError
            If ``strict`` is ``True`` and ``obj_id`` is not registered.
        RuntimeError
            If an internal bidirectional invariant violation is detected during
            unregistration (indicates out-of-band corruption of the graph).
        """
        self._validate_obj_id(obj_id, "unregister")
        if strict and obj_id not in self._deps:
            raise KeyError(
                f"DependencyGraph.unregister: {obj_id!r} is not registered (strict=True)"
            )

        # Pre-check: scan the reverse edges about to be processed and verify
        # the bidirectional invariant BEFORE touching _deps or _rdeps.  Any
        # dependent listed in _rdeps[obj_id] must have a matching _deps entry;
        # if one is missing the graph is already corrupted and we must raise
        # now — before any mutation — so the caller can see a clean error
        # without a partially-updated graph as a side-effect.
        pending_dependents = self._rdeps.get(obj_id, _EMPTY)
        for dependent in pending_dependents:
            if dependent not in self._deps:
                _logger.error(
                    "DependencyGraph.unregister: _rdeps[%r] lists dependent %r "
                    "with no _deps entry; bidirectional invariant violated.",
                    obj_id,
                    dependent,
                )
                raise RuntimeError(
                    f"DependencyGraph.unregister: _rdeps[{obj_id!r}] lists dependent "
                    f"{dependent!r} with no _deps entry; bidirectional invariant violated."
                )

        # Remove forward edges out of obj_id and their mirrored reverse edges.
        # No-op if obj_id was never registered (pop returns the empty default).
        for dep_id in self._deps.pop(obj_id, _EMPTY):
            reverse = self._rdeps.get(dep_id)
            if reverse is not None:
                reverse.discard(obj_id)
                if not reverse:
                    del self._rdeps[dep_id]

        # Remove reverse edges into obj_id and their mirrored forward edges.
        # The pre-check above guarantees every dependent has a _deps entry, so
        # the ``forward is None`` branch below is now a true unreachable
        # backstop (left in place for belt-and-suspenders defence).
        for dependent in self._rdeps.pop(obj_id, _EMPTY):
            forward = self._deps.get(dependent)
            if forward is None:  # pragma: no cover — caught by pre-check above
                raise RuntimeError(
                    f"DependencyGraph.unregister: _rdeps[{obj_id!r}] lists dependent "
                    f"{dependent!r} with no _deps entry; bidirectional invariant violated."
                )
            # Intentionally do NOT delete an emptied forward set: a
            # dependent that loses its last edge is still a registered
            # object, and an empty ``_deps`` entry is its presence marker
            # (identical to a freshly registered Point). ``_rdeps`` is the
            # map that must stay free of empty sets; see the class docstring.
            forward.discard(obj_id)

    def cascade_unregister(self, obj_id: str) -> frozenset[str]:
        """Unregister ``obj_id`` and every transitively dependent object.

        Convenience wrapper around the three-step cascade-delete protocol:
        collect the transitive closure, unregister each dependent (in an
        arbitrary order, since all dependents are removed together), and then
        unregister ``obj_id`` itself if — and only if — it was registered.
        The command layer should use this instead of hand-rolling the three
        steps so the order invariant cannot be violated accidentally.

        The return set contains **exactly** the IDs that were actually
        unregistered by this call, so the command layer can mirror the graph
        mutation onto the project store one-to-one:

        * ``obj_id`` registered, with dependents — all dependents plus
          ``obj_id``.
        * ``obj_id`` registered, no dependents — ``frozenset({obj_id})``.
        * ``obj_id`` not registered, but referenced by registered dependents
          (a forward reference: others were registered naming it before it
          registered itself) — the dependents only; ``obj_id`` is excluded
          because it had no ``_deps`` entry to remove.
        * ``obj_id`` completely unknown — ``frozenset()``; no mutation occurs.

        Parameters
        ----------
        obj_id : str
            The root object to delete.  Must be a non-empty string.  Need not
            be currently registered; see the case table above for what is
            returned and unregistered in each situation.

        Returns
        -------
        frozenset[str]
            Exactly the IDs that were unregistered by this call.  Includes
            ``obj_id`` itself only when ``obj_id`` was registered at the time
            of the call.  Empty when ``obj_id`` is unknown to the graph.

        Raises
        ------
        TypeError
            If ``obj_id`` is not a ``str`` (propagated from
            :meth:`dependents_of`).
        ValueError
            If ``obj_id`` is an empty string (propagated from
            :meth:`dependents_of`).
        RuntimeError
            If an internal bidirectional invariant violation is detected
            (propagated from the pre-mutation check in :meth:`unregister`);
            the graph was already corrupted out-of-band before this call.
        """
        affected = self.dependents_of(obj_id)
        root_registered = self.is_registered(obj_id)
        for dep in affected:
            self.unregister(dep)
        if root_registered:
            self.unregister(obj_id)
            return affected | frozenset({obj_id})
        return affected

    def dependents_of(self, obj_id: str) -> frozenset[str]:
        """Return the transitive closure of objects that depend on ``obj_id``.

        Breadth-first walk over the reverse edges. The result is empty for an
        unknown id or a leaf that nothing references. To distinguish an unknown
        id from a registered leaf with no dependents, use :meth:`is_registered`.

        Callers performing a cascade delete must also call
        ``unregister(obj_id)`` after unregistering all returned dependents —
        the queried object is excluded from the result set but must be pruned
        separately to fully clean the graph (or use :meth:`cascade_unregister`,
        which does all of this in one call).

        Parameters
        ----------
        obj_id : str
            The object whose transitive dependents to collect. Must be a
            non-empty string.

        Returns
        -------
        frozenset[str]
            All object ids that transitively depend on ``obj_id``. The
            frozenset is a read-only snapshot; it cannot be mutated and does
            not share state with the graph. In the well-formed DAG that the
            real domain always produces, ``obj_id`` itself never appears in
            the result. In a pathological cycle, however, ``obj_id`` **will**
            appear: the BFS seeds the result from the first-wave dependents
            only and never pre-places ``obj_id`` into the visited set, so a
            reverse path leading back to it collects it. The BFS terminates
            regardless because the visited-guard prevents re-enqueueing any
            already-collected node.

        Raises
        ------
        TypeError
            If ``obj_id`` is not a ``str`` (including ``None``).
        ValueError
            If ``obj_id`` is an empty string.
        """
        self._validate_obj_id(obj_id, "dependents_of")
        result: set[str] = set()
        queue: deque[str] = deque()
        first_wave = self._rdeps.get(obj_id, _EMPTY)
        result.update(first_wave)
        queue.extend(first_wave)
        while queue:
            current = queue.popleft()
            for node in self._rdeps.get(current, _EMPTY):
                if node not in result:
                    result.add(node)
                    queue.append(node)
        return frozenset(result)

    def is_registered(self, obj_id: str) -> bool:
        """Return whether ``obj_id`` is currently tracked by the graph.

        Exposes the presence-marker invariant: every registered object has a
        ``_deps`` entry, even if its dependency set is empty (e.g. a Point).
        The command layer can use this to check graph state after load without
        exposing ``_deps`` directly.

        Parameters
        ----------
        obj_id : str
            The object id to query. Must be a non-empty string.

        Returns
        -------
        bool
            ``True`` if ``obj_id`` has an entry in ``_deps``; ``False``
            otherwise.

        Raises
        ------
        TypeError
            If ``obj_id`` is not a ``str`` (including ``None``).
        ValueError
            If ``obj_id`` is an empty string.
        """
        self._validate_obj_id(obj_id, "is_registered")
        return obj_id in self._deps

    def _test_only_rdep_key_exists(self, dep_id: str) -> bool:
        """Return whether ``dep_id`` is tracked as a dependency in the reverse edges.

        Test-only predicate so the test suite can assert ``_rdeps``-key pruning
        without reaching into the protected map directly (avoids
        protected-attribute access warnings at every call site). Not part of
        the public API; production code must not call it.

        Parameters
        ----------
        dep_id : str
            The candidate dependency id to look up in ``_rdeps``.

        Returns
        -------
        bool
            ``True`` if ``dep_id`` is currently a key in ``_rdeps``.
        """
        return dep_id in self._rdeps

    def _test_only_dep_ids_of(self, obj_id: str) -> frozenset[str]:
        """Return a read-only snapshot of ``obj_id``'s forward-edge set.

        Test-only accessor so the test suite can assert per-object forward-edge
        pruning without poking ``_deps`` directly. Returns an empty frozenset
        for an unregistered id (no distinction from a registered object whose
        dependency set is empty — use :meth:`is_registered` for that). Not part
        of the public API; production code must not call it.

        Parameters
        ----------
        obj_id : str
            The object whose direct dependencies to snapshot.

        Returns
        -------
        frozenset[str]
            The ids ``obj_id`` directly depends on; empty if unregistered or
            registered with no dependencies.
        """
        return frozenset(self._deps.get(obj_id, _EMPTY))

    def _test_only_assert_consistent(self) -> None:
        """Assert the bidirectional mirror invariant holds on both maps.

        Every forward edge ``(obj_id, dep_id)`` in ``_deps`` must have a
        matching reverse edge in ``_rdeps``, and vice versa. ``_rdeps`` must
        never contain an empty set. Call this at the end of mutation-heavy
        test scenarios to catch any regression that silently breaks the mirror.

        **Note on ``_rdeps`` keys vs. values (the asymmetry):** An ``_rdeps``
        *key* is a *dependency* that something references; it need not itself be
        registered in ``_deps`` (callers may register a dependent before its
        dependency, so the key is a forward reference and asserting its presence
        in ``_deps`` would flag valid references, not bugs). By contrast, every
        *member* of an ``_rdeps`` value set is a *dependent*, and a dependent
        always has a ``_deps`` entry created by its own :meth:`register` call —
        which is why the ``forward is None`` backstop in :meth:`unregister`
        cannot fire via the public API. These two statements describe different
        scenarios (an unregistered dependency-key versus a guaranteed-registered
        dependent-member) and so do not conflict. The pruning logic in
        :meth:`unregister` ensures no stale ``_rdeps`` entries survive a
        properly ordered cascade delete.

        **Warning:** This protected helper is not part of the public API. It
        raises ``AssertionError`` explicitly (no ``assert`` statements), so it
        is **not** disabled by running Python with ``-O``/``-OO``. It is still
        intended for test-time invariant verification only — its O(|edges|)
        full-graph scan makes it unsuitable as a production guard.

        Raises
        ------
        AssertionError
            If any forward edge is missing its reverse mirror, any reverse edge
            is missing its forward mirror, or ``_rdeps`` contains an empty set.
        """
        for obj_id, fwd in self._deps.items():
            for dep_id in fwd:
                if obj_id not in self._rdeps.get(dep_id, _EMPTY):
                    raise AssertionError(
                        f"forward edge {obj_id!r}→{dep_id!r} has no matching reverse edge"
                    )
        for dep_id, rev in self._rdeps.items():
            if not rev:
                raise AssertionError(f"_rdeps must not contain empty sets; found key {dep_id!r}")
            for obj_id in rev:
                if dep_id not in self._deps.get(obj_id, _EMPTY):
                    raise AssertionError(
                        f"reverse edge {dep_id!r}→{obj_id!r} has no matching forward edge"
                    )

    @staticmethod
    def deps_for_type(obj: GeoObject) -> set[str]:  # pylint: disable=too-many-branches
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
        solid        ``set(layers)`` — ``layers`` is a ``tuple[str, ...]`` of
                     Polygon (``pg_``) or Point (``pt_``) ids, with at most one
                     Point id (apex/nadir -- must be first or last element;
                     enforced by ``Solid.__post_init__``). That structural
                     validation (minimum two layers, ``pg_``/``pt_`` prefix
                     rules) lives in ``Solid.__post_init__``; this method
                     adds only its own empty-string reference guard, which
                     defends against instances built outside the dataclass
                     constructor.
        tangent      ``{shape_id, point_id}`` — ``shape_id`` is the id of a
                     Circle or Ball.
        ===========  ===================================================

        Parameters
        ----------
        obj : GeoObject
            The object whose forward-edge set to derive. ``obj.type`` must be
            one of the ten known type strings; all type-specific reference
            attributes must be present on the instance.

        Returns
        -------
        set[str]
            A fresh set of IDs that ``obj`` directly depends on. Empty for a
            Point.

        Raises
        ------
        ValueError
            If ``obj.type`` is not one of the ten known object types.
        AttributeError
            If a known type string is present but the expected type-specific
            attribute is missing on the instance (programming error — the
            model dataclass is inconsistent with its type discriminant).
        """
        # Dispatch on the string discriminant ``obj.type`` — the same
        # discriminated-union key used by the JSON wire format — rather than
        # ``isinstance``. Deliberate trade-off: a static checker cannot verify
        # the subtype-only attribute reads in each arm, so the exhaustive
        # per-type tests plus the ``case _`` guard are the safety net.
        # The ten-arm match plus per-arm validation exceeds pylint's default
        # branch limit; the disable is on the method signature above.
        match obj.type:
            case "point":
                return set()
            case "line":
                if not obj.point_a_id or not obj.point_b_id:
                    raise ValueError(
                        f"deps_for_type: line {obj.id!r} has empty point reference "
                        f"(point_a_id={obj.point_a_id!r}, point_b_id={obj.point_b_id!r})"
                    )
                return {obj.point_a_id, obj.point_b_id}
            case "polygon":
                # Polygon.__post_init__ does not enforce a minimum vertex
                # count, so an empty point_ids list would otherwise register
                # the polygon with no edges — indistinguishable from a Point
                # and invisible to every cascade. Reject it here.
                if not obj.point_ids:
                    raise ValueError(f"deps_for_type: polygon {obj.id!r} has no point references")
                if "" in obj.point_ids:
                    raise ValueError(
                        f"deps_for_type: polygon {obj.id!r} has empty point reference "
                        f"in point_ids={obj.point_ids!r}"
                    )
                return set(obj.point_ids)
            case "ray":
                if not obj.origin_id:
                    raise ValueError(f"deps_for_type: ray {obj.id!r} has empty origin reference")
                return {obj.origin_id}
            case "vector":
                if not obj.origin_id:
                    raise ValueError(f"deps_for_type: vector {obj.id!r} has empty origin reference")
                deps = {obj.origin_id}
                if obj.endpoint_id is not None:
                    if not obj.endpoint_id:
                        raise ValueError(
                            f"deps_for_type: vector {obj.id!r} has empty endpoint reference"
                        )
                    deps.add(obj.endpoint_id)
                return deps
            case "circle" | "ball":
                if not obj.center_id:
                    raise ValueError(
                        f"deps_for_type: {obj.type} {obj.id!r} has empty center reference"
                    )
                return {obj.center_id}
            case "cylinder":
                if not obj.base_center_id:
                    raise ValueError(
                        f"deps_for_type: cylinder {obj.id!r} has empty base center reference"
                    )
                return {obj.base_center_id}
            case "solid":
                if "" in obj.layers:
                    raise ValueError(
                        f"deps_for_type: solid {obj.id!r} has empty layer reference "
                        f"in layers={obj.layers!r}"
                    )
                # Duplicate layer ids collapse intentionally: cascade semantics
                # only need whether a dependency is referenced at least once.
                return set(obj.layers)
            case "tangent":
                if not obj.shape_id or not obj.point_id:
                    raise ValueError(
                        f"deps_for_type: tangent {obj.id!r} has empty reference "
                        f"(shape_id={obj.shape_id!r}, point_id={obj.point_id!r})"
                    )
                return {obj.shape_id, obj.point_id}
            case _:
                raise ValueError(f"deps_for_type: unknown object type {obj.type!r}")
