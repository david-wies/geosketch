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

"""Rule-checking gate between user input and object creation for GeoSketch.

This module is the single home for every *validation* rule that must hold
before a geometry object is admitted into the document: polygon degeneracy /
simplicity / vertex count, circle and ball tangency, ball-tangent
perpendicularity, cylinder axis sanity, positive radius, the structural rules
on a solid's layer stack, solid volume degeneracy, referential existence, and
altitude finiteness. Where :mod:`geometry.services.geometry` *computes*
numbers, this module *judges* them: each function returns ``None`` on success
and raises :class:`ValueError` on failure, never silently degrading.

Unlike the model dataclasses — which enforce their own structural invariants
at construction (a ``Circle`` already rejects ``radius <= EPS_DISTANCE``, a
``Polygon`` already rejects fewer than three vertices) — these validators run
*earlier*, at the boundary where the command layer assembles candidate input
that may reference other objects. They are deliberately allowed to overlap the
model guards: validating up front yields a single, user-facing ``ValueError``
with an actionable message rather than letting a constructor raise deep inside
object creation.

Conventions
-----------
* Every numeric tolerance is imported by name from
  :mod:`geometry.utils.constants` (``EPS_AREA``, ``EPS_DISTANCE``,
  ``EPS_ANGLE``, ``EPS_VOLUME``); this module inlines no bare literal.
* Geometry is never re-derived here. Polygon signed area comes from
  :func:`geometry.signed_area` and 3-D distance from
  :func:`geometry.distance`, so a single source owns each formula.
* Circle tangency is a **2-D** (horizontal ``(easting, northing)``) test
  because a circle is planar; ball tangency is a **3-D** test because a ball
  is a sphere. The two must not be conflated.
* Solid layers are classified as Point vs Polygon by the *resolved object's*
  ``.type`` field (``"point"`` / ``"polygon"``), not by parsing the ID prefix
  string — the prefix is a display convenience, the ``.type`` is the contract.
* Referential existence is a **two-tier contract**. Tier 1 (user-facing): the
  command layer runs :func:`validate_reference_exists` on every vertex ID
  first, which raises :class:`ValueError` for a dangling reference — so a caller
  catching :class:`ValueError` already covers the missing-ID case. Tier 2
  (programmer error): the polygon validators
  (:func:`validate_polygon_non_degenerate`, :func:`validate_polygon_simple`)
  index ``points[pid]`` directly and therefore raise :class:`KeyError`, not
  :class:`ValueError`, if that precondition was skipped. The split is
  intentional: a missing ID reaching these validators is a bug in the call
  sequence, not user-facing bad input, and is surfaced loudly rather than
  folded into the user-error channel.
* It imports neither ``tkinter`` nor ``matplotlib``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np
import shapely

from geometry.models.common import GeoObject
from geometry.models.point import Point
from geometry.models.polygon import Polygon
from geometry.services import geometry as geo
from geometry.utils.constants import EPS_ANGLE, EPS_AREA, EPS_DISTANCE, EPS_VOLUME

__all__ = [
    "validate_polygon_non_degenerate",
    "validate_polygon_simple",
    "validate_polygon_vertex_count",
    "validate_circle_tangent_point",
    "validate_ball_tangent_point",
    "validate_ball_tangent_perpendicular",
    "validate_cylinder_axis_elevation",
    "validate_positive_radius",
    "validate_solid_layers",
    "validate_solid_non_degenerate",
    "validate_reference_exists",
    "validate_altitude_finite",
]


# ---------------------------------------------------------------------------
# shared coordinate guard
# ---------------------------------------------------------------------------


def _require_finite_coords(point: Point, *fields: str) -> None:
    """Reject a point carrying a non-finite coordinate on any named field.

    Point coordinates can be mutated after construction via the point-edit path
    (``GeoObject.__setattr__`` does not re-check finiteness), so a ``nan`` or
    ``±inf`` can reach a validator's geometry computation and poison it: since
    ``nan >= EPS`` and ``nan < EPS`` are both ``False``, the reject branch
    becomes unreachable and the validator silently returns ``None`` instead of
    raising. This helper is the single up-front gate the coordinate-consuming
    validators call before any geometry runs, mirroring the scalar
    ``math.isfinite`` guards already present on radius / direction / elevation.

    Parameters
    ----------
    point : Point
        The point whose coordinates are checked.
    *fields : str
        Attribute names to test (``"easting"``, ``"northing"``, ``"altitude"``).
        Circle validators pass the 2-D pair; ball validators add altitude.

    Raises
    ------
    ValueError
        If any named field's value is non-finite (``nan`` or ``±inf``).
    """
    for field in fields:
        value = getattr(point, field)
        if not math.isfinite(value):
            raise ValueError(
                f"Point {point.id!r} coordinate {field!r} must be finite; got {value!r}"
            )


# ---------------------------------------------------------------------------
# polygon rules
# ---------------------------------------------------------------------------


def validate_polygon_non_degenerate(polygon: Polygon, points: Mapping[str, Point]) -> None:
    """Reject a polygon whose signed area is below the degeneracy tolerance.

    A polygon with ``|signed_area| < EPS_AREA`` encloses no meaningful region
    (collinear vertices, a zero-width sliver, or coincident points) and cannot
    be rendered, filled, or measured, so it is rejected before creation. The
    area is taken from :func:`geometry.signed_area` so the shoelace formula
    lives in exactly one place; only its magnitude matters here (winding is the
    creation path's concern, not validation's).

    Parameters
    ----------
    polygon : Polygon
        The candidate polygon.
    points : Mapping[str, Point]
        Point lookup covering every ID in ``polygon.point_ids``.

    Raises
    ------
    ValueError
        If the signed area is non-finite (a ``nan`` / ``±inf`` coordinate on a
        vertex poisons the shoelace sum, and ``nan < EPS_AREA`` is ``False``, so
        the degeneracy branch would be unreachable), or if
        ``abs(signed_area) < EPS_AREA``.
    KeyError
        If a point ID in ``polygon.point_ids`` is absent from ``points`` (a
        programmer error under the documented precondition that
        :func:`validate_reference_exists` runs on every vertex first).
    """
    # An infinite vertex coordinate makes the shoelace sum evaluate ``inf * 0``,
    # which numpy would surface as a RuntimeWarning. This validator deliberately
    # tolerates a non-finite result and rejects it explicitly below, so the
    # intermediate warning is expected noise and is suppressed here.
    with np.errstate(invalid="ignore"):
        signed = float(geo.signed_area(polygon, points))
    if not math.isfinite(signed):
        raise ValueError(
            f"Polygon {polygon.id!r} has a non-finite signed area "
            f"(a vertex coordinate is nan or ±inf); got {signed!r}"
        )
    area = abs(signed)
    if area < EPS_AREA:
        raise ValueError(
            f"Polygon {polygon.id!r} is degenerate: |signed area| must be "
            f">= {EPS_AREA}; got {area!r}"
        )


def validate_polygon_simple(polygon: Polygon, points: Mapping[str, Point]) -> None:
    """Reject a polygon whose boundary is not a simple ring.

    A simple polygon has a boundary that never crosses itself; a bowtie or any
    figure-eight boundary is non-simple and breaks every downstream area /
    containment / distance operation (which all assume a single well-formed
    ring). Simplicity is decided by :func:`shapely.is_simple` on a shapely
    polygon built from the project's in-memory coordinates, matching how
    :mod:`geometry.services.geometry` constructs shapely geometry at the call
    boundary.

    Simplicity is **not** the same property as non-degeneracy: ``is_simple``
    also reports ``False`` for a collinear or coincident-vertex ring that
    collapses to a line (zero enclosed area), so this validator can reject such
    a ring too — its message names both causes. Dedicated zero-area rejection
    (with the precise ``EPS_AREA`` tolerance) is the job of
    :func:`validate_polygon_non_degenerate`; run both for a full picture.

    Parameters
    ----------
    polygon : Polygon
        The candidate polygon.
    points : Mapping[str, Point]
        Point lookup covering every ID in ``polygon.point_ids``.

    Raises
    ------
    ValueError
        If the polygon has fewer than 3 vertices (a degenerate ring that
        shapely cannot construct), if any vertex coordinate is non-finite (a
        ``nan`` / ``±inf`` poisons ``shapely.is_simple``, which then makes the
        not-simple branch unreachable), or if its boundary is not a simple ring
        (self-intersecting, or collinear/zero-area).
    KeyError
        If a point ID in ``polygon.point_ids`` is absent from ``points`` (a
        programmer error under the documented precondition that
        :func:`validate_reference_exists` runs on every vertex first).
    """
    if len(polygon.point_ids) < 3:
        raise ValueError(
            f"Polygon {polygon.id!r} requires at least 3 vertices; got {len(polygon.point_ids)!r}"
        )
    for pid in polygon.point_ids:
        _require_finite_coords(points[pid], "easting", "northing")
    sp_poly = shapely.Polygon(
        [(points[pid].easting, points[pid].northing) for pid in polygon.point_ids]
    )
    if not shapely.is_simple(sp_poly):
        raise ValueError(
            f"Polygon {polygon.id!r} is not a simple ring (self-intersecting, "
            f"or collinear/zero-area so the boundary collapses to a line); a "
            f"simple ring must not cross itself or degenerate"
        )


def validate_polygon_vertex_count(polygon: Polygon) -> None:
    """Reject a polygon with fewer than three vertices.

    Three vertices is the minimum that can enclose an area; two or fewer
    describes a segment or a point, not a polygon. This duplicates the
    ``Polygon`` constructor's own guard on purpose, so the command layer can
    surface a clean message before attempting construction.

    Parameters
    ----------
    polygon : Polygon
        The candidate polygon.

    Raises
    ------
    ValueError
        If ``len(polygon.point_ids) < 3``.
    """
    count = len(polygon.point_ids)
    if count < 3:
        raise ValueError(f"Polygon {polygon.id!r} requires at least 3 vertices; got {count!r}")


# ---------------------------------------------------------------------------
# circle / ball tangency
# ---------------------------------------------------------------------------


def validate_circle_tangent_point(center: Point, surface_point: Point, radius: float) -> None:
    """Reject a tangent point that does not lie on the circle's circumference.

    A circle is planar in the horizontal ``(easting, northing)`` plane, so its
    circumference test uses the **2-D** horizontal distance
    (``math.hypot`` of the easting/northing deltas) — altitude is irrelevant to
    a planar circle. The point is accepted only when its horizontal distance
    from the centre matches ``radius`` within :data:`EPS_DISTANCE`.

    Parameters
    ----------
    center : Point
        The circle's centre.
    surface_point : Point
        The candidate point on the circumference.
    radius : float
        The circle's radius in metres.

    Raises
    ------
    ValueError
        If ``radius`` or either point's planar coordinates are non-finite
        (``nan`` or ``±inf``), or if
        ``abs(horizontal_distance - radius) >= EPS_DISTANCE``.
    """
    if not math.isfinite(radius):
        raise ValueError(f"Radius must be finite; got {radius!r}")
    _require_finite_coords(center, "easting", "northing")
    _require_finite_coords(surface_point, "easting", "northing")
    horizontal = math.hypot(
        surface_point.easting - center.easting, surface_point.northing - center.northing
    )
    error = abs(horizontal - radius)
    if error >= EPS_DISTANCE:
        raise ValueError(
            f"Tangent point does not lie on the circle: |2D distance - radius| "
            f"must be < {EPS_DISTANCE}; got distance {horizontal!r}, radius "
            f"{radius!r} (error {error!r})"
        )


def validate_ball_tangent_point(center: Point, surface_point: Point, radius: float) -> None:
    """Reject a tangent point that does not lie on the ball's spherical surface.

    A ball is a sphere, so its surface test is **3-D**: it reuses
    :func:`geometry.distance` (``√[(Δe)²+(Δn)²+(Δz)²]``) rather than the
    horizontal-only distance used for a planar circle. The point is accepted
    only when its 3-D distance from the centre matches ``radius`` within
    :data:`EPS_DISTANCE`.

    Parameters
    ----------
    center : Point
        The ball's centre.
    surface_point : Point
        The candidate point on the spherical surface.
    radius : float
        The ball's radius in metres.

    Raises
    ------
    ValueError
        If ``radius`` or either point's 3-D coordinates are non-finite
        (``nan`` or ``±inf``), or if
        ``abs(distance_3d - radius) >= EPS_DISTANCE``.
    """
    if not math.isfinite(radius):
        raise ValueError(f"Radius must be finite; got {radius!r}")
    _require_finite_coords(center, "easting", "northing", "altitude")
    _require_finite_coords(surface_point, "easting", "northing", "altitude")
    dist = float(geo.distance(center, surface_point))
    error = abs(dist - radius)
    if error >= EPS_DISTANCE:
        raise ValueError(
            f"Tangent point does not lie on the ball: |3D distance - radius| "
            f"must be < {EPS_DISTANCE}; got distance {dist!r}, radius {radius!r} "
            f"(error {error!r})"
        )


def validate_ball_tangent_perpendicular(
    center: Point,
    surface_point: Point,
    tangent_direction: float,
    tangent_elevation: float,
) -> None:
    """Reject a ball tangent whose direction is not perpendicular to the radius.

    A line tangent to a sphere at ``surface_point`` must be orthogonal to the
    radius arm ``center → surface_point``. Orthogonality is tested in 3-D via
    the dot product of two unit vectors::

        tangent_unit_3d = (sin(az)·cos(el), cos(az)·cos(el), sin(el))
        radius_unit_3d  = unit(surface_point - center)   in (E, N, Z)

    where ``az = tangent_direction`` (azimuth) and ``el = tangent_elevation``.
    The tangent components use the spec's azimuth convention (``sin`` on
    easting, ``cos`` on northing), matching :func:`geometry.vector_endpoint`.
    Both vectors are unit-length, so ``|dot|`` is ``|cos θ|`` and
    :data:`EPS_ANGLE` is a genuine angular tolerance: the tangent is accepted
    only when ``|dot| < EPS_ANGLE`` (i.e. θ within tolerance of 90°). The tight
    1e-9 rad tolerance is appropriate here because this validator is fed a
    *computed/snapped* tangent direction (from the command layer), not a raw
    hand-entered azimuth/elevation.

    Parameters
    ----------
    center : Point
        The ball's centre.
    surface_point : Point
        The point of tangency on the spherical surface.
    tangent_direction : float
        The tangent's azimuth in radians (CW from North).
    tangent_elevation : float
        The tangent's elevation above the horizontal plane in radians.

    Raises
    ------
    ValueError
        If ``tangent_direction`` or ``tangent_elevation`` is non-finite
        (``nan`` or ``±inf``), if either point's 3-D coordinates are non-finite
        (a poisoned radius vector both skips the coincidence guard and yields a
        ``nan`` dot, making the perpendicular branch unreachable), if ``center``
        and ``surface_point`` coincide (the radius has no direction, so
        perpendicularity is undefined), or if ``abs(dot) >= EPS_ANGLE`` (the
        tangent is not perpendicular).
    """
    if not math.isfinite(tangent_direction) or not math.isfinite(tangent_elevation):
        raise ValueError(
            f"Ball tangent direction and elevation must be finite; got "
            f"direction {tangent_direction!r}, elevation {tangent_elevation!r}"
        )
    _require_finite_coords(center, "easting", "northing", "altitude")
    _require_finite_coords(surface_point, "easting", "northing", "altitude")
    radius_e = surface_point.easting - center.easting
    radius_n = surface_point.northing - center.northing
    radius_z = surface_point.altitude - center.altitude
    norm = math.hypot(radius_e, radius_n, radius_z)
    if norm < EPS_DISTANCE:
        raise ValueError(
            "Ball tangent is undefined: center and surface point coincide "
            "(zero-length radius), so perpendicularity cannot be checked"
        )
    cos_el = math.cos(tangent_elevation)
    tangent_e = math.sin(tangent_direction) * cos_el
    tangent_n = math.cos(tangent_direction) * cos_el
    tangent_z = math.sin(tangent_elevation)
    # Both vectors are unit-length (the tangent by construction; the radius arm
    # is unit-normalised by folding the division by ``norm`` into the dot below),
    # so ``|dot|`` is ``|cos theta|``. Pure-``math`` scalars avoid allocating the
    # transient 3-element NumPy arrays this single-shot check previously built.
    dot = abs((tangent_e * radius_e + tangent_n * radius_n + tangent_z * radius_z) / norm)
    if dot >= EPS_ANGLE:
        raise ValueError(
            f"Ball tangent is not perpendicular to the radius: |dot(tangent, "
            f"radius)| must be < {EPS_ANGLE}; got {dot!r}"
        )


# ---------------------------------------------------------------------------
# cylinder / radius scalars
# ---------------------------------------------------------------------------


def validate_cylinder_axis_elevation(axis_elevation: float) -> None:
    """Reject a cylinder axis elevation at or below zero.

    A cylinder's axis must rise out of the base plane; an ``axis_elevation`` of
    ``0`` collapses the solid into a flat disk and a negative value points the
    axis below the base, neither of which is a valid cylinder. (The upper bound
    — disallowing an inclined axis at exactly vertical — is the ``Cylinder``
    model's concern; this validator guards only the lower, degenerate end.)

    Parameters
    ----------
    axis_elevation : float
        The cylinder axis elevation in radians.

    Raises
    ------
    ValueError
        If ``axis_elevation`` is non-finite (``nan`` or ``±inf``), or if
        ``axis_elevation <= 0``.
    """
    if not math.isfinite(axis_elevation):
        raise ValueError(f"Cylinder axis elevation must be finite; got {axis_elevation!r}")
    if axis_elevation <= 0:
        raise ValueError(
            f"Cylinder axis elevation must be > 0 (a flat or downward axis is "
            f"degenerate); got {axis_elevation!r}"
        )


def validate_positive_radius(radius: float) -> None:
    """Reject a radius at or below the distance tolerance.

    A radius of ``EPS_DISTANCE`` or less describes no meaningful surface. This
    is the common radius-sanity gate for every radial type (Circle, Ball,
    Cylinder); it deliberately uses the **same** bound the per-model
    constructors apply (``radius <= EPS_DISTANCE``) so the command layer can
    surface a uniform, type-agnostic message for the exact boundary case the
    constructor would otherwise reject deep inside object creation — the two
    bounds cannot drift.

    Parameters
    ----------
    radius : float
        The candidate radius in metres.

    Raises
    ------
    ValueError
        If ``radius`` is non-finite (``nan`` or ``±inf``), or if
        ``radius <= EPS_DISTANCE``.
    """
    if not math.isfinite(radius):
        raise ValueError(f"Radius must be finite; got {radius!r}")
    if radius <= EPS_DISTANCE:
        raise ValueError(f"Radius must be > {EPS_DISTANCE}; got {radius!r}")


# ---------------------------------------------------------------------------
# solid rules
# ---------------------------------------------------------------------------


def validate_solid_layers(layers: Sequence[str], objects: Mapping[str, GeoObject]) -> None:
    """Reject a structurally invalid solid layer stack.

    A solid is an ordered stack of cross-section layers, each of which must be
    an existing Polygon or an existing Point (an apex/nadir). The structural
    rules enforced here are, in order:

    * at least two layers (a single cross-section has no extent);
    * every layer ID resolves to an existing object;
    * every resolved object is a Polygon or a Point — nothing else;
    * at most one Point layer (a solid has at most one apex/nadir);
    * the Point layer, if present, is the first or last element.

    Point vs Polygon is decided from the **resolved object's** ``.type`` field
    (``"point"`` / ``"polygon"``), never from the ID prefix string: the prefix
    is a display convenience, while ``.type`` is the authoritative contract and
    survives any future ID-scheme change.

    Parameters
    ----------
    layers : Sequence[str]
        Ordered layer object IDs.
    objects : Mapping[str, GeoObject]
        Object lookup used to resolve and type-classify each layer.

    Raises
    ------
    ValueError
        If any structural rule above is violated.
    """
    if len(layers) < 2:
        raise ValueError(f"Solid requires at least 2 layers; got {len(layers)!r}")

    point_indices: list[int] = []
    for index, layer_id in enumerate(layers):
        obj = objects.get(layer_id)
        if obj is None:
            raise ValueError(f"Solid layer {layer_id!r} references a non-existent object")
        if obj.type not in ("polygon", "point"):
            raise ValueError(
                f"Solid layer {layer_id!r} must be a Polygon or Point; got type {obj.type!r}"
            )
        if obj.type == "point":
            point_indices.append(index)

    if len(point_indices) > 1:
        offenders = [layers[i] for i in point_indices]
        raise ValueError(
            f"Solid may contain at most one Point layer (apex/nadir); "
            f"got {len(point_indices)}: {offenders!r}"
        )
    if point_indices and point_indices[0] not in (0, len(layers) - 1):
        raise ValueError(
            f"Solid Point layer must be the first or last layer; got "
            f"{layers[point_indices[0]]!r} at index {point_indices[0]!r}"
        )


def validate_solid_non_degenerate(volume: float) -> None:
    """Reject a solid whose volume is below the degeneracy tolerance.

    The 3-D analogue of :func:`validate_polygon_non_degenerate`. A solid whose
    layers are coplanar (zero vertical extent, or a coplanar-hull fallback)
    encloses ``|volume| < EPS_VOLUME`` and is rejected. The structural
    :func:`validate_solid_layers` check cannot catch this, because a layer
    stack can be structurally valid yet geometrically flat — only the computed
    volume reveals the collapse.

    Parameters
    ----------
    volume : float
        The solid's signed or unsigned volume in cubic metres, as computed by
        the geometry layer.

    Raises
    ------
    ValueError
        If ``volume`` is non-finite (``nan`` or ``±inf``) — a ``nan`` from a
        degenerate hull must not slip the gate — or if
        ``abs(volume) < EPS_VOLUME``.
    """
    if not math.isfinite(volume):
        raise ValueError(f"Volume must be finite; got {volume!r}")
    magnitude = abs(volume)
    if magnitude < EPS_VOLUME:
        raise ValueError(
            f"Solid is degenerate: |volume| must be >= {EPS_VOLUME}; got {magnitude!r}"
        )


# ---------------------------------------------------------------------------
# referential / scalar rules
# ---------------------------------------------------------------------------


def validate_reference_exists(obj_id: str, objects: Mapping[str, GeoObject]) -> None:
    """Reject a reference to an object that is not in the document.

    Every inter-object reference (line → point, polygon → point, tangent →
    shape, solid → layer) is an ID string that must resolve to a live object.
    This is the generic existence gate the command layer calls before wiring a
    reference, so a dangling ID fails loud with the offending value rather than
    surfacing later as a ``KeyError`` deep in a geometry computation.

    Parameters
    ----------
    obj_id : str
        The referenced object ID.
    objects : Mapping[str, GeoObject]
        The document's object lookup.

    Raises
    ------
    ValueError
        If ``obj_id`` is not a key in ``objects``.
    """
    if obj_id not in objects:
        raise ValueError(f"Referenced object {obj_id!r} does not exist")


def validate_altitude_finite(altitude: float) -> None:
    """Reject a non-finite altitude (``nan`` or ``±inf``).

    Altitude feeds 3-D distance, vector endpoints, and slice-plane membership;
    a ``nan`` or infinite value silently poisons every one of those. The
    ``Point`` constructor enforces the same rule, but this validator lets the
    point-import and form paths reject bad input before construction.

    Parameters
    ----------
    altitude : float
        The candidate altitude (Z) in metres.

    Raises
    ------
    ValueError
        If ``altitude`` is not finite.
    """
    if not math.isfinite(altitude):
        raise ValueError(f"Altitude must be finite; got {altitude!r}")
