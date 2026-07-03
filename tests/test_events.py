"""
Tests for the canonical event schema and event store.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from src.events import CanonicalEvent, CanonicalEventType, EventStore


def test_canonical_event_type_values_complete():
    expected = {
        "ENTRY", "EXIT", "REENTRY",
        "ZONE_ENTER", "ZONE_EXIT", "ZONE_DWELL",
        "QUEUE_ENTER", "QUEUE_EXIT", "QUEUE_ABANDON", "CHECKOUT_SERVICE",
        "PURCHASE", "REVENUE_ATTRIBUTED",
        "STAFF_INTERACTION", "STAFF_TRACK",
        "CROSS_CAMERA_MATCH", "CROSS_CAMERA_REJECT",
    }
    assert set(CanonicalEventType.values()) == expected


def test_canonical_event_round_trip():
    ts = datetime(2026, 4, 10, 12, 30, 0)
    ev = CanonicalEvent(
        event_id="EVT_test_1",
        event_type=CanonicalEventType.ENTRY,
        store_id="ST_TEST",
        camera_id="CAM_1",
        visitor_id="V1",
        zone_id="ENTRY",
        timestamp=ts,
        confidence=0.95,
        bbox=[100, 200, 300, 400],
        track_id=42,
        frame_number=1234,
        metadata={"detector_type": "yolov8", "queue_depth": 2},
    )
    dumped = ev.to_dict()
    assert dumped["event_type"] == "ENTRY"
    assert dumped["store_id"] == "ST_TEST"
    assert dumped["metadata"]["queue_depth"] == 2
    # Round-trip
    again = CanonicalEvent.model_validate_json(json.dumps(dumped))
    assert again.event_id == ev.event_id
    assert again.event_type == CanonicalEventType.ENTRY


def test_event_store_append_and_iter(tmp_path: Path):
    store = EventStore(root=tmp_path / "events")
    ts = datetime(2026, 4, 10, 12, 0, 0)
    ev1 = CanonicalEvent(
        event_id="e1", event_type=CanonicalEventType.ENTRY,
        store_id="S1", camera_id="CAM_1", visitor_id="V1",
        timestamp=ts, confidence=0.9,
    )
    ev2 = CanonicalEvent(
        event_id="e2", event_type=CanonicalEventType.ZONE_ENTER,
        store_id="S1", camera_id="CAM_1", visitor_id="V1",
        zone_id="FLOOR_CENTER", timestamp=ts, confidence=0.9,
    )
    store.append(ev1)
    store.append(ev2)
    assert store.count("S1") == 2
    events = list(store.iter_events("S1"))
    assert [e.event_id for e in events] == ["e1", "e2"]


def test_event_store_handles_missing_camera(tmp_path: Path):
    """POS-attributed events without a camera_id go to a shared file."""
    store = EventStore(root=tmp_path / "events")
    ts = datetime(2026, 4, 10, 12, 0, 0)
    ev = CanonicalEvent(
        event_id="p1", event_type=CanonicalEventType.PURCHASE,
        store_id="S1", camera_id=None, visitor_id="V1",
        timestamp=ts, confidence=1.0,
        metadata={"amount": 250.0, "transaction_id": "TXN_001"},
    )
    store.append(ev)
    assert store.count("S1") == 1
    assert (store.root / "S1" / "2026-04-10" / "_system.jsonl").exists()


def test_event_store_filters_by_date(tmp_path: Path):
    store = EventStore(root=tmp_path / "events")
    for i, day in enumerate([1, 2, 3]):
        ts = datetime(2026, 4, day, 12, 0, 0)
        ev = CanonicalEvent(
            event_id=f"e{i}", event_type=CanonicalEventType.ENTRY,
            store_id="S1", camera_id="CAM_1", visitor_id=f"V{i}",
            timestamp=ts, confidence=0.9,
        )
        store.append(ev)
    # Filter by date
    only_day2 = list(store.iter_events("S1", date="2026-04-02"))
    assert len(only_day2) == 1
    assert only_day2[0].event_id == "e1"


def test_event_store_list_dates(tmp_path: Path):
    store = EventStore(root=tmp_path / "events")
    for day in [1, 5, 3]:
        ts = datetime(2026, 4, day, 12, 0, 0)
        ev = CanonicalEvent(
            event_id=f"e{day}", event_type=CanonicalEventType.ENTRY,
            store_id="S1", camera_id="CAM_1", visitor_id="V1",
            timestamp=ts, confidence=0.9,
        )
        store.append(ev)
    dates = store.list_dates("S1")
    assert dates == ["2026-04-01", "2026-04-03", "2026-04-05"]
