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

"""Command pattern and undo/redo history for GeoSketch mutations.

Every user-visible change to the object store — create, delete, modify, move,
re-vertex, bulk-import — is expressed as a :class:`Command`: an object that
knows how to apply itself (:meth:`Command.do`) and how to reverse itself
(:meth:`Command.undo`). :class:`CommandHistory` records the applied commands in
a bounded undo buffer and a redo stack, so the UI can step backwards and
forwards through the edit history.

Why a command per mutation, rather than diffing snapshots
---------------------------------------------------------
The object store is a flat ``dict[str, GeoObject]`` keyed by ID string, and
every inter-object reference is an ID string rather than a memory pointer (see
``CLAUDE.md`` §4). That means a command can swap a whole object *instance* in
and out of the dict on do/undo without breaking any referrer — nobody holds a
pointer to the old instance.

Two restore strategies coexist, chosen per command:

* **Deepcopy snapshots** — the three *editing* commands
  (:class:`ModifyObjectCommand`, :class:`MovePointCommand`,
  :class:`ModifyPolygonVerticesCommand`) take :func:`copy.deepcopy` snapshots of
  the affected objects before and after the edit and restore those snapshots
  verbatim, which is simpler and more robust than computing field-level diffs.
* **Live-instance swap** — :class:`CreateObjectCommand` reuses the single live
  instance it was handed, and :class:`CascadeDeleteCommand` stores live
  references to the instances it removes. No deepcopy is needed because a
  removed (or not-yet-inserted) instance is never mutated in place while it is
  out of the store, so swapping it back in restores the original field state
  faithfully.

Collaborators, not a Project
----------------------------
``geometry/project.py`` is still an empty stub, so there is no ``Project`` class
to own the store. Each command is instead constructed with the three live
collaborators it needs:

* ``objects`` — the ``dict[str, GeoObject]`` object store (ID -> object);
* ``graph`` — the :class:`~geometry.services.dep_graph.DependencyGraph` that
  tracks reference edges for cascade delete and point-move recompute;
* ``bus`` — the :class:`~geometry.utils.events.EventBus` that notifies the UI.

A future ``Project`` will own all three and push commands into a
:class:`CommandHistory`; until then the command layer stands alone and the tests
wire the collaborators directly. This module imports only models, services, and
utils — never ``tkinter`` or ``matplotlib``.

Recompute on point move
-----------------------
A :class:`MovePointCommand` is the one command that derives new field values
rather than merely restoring a snapshot: moving a Point changes the stored
directions/distances of everything that references it. The per-type recompute
rules live in :func:`MovePointCommand._recompute_dependent`; its docstring is
the reference for which derived scalars each dependent type caches.
"""

from __future__ import annotations

import copy
import dataclasses
import logging
from collections import deque
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from geometry.models import GeoObject
from geometry.models.common import DirectionMode
from geometry.models.line import Line
from geometry.models.polygon import Polygon
from geometry.models.tangent import Tangent
from geometry.models.vector import Vector
from geometry.services import validation
from geometry.services.dep_graph import DependencyGraph
from geometry.services.geometry import azimuth as _azimuth
from geometry.services.geometry import distance as _distance
from geometry.services.geometry import elevation as _elevation
from geometry.services.geometry import is_convex as _is_convex
from geometry.services.geometry import signed_area as _signed_area
from geometry.services.geometry import tangent_direction as _tangent_direction
from geometry.utils.angles import azimuth_to_angle, normalize_to_2pi
from geometry.utils.events import (
    HISTORY_CHANGED,
    OBJECT_CREATED,
    OBJECT_DELETED,
    OBJECT_MODIFIED,
    PROJECT_LOADED,
    EventBus,
)

__all__ = [
    "MAX_HISTORY",
    "Command",
    "CommandHistory",
    "CreateObjectCommand",
    "CascadeDeleteCommand",
    "ModifyObjectCommand",
    "MovePointCommand",
    "ModifyPolygonVerticesCommand",
    "BulkImportCommand",
]

_logger = logging.getLogger(__name__)

#: Maximum number of commands retained in the undo buffer. Older commands are
#: silently dropped once this bound is exceeded (the ``deque`` ``maxlen``
#: semantics). Redo is unbounded between actions but is cleared whenever a fresh
#: command is pushed, so it never grows past the undo bound either.
MAX_HISTORY = 100


@runtime_checkable
class Command(Protocol):
    """Structural protocol for an undoable mutation.

    Any object exposing a ``description`` string plus :meth:`do` and
    :meth:`undo` methods satisfies this protocol; :class:`CommandHistory` relies
    only on these three members and never on a concrete base class, so command
    classes need not inherit from anything. ``@runtime_checkable`` lets tests
    assert ``isinstance(cmd, Command)`` structurally.

    Caveat: ``@runtime_checkable`` only checks **member presence**. An
    ``isinstance(cmd, Command)`` test passes as long as the object has
    ``description``, ``do`` and ``undo`` attributes — it does *not* verify their
    signatures, that ``do``/``undo`` are callable with no required arguments, or
    that ``description`` is actually a ``str``. Treat a passing check as "looks
    structurally command-shaped", not as a full contract guarantee.

    The contract is that :meth:`undo` exactly reverses the state change made by
    the most recent :meth:`do`, so that an arbitrary ``do``/``undo``/``do`` …
    sequence is always consistent with the object store.

    Fields
    ------
    description : str
        Short human-readable label for the command (e.g. shown in an Edit menu
        "Undo <description>" item).
    """

    description: str

    def do(self) -> None:
        """Apply the mutation to the object store, graph, and event bus."""

    def undo(self) -> None:
        """Reverse the mutation applied by the most recent :meth:`do`."""


class CommandHistory:
    """Bounded undo buffer plus redo stack over :class:`Command` objects.

    The undo buffer is a :class:`collections.deque` capped at :data:`MAX_HISTORY`
    entries: pushing past the cap silently discards the oldest command, which is
    the standard "you can only undo the last N actions" behaviour. The redo
    stack is an ordinary list, cleared every time a *new* command is pushed —
    once you take a fresh action, the branch you had undone is no longer
    reachable.

    Every state-changing method fires :data:`~geometry.utils.events.HISTORY_CHANGED`
    carrying the current :attr:`can_undo` / :attr:`can_redo` flags, so a toolbar
    can enable/disable its Undo/Redo controls without polling. The history also
    subscribes to :data:`~geometry.utils.events.PROJECT_LOADED` and clears itself
    when a new project is loaded — undo history from the previous project is
    meaningless against the new object store.

    The bus is **required** (no ``None`` default): a missing bus would silently
    disable the :data:`PROJECT_LOADED` self-clear, a real behavioural divergence,
    and is inconsistent with the command classes which all require a non-optional
    bus. Event-agnostic tests can simply pass a fresh ``EventBus()`` with no
    subscribers, which makes every ``fire`` a no-op.

    Fields
    ------
    _bus : EventBus
        Event bus used to publish :data:`HISTORY_CHANGED` and to receive
        :data:`PROJECT_LOADED`.
    _undo : collections.deque[Command]
        Applied commands, oldest at the left, newest at the right. Capped at
        :data:`MAX_HISTORY`; overflow drops the oldest entry.
    _redo : list[Command]
        Commands that have been undone and may be re-applied, newest on top
        (end of the list). Cleared by :meth:`push`.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._undo: deque[Command] = deque(maxlen=MAX_HISTORY)
        self._redo: list[Command] = []
        # Clear history on project load: undo entries reference objects from
        # the previous project and would corrupt the freshly loaded store.
        bus.subscribe(PROJECT_LOADED, self._on_project_loaded)

    def _on_project_loaded(self) -> None:
        """Clear all history when a new project is loaded (bus handler)."""
        self.clear()

    def _fire_history_changed(self) -> None:
        """Publish :data:`HISTORY_CHANGED` with the current undo/redo flags."""
        self._bus.fire(HISTORY_CHANGED, can_undo=self.can_undo, can_redo=self.can_redo)

    @property
    def can_undo(self) -> bool:
        """Whether at least one command is available to undo."""
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        """Whether at least one undone command is available to redo."""
        return bool(self._redo)

    def push(self, cmd: Command) -> None:
        """Apply ``cmd`` and record it as the newest undoable command.

        Calls ``cmd.do()`` first so a command that raises mid-apply never enters
        the history (the buffers stay consistent with the store). On success the
        command is appended to the undo buffer and the redo stack is cleared —
        taking a new action invalidates any previously undone branch.

        Parameters
        ----------
        cmd : Command
            The command to apply and record.
        """
        cmd.do()
        self._undo.append(cmd)
        self._redo.clear()
        self._fire_history_changed()

    def undo(self) -> Command | None:
        """Reverse the newest command and move it to the redo stack.

        The top command is *peeked* and :meth:`Command.undo` is applied before
        either stack is mutated. If ``undo`` raises (e.g. a bus handler throws —
        :meth:`EventBus.fire` propagates — or a partial mutation fails) the
        command stays on the undo stack and :data:`HISTORY_CHANGED` never fires,
        so the failed transition is fully recoverable rather than losing the
        command from both stacks.

        Returns
        -------
        Command or None
            The command that was undone, or ``None`` if the undo buffer was
            empty (no-op).
        """
        if not self._undo:
            return None
        cmd = self._undo[-1]  # peek; stacks untouched if undo() raises
        cmd.undo()
        self._undo.pop()
        self._redo.append(cmd)
        self._fire_history_changed()
        return cmd

    def redo(self) -> Command | None:
        """Re-apply the most recently undone command.

        The top command is *peeked* and :meth:`Command.do` is applied before
        either stack is mutated. If ``do`` raises (e.g. a bus handler throws —
        :meth:`EventBus.fire` propagates — or a partial mutation fails) the
        command stays on the redo stack and :data:`HISTORY_CHANGED` never fires,
        so the failed transition is fully recoverable rather than losing the
        command from both stacks.

        Returns
        -------
        Command or None
            The command that was re-applied, or ``None`` if the redo stack was
            empty (no-op).
        """
        if not self._redo:
            return None
        cmd = self._redo[-1]  # peek; stacks untouched if do() raises
        cmd.do()
        self._redo.pop()
        self._undo.append(cmd)
        self._fire_history_changed()
        return cmd

    def clear(self) -> None:
        """Empty both the undo buffer and the redo stack.

        Fires :data:`HISTORY_CHANGED` so listeners disable their controls. Used
        directly and as the :data:`PROJECT_LOADED` handler.
        """
        self._undo.clear()
        self._redo.clear()
        self._fire_history_changed()


class CreateObjectCommand:
    """Create a single object: insert it into the store and register its edges.

    :meth:`do` adds ``obj`` to the store and registers its dependency edges via
    :meth:`DependencyGraph.add` (which derives the edge set from ``obj.type``),
    then fires :data:`OBJECT_CREATED`. :meth:`undo` removes the object and
    unregisters it, firing :data:`OBJECT_DELETED`. Because references are ID
    strings, re-inserting the same instance on redo restores every referrer
    automatically.

    Single-call semantics: this command assumes :meth:`do` runs before
    :meth:`undo`. :class:`CommandHistory` always calls :meth:`do` first (via
    :meth:`CommandHistory.push`), so no guard is needed in normal use. Calling
    :meth:`undo` prematurely (before any :meth:`do`) would attempt to remove an
    object that the store never received; that missing-key case is handled
    defensively as a logged no-op rather than a bare ``KeyError``.

    Fields
    ------
    description : str
        ``"Create <type> '<name>'"``, captured from ``obj`` at construction.
    _objects : dict[str, GeoObject]
        The object store this command mutates.
    _graph : DependencyGraph
        The dependency graph kept in sync with the store.
    _bus : EventBus
        Event bus for create/delete notifications.
    _obj : GeoObject
        The object to create. The same instance is re-used across do/undo/redo.
    """

    def __init__(
        self,
        objects: dict[str, GeoObject],
        graph: DependencyGraph,
        bus: EventBus,
        obj: GeoObject,
    ) -> None:
        self._objects = objects
        self._graph = graph
        self._bus = bus
        self._obj = obj
        self.description = f"Create {obj.type} '{obj.name}'"

    def do(self) -> None:
        """Insert the object, register its edges, fire :data:`OBJECT_CREATED`.

        The store insert and graph registration are made atomic: if
        :meth:`DependencyGraph.add` raises (e.g. a malformed reference field), the
        just-inserted store entry is removed before the exception propagates, so a
        failed create never leaves the object orphaned in the store with no graph
        edges. This also keeps :class:`BulkImportCommand`'s rollback exact, since
        a failed wrapped create contributes no partial state of its own.
        """
        self._objects[self._obj.id] = self._obj
        try:
            self._graph.add(self._obj)
        except Exception:
            _logger.error(
                "CreateObjectCommand.do: graph registration failed for %r; "
                "removing the just-inserted store entry",
                self._obj.id,
                exc_info=True,
            )
            del self._objects[self._obj.id]
            raise
        self._bus.fire(OBJECT_CREATED, obj_id=self._obj.id)

    def undo(self) -> None:
        """Remove the object, unregister it, fire :data:`OBJECT_DELETED`.

        Guards the store removal: if the object was already removed out-of-band
        (so ``self._obj.id`` is absent from the store) the store removal is a
        logged no-op rather than a bare ``KeyError``. The graph is still
        unregistered in that branch: :meth:`DependencyGraph.unregister` is
        idempotent at its default ``strict=False``, so unregistering an id whose
        store entry is already gone simply prunes any stale graph edge and keeps
        the store and graph in sync (whereas skipping it would leave a dangling
        edge for an object the store no longer holds). No :data:`OBJECT_DELETED`
        fires in that branch — nothing was removed from the store — so it returns
        immediately after the idempotent unregister. On the normal path the
        object is removed, unregistered, and the delete event fired.
        """
        if self._obj.id not in self._objects:
            _logger.warning(
                "CreateObjectCommand.undo: object %r already absent from the store; "
                "treating store removal as a no-op and unregistering (idempotently) "
                "to keep the graph in sync",
                self._obj.id,
            )
            self._graph.unregister(self._obj.id)
            return
        del self._objects[self._obj.id]
        self._graph.unregister(self._obj.id)
        self._bus.fire(OBJECT_DELETED, obj_ids=[self._obj.id])


class CascadeDeleteCommand:
    """Delete an object and its full transitive dependent closure.

    Deleting a Point must also delete every Line/Ray/Vector/Circle/Tangent/
    Polygon that references it, transitively (``CLAUDE.md`` §5). :meth:`do`
    computes the closure from the graph, snapshots every affected live instance,
    removes them all from the store and graph, then fires a single
    :data:`OBJECT_DELETED` carrying the whole removed ID set. :meth:`undo`
    re-inserts every snapshot and re-registers its edges, firing
    :data:`OBJECT_CREATED` per restored object.

    The closure is recomputed inside :meth:`do` (not captured once at
    construction), so a redo after an intervening undo re-derives the identical
    set from the restored graph. The deleted instances are never mutated while
    out of the store, so the snapshot preserves their original IDs and field
    state for a faithful restore.

    Single-call semantics: this command assumes :meth:`do` runs before
    :meth:`undo`. :class:`CommandHistory` always calls :meth:`do` first, so no
    guard is required; a premature :meth:`undo` (before any :meth:`do`) simply
    iterates an empty snapshot and is a harmless no-op.

    Atomicity: :meth:`do` removes each ``(store entry, graph edge set)`` pair in
    turn, but if any removal raises mid-cascade it restores every pair already
    removed before re-raising, so the store and graph never disagree about a
    half-deleted closure (and no :data:`OBJECT_DELETED` fires for a failed
    cascade).

    Fields
    ------
    description : str
        ``"Delete <type> '<name>'"`` for the root, captured at construction
        (the root is gone from the store after :meth:`do`, so the label cannot
        be derived lazily).
    _objects : dict[str, GeoObject]
        The object store this command mutates.
    _graph : DependencyGraph
        The dependency graph kept in sync with the store.
    _bus : EventBus
        Event bus for create/delete notifications.
    _root_id : str
        ID of the object whose deletion triggers the cascade.
    _snapshot : dict[str, GeoObject]
        Live instances removed by the most recent :meth:`do`, keyed by ID, used
        to restore them on :meth:`undo`. Empty until the first :meth:`do`.
    """

    def __init__(
        self,
        objects: dict[str, GeoObject],
        graph: DependencyGraph,
        bus: EventBus,
        root_id: str,
    ) -> None:
        self._objects = objects
        self._graph = graph
        self._bus = bus
        self._root_id = root_id
        root = objects[root_id]
        self.description = f"Delete {root.type} '{root.name}'"
        self._snapshot: dict[str, GeoObject] = {}

    def do(self) -> None:
        """Remove the root plus its dependent closure; fire one delete event.

        Removal is atomic: if any per-object removal raises mid-cascade, every
        already-removed object is re-inserted and re-registered before the
        exception propagates, so the store and graph are restored exactly to
        their pre-:meth:`do` state and no partial deletion persists.
        """
        closure = self._graph.dependents_of(self._root_id) | {self._root_id}
        # Store the live instances directly: they are not mutated while deleted,
        # so their original IDs/state are preserved for a faithful undo.
        self._snapshot = {oid: self._objects[oid] for oid in closure if oid in self._objects}
        store_removed: list[GeoObject] = []
        try:
            for oid, obj in self._snapshot.items():
                del self._objects[oid]
                store_removed.append(obj)  # record before the graph call can raise
                self._graph.unregister(oid)
        except Exception:  # pylint: disable=broad-exception-caught
            # Roll back so a failure on the k-th object never leaves the store
            # and graph half-deleted and disagreeing. Restore the store from the
            # objects removed so far, then re-register EVERY snapshot object's
            # edges: unregistering one object collaterally prunes the forward
            # back-edges of *other* objects that referenced it, so re-adding only
            # the fully-removed ones would leave those siblings missing edges.
            # ``add`` replaces (it does not accumulate), so re-adding an object
            # that is still registered is a safe no-op that reinstates its edges.
            #
            # The rollback itself is fault-tolerant: each restore step is guarded
            # so a step that raises is logged and skipped rather than aborting the
            # remaining steps or masking the ORIGINAL exception. The bare ``raise``
            # at the end re-raises that original exception; ``_snapshot`` is always
            # cleared first, so even a partially-failed rollback cannot leave a
            # later ``undo`` re-applying this failed delete.
            _logger.error(
                "CascadeDeleteCommand.do: failed mid-cascade for root %r after "
                "removing %d store entr(ies); rolling back",
                self._root_id,
                len(store_removed),
                exc_info=True,
            )
            for obj in store_removed:
                try:
                    self._objects[obj.id] = obj
                except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught
                    _logger.error(
                        "CascadeDeleteCommand.do: rollback failed to restore store "
                        "entry %r; continuing",
                        obj.id,
                        exc_info=True,
                    )
            for obj in self._snapshot.values():
                try:
                    self._graph.add(obj)
                except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught
                    _logger.error(
                        "CascadeDeleteCommand.do: rollback failed to re-register "
                        "edges for %r; continuing",
                        obj.id,
                        exc_info=True,
                    )
            self._snapshot = {}
            raise
        self._bus.fire(OBJECT_DELETED, obj_ids=list(self._snapshot))

    def undo(self) -> None:
        """Re-insert every removed object and re-register its edges.

        Restoration is atomic and mirrors the hardened :meth:`do` rollback: each
        snapshot object is re-inserted into the store and re-registered in the
        graph in turn, firing :data:`OBJECT_CREATED` per object. If any step
        raises mid-restore, the partial restore is rolled back — the store
        entries re-inserted so far are removed and their graph edges unregistered
        (idempotently, at ``strict=False``) — and the ORIGINAL exception is
        re-raised. Each rollback step is itself guarded so one failing step
        neither aborts the others nor masks the original exception.
        ``_snapshot`` is left intact so the command stays recoverable for a later
        :meth:`undo` retry.
        """
        restored: list[GeoObject] = []
        try:
            for obj in self._snapshot.values():
                self._objects[obj.id] = obj
                restored.append(obj)  # record before the graph call can raise
                self._graph.add(obj)
                self._bus.fire(OBJECT_CREATED, obj_id=obj.id)
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.error(
                "CascadeDeleteCommand.undo: failed mid-restore for root %r after "
                "restoring %d object(s); rolling back the partial restore",
                self._root_id,
                len(restored),
                exc_info=True,
            )
            for obj in restored:
                try:
                    self._objects.pop(obj.id, None)
                    self._graph.unregister(obj.id)
                except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught
                    _logger.error(
                        "CascadeDeleteCommand.undo: rollback failed to remove "
                        "partial restore of %r; continuing",
                        obj.id,
                        exc_info=True,
                    )
            raise


class ModifyObjectCommand:
    """Edit envelope/property fields of one object (no reference change).

    Covers display-envelope and direction-metadata edits such as ``name``,
    ``color``, ``line_color``, ``fill_color``, ``alpha``, ``visibility``,
    ``direction_mode``, and ``direction_units`` — fields whose change does **not**
    alter which other objects this one references. Because no reference changes,
    the dependency graph is left untouched.

    :meth:`do` swaps in an ``after`` copy with the requested changes applied;
    :meth:`undo` swaps the original ``before`` copy back. Both fire
    :data:`OBJECT_MODIFIED`. Changes are applied with :func:`setattr` on a
    deep copy, so the read-only ``id``/``type`` guard is respected and the
    original instance is never mutated in place.

    Fields
    ------
    description : str
        ``"Modify <type> '<name>'"`` derived from the pre-edit object.
    _objects : dict[str, GeoObject]
        The object store this command mutates.
    _obj_id : str
        ID of the object being edited.
    _bus : EventBus
        Event bus for modify notifications.
    _before : GeoObject
        Deep copy of the object as it was before the edit.
    _after : GeoObject
        Deep copy of the object with ``changes`` applied.
    """

    def __init__(
        self,
        objects: dict[str, GeoObject],
        graph: DependencyGraph,
        bus: EventBus,
        obj_id: str,
        changes: dict[str, Any],
    ) -> None:
        # ``graph`` is accepted but unused: an envelope/property edit changes no
        # references, so the dependency graph never needs updating. Keeping it in
        # the signature lets the (future) Project construct every command the
        # same way.
        del graph
        self._objects = objects
        self._obj_id = obj_id
        self._bus = bus
        before = copy.deepcopy(objects[obj_id])
        after = copy.deepcopy(before)
        # Validate every key against the model's declared fields before any
        # setattr, so a typo (e.g. ``"colour"``) raises rather than silently
        # creating a stray attribute that no renderer reads. The models are
        # dataclasses, so ``dataclasses.fields`` is the authoritative field set.
        valid_fields = {f.name for f in dataclasses.fields(after)}
        for key in changes:
            if key not in valid_fields:
                raise ValueError(
                    f"ModifyObjectCommand: unknown field {key!r} for type "
                    f"{before.type!r} (object {obj_id!r})"
                )
        for key, value in changes.items():
            setattr(after, key, value)
        self._before = before
        self._after = after
        self.description = f"Modify {before.type} '{before.name}'"

    def do(self) -> None:
        """Install the edited copy and fire :data:`OBJECT_MODIFIED`."""
        self._objects[self._obj_id] = self._after
        self._bus.fire(OBJECT_MODIFIED, obj_id=self._obj_id)

    def undo(self) -> None:
        """Restore the pre-edit copy and fire :data:`OBJECT_MODIFIED`."""
        self._objects[self._obj_id] = self._before
        self._bus.fire(OBJECT_MODIFIED, obj_id=self._obj_id)


class MovePointCommand:
    """Move a Point's coordinates and recompute every dependent's derived values.

    Moving a Point changes the geometry of everything that references it: a
    Line's stored ``direction``/``elevation``, a Vector's recomputed
    ``length``/``direction``/``elevation`` (endpoint mode only), a Tangent's
    ``direction``, and a Polygon's cached ``is_convex`` (``CLAUDE.md`` §5). This
    command snapshots the point plus every dependent both *before* the move and,
    using a recompute pass, *after* it; :meth:`do` installs the after-state and
    :meth:`undo` restores the before-state, firing :data:`OBJECT_MODIFIED` for
    the point and each affected dependent in turn.

    The graph is **not** touched: a move changes no references, only coordinates,
    so the edge set is invariant. Both snapshots are computed once at
    construction, so do/undo/redo are pure dict swaps with no recomputation.

    Fields
    ------
    description : str
        ``"Move <name>"`` for the moved point.
    _objects : dict[str, GeoObject]
        The object store this command mutates.
    _bus : EventBus
        Event bus for modify notifications.
    _ids : list[str]
        IDs touched by the move: the point first, then each recomputed
        dependent. Drives the per-object :data:`OBJECT_MODIFIED` fan-out.
    _before : dict[str, GeoObject]
        Pre-move deep copies of the point and every dependent, keyed by ID.
    _after : dict[str, GeoObject]
        Post-move deep copies (point with new coords; dependents recomputed
        against the moved store), keyed by ID.
    """

    def __init__(
        self,
        objects: dict[str, GeoObject],
        graph: DependencyGraph,
        bus: EventBus,
        point_id: str,
        *,
        easting: float,
        northing: float,
        altitude: float | None = None,
    ) -> None:
        self._objects = objects
        self._bus = bus
        point = objects[point_id]
        self.description = f"Move {point.name}"

        dependent_ids = [dep_id for dep_id in graph.dependents_of(point_id) if dep_id in objects]

        # Snapshot the before-state: the point and every dependent, untouched.
        self._before: dict[str, GeoObject] = {point_id: copy.deepcopy(point)}
        for dep_id in dependent_ids:
            self._before[dep_id] = copy.deepcopy(objects[dep_id])

        # Build the moved point, then a store view that reflects the move so the
        # recompute helper resolves dependents against the new coordinates.
        moved_point = copy.deepcopy(point)
        moved_point.easting = easting
        moved_point.northing = northing
        if altitude is not None:
            moved_point.altitude = altitude
        moved_store = {**objects, point_id: moved_point}

        self._after: dict[str, GeoObject] = {point_id: moved_point}
        for dep_id in dependent_ids:
            dependent = objects[dep_id]
            try:
                self._after[dep_id] = self._recompute_dependent(dependent, moved_store)
            except ValueError as exc:
                # A move can invalidate a dependent's geometry — e.g. it makes a
                # Tangent's surface point coincide horizontally with its circle's
                # center, so ``tangent_direction`` raises "zero-radius circle has
                # no tangent". The failure happens here in ``__init__`` before any
                # store mutation, so the store/graph stay clean; re-raise with the
                # moved point and offending dependent named, and the move rejected.
                _logger.error(
                    "MovePointCommand: moving point %r would invalidate dependent "
                    "%r; rejecting the move (%s)",
                    point_id,
                    dep_id,
                    exc,
                    exc_info=True,
                )
                raise ValueError(
                    f"Cannot move point {point_id!r}: it would invalidate dependent "
                    f"{dep_id!r} ({exc}); the move was rejected"
                ) from exc
            except (KeyError, AttributeError) as exc:
                # A dangling reference rather than invalid geometry: e.g. the
                # dependent names a store id (an endpoint, a circle center) that
                # is absent, so ``_recompute_dependent`` raises ``KeyError`` (or
                # ``AttributeError`` resolving a field on a missing object). This
                # is a structural inconsistency, not a user-rejectable geometry
                # error, so surface it as a ``RuntimeError`` naming the move and
                # the offending dependent, chained from the original exception.
                _logger.error(
                    "MovePointCommand: recompute of dependent %r for moved point %r "
                    "hit a dangling reference (%r)",
                    dep_id,
                    point_id,
                    exc,
                    exc_info=True,
                )
                raise RuntimeError(
                    f"Cannot move point {point_id!r}: dependent {dep_id!r} has a "
                    f"dangling reference ({exc!r}); the store is inconsistent"
                ) from exc

        # Point first so the UI updates the marker before its dependents.
        self._ids = [point_id, *dependent_ids]

    @staticmethod
    def _recompute_dependent(obj: GeoObject, store: dict[str, GeoObject]) -> GeoObject:
        """Return a deep copy of ``obj`` with its point-derived scalars refreshed.

        ``store`` must already reflect the moved point's new coordinates. The
        per-type rules:

        * **Line** — recompute ``direction`` (azimuth ``point_a -> point_b``,
          converted to the line's ``direction_mode``) and ``elevation``.
        * **Vector** — only in Origin+Endpoint mode (``endpoint_id is not None``):
          recompute ``direction``, ``elevation``, and ``length`` from
          ``origin -> endpoint``. In Length+Direction mode the vector merely
          translates with its origin, so it is returned unchanged.
        * **Ray** — a ray is an origin plus an *intrinsic* direction, so moving
          its origin only translates it; nothing point-derived is stored, hence
          a no-op copy (this is why Ray differs from Line/Vector despite the
          issue grouping them together).
        * **Tangent** — recompute ``direction`` from
          :func:`~geometry.services.geometry.tangent_direction` (center -> point),
          converted to the tangent's mode. ``elevation`` is intentionally left
          as-is: a Circle tangent keeps ``elevation == 0.0`` and a Ball tangent
          keeps its user-supplied elevation.
        * **Polygon** — recompute the cached ``is_convex`` flag.
        * **Circle / Ball / Cylinder / Solid** — no point-derived stored scalar,
          returned as an unchanged copy.

        Parameters
        ----------
        obj : GeoObject
            The dependent to recompute (not mutated; a copy is returned).
        store : dict[str, GeoObject]
            Object store already reflecting the moved point's coordinates.

        Returns
        -------
        GeoObject
            A deep copy of ``obj`` with refreshed derived scalars.
        """
        result = copy.deepcopy(obj)
        if isinstance(result, Line):
            az = float(_azimuth(store[result.point_a_id], store[result.point_b_id]))
            result.direction = MovePointCommand._directed_value(az, result.direction_mode)
            result.elevation = float(_elevation(store[result.point_a_id], store[result.point_b_id]))
        elif isinstance(result, Vector):
            # Length+Direction vectors (endpoint_id is None) translate with the
            # origin and store no point-derived geometry, so leave them as-is.
            if result.endpoint_id is not None:
                origin = store[result.origin_id]
                endpoint = store[result.endpoint_id]
                az = float(_azimuth(origin, endpoint))
                result.direction = MovePointCommand._directed_value(az, result.direction_mode)
                result.elevation = float(_elevation(origin, endpoint))
                result.length = float(_distance(origin, endpoint))
        elif isinstance(result, Tangent):
            shape = store[result.shape_id]
            center = store[shape.center_id]
            point = store[result.point_id]
            az = float(_tangent_direction(center, point))
            result.direction = MovePointCommand._directed_value(az, result.direction_mode)
            # elevation is deliberately not recomputed (see method docstring).
        elif isinstance(result, Polygon):
            # Per spec (MVP.md:1087-1088) a point move refreshes only the cached
            # convexity flag; it deliberately does NOT re-wind or re-validate
            # simplicity of a polygon containing the moved point. Re-winding and
            # simplicity validation are ModifyPolygonVerticesCommand's job (a
            # vertex-set edit), not a coordinate move's — do not "fix" this to
            # call the polygon validators here.
            result.is_convex = bool(_is_convex(result, store))
        # Ray / Circle / Ball / Cylinder / Solid: unchanged copy.
        return result

    @staticmethod
    def _directed_value(az: float, mode: DirectionMode) -> float:
        """Convert an azimuth (radians) into the stored value for ``mode``.

        In :attr:`DirectionMode.AZIMUTH` the azimuth is stored directly
        (normalised into ``[0, 2π)``); in :attr:`DirectionMode.ANGLE` it is
        converted to a math angle via :func:`azimuth_to_angle`, which already
        returns a ``normalize_to_2pi`` result, so no second normalisation is
        applied there. Mirrors the conversion the creation path uses so a moved
        object's stored ``direction`` matches a freshly created one.

        Parameters
        ----------
        az : float
            Azimuth in radians (CW from North).
        mode : DirectionMode
            The dependent object's stored direction convention.

        Returns
        -------
        float
            The value to store in the object's ``direction`` field.
        """
        if mode is DirectionMode.AZIMUTH:
            return float(normalize_to_2pi(az))
        # azimuth_to_angle already normalises into [0, 2π), so no outer
        # normalize_to_2pi is needed here (it would be a no-op).
        return float(azimuth_to_angle(az))

    def do(self) -> None:
        """Install the moved point and recomputed dependents; fire per object."""
        for oid in self._ids:
            self._objects[oid] = self._after[oid]
        for oid in self._ids:
            self._bus.fire(OBJECT_MODIFIED, obj_id=oid)

    def undo(self) -> None:
        """Restore the pre-move point and dependents; fire per object."""
        for oid in self._ids:
            self._objects[oid] = self._before[oid]
        for oid in self._ids:
            self._bus.fire(OBJECT_MODIFIED, obj_id=oid)


class ModifyPolygonVerticesCommand:
    """Replace a Polygon's vertex list and refresh its cached convexity.

    Changing ``point_ids`` alters which Points the polygon references, so unlike
    :class:`ModifyObjectCommand` this command **does** update the dependency
    graph: :meth:`DependencyGraph.add` re-registers the new edge set (and
    restores the old set on undo).

    The construction sequence mirrors the polygon *creation* path (``CLAUDE.md``
    §3, spec/MVP.md: "Modifying a polygon's point list reorders CCW, validates
    that the polygon is simple, and updates the convexity flag"). In
    :meth:`__init__`, before any store mutation, the candidate ring is:

    1. built with the new ``point_ids``;
    2. rejected if degenerate (``|signed_area| < EPS_AREA``);
    3. reordered to CCW — if the signed area is negative (CW) the vertex tuple
       is reversed, since a positive signed area is CCW;
    4. validated for simplicity (no self-intersection) on the final, reordered
       ring; and
    5. only then has its cached ``is_convex`` recomputed (meaningful only on a
       simple, CCW ring).

    Because every rejection happens in :meth:`__init__` before the store is
    touched, a rejected edit never enters the undo history — the same safety
    property the other commands rely on. The ``is_convex`` flag stays coherent
    with ``point_ids`` (the two are co-owned by this command per the ``Polygon``
    model contract).

    Fields
    ------
    description : str
        ``"Edit vertices of '<name>'"``.
    _objects : dict[str, GeoObject]
        The object store this command mutates.
    _graph : DependencyGraph
        The dependency graph re-registered on do/undo.
    _bus : EventBus
        Event bus for modify notifications.
    _polygon_id : str
        ID of the polygon being re-vertexed.
    _before : Polygon
        Deep copy with the original ``point_ids``/``is_convex``.
    _after : Polygon
        Deep copy with the new ``point_ids`` reordered CCW, validated simple,
        and with recomputed ``is_convex``.
    """

    def __init__(
        self,
        objects: dict[str, GeoObject],
        graph: DependencyGraph,
        bus: EventBus,
        polygon_id: str,
        new_point_ids: Sequence[str],
    ) -> None:
        self._objects = objects
        self._graph = graph
        self._bus = bus
        self._polygon_id = polygon_id
        before = copy.deepcopy(objects[polygon_id])
        after = copy.deepcopy(before)
        after.point_ids = tuple(new_point_ids)
        # Mirror the polygon creation path: reject degeneracy, reorder CCW,
        # validate simplicity, then cache convexity — all before any mutation,
        # so a rejected edit never enters history. (CLAUDE.md §3, spec/MVP.md.)
        validation.validate_polygon_non_degenerate(after, objects)
        if float(_signed_area(after, objects)) < 0.0:
            # Negative signed area == clockwise; reverse to store CCW.
            after.point_ids = tuple(reversed(after.point_ids))
        validation.validate_polygon_simple(after, objects)
        after.is_convex = bool(_is_convex(after, objects))
        self._before = before
        self._after = after
        self.description = f"Edit vertices of '{before.name}'"

    def do(self) -> None:
        """Install the new vertex set, re-register edges, fire modify."""
        self._objects[self._polygon_id] = self._after
        self._graph.add(self._after)
        self._bus.fire(OBJECT_MODIFIED, obj_id=self._polygon_id)

    def undo(self) -> None:
        """Restore the original vertex set, re-register edges, fire modify."""
        self._objects[self._polygon_id] = self._before
        self._graph.add(self._before)
        self._bus.fire(OBJECT_MODIFIED, obj_id=self._polygon_id)


class BulkImportCommand:
    """Apply many object creations as a single undoable unit.

    Wraps one :class:`CreateObjectCommand` per imported object so a whole file
    import is one entry in the undo history rather than dozens. :meth:`do`
    applies the wrapped creations in order; :meth:`undo` reverses them in the
    opposite order, so an object is never removed before something created after
    it (which, with ID-string references, would not matter for correctness but
    keeps the event order intuitive).

    Both :meth:`do` and :meth:`undo` are atomic: if a wrapped create (or its
    reversal) raises mid-batch, the creations already applied in that call are
    rolled back before the exception propagates, so a partially-applied batch
    never persists in the store or graph.

    Fields
    ------
    description : str
        Caller-supplied label, or ``"Import <n> object(s)"`` by default.
    _commands : list[CreateObjectCommand]
        The per-object create commands, in import order.
    """

    def __init__(
        self,
        objects: dict[str, GeoObject],
        graph: DependencyGraph,
        bus: EventBus,
        objs: Sequence[GeoObject],
        description: str | None = None,
    ) -> None:
        self._commands = [CreateObjectCommand(objects, graph, bus, obj) for obj in objs]
        self.description = description or f"Import {len(objs)} object(s)"

    def do(self) -> None:
        """Apply each wrapped creation in import order, atomically.

        If a wrapped :meth:`CreateObjectCommand.do` raises mid-batch, every
        creation already applied in this call is undone (newest first) before the
        exception propagates, so a partial import never persists.
        """
        applied: list[CreateObjectCommand] = []
        try:
            for cmd in self._commands:
                cmd.do()
                applied.append(cmd)
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.error(
                "BulkImportCommand.do: failed after applying %d of %d creation(s); rolling back",
                len(applied),
                len(self._commands),
                exc_info=True,
            )
            # Fault-tolerant rollback: a wrapped ``undo`` that itself raises is
            # logged and skipped so every remaining applied create is still
            # reversed, and the ORIGINAL exception (re-raised by the bare
            # ``raise``) is never masked by a rollback-step exception.
            for cmd in reversed(applied):
                try:
                    cmd.undo()
                except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught
                    _logger.error(
                        "BulkImportCommand.do: rollback undo of %r failed; continuing",
                        cmd.description,
                        exc_info=True,
                    )
            raise

    def undo(self) -> None:
        """Reverse each wrapped creation in the opposite order, atomically.

        If a wrapped :meth:`CreateObjectCommand.undo` raises mid-batch, every
        reversal already applied in this call is re-applied before the exception
        propagates, so the store is not left in a partially-undone state.
        """
        reversed_so_far: list[CreateObjectCommand] = []
        try:
            for cmd in reversed(self._commands):
                cmd.undo()
                reversed_so_far.append(cmd)
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.error(
                "BulkImportCommand.undo: failed after reversing %d of %d creation(s); restoring",
                len(reversed_so_far),
                len(self._commands),
                exc_info=True,
            )
            # Fault-tolerant restoration: a wrapped ``do`` that itself raises is
            # logged and skipped so every already-reversed create is still
            # restored, and the ORIGINAL exception (re-raised by the bare
            # ``raise``) is never masked by a restoration-step exception.
            for cmd in reversed(reversed_so_far):
                try:
                    cmd.do()
                except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught
                    _logger.error(
                        "BulkImportCommand.undo: restoration do of %r failed; continuing",
                        cmd.description,
                        exc_info=True,
                    )
            raise
