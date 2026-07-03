"""
Multi-store analytics orchestrator.

Ties together the metadata system, the event store, the identity graph,
and the dataset generator into a single, store-agnostic surface.  Every
call here is metadata-driven — no hardcoded store IDs, zone IDs, or
camera roles.

Used by the API for cross-store endpoints and by the dashboard for the
store selector.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..datasets import build_all_datasets
from ..events import EventStore
from ..identity_graph import IdentityGraph
from ..metadata import StoreMetadata, load_store_metadata
from ..stores import StoreRecord, StoreRegistry, default_registry

logger = logging.getLogger(__name__)


@dataclass
class StoreAnalytics:
    """The full analytics surface for a single store."""

    store_id: str
    store_name: str
    cameras: int
    zones: int
    layout: str
    # From the event store + identity graph
    events_total: int = 0
    visitors: int = 0
    non_staff_visitors: int = 0
    staff: int = 0
    conversion_rate: float = 0.0
    revenue: float = 0.0
    revenue_per_visitor: float = 0.0
    revenue_by_zone: Dict[str, float] = field(default_factory=dict)
    # Datasets
    datasets: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MultiStoreAnalytics:
    """Runs the analytics surface across every registered store.

    Construction is cheap; queries are lazy and cached per-store for
    the lifetime of the orchestrator.  This makes it safe to use as a
    long-lived service in the API.
    """

    def __init__(
        self,
        data_root: Path | str = "data",
        events_root: Path | str = "datasets/events",
        datasets_root: Path | str = "datasets",
    ) -> None:
        self.registry = StoreRegistry(data_root)
        self.events_root = Path(events_root)
        self.datasets_root = Path(datasets_root)
        self._cache: Dict[str, StoreAnalytics] = {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def list_stores(self) -> List[StoreRecord]:
        return self.registry.list_records()

    def store_ids(self) -> List[str]:
        return self.registry.list_store_ids()

    # ------------------------------------------------------------------
    # Single-store analytics
    # ------------------------------------------------------------------

    def get_metadata(self, store_id: str) -> StoreMetadata:
        return self.registry.get(store_id)

    def analytics_for(self, store_id: str, *, refresh: bool = False) -> StoreAnalytics:
        if not refresh and store_id in self._cache:
            return self._cache[store_id]
        sm = self.registry.get(store_id)
        rec = next((r for r in self.registry if r.store_id == store_id), None)
        analytics = StoreAnalytics(
            store_id=store_id,
            store_name=sm.store_name,
            cameras=len(sm.cameras),
            zones=len(sm.zones),
            layout=f"{int(sm.layout.width)}x{int(sm.layout.height)}",
        )
        # Populate from identity graph if any events exist
        event_store = EventStore(root=self.events_root)
        if event_store.count(store_id) > 0:
            graph = IdentityGraph.from_event_store(store_id, event_store)
            analytics.events_total = event_store.count(store_id)
            analytics.visitors = graph.total_visitors()
            analytics.non_staff_visitors = graph.non_staff_visitors()
            analytics.staff = graph.total_staff()
            analytics.conversion_rate = round(graph.conversion_rate(), 4)
            analytics.revenue = round(graph.total_revenue(), 2)
            analytics.revenue_per_visitor = round(graph.revenue_per_visitor(), 2)
            analytics.revenue_by_zone = {k: round(v, 2) for k, v in graph.revenue_per_zone().items()}
        self._cache[store_id] = analytics
        return analytics

    # ------------------------------------------------------------------
    # Cross-store summary
    # ------------------------------------------------------------------

    def cross_store_summary(self) -> Dict[str, Any]:
        out: List[Dict[str, Any]] = []
        for sid in self.store_ids():
            a = self.analytics_for(sid)
            out.append({
                "store_id": sid,
                "store_name": a.store_name,
                "cameras": a.cameras,
                "zones": a.zones,
                "events_total": a.events_total,
                "visitors": a.visitors,
                "non_staff_visitors": a.non_staff_visitors,
                "conversion_rate": a.conversion_rate,
                "revenue": a.revenue,
            })
        total_revenue = sum(item["revenue"] for item in out)
        total_visitors = sum(item["non_staff_visitors"] for item in out)
        avg_conversion = (
            sum(item["conversion_rate"] for item in out) / len(out) if out else 0.0
        )
        return {
            "store_count": len(out),
            "total_revenue": round(total_revenue, 2),
            "total_visitors": total_visitors,
            "avg_conversion_rate": round(avg_conversion, 4),
            "stores": out,
        }

    # ------------------------------------------------------------------
    # Dataset generation
    # ------------------------------------------------------------------

    def generate_datasets(self, store_id: str) -> Dict[str, Any]:
        event_store = EventStore(root=self.events_root)
        return build_all_datasets(
            store_id,
            event_store=event_store,
            out_root=self.datasets_root,
        )

    def generate_datasets_for_all(self) -> Dict[str, Dict[str, Any]]:
        return {sid: self.generate_datasets(sid) for sid in self.store_ids()}


def default_analytics() -> MultiStoreAnalytics:
    return MultiStoreAnalytics()


__all__ = [
    "MultiStoreAnalytics",
    "StoreAnalytics",
    "default_analytics",
]
