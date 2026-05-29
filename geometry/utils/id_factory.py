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

"""Per-type identifier factory for GeoSketch objects.

Every persistable object in the scene owns a string identifier of the
form ``"<prefix>_<positive_int>"`` (e.g. ``pt_001`` for a Point,
``ln_042`` for a Line). The integer suffix is strictly greater than
every existing same-prefix ID in the scene. The :class:`IDFactory`
class below is the single allocator for these IDs; service code must
never construct an ID string by hand.

The minted suffix is **zero-padded to three digits** when the running
counter is < 1000 (matching the spec's ``pt_001`` examples) and is
emitted with its natural width once the counter exceeds 999. The
``<prefix>_<positive int>`` regex enforced by the persistence layer
admits both forms, so the format remains stable on round-trip.

Reseeding behaviour
-------------------
On project load the loader hands every persisted ID to
:meth:`IDFactory.reseed`, which scans for the maximum integer suffix
per prefix and sets the running counter just above it. Subsequent
:meth:`next_id` calls then never collide with the loaded IDs. Reseed
is **additive** — it raises the counter to ``max + 1`` per prefix it
sees, but leaves untouched any prefix not present in the input. The
loader is expected to call ``reseed`` exactly once on a freshly
constructed factory, but successive calls are safe (each one moves
counters forward, never backward).
"""

from __future__ import annotations

import re

# Match a single ID literal. ``<prefix>`` is one or more lowercase ASCII
# letters; ``<n>`` is one or more ASCII decimal digits with no sign. The
# digit class is spelled ``[0-9]`` rather than ``\d`` so that non-ASCII
# Unicode digits (which ``\d`` matches) are rejected — keeping reseed's
# accepted format identical to the ASCII-strict ``next_id`` path. The
# regex is anchored so trailing garbage is rejected rather than silently
# accepted.
_ID_RE: re.Pattern[str] = re.compile(r"^([a-z]+)_([0-9]+)$")

# The minimum width to zero-pad the integer suffix to. Pure cosmetic —
# the persistence regex accepts any positive integer width, but matching
# the spec's example IDs (``pt_001``) keeps file diffs readable.
_PAD_WIDTH = 3


class IDFactory:
    """Allocator that hands out fresh per-prefix object identifiers.

    The factory maintains an in-memory ``{prefix: last_used_int}`` map.
    Each call to :meth:`next_id` increments the counter for the given
    prefix and returns the formatted ID. On project load the counter is
    reseeded from the persisted IDs via :meth:`reseed`, ensuring newly
    minted IDs never collide with loaded ones.

    Concurrency note: the factory is **not** thread-safe. GeoSketch is a
    single-threaded tkinter app and the factory is only touched from the
    main loop; promoting it to thread-safe would mean adding a lock to
    every ``next_id`` call for no benefit. If a future feature introduces
    background threads that mutate the object store, gate the factory
    behind an explicit lock at that call site.

    Fields
    ------
    _counters : dict[str, int]
        Maps each prefix seen so far to the highest integer suffix
        already minted (or reseeded). The next mint for that prefix
        returns ``_counters[prefix] + 1``. Defaults to ``0`` for unseen
        prefixes via :py:meth:`dict.get`.
    """

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def next_id(self, prefix: str) -> str:
        """Mint and return the next ID for ``prefix``.

        Parameters
        ----------
        prefix : str
            The 2-letter ID prefix (e.g. ``"pt"``, ``"ln"``). Must be a
            non-empty lowercase ASCII identifier — the same character
            class the persistence regex enforces.

        Returns
        -------
        str
            A freshly minted ID of the form ``"<prefix>_<n>"`` where
            ``n`` is one greater than the highest ``n`` previously
            issued or reseeded for this prefix. Suffixes < 1000 are
            zero-padded to three digits (e.g. ``pt_001``); larger
            suffixes use their natural width.

        Raises
        ------
        ValueError
            If ``prefix`` is empty or contains anything other than
            lowercase ASCII letters.
        """
        if not prefix or not prefix.isascii() or not prefix.isalpha() or not prefix.islower():
            raise ValueError(
                f"IDFactory prefix must be a non-empty lowercase ASCII string; got {prefix!r}."
            )
        nxt = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = nxt
        return f"{prefix}_{nxt:0{_PAD_WIDTH}d}"

    def reseed(self, ids: list[str]) -> None:
        """Raise per-prefix counters above the maximum integer in ``ids``.

        Called by the project loader after all objects have been
        reconstructed, with the full list of loaded IDs. For each
        prefix observed in ``ids`` the counter is set to the maximum
        integer suffix seen, so the next :meth:`next_id` call for that
        prefix returns ``max + 1``. Prefixes absent from ``ids`` are
        left untouched.

        The method is monotonic: it never lowers a counter. Re-seeding
        with a subset of IDs is therefore safe.

        Parameters
        ----------
        ids : list[str]
            Sequence of persisted IDs, each matching the
            ``<prefix>_<positive_int>`` regex. Order is irrelevant.

        Raises
        ------
        ValueError
            If any ID does not match the canonical
            ``<prefix>_<positive_int>`` format (lowercase letters,
            underscore, one or more digits).
        """
        for raw in ids:
            match = _ID_RE.match(raw)
            if match is None:
                raise ValueError(
                    f"Malformed ID {raw!r}; expected format '<prefix>_<positive_int>' "
                    f"with a lowercase letter prefix and digit-only suffix."
                )
            prefix, digits = match.group(1), match.group(2)
            value = int(digits)
            if value < 1:
                raise ValueError(f"ID suffix must be a positive integer (>= 1); got {raw!r}.")
            current = self._counters.get(prefix, 0)
            if value > current:
                self._counters[prefix] = value


__all__ = ["IDFactory"]
