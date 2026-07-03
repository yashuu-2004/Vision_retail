"""
PROMPT: Write tests for the CrossCameraReIdentifier module covering
timeline construction, temporal visitor matching, confidence assignment,
global visitor mapping, and execution flow without requiring a real database.

CHANGES MADE: Added synthetic ENTRY/EXIT sequences across multiple cameras,
validated high- and medium-confidence matches, and exercised the run()
pipeline using mocked database query chains.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from src.analytics.cross_camera_reid import CrossCameraReIdentifier


class FakeEvent:
    def __init__(
        self,
        camera_code,
        visitor_id,
        event_type,
        timestamp,
        zone_id=None,
        event_id="evt",
    ):
        self.camera_code = camera_code
        self.visitor_id = visitor_id
        self.event_type = event_type
        self.event_timestamp = timestamp
        self.zone_id = zone_id
        self.event_id = event_id


def test_build_timelines_groups_events_by_camera_and_visitor():
    db = MagicMock()
    store = MagicMock()

    engine = CrossCameraReIdentifier(db, store)

    now = datetime.utcnow()

    events = [
        FakeEvent("CAM_1", "VIS_1", "ENTRY", now),
        FakeEvent("CAM_1", "VIS_1", "EXIT", now + timedelta(seconds=5)),
        FakeEvent("CAM_2", "VIS_2", "ENTRY", now + timedelta(seconds=10)),
    ]

    timelines = engine._build_timelines(events)

    assert "CAM_1" in timelines
    assert "VIS_1" in timelines["CAM_1"]
    assert len(timelines["CAM_1"]["VIS_1"]) == 2


def test_match_visitors_across_cameras_high_confidence():
    db = MagicMock()
    store = MagicMock()

    engine = CrossCameraReIdentifier(db, store)

    now = datetime.utcnow()

    timelines = {
        "CAM_1": {
            "VIS_A": [
                {"event_type": "EXIT", "timestamp": now}
            ]
        },
        "CAM_2": {
            "VIS_B": [
                {"event_type": "ENTRY", "timestamp": now + timedelta(seconds=5)}
            ]
        },
    }

    matches = engine._match_visitors_across_cameras(timelines, [])

    assert len(matches) == 1
    assert matches[0]["confidence"] == "high"
    assert matches[0]["time_diff"] == 5


def test_match_visitors_across_cameras_medium_confidence():
    db = MagicMock()
    store = MagicMock()

    engine = CrossCameraReIdentifier(db, store)

    now = datetime.utcnow()

    timelines = {
        "CAM_1": {
            "VIS_A": [
                {"event_type": "EXIT", "timestamp": now}
            ]
        },
        "CAM_2": {
            "VIS_B": [
                {"event_type": "ENTRY", "timestamp": now + timedelta(seconds=20)}
            ]
        },
    }

    matches = engine._match_visitors_across_cameras(timelines, [])

    assert len(matches) == 1
    assert matches[0]["confidence"] == "medium"


def test_match_visitors_outside_window_not_linked():
    db = MagicMock()
    store = MagicMock()

    engine = CrossCameraReIdentifier(db, store)

    now = datetime.utcnow()

    timelines = {
        "CAM_1": {
            "VIS_A": [
                {"event_type": "EXIT", "timestamp": now}
            ]
        },
        "CAM_2": {
            "VIS_B": [
                {"event_type": "ENTRY", "timestamp": now + timedelta(seconds=60)}
            ]
        },
    }

    matches = engine._match_visitors_across_cameras(timelines, [])

    assert matches == []


def test_run_creates_global_ids():
    now = datetime.utcnow()

    events = [
        FakeEvent("CAM_1", "VIS_1", "ENTRY", now),
        FakeEvent("CAM_1", "VIS_1", "EXIT", now + timedelta(seconds=5)),
        FakeEvent("CAM_2", "VIS_2", "ENTRY", now + timedelta(seconds=10)),
    ]

    query = MagicMock()
    query.filter.return_value.order_by.return_value.all.return_value = events

    db = MagicMock()
    db.query.return_value = query

    store = MagicMock()
    store.id = 1

    engine = CrossCameraReIdentifier(db, store)

    result = engine.run()

    assert isinstance(result, dict)
    assert len(result) >= 2
    assert any(v.startswith("GLOBAL_") or v.startswith("MATCHED_") for v in result.values())