"""
Customer Identity Graph.

A simple, in-memory directed graph of Visitor nodes and Edges derived
from canonical events.  Built once from an :class:`EventStore` and then
queried for analytics, dataset generation, and the journey engine.

The graph is intentionally lightweight — no Neo4j, no external
services.  Everything lives in Python dicts and can be serialised to
JSON for the API.

Node types
----------
* ``visitor`` — a customer with a stable ``visitor_id`` (after cross-
  camera ReID merges local track IDs).

Edge types
----------
* ``SeenInCamera``
* ``VisitedZone``
* ``Queued``
* ``Purchased``
* ``Exited``
* ``ReEntered``
* ``StaffInteraction``
* ``CrossCameraMatch`` (provenance — which tracks were merged)
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Tuple

from ..events import CanonicalEvent, CanonicalEventType, EventStore


# Edge vocabulary --------------------------------------------------------

EDGE_SEEN_IN_CAMERA = "SeenInCamera"
EDGE_VISITED_ZONE = "VisitedZone"
EDGE_QUEUED = "Queued"
EDGE_PURCHASED = "Purchased"
EDGE_EXITED = "Exited"
EDGE_REENTERED = "ReEntered"
EDGE_STAFF_INTERACTION = "StaffInteraction"
EDGE_CROSS_CAMERA_MATCH = "CrossCameraMatch"


@dataclass
class Edge:
    """A directed edge between a visitor and a target node."""

    edge_type: str
    target: str  # zone_id, camera_id, transaction_id, or other visitor
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_type": self.edge_type,
            "target": self.target,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class VisitorNode:
    """A single visitor."""

    visitor_id: str
    is_staff: bool = False
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    cameras_seen: Set[str] = field(default_factory=set)
    zones_visited: Set[str] = field(default_factory=set)
    edges: List[Edge] = field(default_factory=list)
    total_dwell_ms: int = 0
    has_purchase: bool = False
    purchase_amount: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "visitor_id": self.visitor_id,
            "is_staff": self.is_staff,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "cameras_seen": sorted(self.cameras_seen),
            "zones_visited": sorted(self.zones_visited),
            "has_purchase": self.has_purchase,
            "purchase_amount": self.purchase_amount,
            "total_dwell_ms": self.total_dwell_ms,
            "edges": [e.to_dict() for e in self.edges],
        }


class IdentityGraph:
    """Visitor × Zone × Camera × Purchase directed graph."""

    def __init__(self, store_id: str) -> None:
        self.store_id = store_id
        self._visitors: Dict[str, VisitorNode] = {}
        # Adjacency indices for fast lookup
        self._by_camera: Dict[str, Set[str]] = defaultdict(set)
        self._by_zone: Dict[str, Set[str]] = defaultdict(set)
        self._purchases: List[Dict[str, Any]] = []

    # Construction -------------------------------------------------------

    @classmethod
    def from_events(cls, store_id: str, events: Iterable[CanonicalEvent]) -> "IdentityGraph":
        graph = cls(store_id)
        for ev in events:
            if ev.store_id != store_id:
                continue
            graph.add_event(ev)
        return graph

    @classmethod
    def from_event_store(cls, store_id: str, event_store: EventStore) -> "IdentityGraph":
        return cls.from_events(store_id, event_store.iter_events(store_id))

    def add_event(self, ev: CanonicalEvent) -> None:
        if ev.visitor_id is None:
            return
        node = self._visitors.setdefault(ev.visitor_id, VisitorNode(visitor_id=ev.visitor_id))
        node.is_staff = node.is_staff or ev.is_staff
        if ev.timestamp:
            if node.first_seen is None or ev.timestamp < node.first_seen:
                node.first_seen = ev.timestamp
            if node.last_seen is None or ev.timestamp > node.last_seen:
                node.last_seen = ev.timestamp
        if ev.dwell_ms:
            node.total_dwell_ms += int(ev.dwell_ms)

        et = ev.event_type if isinstance(ev.event_type, CanonicalEventType) else CanonicalEventType(ev.event_type)
        meta = dict(ev.metadata or {})

        if et in (CanonicalEventType.ENTRY, CanonicalEventType.REENTRY):
            if ev.camera_id:
                node.cameras_seen.add(ev.camera_id)
                self._by_camera[ev.camera_id].add(ev.visitor_id)
                node.edges.append(Edge(EDGE_SEEN_IN_CAMERA, ev.camera_id, ev.timestamp, meta))
            if et == CanonicalEventType.REENTRY:
                node.edges.append(Edge(EDGE_REENTERED, ev.camera_id or "", ev.timestamp, meta))
            return

        if et in (CanonicalEventType.ZONE_ENTER, CanonicalEventType.ZONE_DWELL):
            if ev.zone_id:
                node.zones_visited.add(ev.zone_id)
                self._by_zone[ev.zone_id].add(ev.visitor_id)
                node.edges.append(Edge(EDGE_VISITED_ZONE, ev.zone_id, ev.timestamp, meta))
            return

        if et in (CanonicalEventType.QUEUE_ENTER,):
            if ev.zone_id:
                node.edges.append(Edge(EDGE_QUEUED, ev.zone_id, ev.timestamp, meta))
            return

        if et in (CanonicalEventType.PURCHASE, CanonicalEventType.REVENUE_ATTRIBUTED):
            amount = float(meta.get("amount", 0.0) or 0.0)
            node.has_purchase = True
            node.purchase_amount += amount
            self._purchases.append({
                "visitor_id": ev.visitor_id,
                "amount": amount,
                "timestamp": ev.timestamp.isoformat(),
                "metadata": meta,
            })
            node.edges.append(Edge(EDGE_PURCHASED, meta.get("transaction_id", ""), ev.timestamp, meta))
            return

        if et == CanonicalEventType.EXIT:
            node.edges.append(Edge(EDGE_EXITED, ev.camera_id or "", ev.timestamp, meta))
            return

        if et == CanonicalEventType.STAFF_INTERACTION:
            node.edges.append(Edge(EDGE_STAFF_INTERACTION, ev.zone_id or "", ev.timestamp, meta))
            return

        if et == CanonicalEventType.CROSS_CAMERA_MATCH:
            # Provenance edge: visitor matched across cameras
            from_visitor = meta.get("from_visitor_id")
            if from_visitor:
                node.edges.append(Edge(EDGE_CROSS_CAMERA_MATCH, from_visitor, ev.timestamp, meta))
            return

    # Queries -----------------------------------------------------------

    def __len__(self) -> int:
        return len(self._visitors)

    def __iter__(self) -> Iterator[VisitorNode]:
        return iter(self._visitors.values())

    def visitors(self) -> List[VisitorNode]:
        return list(self._visitors.values())

    def visitor(self, visitor_id: str) -> Optional[VisitorNode]:
        return self._visitors.get(visitor_id)

    def visitors_in_zone(self, zone_id: str) -> List[VisitorNode]:
        return [self._visitors[v] for v in self._by_zone.get(zone_id, set())]

    def visitors_in_camera(self, camera_id: str) -> List[VisitorNode]:
        return [self._visitors[v] for v in self._by_camera.get(camera_id, set())]

    def purchasers(self) -> List[VisitorNode]:
        return [v for v in self._visitors.values() if v.has_purchase]

    # Metrics -----------------------------------------------------------

    def total_visitors(self) -> int:
        return len(self._visitors)

    def total_staff(self) -> int:
        return sum(1 for v in self._visitors.values() if v.is_staff)

    def non_staff_visitors(self) -> int:
        return self.total_visitors() - self.total_staff()

    def total_purchases(self) -> int:
        return len(self._purchases)

    def total_revenue(self) -> float:
        return float(sum(p["amount"] for p in self._purchases))

    def conversion_rate(self) -> float:
        non_staff = self.non_staff_visitors()
        if non_staff <= 0:
            return 0.0
        # Unique purchasers (a visitor may have multiple purchases)
        unique_purchasers = len(self.purchasers())
        return unique_purchasers / non_staff

    def revenue_per_visitor(self) -> float:
        non_staff = self.non_staff_visitors()
        if non_staff <= 0:
            return 0.0
        return self.total_revenue() / non_staff

    def revenue_per_zone(self) -> Dict[str, float]:
        out: Dict[str, float] = defaultdict(float)
        for v in self._visitors.values():
            if not v.has_purchase:
                continue
            for z in v.zones_visited:
                out[z] += v.purchase_amount
        return dict(out)

    # Serialisation ----------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "store_id": self.store_id,
            "total_visitors": self.total_visitors(),
            "non_staff_visitors": self.non_staff_visitors(),
            "total_staff": self.total_staff(),
            "total_purchases": self.total_purchases(),
            "total_revenue": self.total_revenue(),
            "conversion_rate": self.conversion_rate(),
            "revenue_per_visitor": self.revenue_per_visitor(),
            "purchases": self._purchases,
            "visitors": [v.to_dict() for v in self._visitors.values()],
        }

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)


__all__ = [
    "EDGE_CROSS_CAMERA_MATCH",
    "EDGE_EXITED",
    "EDGE_PURCHASED",
    "EDGE_QUEUED",
    "EDGE_REENTERED",
    "EDGE_SEEN_IN_CAMERA",
    "EDGE_STAFF_INTERACTION",
    "EDGE_VISITED_ZONE",
    "Edge",
    "IdentityGraph",
    "VisitorNode",
]
