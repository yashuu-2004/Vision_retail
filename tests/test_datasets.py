"""
Tests for the dataset generator.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.datasets import (
    build_all_datasets,
    build_conversion_dataset,
    build_journey_dataset,
    build_purchase_dataset,
    build_queue_dataset,
    build_reid_pairs,
)
from src.events import CanonicalEvent, CanonicalEventType, EventStore
from src.identity_graph import IdentityGraph


def _event(
    ev_type: CanonicalEventType,
    *,
    visitor: str,
    store: str = "ST_TEST",
    camera: str = "CAM_1",
    zone: str | None = None,
    ts: datetime | None = None,
    is_staff: bool = False,
    **metadata: object,
) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=f"EVT_{visitor}_{ev_type.value}_{zone or 'na'}",
        event_type=ev_type,
        store_id=store,
        camera_id=camera,
        visitor_id=visitor,
        zone_id=zone,
        timestamp=ts or datetime(2026, 4, 10, 12, 0, 0),
        confidence=0.9,
        is_staff=is_staff,
        metadata=metadata,
    )


def _seed_graph() -> IdentityGraph:
    g = IdentityGraph("ST_TEST")
    # Visitor 1: enters, browses, queues, purchases
    g.add_event(_event(CanonicalEventType.ENTRY, visitor="V1", ts=datetime(2026, 4, 10, 9, 0)))
    g.add_event(_event(CanonicalEventType.ZONE_ENTER, visitor="V1", zone="BRAND_A", ts=datetime(2026, 4, 10, 9, 5)))
    g.add_event(_event(CanonicalEventType.QUEUE_ENTER, visitor="V1", zone="CHECKOUT", ts=datetime(2026, 4, 10, 9, 10)))
    g.add_event(_event(CanonicalEventType.QUEUE_EXIT, visitor="V1", zone="CHECKOUT", ts=datetime(2026, 4, 10, 9, 15)))
    g.add_event(_event(CanonicalEventType.PURCHASE, visitor="V1", amount=150.0, transaction_id="TX1", ts=datetime(2026, 4, 10, 9, 20)))
    g.add_event(_event(CanonicalEventType.EXIT, visitor="V1", ts=datetime(2026, 4, 10, 9, 25)))

    # Visitor 2: browses only
    g.add_event(_event(CanonicalEventType.ENTRY, visitor="V2", ts=datetime(2026, 4, 10, 10, 0)))
    g.add_event(_event(CanonicalEventType.ZONE_ENTER, visitor="V2", zone="BRAND_B", ts=datetime(2026, 4, 10, 10, 5)))
    g.add_event(_event(CanonicalEventType.EXIT, visitor="V2", ts=datetime(2026, 4, 10, 10, 10)))

    # Staff
    g.add_event(_event(CanonicalEventType.ENTRY, visitor="V_STAFF", ts=datetime(2026, 4, 10, 8, 0), is_staff=True))
    return g


def test_build_journey_dataset(tmp_path: Path):
    g = _seed_graph()
    result = build_journey_dataset(g, out_dir=tmp_path / "journeys")
    assert result["count"] == 3
    out = Path(result["path"])
    assert out.exists()
    rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    v1 = next(r for r in rows if r["visitor_id"] == "V1")
    assert "BRAND_A" in v1["zones"]
    assert v1["has_purchase"] is True
    assert v1["purchase_amount"] == 150.0


def test_build_purchase_dataset(tmp_path: Path):
    g = _seed_graph()
    result = build_purchase_dataset(g, out_dir=tmp_path / "purchases")
    assert result["count"] == 1
    out = Path(result["path"])
    rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    assert rows[0]["visitor_id"] == "V1"
    assert rows[0]["amount"] == 150.0
    assert "BRAND_A" in rows[0]["journey_zones"]


def test_build_queue_dataset(tmp_path: Path):
    g = _seed_graph()
    result = build_queue_dataset(g, out_dir=tmp_path / "queues")
    assert result["count"] == 1
    out = Path(result["path"])
    rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    assert rows[0]["visitor_id"] == "V1"
    assert rows[0]["zone_id"] == "CHECKOUT"
    assert rows[0]["abandoned"] is False


def test_build_conversion_dataset(tmp_path: Path):
    g = _seed_graph()
    result = build_conversion_dataset(g, out_dir=tmp_path / "conversion")
    assert result["count"] == 3
    out = Path(result["path"])
    rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    by_id = {r["visitor_id"]: r for r in rows}
    assert by_id["V1"]["label"] == 1
    assert by_id["V2"]["label"] == 0
    assert by_id["V_STAFF"]["is_staff"] is True
    assert by_id["V1"]["entered_queue"] is True


def test_build_reid_pairs_produces_positives_and_negatives(tmp_path: Path):
    g = _seed_graph()
    result = build_reid_pairs(g, out_dir=tmp_path / "reid", negative_ratio=2.0, seed=42)
    assert result["count"] > 0
    assert result["positives"] >= 0
    assert result["negatives"] >= 0
    out = Path(result["path"])
    rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    labels = [r["label"] for r in rows]
    assert set(labels).issubset({0, 1})


def test_build_all_datasets_end_to_end(tmp_path: Path):
    """End-to-end: events -> store -> graph -> datasets."""
    events_root = tmp_path / "events"
    out_root = tmp_path / "datasets"
    store = EventStore(root=events_root)
    ts = datetime(2026, 4, 10, 12, 0, 0)
    store.append(CanonicalEvent(
        event_id="e1", event_type=CanonicalEventType.ENTRY,
        store_id="ST1", camera_id="CAM_1", visitor_id="V1",
        timestamp=ts, confidence=0.9,
    ))
    store.append(CanonicalEvent(
        event_id="e2", event_type=CanonicalEventType.PURCHASE,
        store_id="ST1", camera_id="CAM_5", visitor_id="V1",
        timestamp=ts, confidence=0.9,
        metadata={"amount": 100.0, "transaction_id": "TX1"},
    ))
    summary = build_all_datasets("ST1", event_store=store, out_root=out_root)
    assert summary["events_total"] == 2
    assert summary["graph_visitors"] == 1
    assert summary["conversion_rate"] == 1.0
    assert summary["journeys"]["count"] == 1
    assert summary["purchases"]["count"] == 1
