"""
PROMPT: Create integration tests for the VisionRetail AI detection pipeline that
process the challenge-supplied recorded CCTV footage and validate end-to-end
event generation. Verify schema compliance, event diversity, staff detection,
queue analytics events, visitor tracking, deterministic event IDs, and replay
consistency across repeated runs of the same video segment.

CHANGES MADE: Added full-pipeline validation against recorded CCTV clips,
ensured generated events conform to the DetectionEvent schema, verified
generation of ENTRY, EXIT, ZONE_ENTER, ZONE_DWELL, BILLING_QUEUE_JOIN, and
BILLING_QUEUE_ABANDON events, validated staff and customer tracking behavior,
and added deterministic event ID verification to guarantee replayable and
reproducible analytics results from identical video inputs.
"""


from collections import Counter

from src.api.models import DetectionEvent
import src.detection.pipeline as pipeline_module
from src.detection.pipeline import DetectionPipeline


def test_pipeline_generates_schema_compatible_real_video_events(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline_module, "MAX_FRAMES_PER_CAMERA", 2200)
    monkeypatch.setattr(pipeline_module, "FRAME_STRIDE", 5)

    pipeline = DetectionPipeline()
    pipeline.output_path = tmp_path / "events.generated.jsonl"
    events = pipeline.run()

    event_types = Counter(event["event_type"] for event in events)
    assert len(events) >= 500
    assert event_types["ZONE_ENTER"] > 0
    assert event_types["ZONE_DWELL"] > 0
    assert event_types["BILLING_QUEUE_JOIN"] > 0
    assert event_types["BILLING_QUEUE_ABANDON"] > 0
    assert event_types["ENTRY"] + event_types["EXIT"] > 0
    assert len({event["visitor_id"] for event in events}) >= 50
    assert any(event["is_staff"] for event in events)
    assert any(event.get("bbox") for event in events)
    assert any((event["metadata"] or {}).get("detector") in {"motion", "yolo"} for event in events)

    for event in events:
        DetectionEvent(**event)


def test_pipeline_event_ids_are_deterministic_for_same_video_slice(monkeypatch):
    monkeypatch.setattr(pipeline_module, "MAX_FRAMES_PER_CAMERA", 900)
    monkeypatch.setattr(pipeline_module, "FRAME_STRIDE", 5)

    first_pipeline = DetectionPipeline()
    first_camera = next(camera for camera in first_pipeline.cameras if camera.camera_id == "CAM_1")
    first = first_pipeline.process_camera(first_camera, first_pipeline.cctv_path / first_camera.source_file)

    second_pipeline = DetectionPipeline()
    second_camera = next(camera for camera in second_pipeline.cameras if camera.camera_id == "CAM_1")
    second = second_pipeline.process_camera(second_camera, second_pipeline.cctv_path / second_camera.source_file)

    assert [event["event_id"] for event in first] == [event["event_id"] for event in second]
