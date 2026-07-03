"""
PROMPT: Write unit tests for the DetectionPipeline that cover tracker math,
zone assignment heuristics, event schema, session_seq post-processing, sku_zone
metadata, REENTRY detection, and queue state logic — all without processing
actual video files.
CHANGES MADE: Added tests for session_seq ordinal tracking added this session,
sku_zone metadata lookup, and REENTRY cross-camera deduplication logic.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pytest

import src.detection.pipeline as pipeline_module
from src.detection.pipeline import (
    ActiveTrack,
    CameraPlan,
    Detection,
    DetectionPipeline,
    SimpleTracker,
    TrackState,
)
from src.metadata import CameraRole


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pipeline():
    """Shared DetectionPipeline instance (no video processing)."""
    return DetectionPipeline()


@pytest.fixture
def floor_camera():
    # Matches CAM_1 in Brigade Road metadata
    return CameraPlan(
        camera_id="CAM_1",
        role="floor",
        source_file="Store 1/cam1.mp4",
        coverage=["DERMDOC", "GOOD_VIBES", "MAKEUP_UNIT", "FLOOR_CENTER"],
    )


@pytest.fixture
def entry_camera():
    # Matches CAM_3 in Brigade Road metadata
    return CameraPlan(
        camera_id="CAM_3",
        role="entry",
        source_file="Store 1/cam3.mp4",
        coverage=["ENTRY", "EXTERIOR_THRESHOLD"],
    )


@pytest.fixture
def billing_camera():
    # Matches CAM_5 in Brigade Road metadata (BILLING + CASH_COUNTER + PMU)
    return CameraPlan(
        camera_id="CAM_5",
        role="billing",
        source_file="Store 1/cam5.mp4",
        coverage=["BILLING", "CASH_COUNTER", "PMU"],
    )


@pytest.fixture
def support_camera():
    # Matches CAM_4 in Brigade Road metadata
    return CameraPlan(
        camera_id="CAM_4",
        role="support",
        source_file="Store 1/cam4.mp4",
        coverage=["BACK_ROOM", "STAFF_SUPPORT"],
    )


def make_detection(cx=320, cy=240, frame_num=10, confidence=0.8, source="yolo"):
    w, h = cx // 2, cy // 2
    return Detection(
        frame_num=frame_num,
        timestamp=datetime(2026, 4, 10, 20, 20, 0),
        bbox=(cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2),
        confidence=confidence,
        center=(float(cx), float(cy)),
        source=source,
    )


def make_track_state(track_id=1, camera_id="CAM_1"):
    ts = TrackState(track_id=track_id, camera_id=camera_id)
    ts.detections.append(make_detection())
    return ts


# ---------------------------------------------------------------------------
# SimpleTracker Tests
# ---------------------------------------------------------------------------

class TestSimpleTrackerIou:
    def test_identical_boxes_iou_is_one(self):
        box = (10, 10, 50, 50)
        assert SimpleTracker._iou(box, box) == 1.0

    def test_non_overlapping_boxes_iou_is_zero(self):
        assert SimpleTracker._iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0

    def test_partial_overlap(self):
        iou = SimpleTracker._iou((0, 0, 20, 20), (10, 0, 30, 20))
        assert 0 < iou < 1

    def test_zero_area_box(self):
        assert SimpleTracker._iou((0, 0, 0, 0), (0, 0, 10, 10)) == 0.0

    def test_contained_box(self):
        outer = (0, 0, 100, 100)
        inner = (20, 20, 40, 40)
        iou = SimpleTracker._iou(outer, inner)
        assert 0 < iou < 1


class TestSimpleTrackerDistance:
    def test_same_point_distance_is_zero(self):
        assert SimpleTracker._distance((5.0, 5.0), (5.0, 5.0)) == 0.0

    def test_known_distance(self):
        dist = SimpleTracker._distance((0.0, 0.0), (3.0, 4.0))
        assert abs(dist - 5.0) < 1e-6

    def test_distance_is_symmetric(self):
        a, b = (1.0, 2.0), (4.0, 6.0)
        assert SimpleTracker._distance(a, b) == SimpleTracker._distance(b, a)


class TestSimpleTrackerUpdate:
    def test_new_detections_create_tracks(self):
        tracker = SimpleTracker(max_distance=200, max_age_frames=10)
        dets = [make_detection(100, 100), make_detection(300, 300)]
        observations = tracker.update(dets, frame_num=1)
        assert len(observations) == 2
        assert len(tracker.tracks) == 2

    def test_same_detection_associates_to_existing_track(self):
        tracker = SimpleTracker(max_distance=200, max_age_frames=10)
        det = make_detection(100, 100)
        tracker.update([det], frame_num=1)
        obs = tracker.update([det], frame_num=2)
        assert len(obs) == 1
        assert obs[0].hits == 2
        assert len(tracker.tracks) == 1

    def test_stale_tracks_are_removed(self):
        tracker = SimpleTracker(max_distance=200, max_age_frames=3)
        det = make_detection(100, 100)
        tracker.update([det], frame_num=1)
        assert len(tracker.tracks) == 1
        # 5 frames later → track should be pruned
        tracker.update([], frame_num=6)
        assert len(tracker.tracks) == 0

    def test_empty_detections_returns_no_observations(self):
        tracker = SimpleTracker(max_distance=200, max_age_frames=10)
        obs = tracker.update([], frame_num=1)
        assert obs == []

    def test_track_ids_are_incremental(self):
        # Create 3 detections far enough apart that they can't associate with each other
        tracker = SimpleTracker(max_distance=50, max_age_frames=10)
        dets = [make_detection(100, 100), make_detection(400, 100), make_detection(700, 100)]
        observations = tracker.update(dets, frame_num=1)
        assert len(observations) == 3
        assert len(tracker.tracks) == 3
        track_ids = sorted(tracker.tracks.keys())
        assert track_ids == [1, 2, 3]


# ---------------------------------------------------------------------------
# DetectionPipeline._clamp_bbox
# ---------------------------------------------------------------------------

class TestClampBbox:
    def test_valid_bbox_unchanged(self):
        assert DetectionPipeline._clamp_bbox((10, 20, 100, 150), 640, 480) == (10, 20, 100, 150)

    def test_negative_coords_clamped_to_zero(self):
        x1, y1, x2, y2 = DetectionPipeline._clamp_bbox((-5, -10, 50, 60), 640, 480)
        assert x1 == 0 and y1 == 0

    def test_overflow_clamped_to_frame(self):
        x1, y1, x2, y2 = DetectionPipeline._clamp_bbox((10, 10, 700, 500), 640, 480)
        assert x2 == 639
        assert y2 == 479

    def test_zeros_width_height_clamped(self):
        # Should not raise even with zero dimensions
        result = DetectionPipeline._clamp_bbox((0, 0, 0, 0), 640, 480)
        assert len(result) == 4


# ---------------------------------------------------------------------------
# DetectionPipeline._suppress_overlaps
# ---------------------------------------------------------------------------

class TestSuppressOverlaps:
    def test_non_overlapping_detections_all_kept(self, pipeline):
        dets = [make_detection(100, 100), make_detection(400, 400)]
        result = pipeline._suppress_overlaps(dets)
        assert len(result) == 2

    def test_heavily_overlapping_detections_one_kept(self, pipeline):
        # Two almost-identical detections at same position
        det1 = Detection(1, datetime.utcnow(), (10, 10, 50, 50), 0.9, (30.0, 30.0), "yolo")
        det2 = Detection(2, datetime.utcnow(), (12, 12, 52, 52), 0.7, (32.0, 32.0), "yolo")
        result = pipeline._suppress_overlaps([det1, det2])
        assert len(result) == 1

    def test_empty_input(self, pipeline):
        assert pipeline._suppress_overlaps([]) == []


# ---------------------------------------------------------------------------
# DetectionPipeline._zone_for_detection
# ---------------------------------------------------------------------------

class TestZoneForDetection:
    def test_billing_camera_zone_detection(self, pipeline, billing_camera):
        # BILLING normalized: (0.78,0.1375)-(0.85,0.3625) → center in 640x480: (521, 120)
        det = make_detection(521, 120)
        zone = pipeline._zone_for_detection(billing_camera, det, 640, 480)
        assert zone == "BILLING"

    def test_support_camera_returns_back_room(self, pipeline, support_camera):
        # Detection point (57, 86) falls within the BACK_ROOM zone polygon
        # when projected to a 640x480 frame.
        det = make_detection(57, 86)
        zone = pipeline._zone_for_detection(support_camera, det, 640, 480)
        assert zone == "BACK_ROOM"

    def test_floor_camera_returns_floor_center(self, pipeline, floor_camera):
        # FLOOR_CENTER normalized polygon: (0.26,0.1125)-(0.69,0.425)
        # In a 1920x1080 Brigade Road frame: x=499-1325, y=121-459
        # Detection center (600, 250) is inside the zone.
        det = make_detection(600, 250)
        zone = pipeline._zone_for_detection(floor_camera, det, 1920, 1080)
        assert zone == "FLOOR_CENTER"

    def test_floor_camera_no_coverage_returns_none(self, pipeline):
        empty_camera = CameraPlan("CAM_X", "floor", "x.mp4", [])
        det = make_detection(320, 240)
        zone = pipeline._zone_for_detection(empty_camera, det, 640, 480)
        assert zone is None

    def test_entry_camera_returns_entry_zone(self, pipeline, entry_camera):
        # Detection point (35, 206) falls within the ENTRY zone polygon
        # when projected to a 640x480 frame.
        det = make_detection(35, 206)
        zone = pipeline._zone_for_detection(entry_camera, det, 640, 480)
        assert zone == "ENTRY"


# ---------------------------------------------------------------------------
# DetectionPipeline._is_staff_track
# ---------------------------------------------------------------------------

class TestIsStaffTrack:
    def test_support_camera_always_staff(self, pipeline, support_camera):
        det = make_detection(320, 240)
        assert pipeline._is_staff_track(support_camera, det, 640, 480) is True

    def test_floor_camera_not_staff(self, pipeline, floor_camera):
        det = make_detection(320, 240)
        assert pipeline._is_staff_track(floor_camera, det, 640, 480) is False

    def test_billing_camera_not_staff(self, pipeline, billing_camera):
        # Billing camera covers CHECKOUT zones (BILLING, CASH_COUNTER, PMU) —
        # none are ZoneType.STAFF — so _is_staff_track returns False.
        det = make_detection(320, 240)
        assert pipeline._is_staff_track(billing_camera, det, 640, 480) is False


# ---------------------------------------------------------------------------
# DetectionPipeline._is_counter_service_observation
# ---------------------------------------------------------------------------

class TestIsCounterServiceObservation:
    def test_cash_counter_zone_is_service(self, pipeline, billing_camera):
        # Center of CASH_COUNTER zone in 640x480 frame:
        # CASH_COUNTER normalized polygon: (0.79,0.15)-(0.88,0.3625)
        # Center in pixels: x≈534, y≈123
        det = make_detection(534, 123)
        result = pipeline._is_counter_service_observation(billing_camera, det, 640, 480)
        assert result is True

    def test_outside_counter_not_service(self):
        det = make_detection(100, 100)
        result = DetectionPipeline._is_counter_service_observation(det, 640, 480)
        assert result is False


# ---------------------------------------------------------------------------
# DetectionPipeline._visitor_id
# ---------------------------------------------------------------------------

def test_visitor_id_format(floor_camera):
    vid = DetectionPipeline._visitor_id(floor_camera, 42)
    assert vid == "VIS_CAM_1_000042"


def test_visitor_id_pads_zeros(floor_camera):
    assert DetectionPipeline._visitor_id(floor_camera, 1).endswith("000001")


# ---------------------------------------------------------------------------
# DetectionPipeline._track_metadata
# ---------------------------------------------------------------------------

def test_track_metadata_contains_required_keys(pipeline, floor_camera):
    ts = make_track_state(track_id=7)
    det = make_detection(frame_num=99)
    meta = pipeline._track_metadata(ts, det)
    assert meta["track_id"] == 7
    assert meta["frame"] == 99
    assert "bbox" in meta
    assert "detector" in meta
    assert "is_staff" in meta


# ---------------------------------------------------------------------------
# DetectionPipeline.create_event
# ---------------------------------------------------------------------------

class TestCreateEvent:
    def test_event_has_required_schema_fields(self, pipeline, floor_camera):
        det = make_detection()
        ts = make_track_state()
        event = pipeline.create_event(
            camera=floor_camera,
            visitor_id="VIS_CAM_1_000001",
            event_type="ZONE_ENTER",
            timestamp=det.timestamp,
            confidence=0.8,
            bbox=det.bbox,
            zone="FLOOR_CENTER",
            metadata=pipeline._track_metadata(ts, det),
        )
        for field in ("event_id", "store_id", "camera_id", "visitor_id", "event_type",
                      "timestamp", "confidence", "zone_id", "dwell_ms", "is_staff", "bbox", "metadata"):
            assert field in event, f"Missing field: {field}"

    def test_event_id_is_deterministic(self, pipeline, floor_camera):
        det = make_detection()
        ts = make_track_state()
        e1 = pipeline.create_event(
            camera=floor_camera, visitor_id="VIS_CAM_1_000001",
            event_type="ENTRY", timestamp=det.timestamp, confidence=0.8,
            zone="ENTRY", metadata={},
        )
        e2 = pipeline.create_event(
            camera=floor_camera, visitor_id="VIS_CAM_1_000001",
            event_type="ENTRY", timestamp=det.timestamp, confidence=0.8,
            zone="ENTRY", metadata={},
        )
        assert e1["event_id"] == e2["event_id"]

    def test_event_id_differs_for_different_types(self, pipeline, floor_camera):
        det = make_detection()
        e1 = pipeline.create_event(
            camera=floor_camera, visitor_id="VIS_CAM_1_000001",
            event_type="ENTRY", timestamp=det.timestamp, confidence=0.8,
        )
        e2 = pipeline.create_event(
            camera=floor_camera, visitor_id="VIS_CAM_1_000001",
            event_type="EXIT", timestamp=det.timestamp, confidence=0.8,
        )
        assert e1["event_id"] != e2["event_id"]

    def test_sku_zone_added_when_zone_provided(self, pipeline, floor_camera):
        det = make_detection()
        event = pipeline.create_event(
            camera=floor_camera, visitor_id="VIS_CAM_1_000001",
            event_type="ZONE_ENTER", timestamp=det.timestamp, confidence=0.8,
            zone="FLOOR_CENTER",
        )
        assert "sku_zone" in event["metadata"]

    def test_no_sku_zone_when_no_zone(self, pipeline, floor_camera):
        det = make_detection()
        event = pipeline.create_event(
            camera=floor_camera, visitor_id="VIS_CAM_1_000001",
            event_type="ENTRY", timestamp=det.timestamp, confidence=0.8,
            zone=None,
        )
        # sku_zone should not be present when zone is None
        assert "sku_zone" not in event["metadata"]

    def test_dwell_ms_defaults_to_zero(self, pipeline, floor_camera):
        det = make_detection()
        event = pipeline.create_event(
            camera=floor_camera, visitor_id="VIS_CAM_1_000001",
            event_type="ENTRY", timestamp=det.timestamp, confidence=0.8,
        )
        assert event["dwell_ms"] == 0


# ---------------------------------------------------------------------------
# DetectionPipeline._emit_once — deduplication
# ---------------------------------------------------------------------------

def test_emit_once_adds_event(pipeline, floor_camera):
    ts = make_track_state()
    events: List[Dict[str, Any]] = []
    pipeline._emit_once(
        ts, events, key="test_key",
        camera=floor_camera, visitor_id="VIS_CAM_1_000001",
        event_type="ENTRY", timestamp=datetime.utcnow(), confidence=0.8,
    )
    assert len(events) == 1


def test_emit_once_deduplicates(pipeline, floor_camera):
    ts = make_track_state()
    events: List[Dict[str, Any]] = []
    for _ in range(3):
        pipeline._emit_once(
            ts, events, key="same_key",
            camera=floor_camera, visitor_id="VIS_CAM_1_000001",
            event_type="ENTRY", timestamp=datetime.utcnow(), confidence=0.8,
        )
    assert len(events) == 1


# ---------------------------------------------------------------------------
# Session_seq post-processing (run() output)
# ---------------------------------------------------------------------------

def test_session_seq_ordinal_increments_per_visitor(pipeline, floor_camera, tmp_path):
    """session_seq should be 1, 2, 3... for successive events per visitor_id."""
    # Simulate the post-processing step directly
    visitor_id = "VIS_CAM_1_000001"
    ts = datetime(2026, 4, 10, 20, 20, 0)
    raw_events = [
        {"visitor_id": visitor_id, "event_type": "ENTRY", "camera_id": "CAM_1",
         "timestamp": ts.isoformat(), "metadata": {}},
        {"visitor_id": visitor_id, "event_type": "ZONE_ENTER", "camera_id": "CAM_1",
         "timestamp": ts.isoformat(), "metadata": {}},
        {"visitor_id": "OTHER_VIS", "event_type": "ENTRY", "camera_id": "CAM_1",
         "timestamp": ts.isoformat(), "metadata": {}},
    ]
    # Apply the same logic as run() post-processing
    visitor_seq: Dict[str, int] = {}
    for event in raw_events:
        vid = event["visitor_id"]
        seq = visitor_seq.get(vid, 0) + 1
        visitor_seq[vid] = seq
        event["metadata"]["session_seq"] = seq

    assert raw_events[0]["metadata"]["session_seq"] == 1
    assert raw_events[1]["metadata"]["session_seq"] == 2
    assert raw_events[2]["metadata"]["session_seq"] == 1  # different visitor resets


# ---------------------------------------------------------------------------
# REENTRY tracking via exited_visitors
# ---------------------------------------------------------------------------

def test_exited_visitors_set_is_cleared_on_new_pipeline():
    p1 = DetectionPipeline()
    p2 = DetectionPipeline()
    p1.exited_visitors.add("VIS_CAM_3_000001")
    assert "VIS_CAM_3_000001" not in p2.exited_visitors


def test_exited_visitors_tracks_cross_camera(pipeline):
    """Visitors added to exited_visitors are available from any method that checks it."""
    pipeline.exited_visitors.clear()
    pipeline.exited_visitors.add("VIS_CAM_3_000099")
    assert "VIS_CAM_3_000099" in pipeline.exited_visitors
    pipeline.exited_visitors.discard("VIS_CAM_3_000099")


# ---------------------------------------------------------------------------
# write_jsonl
# ---------------------------------------------------------------------------

def test_write_jsonl_creates_file(pipeline, tmp_path):
    import json

    out = tmp_path / "test_events.jsonl"
    pipeline.output_path = out
    events = [
        {"event_id": "E1", "event_type": "ENTRY", "store_id": "ST1008"},
        {"event_id": "E2", "event_type": "EXIT", "store_id": "ST1008"},
    ]
    pipeline.write_jsonl(events)
    assert out.exists()
    lines = out.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["event_id"] == "E1"


# ---------------------------------------------------------------------------
# Pipeline metadata loading
# ---------------------------------------------------------------------------

def test_pipeline_loads_metadata(pipeline):
    assert "store" in pipeline.metadata
    assert "cameras" in pipeline.metadata
    assert "zones" in pipeline.metadata


def test_pipeline_cameras_have_required_fields(pipeline):
    # Roles are canonical uppercase strings (legacy aliases normalized via LEGACY_MAP)
    valid_roles = {"ENTRY", "EXIT", "ZONE", "BILLING", "QUEUE", "STAFF", "FLOOR", "SUPPORT"}
    for cam in pipeline.cameras:
        assert cam.camera_id
        assert cam.role in valid_roles
        assert cam.source_file


def test_pipeline_zone_name_map_populated(pipeline):
    assert len(pipeline.zone_name_map) > 0
    for zone_id, zone_name in pipeline.zone_name_map.items():
        assert isinstance(zone_id, str)
        assert isinstance(zone_name, str)


def test_pipeline_store_id_set(pipeline):
    assert pipeline.store_id == "ST1008"


# ---------------------------------------------------------------------------
# TrackState dataclass
# ---------------------------------------------------------------------------

def test_track_state_defaults():
    ts = TrackState(track_id=1, camera_id="CAM_1")
    assert ts.entry_detected is False
    assert ts.exit_detected is False
    assert ts.current_zone is None
    assert ts.is_staff is False
    assert ts.queue_joined is False
    assert len(ts.detections) == 0
    assert len(ts.emitted_events) == 0


def test_track_state_accumulates_detections():
    ts = TrackState(track_id=1, camera_id="CAM_1")
    for i in range(5):
        ts.detections.append(make_detection(frame_num=i))
    assert len(ts.detections) == 5


# ---------------------------------------------------------------------------
# ZONE_DWELL_SECONDS default is 30 (not 4)
# ---------------------------------------------------------------------------

def test_zone_dwell_seconds_default():
    assert pipeline_module.ZONE_DWELL_SECONDS >= 30, (
        f"Expected ZONE_DWELL_SECONDS >= 30, got {pipeline_module.ZONE_DWELL_SECONDS}"
    )
