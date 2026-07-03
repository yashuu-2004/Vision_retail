"""
Store metadata schema.

This module is the canonical definition of the on-disk shape of a store.
It is intentionally framework-free (no Pydantic dependency) so it can be
imported in constrained environments like the video pipeline and the
training scripts.

A store is fully described by a single :class:`StoreMetadata` object that
holds the camera list, the zone list, the layout, and the camera
transition graph.  Every polygon is normalized to 0-1 coordinates so the
same metadata is independent of video resolution.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


SCHEMA_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class CameraRole(Enum):
    """What kind of activity a camera primarily captures.

    The pipeline uses the role to decide which event generators run on
    a given camera (e.g. queue logic only on BILLING cameras).  A new
    store can use any subset of these roles.

    Canonical values: ENTRY, EXIT, ZONE, BILLING, QUEUE, STAFF.
    Legacy aliases accepted for backward compat: FLOOR→ZONE, SUPPORT→STAFF.
    """

    # Canonical values (Phase 1 spec)
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    ZONE = "ZONE"
    BILLING = "BILLING"
    QUEUE = "QUEUE"
    STAFF = "STAFF"
    # Legacy aliases from existing Brigade Road metadata
    FLOOR = "FLOOR"
    SUPPORT = "SUPPORT"

    @classmethod
    def from_string(cls, value: str) -> "CameraRole":
        normalized = (value or "").strip().upper()
        # _CAMERA_ROLE_LEGACY is defined at module level after this class
        leg = globals().get("_CAMERA_ROLE_LEGACY", {})
        if normalized in leg:
            return cls(leg[normalized])
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(
                f"Unknown camera role '{value}'. "
                f"Allowed: {[r.value for r in cls]}"
            ) from exc


class ZoneType(Enum):
    """What a zone represents in the store.

    Used for analytics segmentation (e.g. BRAND vs AISLE vs CHECKOUT
    conversion rates) and for filtering during onboarding.

    Canonical values: ENTRY, EXIT, AISLE, DISPLAY, BRAND, CHECKOUT,
    QUEUE, STAFF.

    Legacy values accepted for backward-compat with existing Brigade Road
    metadata: FLOOR, ZONE, BILLING, SERVICE, SKIN, MAKEUP, HAIR,
    PERSONAL_CARE, BACK_AREA.  Legacy values are normalised to their
    nearest canonical equivalent internally.
    """

    # Canonical values (Phase 1 spec)
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    AISLE = "AISLE"
    DISPLAY = "DISPLAY"
    BRAND = "BRAND"
    CHECKOUT = "CHECKOUT"
    QUEUE = "QUEUE"
    STAFF = "STAFF"
    # Legacy values (existing Brigade Road data)
    FLOOR = "FLOOR"
    ZONE = "ZONE"
    BILLING = "BILLING"
    SERVICE = "SERVICE"
    SKIN = "SKIN"
    MAKEUP = "MAKEUP"
    HAIR = "HAIR"
    PERSONAL_CARE = "PERSONAL_CARE"
    BACK_AREA = "BACK_AREA"

    @classmethod
    def from_string(cls, value: str) -> "ZoneType":
        normalized = (value or "").strip().upper()
        # _ZONE_TYPE_LEGACY is defined at module level after this class
        leg = globals().get("_ZONE_TYPE_LEGACY", {})
        if normalized in leg:
            return cls(leg[normalized])
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(
                f"Unknown zone type '{value}'. "
                f"Allowed: {[t.value for t in cls]}"
            ) from exc


# ---------------------------------------------------------------------------
# Legacy value normalisers (must live here — after the enum classes — so
# enum members are in scope; never declared inside an Enum class body or
# Python will treat them as members).
# ---------------------------------------------------------------------------

_CAMERA_ROLE_LEGACY: Dict[str, str] = {
    "FLOOR": "ZONE",
    "SUPPORT": "STAFF",
}

_ZONE_TYPE_LEGACY: Dict[str, str] = {
    "FLOOR": "AISLE",
    "ZONE": "AISLE",
    "BILLING": "CHECKOUT",
    "SERVICE": "STAFF",
    "SKIN": "BRAND",
    "MAKEUP": "BRAND",
    "HAIR": "BRAND",
    "PERSONAL_CARE": "BRAND",
    "BACK_AREA": "STAFF",
}


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


@dataclass
class EntryLine:
    """Entry/exit detection line for an entry/exit camera.

    The pipeline uses this to derive entry/exit events from a track's
    trajectory.  All values are in normalized 0-1 coordinates.

    Attributes:
        y_normalized: Vertical position of the line (0 top, 1 bottom).
        exterior_side: "above" or "below" the line is the exterior.
    """

    y_normalized: float
    exterior_side: str = "above"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "y_normalized": self.y_normalized,
            "exterior_side": self.exterior_side,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EntryLine":
        return cls(
            y_normalized=float(payload["y_normalized"]),
            exterior_side=str(payload.get("exterior_side", "above")),
        )


@dataclass
class LayoutMetadata:
    """Logical layout of the store floor.

    Width/height are in arbitrary layout units (we treat them as pixels
    of the layout image).  Polygons in zones and cameras are stored in
    normalized 0-1 space so they remain independent of this size.
    """

    width: float
    height: float
    image: Optional[str] = None
    units: str = "px"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "image": self.image,
            "units": self.units,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LayoutMetadata":
        return cls(
            width=float(payload["width"]),
            height=float(payload["height"]),
            image=payload.get("image"),
            units=str(payload.get("units", "px")),
        )


@dataclass
class CameraMetadata:
    """One physical camera in the store.

    Attributes:
        camera_id: Stable identifier used in events and DB.  Unique per
            store.  Convention: ``CAM_<n>`` or ``<AREA>_<n>`` but the
            platform treats it as opaque.
        role: What kind of activity the camera primarily captures.
        source_file: Filename inside the store's ``cameras/`` folder.
        name: Optional human-readable name for dashboards.
        fps: Optional expected FPS.  Pipeline uses actual cv2 value.
        resolution: Optional ``[width, height]`` in pixels.
        coverage: List of zone_ids this camera's view contains.
        zone_polygons: Optional per-camera normalized polygons.  When
            absent, the loader derives a rectangular polygon from each
            zone's ``layout_box``.
        adjacent_cameras: Optional explicit adjacency list.  When
            absent, the loader uses the ``transition_graph``.
        entry_line: Optional explicit entry/exit detection line.  Used
            only for cameras with role ENTRY/EXIT.
    """

    camera_id: str
    role: CameraRole
    source_file: str
    name: Optional[str] = None
    fps: Optional[float] = None
    resolution: Optional[Tuple[int, int]] = None
    coverage: List[str] = field(default_factory=list)
    zone_polygons: Dict[str, List[Tuple[float, float]]] = field(default_factory=dict)
    adjacent_cameras: List[str] = field(default_factory=list)
    entry_line: Optional[EntryLine] = None

    def __post_init__(self) -> None:
        # Normalize entry_line dict -> EntryLine (handles programmatic construction)
        if isinstance(self.entry_line, dict):
            self.entry_line = EntryLine.from_dict(self.entry_line)
        # Normalize role string -> CameraRole
        if isinstance(self.role, str):
            self.role = CameraRole.from_string(self.role)

    def to_dict(self) -> Dict[str, Any]:
        entry_line_val = self.entry_line
        if isinstance(entry_line_val, EntryLine):
            entry_line_out = entry_line_val.to_dict()
        elif isinstance(entry_line_val, dict):
            entry_line_out = entry_line_val
        else:
            entry_line_out = None
        return {
            "camera_id": self.camera_id,
            "role": self.role.value,
            "source_file": self.source_file,
            "name": self.name,
            "fps": self.fps,
            "resolution": list(self.resolution) if self.resolution else None,
            "coverage": list(self.coverage),
            "zone_polygons": {
                zid: [list(pt) for pt in poly]
                for zid, poly in self.zone_polygons.items()
            },
            "adjacent_cameras": list(self.adjacent_cameras),
            "entry_line": entry_line_out,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CameraMetadata":
        resolution = payload.get("resolution")
        resolution_pair: Optional[Tuple[int, int]] = None
        if resolution is not None:
            resolution_pair = (int(resolution[0]), int(resolution[1]))

        return cls(
            camera_id=str(payload["camera_id"]),
            role=CameraRole.from_string(str(payload.get("role", "ZONE"))),
            source_file=str(payload["source_file"]),
            name=payload.get("name"),
            fps=float(payload["fps"]) if payload.get("fps") is not None else None,
            resolution=resolution_pair,
            coverage=[str(z) for z in payload.get("coverage", [])],
            zone_polygons={
                str(zid): [(float(x), float(y)) for x, y in (poly or [])]
                for zid, poly in (payload.get("zone_polygons") or {}).items()
            },
            adjacent_cameras=[str(c) for c in payload.get("adjacent_cameras", [])],
            entry_line=EntryLine.from_dict(payload["entry_line"])
            if payload.get("entry_line")
            else None,
        )


@dataclass
class ZoneMetadata:
    """One logical zone in the store (brand, aisle, checkout, etc.).

    Attributes:
        zone_id: Stable identifier unique per store.
        zone_name: Human-readable name for dashboards.
        zone_type: Used for analytics segmentation.
        layout_box: Optional ``[x1, y1, x2, y2]`` in layout pixels.
        polygon: Optional normalized polygon.  When the camera doesn't
            supply its own ``zone_polygons``, this is what gets used.
        brands: Optional list of brand names sold in this zone (mainly
            for BRAND zones).
        metadata: Freeform additional info (e.g. planogram refs).
    """

    zone_id: str
    zone_name: str
    zone_type: ZoneType
    layout_box: Optional[Tuple[float, float, float, float]] = None
    polygon: List[Tuple[float, float]] = field(default_factory=list)
    brands: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalize zone_type string -> ZoneType
        if isinstance(self.zone_type, str):
            self.zone_type = ZoneType.from_string(self.zone_type)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "zone_type": self.zone_type.value,
            "layout_box": list(self.layout_box) if self.layout_box else None,
            "polygon": [list(pt) for pt in self.polygon],
            "brands": list(self.brands),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ZoneMetadata":
        layout_box = payload.get("layout_box")
        layout_tuple: Optional[Tuple[float, float, float, float]] = None
        if layout_box is not None:
            layout_tuple = (
                float(layout_box[0]),
                float(layout_box[1]),
                float(layout_box[2]),
                float(layout_box[3]),
            )
        return cls(
            zone_id=str(payload["zone_id"]),
            zone_name=str(payload.get("zone_name", payload["zone_id"])),
            zone_type=ZoneType.from_string(str(payload.get("zone_type", "AISLE"))),
            layout_box=layout_tuple,
            polygon=[(float(x), float(y)) for x, y in (payload.get("polygon") or [])],
            brands=[str(b) for b in payload.get("brands", [])],
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass
class TransitionGraph:
    """Adjacency list of allowed camera transitions.

    Used by cross-camera ReID to decide which camera a track in camera
    A could plausibly be the same person as a track in camera B.

    Edges are directional.  The graph should be symmetric for normal
    flow but a store can express one-way restrictions (e.g. exit-only
    cameras).
    """

    edges: Dict[str, List[str]] = field(default_factory=dict)

    def neighbors(self, camera_id: str) -> List[str]:
        return list(self.edges.get(camera_id, []))

    def has_edge(self, from_camera: str, to_camera: str) -> bool:
        return to_camera in self.edges.get(from_camera, [])

    def to_dict(self) -> Dict[str, List[str]]:
        return {k: list(v) for k, v in self.edges.items()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TransitionGraph":
        return cls(
            edges={
                str(src): [str(dst) for dst in dsts]
                for src, dsts in payload.items()
            }
        )


# ---------------------------------------------------------------------------
# Top-level container
# ---------------------------------------------------------------------------


@dataclass
class StoreMetadata:
    """Full metadata for a single store.

    The single source of truth.  The detection pipeline and every
    downstream service read this.
    """

    store_id: str
    store_name: str
    layout: LayoutMetadata
    zones: List[ZoneMetadata]
    cameras: List[CameraMetadata]
    transition_graph: TransitionGraph
    city: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    layout_source: Optional[str] = None
    layout_notes: Optional[str] = None
    schema_version: str = SCHEMA_VERSION

    # ------------------------------------------------------------------
    # Convenience accessors used widely by the pipeline
    # ------------------------------------------------------------------

    @property
    def zone_ids(self) -> List[str]:
        return [z.zone_id for z in self.zones]

    @property
    def zone_by_id(self) -> Dict[str, ZoneMetadata]:
        return {z.zone_id: z for z in self.zones}

    @property
    def camera_by_id(self) -> Dict[str, CameraMetadata]:
        return {c.camera_id: c for c in self.cameras}

    def zones_for_camera(self, camera_id: str) -> List[ZoneMetadata]:
        camera = self.camera_by_id.get(camera_id)
        if not camera:
            return []
        by_id = self.zone_by_id
        return [by_id[zid] for zid in camera.coverage if zid in by_id]

    def transition_neighbors(self, camera_id: str) -> List[str]:
        return self.transition_graph.neighbors(camera_id)

    # ------------------------------------------------------------------
    # (De)serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "store": {
                "store_id": self.store_id,
                "store_name": self.store_name,
                "city": self.city,
                "country": self.country,
                "timezone": self.timezone,
                "aliases": list(self.aliases),
                "layout_source": self.layout_source,
                "layout_notes": self.layout_notes,
                "layout": self.layout.to_dict(),
            },
            "zones": [z.to_dict() for z in self.zones],
            "cameras": [c.to_dict() for c in self.cameras],
            "transition_graph": self.transition_graph.to_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    def write_to(self, path: Path) -> None:
        path.write_text(self.to_json(indent=2))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StoreMetadata":
        # Backward compat: legacy flat format (store_1/store_2) had
        # top-level store_id instead of nested store.store_id.
        store_block = payload.get("store") or {}
        top_level_id = payload.get("store_id")
        nested_id = store_block.get("store_id")
        resolved_store_id = nested_id or top_level_id
        if not resolved_store_id:
            raise KeyError(
                "store.store_id or top-level store_id is required"
            )

        # Backward compat: legacy Brigade Road used "camera_adjacency" instead
        # of "transition_graph".
        graph_source = (
            payload.get("transition_graph")
            or payload.get("camera_adjacency")
            or {}
        )
        # Also accept top-level cameras list for legacy format
        cameras_raw = payload.get("cameras") or []
        zones_raw = payload.get("zones") or []

        layout_block = store_block.get("layout") or {
            "width": 1000.0,
            "height": 800.0,
        }
        return cls(
            schema_version=str(payload.get("schema_version", SCHEMA_VERSION)),
            store_id=str(resolved_store_id),
            store_name=str(
                store_block.get("store_name") or resolved_store_id
            ),
            city=store_block.get("city"),
            country=store_block.get("country"),
            timezone=store_block.get("timezone"),
            aliases=[str(a) for a in store_block.get("aliases", [])],
            layout_source=store_block.get("layout_source"),
            layout_notes=store_block.get("layout_notes"),
            layout=LayoutMetadata.from_dict(layout_block),
            zones=[ZoneMetadata.from_dict(z) for z in zones_raw],
            cameras=[CameraMetadata.from_dict(c) for c in cameras_raw],
            transition_graph=TransitionGraph.from_dict(graph_source),
        )

    @classmethod
    def from_json_file(cls, path: Path) -> "StoreMetadata":
        return cls.from_dict(json.loads(path.read_text()))


# ---------------------------------------------------------------------------
# Builder helpers used by the metadata onboarding tool
# ---------------------------------------------------------------------------


def build_store_metadata(
    *,
    store_id: str,
    store_name: str,
    layout_width: float = 1000.0,
    layout_height: float = 800.0,
    layout_image: Optional[str] = None,
    layout_units: str = "px",
    city: Optional[str] = None,
    country: Optional[str] = None,
    timezone: Optional[str] = None,
    aliases: Optional[Iterable[str]] = None,
    layout_source: Optional[str] = None,
    layout_notes: Optional[str] = None,
    zones: Optional[Iterable[ZoneMetadata]] = None,
    cameras: Optional[Iterable[CameraMetadata]] = None,
    transition_edges: Optional[Mapping[str, Iterable[str]]] = None,
) -> StoreMetadata:
    """Programmatic constructor used by the onboarding tool.

    All arguments are explicit; the function does no inference.  Anything
    not provided gets a safe empty default.
    """

    zone_list = list(zones or [])
    camera_list = list(cameras or [])

    edge_map: Dict[str, List[str]] = {}
    for src, dsts in (transition_edges or {}).items():
        edge_map[str(src)] = [str(d) for d in dsts]

    # Backfill adjacent_cameras from the transition graph where missing.
    by_id = {c.camera_id: c for c in camera_list}
    for camera in camera_list:
        if not camera.adjacent_cameras:
            camera.adjacent_cameras = list(edge_map.get(camera.camera_id, []))

    return StoreMetadata(
        store_id=store_id,
        store_name=store_name,
        layout=LayoutMetadata(
            width=layout_width,
            height=layout_height,
            image=layout_image,
            units=layout_units,
        ),
        zones=zone_list,
        cameras=camera_list,
        transition_graph=TransitionGraph(edges=edge_map),
        city=city,
        country=country,
        timezone=timezone,
        aliases=list(aliases or []),
        layout_source=layout_source,
        layout_notes=layout_notes,
    )
