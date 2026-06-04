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
class Solid(GeoObject):
    """A 3D solid defined by an ordered stack of cross-section layers.

    Each layer is a Polygon ID or a Point ID (apex/nadir). Layers are ordered
    bottom-to-top by user declaration — not derived from altitude. The closed
    shell is formed by connecting adjacent layers; the volume is computed by
    the Mirtich (1996) polyhedral mass algorithm.

    Fields
    ------
    layers : tuple[str, ...]
        Ordered references to existing Polygon (``pg_``) or Point (``pt_``) IDs.
        Every entry must carry one of those two prefixes — any other prefix is
        rejected at construction. At least 2 entries. At most one entry may be a
        Point ID; it must be first or last.
    line_color : str
        Edge/stroke color.
    fill_color : str
        Face fill color (rendered in 3D and Slice views).

    See Also
    --------
    geometry.models.common.GeoObject : Shared envelope fields (``id``, ``name``,
        ``type``, ``alpha``, ``visibility``) inherited by every concrete model.
    """

    layers: tuple[str, ...]
    line_color: str
    fill_color: str
    type: str = field(init=False, default="solid")

    def __post_init__(self) -> None:
        super().__post_init__()
        self.layers = tuple(self.layers)
        if len(self.layers) < 2:
            raise ValueError("Solid requires at least 2 layer IDs")
        # A layer is either a Polygon (``pg_``) or a Point (``pt_``); anything
        # else (typo, empty string, ``ci_001``) would otherwise be silently
        # treated as a polygon. Reject it here rather than deferring to the
        # services layer, since a mis-prefixed ID is a real correctness footgun.
        bad_prefixes = [
            layer_id
            for layer_id in self.layers
            if not (layer_id.startswith("pg_") or layer_id.startswith("pt_"))
        ]
        if bad_prefixes:
            raise ValueError(
                f"Solid layers must be Polygon ('pg_') or Point ('pt_') IDs; "
                f"got mis-prefixed: {bad_prefixes}"
            )
        # Per spec §10: at most one layer may be a Point ID (the apex/nadir),
        # and it must be the first or last element. Both sub-rules are decidable
        # from the ``pt_`` ID prefix alone — no cross-object lookup needed.
        point_indices = [i for i, layer_id in enumerate(self.layers) if layer_id.startswith("pt_")]
        if len(point_indices) > 1:
            raise ValueError(
                f"Solid layers may contain at most one Point ID (apex/nadir); "
                f"got {len(point_indices)}: {[self.layers[i] for i in point_indices]}"
            )
        if point_indices and point_indices[0] not in (0, len(self.layers) - 1):
            raise ValueError(
                f"Solid apex/nadir Point ID must be the first or last layer; "
                f"got {self.layers[point_indices[0]]!r} at index {point_indices[0]}"
            )
