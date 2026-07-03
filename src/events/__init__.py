"""
Canonical event schema for the VisionRetail AI platform.

This module is the *single source of truth* for what kinds of events the
detection pipeline, POS attribution, cross-camera ReID, and analytics
engines can produce.  Every event in the system is one of these types;
nothing else flows into the analytics layer or the dataset generators.

Why this exists
---------------
Before the event-sourcing refactor, event types were strings scattered
across the pipeline (``"ENTRY"``, ``"ZONE_ENTER"``, ``"BILLING_QUEUE_JOIN"``,
``"PURCHASE"``, ...).  Each subsystem accepted a different set, and
mismatches surfaced as silent analytics gaps.

``CanonicalEventType`` is the closed set, with a stable string ``value``
suitable for storage in JSON/JSONL/Postgres.  All event payloads are
Pydantic models with JSON-safe defaults, so they round-trip cleanly into
the API, the dataset writers, and the identity graph.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .store import EventStore


class CanonicalEventType(str, Enum):
    """The closed set of event types emitted by the platform.

    Add a new value only when an entirely new business concept is
    needed; field-level variations belong in the event payload, not in
    a new event type.
    """

    # Visitor lifecycle
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    REENTRY = "REENTRY"

    # Zone behaviour
    ZONE_ENTER = "ZONE_ENTER"
    ZONE_EXIT = "ZONE_EXIT"
    ZONE_DWELL = "ZONE_DWELL"

    # Checkout / queue
    QUEUE_ENTER = "QUEUE_ENTER"
    QUEUE_EXIT = "QUEUE_EXIT"
    QUEUE_ABANDON = "QUEUE_ABANDON"
    CHECKOUT_SERVICE = "CHECKOUT_SERVICE"

    # Commerce
    PURCHASE = "PURCHASE"
    REVENUE_ATTRIBUTED = "REVENUE_ATTRIBUTED"

    # Staff / supervision
    STAFF_INTERACTION = "STAFF_INTERACTION"
    STAFF_TRACK = "STAFF_TRACK"

    # Cross-camera identity
    CROSS_CAMERA_MATCH = "CROSS_CAMERA_MATCH"
    CROSS_CAMERA_REJECT = "CROSS_CAMERA_REJECT"

    @classmethod
    def values(cls) -> List[str]:
        return [m.value for m in cls]


class CanonicalEvent(BaseModel):
    """Universal event envelope.

    Every event that flows through the platform — whether produced by
    the detection pipeline, POS attribution, cross-camera ReID, or the
    staff detector — conforms to this shape.  The ``event_id`` is
    deterministic from the producer + content so duplicate ingests are
    idempotent.

    ``metadata`` is a free-form extension point; canonical fields stay
    at the top level for analytics queries.
    """

    event_id: str
    event_type: CanonicalEventType
    store_id: str
    camera_id: Optional[str] = None
    visitor_id: Optional[str] = None
    zone_id: Optional[str] = None
    timestamp: datetime
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    dwell_ms: Optional[int] = None
    is_staff: bool = False
    bbox: Optional[List[int]] = None
    track_id: Optional[int] = None
    frame_number: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        out = self.model_dump(mode="json")
        # Keep the enum as its string for downstream JSON consumers.
        if isinstance(out.get("event_type"), dict):
            out["event_type"] = self.event_type.value
        return out


# Validation helper ----------------------------------------------------------

def is_canonical_event_type(value: Any) -> bool:
    """Return True if ``value`` is a known canonical event type."""
    if isinstance(value, CanonicalEventType):
        return True
    if isinstance(value, str):
        return value in CanonicalEventType.values()
    return False


__all__ = [
    "CanonicalEvent",
    "CanonicalEventType",
    "EventStore",
    "is_canonical_event_type",
]
