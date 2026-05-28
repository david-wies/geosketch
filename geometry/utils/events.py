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

"""Minimal synchronous publish-subscribe event bus.

Used by ``project.py`` to decouple model mutations from UI refreshes.
Components that need to react to model changes subscribe to named
events; the model fires them. This avoids hard wiring callbacks into
the model layer and keeps the layering rule in
``docs/geo-sketch-design.md`` clean (the model never imports
``tkinter`` or ``matplotlib``).

The bus is **synchronous**: every handler runs to completion on the
firing thread before :meth:`EventBus.fire` returns. GeoSketch is a
single-threaded tkinter app; async dispatch would add complexity for
no benefit and would break the "all handlers run in the main loop"
contract the design relies on.

Named events
------------
The seven events defined by ``docs/geo-sketch-design.md`` are exposed
here as module-level string constants. Service and UI code should use
the constants rather than re-typing the string so typos surface as
``NameError`` rather than as silently-dropped events.

==================  ===========================================
Constant            Payload (kwargs)
==================  ===========================================
``OBJECT_CREATED``  ``obj_id: str``
``OBJECT_MODIFIED`` ``obj_id: str``
``OBJECT_DELETED``  ``obj_ids: list[str]``  (full cascade set)
``SELECTION_CHANGED`` ``obj_id: str | None``
``CANVAS_STALE``    *(no payload)*
``PROJECT_LOADED``  *(no payload)*
``HISTORY_CHANGED`` ``can_undo: bool, can_redo: bool``
==================  ===========================================

The bus itself does not validate event names or payload shapes —
keeping it untyped is a deliberate trade-off so future events can be
added without modifying this module. The constants are the canonical
spelling for the current set.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Canonical event names. Use these constants rather than raw strings so
# typos surface at import time rather than as a silently dropped event.
OBJECT_CREATED: str = "object_created"
OBJECT_MODIFIED: str = "object_modified"
OBJECT_DELETED: str = "object_deleted"
SELECTION_CHANGED: str = "selection_changed"
CANVAS_STALE: str = "canvas_stale"
PROJECT_LOADED: str = "project_loaded"
HISTORY_CHANGED: str = "history_changed"

#: The full set of events documented in ``docs/geo-sketch-design.md``.
#: Exposed for tests and for any caller that wants to iterate over the
#: known event set. Not used to validate :meth:`EventBus.fire` calls —
#: the bus accepts arbitrary event names by design.
DEFINED_EVENTS: frozenset[str] = frozenset(
    {
        OBJECT_CREATED,
        OBJECT_MODIFIED,
        OBJECT_DELETED,
        SELECTION_CHANGED,
        CANVAS_STALE,
        PROJECT_LOADED,
        HISTORY_CHANGED,
    }
)

# A handler accepts whatever keyword payload its publisher emits. Typing
# the payload as ``**Any`` is the most faithful representation; concrete
# call sites are documented above on the event constants.
EventHandler = Callable[..., None]


class EventBus:
    """Synchronous in-process publish-subscribe bus.

    Subscribers register a handler against a named event. When that
    event is fired, every subscribed handler is invoked in subscription
    order with the payload passed as keyword arguments. The bus does
    not validate event names — subscribing to and firing an
    arbitrary string is allowed so the bus stays decoupled from the
    set of "official" events defined at module scope.

    Handler exceptions propagate to the firer (they are *not*
    swallowed). This matches the tkinter single-thread model where the
    main loop is the obvious place for an unexpected exception to
    surface. Callers that need fault isolation across handlers must
    wrap their handler body in a ``try/except`` themselves.

    Duplicate subscriptions are de-duplicated: subscribing the same
    handler to the same event twice has the same effect as subscribing
    once. This prevents the most common UI-layer bug (a widget
    re-subscribes on rebuild and ends up handling each event twice).

    Fields
    ------
    _subscribers : dict[str, list[EventHandler]]
        Maps each event name to its ordered handler list. Lists are
        used (rather than sets) so subscription order is preserved and
        observable from tests; de-duplication is enforced manually on
        :meth:`subscribe`.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event: str, handler: EventHandler) -> None:
        """Register ``handler`` to be invoked when ``event`` is fired.

        Subscribing the same ``(event, handler)`` pair twice is a no-op:
        the handler is registered exactly once. This avoids the
        repeated-handler bug that plagues UI rebuild paths.

        Parameters
        ----------
        event : str
            Event name. May be one of the module-level constants
            (preferred) or any other string.
        handler : EventHandler
            Callable invoked with the payload as ``**kwargs``.
        """
        handlers = self._subscribers.setdefault(event, [])
        if handler not in handlers:
            handlers.append(handler)

    def unsubscribe(self, event: str, handler: EventHandler) -> None:
        """Remove ``handler`` from ``event``'s subscriber list.

        Unsubscribing a handler that was never registered (or that has
        already been removed) is a no-op, mirroring the idempotent
        behaviour of :meth:`subscribe`. The empty-list entry is left
        in place to keep the implementation simple; it does not affect
        :meth:`fire` semantics.

        Parameters
        ----------
        event : str
            Event name the handler was registered under.
        handler : EventHandler
            The exact callable object previously passed to
            :meth:`subscribe`.
        """
        handlers = self._subscribers.get(event)
        if handlers is None:
            return
        try:
            handlers.remove(handler)
        except ValueError:
            # Handler was not subscribed; treat as a no-op rather than
            # raising — symmetric with subscribe's idempotency.
            pass

    def fire(self, event: str, **payload: Any) -> None:
        """Synchronously dispatch ``event`` to every subscribed handler.

        Handlers are invoked in subscription order. If a handler
        raises, the exception propagates and any handlers that have
        not yet been invoked for this fire call are **not** invoked.
        Subscribers added or removed by a handler during dispatch take
        effect on the *next* :meth:`fire` call — the snapshot taken at
        the top of this method is iterated to completion.

        Parameters
        ----------
        event : str
            Event name. If no handler is subscribed to this event the
            call is a silent no-op.
        **payload : Any
            Keyword arguments passed through to every handler. See the
            module docstring for the canonical payload of each defined
            event.
        """
        # Copy the list so that handlers which mutate the subscriber
        # set during dispatch do not invalidate the iteration. A new
        # subscription added mid-fire takes effect on the next fire.
        for handler in list(self._subscribers.get(event, ())):
            handler(**payload)


__all__ = [
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
