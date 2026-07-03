"""
Canonical store metadata module.

Every store in the platform is described by a single ``metadata.json`` file
that conforms to the schema in this module.  The detection pipeline, the
analytics engine, the journey builder, the purchase attribution engine, the
training pipeline and the multi-store onboarding tool all read this same
schema.

The schema is the single source of truth for:

  * the store identity and physical layout
  * every camera in the store (role, video source, coverage)
  * every zone in the store (type, polygon, brands)
  * the camera transition graph used for cross-camera ReID
  * billing/queue/entry/exit heuristics derived from polygons

Design principles:

  * **No code changes for a new store.**  Onboarding a new store means
    dropping a metadata.json + cameras/ + pos.csv into a folder.  The
    pipeline discovers everything from metadata.
  * **Hard-fail validation.**  Bad metadata fails fast with a clear message
    — we never silently fall back to a default that masks the real issue.
  * **Normalized polygons.**  All zone polygons are stored in 0-1
    coordinates so a single polygon works across any camera resolution.
  * **Bilingual roles.**  Camera roles and zone types are enumerated to
    keep the API and storage consistent.
"""

from .schema import (
    SCHEMA_VERSION,
    CameraMetadata,
    CameraRole,
    EntryLine,
    LayoutMetadata,
    StoreMetadata,
    TransitionGraph,
    ZoneMetadata,
    ZoneType,
    build_store_metadata,
)
from .loader import (
    MetadataLoadError,
    load_store_metadata,
)
from .validator import (
    MetadataValidationError,
    ValidationIssue,
    validate_store_metadata,
    validate_transition_graph,
    validate_zone_polygon,
    summarize_issues,
)

__all__ = [
    "SCHEMA_VERSION",
    "CameraMetadata",
    "CameraRole",
    "EntryLine",
    "LayoutMetadata",
    "StoreMetadata",
    "TransitionGraph",
    "ZoneMetadata",
    "ZoneType",
    "build_store_metadata",
    "MetadataLoadError",
    "load_store_metadata",
    "MetadataValidationError",
    "ValidationIssue",
    "validate_store_metadata",
    "validate_transition_graph",
    "validate_zone_polygon",
]
