"""
Metadata validator.

Hard-fail validation.  Every problem is reported as a
:class:`ValidationIssue` with a stable error code and a clear message.
The pipeline never silently falls back to a default that masks the real
issue.

Validation rules
----------------

* ``store_id`` and ``store_name`` are required and non-empty.
* Every camera must have a unique ``camera_id``, a valid role, a
  ``source_file`` that exists in the store's ``cameras/`` folder, and a
  list of ``coverage`` zones that exist in the zone list.
* Every zone must have a unique ``zone_id`` and a valid ``zone_type``.
* The transition graph must reference camera_ids that exist and must be
  symmetric for non-exit-only cameras (i.e. if A→B is listed and B is
  not EXIT/STAFF, then B→A is encouraged but not required).
* Every polygon's points must be normalized to [0, 1] and have at
  least three points (or be empty).
* Camera roles and zone types must be in the allowed enums.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from .schema import CameraRole, StoreMetadata, ZoneType


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Issue model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationIssue:
    """A single problem found in a store's metadata."""

    code: str
    message: str
    path: str = ""  # JSON-pointer-ish path, e.g. "cameras[2].role"

    def __str__(self) -> str:
        if self.path:
            return f"[{self.code}] at {self.path}: {self.message}"
        return f"[{self.code}] {self.message}"


class MetadataValidationError(RuntimeError):
    """Raised by helpers that aggregate issues and bail on the first."""

    def __init__(self, issues: Sequence[ValidationIssue]):
        self.issues = list(issues)
        super().__init__("\n".join(str(i) for i in self.issues))


# ---------------------------------------------------------------------------
# Polygon helpers
# ---------------------------------------------------------------------------


def validate_zone_polygon(
    polygon: Sequence[Sequence[float]],
    *,
    path: str = "",
) -> List[ValidationIssue]:
    """Return a list of issues for a single polygon.  Empty list == OK."""

    issues: List[ValidationIssue] = []
    pts = list(polygon or [])
    if not pts:
        return issues
    if len(pts) < 3:
        issues.append(
            ValidationIssue(
                code="POLYGON_TOO_FEW_POINTS",
                message=f"Polygon has {len(pts)} point(s); minimum 3 required.",
                path=path,
            )
        )
        return issues
    for idx, point in enumerate(pts):
        if len(point) != 2:
            issues.append(
                ValidationIssue(
                    code="POLYGON_BAD_POINT_SHAPE",
                    message=(
                        f"Polygon point #{idx} has {len(point)} coordinate(s); "
                        f"expected 2 (x, y)."
                    ),
                    path=f"{path}[{idx}]",
                )
            )
            continue
        x, y = point
        if not (0.0 <= x <= 1.0):
            issues.append(
                ValidationIssue(
                    code="POLYGON_X_OUT_OF_RANGE",
                    message=(
                        f"Polygon point #{idx} x={x} is outside [0, 1]. "
                        f"Polygons must be stored in normalized 0-1 space."
                    ),
                    path=f"{path}[{idx}]",
                )
            )
        if not (0.0 <= y <= 1.0):
            issues.append(
                ValidationIssue(
                    code="POLYGON_Y_OUT_OF_RANGE",
                    message=(
                        f"Polygon point #{idx} y={y} is outside [0, 1]. "
                        f"Polygons must be stored in normalized 0-1 space."
                    ),
                    path=f"{path}[{idx}]",
                )
            )
    return issues


def validate_zone_box(
    box: Optional[Sequence[float]],
    *,
    path: str = "",
) -> List[ValidationIssue]:
    """Validate a ``layout_box`` (4 floats)."""

    if box is None:
        return []
    if len(box) != 4:
        return [
            ValidationIssue(
                code="LAYOUT_BOX_WRONG_SHAPE",
                message=(
                    f"layout_box has {len(box)} values; expected 4 "
                    f"(x1, y1, x2, y2)."
                ),
                path=path,
            )
        ]
    x1, y1, x2, y2 = (float(v) for v in box)
    if x2 <= x1 or y2 <= y1:
        return [
            ValidationIssue(
                code="LAYOUT_BOX_DEGENERATE",
                message=(
                    f"layout_box [{x1}, {y1}, {x2}, {y2}] is degenerate "
                    f"(x2<=x1 or y2<=y1)."
                ),
                path=path,
            )
        ]
    return []


# ---------------------------------------------------------------------------
# Transition graph
# ---------------------------------------------------------------------------


def validate_transition_graph(
    graph_edges: dict,
    camera_ids: Iterable[str],
    *,
    path: str = "transition_graph",
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    known = set(camera_ids)
    for src, dsts in graph_edges.items():
        if src not in known:
            issues.append(
                ValidationIssue(
                    code="TRANSITION_UNKNOWN_CAMERA",
                    message=(
                        f"transition_graph references unknown camera {src!r}; "
                        f"known: {sorted(known)}."
                    ),
                    path=f"{path}.{src}",
                )
            )
        for dst in dsts or []:
            if dst not in known:
                issues.append(
                    ValidationIssue(
                        code="TRANSITION_UNKNOWN_NEIGHBOR",
                        message=(
                            f"transition_graph.{src} references unknown "
                            f"camera {dst!r}."
                        ),
                        path=f"{path}.{src}",
                    )
                )
            if dst == src:
                issues.append(
                    ValidationIssue(
                        code="TRANSITION_SELF_LOOP",
                        message=f"transition_graph.{src} includes self.",
                        path=f"{path}.{src}",
                    )
                )
    return issues


# ---------------------------------------------------------------------------
# Top-level validator
# ---------------------------------------------------------------------------


_REQUIRED_TOP_KEYS = ("store", "zones", "cameras", "transition_graph")


def _check_required_keys(
    raw: object,
    *,
    path: str = "",
) -> List[ValidationIssue]:
    if not isinstance(raw, dict):
        return [
            ValidationIssue(
                code="METADATA_NOT_OBJECT",
                message="Top-level metadata must be a JSON object.",
                path=path,
            )
        ]
    issues: List[ValidationIssue] = []
    for key in _REQUIRED_TOP_KEYS:
        if key not in raw:
            issues.append(
                ValidationIssue(
                    code="METADATA_MISSING_KEY",
                    message=f"Top-level metadata is missing required key {key!r}.",
                    path=key,
                )
            )
    return issues


def validate_store_metadata(
    metadata: StoreMetadata,
    *,
    strict: bool = True,
    data_dir: Optional[Path] = None,
) -> List[ValidationIssue]:
    """Validate an already-parsed :class:`StoreMetadata`.

    Args:
        metadata: Parsed metadata to validate.
        strict: If true (default), unknown roles/zone_types are
            rejected.  Set to false during forward-compat ingestion to
            just warn on unknown enums.
        data_dir: If provided, the validator also checks that each
            camera's ``source_file`` exists under
            ``data_dir/<store_id>/cameras/``.

    Returns:
        List of :class:`ValidationIssue` (empty == OK).
    """

    issues: List[ValidationIssue] = []

    # Store identity
    if not metadata.store_id:
        issues.append(
            ValidationIssue(
                code="STORE_ID_EMPTY",
                message="store.store_id is required.",
                path="store.store_id",
            )
        )
    if not metadata.store_name:
        issues.append(
            ValidationIssue(
                code="STORE_NAME_EMPTY",
                message="store.store_name is required.",
                path="store.store_name",
            )
        )

    # Layout
    if metadata.layout.width <= 0 or metadata.layout.height <= 0:
        issues.append(
            ValidationIssue(
                code="LAYOUT_BAD_SIZE",
                message=(
                    f"layout.width and layout.height must be > 0; "
                    f"got {metadata.layout.width} x {metadata.layout.height}."
                ),
                path="store.layout",
            )
        )

    # Zones
    zone_ids: List[str] = []
    for idx, zone in enumerate(metadata.zones):
        if not zone.zone_id:
            issues.append(
                ValidationIssue(
                    code="ZONE_ID_EMPTY",
                    message=f"zones[{idx}].zone_id is required.",
                    path=f"zones[{idx}].zone_id",
                )
            )
        if zone.zone_id in zone_ids:
            issues.append(
                ValidationIssue(
                    code="ZONE_ID_DUPLICATE",
                    message=(
                        f"zones[{idx}].zone_id {zone.zone_id!r} is "
                        f"duplicated."
                    ),
                    path=f"zones[{idx}].zone_id",
                )
            )
        zone_ids.append(zone.zone_id)
        issues.extend(
            validate_zone_polygon(zone.polygon, path=f"zones[{idx}].polygon")
        )
        issues.extend(
            validate_zone_box(zone.layout_box, path=f"zones[{idx}].layout_box")
        )
        if strict and zone.zone_type not in ZoneType:
            issues.append(
                ValidationIssue(
                    code="ZONE_TYPE_UNKNOWN",
                    message=(
                        f"zones[{idx}].zone_type {zone.zone_type!r} is not "
                        f"in {[t.value for t in ZoneType]}."
                    ),
                    path=f"zones[{idx}].zone_type",
                )
            )

    # Cameras
    camera_ids: List[str] = []
    zone_id_set = set(zone_ids)
    for idx, camera in enumerate(metadata.cameras):
        if not camera.camera_id:
            issues.append(
                ValidationIssue(
                    code="CAMERA_ID_EMPTY",
                    message=f"cameras[{idx}].camera_id is required.",
                    path=f"cameras[{idx}].camera_id",
                )
            )
        if camera.camera_id in camera_ids:
            issues.append(
                ValidationIssue(
                    code="CAMERA_ID_DUPLICATE",
                    message=(
                        f"cameras[{idx}].camera_id {camera.camera_id!r} is "
                        f"duplicated."
                    ),
                    path=f"cameras[{idx}].camera_id",
                )
            )
        camera_ids.append(camera.camera_id)

        if not camera.source_file:
            issues.append(
                ValidationIssue(
                    code="CAMERA_SOURCE_FILE_MISSING",
                    message=(
                        f"cameras[{idx}].source_file is required (filename "
                        f"inside the store's cameras/ folder)."
                    ),
                    path=f"cameras[{idx}].source_file",
                )
            )
        elif data_dir is not None:
            # cameras live in <metadata_dir>/cameras/, not <data_dir>/<store_id>/cameras/
            # data_dir is metadata_path.parent (the store folder), not the data/ root
            expected = data_dir / "cameras" / camera.source_file
            if not expected.exists():
                issues.append(
                    ValidationIssue(
                        code="CAMERA_SOURCE_FILE_NOT_FOUND",
                        message=(
                            f"cameras[{idx}].source_file {camera.source_file!r} "
                            f"does not exist at {expected}."
                        ),
                        path=f"cameras[{idx}].source_file",
                    )
                )

        for c_idx, zone_id in enumerate(camera.coverage):
            if zone_id not in zone_id_set:
                issues.append(
                    ValidationIssue(
                        code="CAMERA_COVERAGE_UNKNOWN_ZONE",
                        message=(
                            f"cameras[{idx}].coverage[{c_idx}] {zone_id!r} "
                            f"is not in the store's zone list."
                        ),
                        path=f"cameras[{idx}].coverage[{c_idx}]",
                    )
                )

        for zid, poly in camera.zone_polygons.items():
            if zid not in zone_id_set:
                issues.append(
                    ValidationIssue(
                        code="CAMERA_ZONE_POLYGON_UNKNOWN_ZONE",
                        message=(
                            f"cameras[{idx}].zone_polygons references unknown "
                            f"zone {zid!r}."
                        ),
                        path=f"cameras[{idx}].zone_polygons.{zid}",
                    )
                )
            issues.extend(
                validate_zone_polygon(
                    poly, path=f"cameras[{idx}].zone_polygons.{zid}"
                )
            )

        if strict and camera.role not in CameraRole:
            issues.append(
                ValidationIssue(
                    code="CAMERA_ROLE_UNKNOWN",
                    message=(
                        f"cameras[{idx}].role {camera.role!r} is not in "
                        f"{[r.value for r in CameraRole]}."
                    ),
                    path=f"cameras[{idx}].role",
                )
            )

    # Transition graph
    issues.extend(
        validate_transition_graph(
            metadata.transition_graph.edges,
            camera_ids,
        )
    )

    # If a camera lists adjacent_cameras they must all be in the graph
    # (this is informational, not fatal).
    graph_set = {src for src in metadata.transition_graph.edges}
    for idx, camera in enumerate(metadata.cameras):
        for adj in camera.adjacent_cameras:
            if adj not in {c.camera_id for c in metadata.cameras}:
                issues.append(
                    ValidationIssue(
                        code="CAMERA_ADJACENT_UNKNOWN",
                        message=(
                            f"cameras[{idx}].adjacent_cameras references "
                            f"unknown camera {adj!r}."
                        ),
                        path=f"cameras[{idx}].adjacent_cameras",
                    )
                )
            if camera.camera_id not in graph_set and adj:
                issues.append(
                    ValidationIssue(
                        code="CAMERA_ADJACENT_MISSING_GRAPH_ENTRY",
                        message=(
                            f"cameras[{idx}] {camera.camera_id!r} lists "
                            f"adjacent_cameras but is missing from "
                            f"transition_graph; add {camera.camera_id!r} "
                            f"to transition_graph."
                        ),
                        path="transition_graph",
                    )
                )
                break  # one warning per camera is enough

    return issues


def summarize_issues(issues: Sequence[ValidationIssue]) -> str:
    if not issues:
        return "no issues"
    return f"{len(issues)} issue(s): " + "; ".join(
        f"{i.code}@{i.path or 'root'}" for i in issues
    )
