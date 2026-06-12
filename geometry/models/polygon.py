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

from dataclasses import dataclass, field

from geometry.models.common import GeoObject


@dataclass
class Polygon(GeoObject):
    """A polygon defined by an ordered tuple of point IDs.

    Vertex order is CCW — the services layer enforces winding order on
    creation and modification; this model stores the result as-is.

    ``is_convex`` is set by the services layer (using the cross-product
    method) on creation and after any modification.

    The ``point_ids`` sequence is **defensively converted** to a tuple in
    ``__post_init__`` so that polygon vertex membership cannot be mutated in
    place through an aliased source object.

    Fields
    ------
    point_ids : tuple[str, ...]
        Ordered point IDs in CCW winding order. The constructor defensively
        converts the supplied sequence to an immutable tuple independent of the
        caller's reference (see Notes).  Must only be replaced by
        ``ModifyPolygonVerticesCommand``.
    is_convex : bool
        True if the polygon is convex; cached by the services layer.
        Must only be updated by ``PolygonService.create()`` and by
        ``ModifyPolygonVerticesCommand.do()``/``undo()``.  Treat as read-only
        from UI code and other commands — see Notes.
    line_color : str
        Hex colour string for the outline stroke.
    fill_color : str
        Hex colour string for the interior fill.

    See Also
    --------
    geometry.models.common.GeoObject : Shared envelope fields (``id``, ``name``,
        ``type``, ``alpha``, ``visibility``) inherited by every concrete model.

    Notes
    -----
    Both ``point_ids`` and ``is_convex`` follow a single-writer convention:
    ``ModifyPolygonVerticesCommand`` is the only mutator for both, and
    ``PolygonService.create()`` is the only initial setter for ``is_convex``.
    The two fields must stay coherent (``is_convex`` always reflects the
    current ``point_ids``), so they are co-owned by the same command path.
    """

    point_ids: tuple[str, ...]
    is_convex: bool
    line_color: str
    fill_color: str
    type: str = field(init=False, default="polygon")

    def __post_init__(self) -> None:
        super().__post_init__()
        self.point_ids = tuple(self.point_ids)
