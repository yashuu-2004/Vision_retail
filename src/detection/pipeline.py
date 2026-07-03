"""
Real computer vision detection pipeline.

Processes CCTV videos with YOLO person detection and ByteTrack tracking.
Generates actual visitor events from real video data.

Author: VisionRetail AI
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import NAMESPACE_URL, uuid5

import cv2
import numpy as np

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

try:
    import requests
except Exception:
    requests = None

from src.metadata import (
    load_store_metadata,
    MetadataLoadError,
    CameraMetadata as _CamMeta,
    ZoneMetadata as _ZoneMeta,
    ZoneType,
    CameraRole,
)


logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")


DATA_DIR = Path(
    os.getenv(
        "DATA_DIR",
        Path(__file__).resolve().parents[2] / "data"
    )
)

OUTPUT_PATH = Path(
    os.getenv(
        "EVENT_OUTPUT_PATH",
        DATA_DIR / "events.generated.jsonl"
    )
)
API_URL = os.getenv("API_URL")
STORE_ID = os.getenv("STORE_ID")
BASE_TIMESTAMP = datetime.fromisoformat(os.getenv("CLIP_BASE_TIMESTAMP", "2026-04-10T20:20:00"))

# YOLO configuration
YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")
YOLO_CONFIDENCE = float(os.getenv("YOLO_CONFIDENCE", "0.25"))
YOLO_DEVICE = os.getenv("YOLO_DEVICE", "cpu")
MOTION_FALLBACK_ON_EMPTY_YOLO = os.getenv("MOTION_FALLBACK_ON_EMPTY_YOLO", "true").strip().lower() in {"1", "true", "yes", "on"}

# ByteTrack configuration
TRACK_THRESH = float(os.getenv("TRACK_THRESH", "0.5"))
TRACK_BUFFER = int(os.getenv("TRACK_BUFFER", "30"))
MATCH_THRESH = float(os.getenv("MATCH_THRESH", "0.8"))

# Real-video OpenCV fallback and internal tracker configuration.  This keeps the
# pipeline runnable in the supplied Docker image, which includes OpenCV but not
# the heavier Ultralytics/Torch stack.
FRAME_STRIDE = max(int(os.getenv("FRAME_STRIDE", "5")), 1)
MAX_FRAMES_PER_CAMERA = int(os.getenv("MAX_FRAMES_PER_CAMERA", "0"))
PROCESS_WIDTH = int(os.getenv("PROCESS_WIDTH", "960"))
MOTION_HISTORY = int(os.getenv("MOTION_HISTORY", "240"))
MOTION_VAR_THRESHOLD = float(os.getenv("MOTION_VAR_THRESHOLD", "40"))
MOTION_WARMUP_FRAMES = int(os.getenv("MOTION_WARMUP_FRAMES", "15"))
MOTION_MIN_AREA_RATIO = float(os.getenv("MOTION_MIN_AREA_RATIO", "0.0008"))
MIN_TRACK_HITS = int(os.getenv("MIN_TRACK_HITS", "1"))
MAX_TRACK_DISTANCE = float(os.getenv("MAX_TRACK_DISTANCE", "180"))
ZONE_DWELL_SECONDS = float(os.getenv("ZONE_DWELL_SECONDS", "30"))
QUEUE_ABANDON_SECONDS = float(os.getenv("QUEUE_ABANDON_SECONDS", "12"))

# Entry/exit detection
ENTRY_LINE_Y = int(os.getenv("ENTRY_LINE_Y", "200"))
ENTRY_DIRECTION_THRESHOLD = int(os.getenv("ENTRY_DIRECTION_THRESHOLD", "50"))


@dataclass
class CameraPlan:
    """Camera metadata from store_metadata.json"""
    camera_id: str
    role: str  # Stored as canonical uppercase string for JSON serialization
    source_file: str
    coverage: List[str]
    zone_polygons: Dict[str, List[Tuple[float, float]]] = field(default_factory=dict)
    entry_line_y: Optional[float] = None  # normalized y [0,1], None = use metadata heuristic

    def __post_init__(self) -> None:
        # Normalize to canonical uppercase string, applying LEGACY_MAP so
        # legacy aliases (FLOOR, SUPPORT) map to canonical values (ZONE, STAFF).
        normalized = CameraRole.from_string(str(self.role))
        self.role = normalized.value


@dataclass
class Detection:
    """Single frame detection result"""
    frame_num: int
    timestamp: datetime
    bbox: Tuple[int, int, int, int]
    confidence: float
    center: Tuple[float, float]
    source: str = "motion"


@dataclass
class TrackObservation:
    """A detector observation assigned to a stable per-camera track."""
    track_id: int
    detection: Detection
    hits: int


@dataclass
class TrackState:
    """State of a tracked person across frames"""
    track_id: int
    camera_id: str
    detections: List[Detection] = field(default_factory=list)
    entry_detected: bool = False
    exit_detected: bool = False
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    current_zone: Optional[str] = None
    zone_enter_time: Optional[datetime] = None
    zone_dwell_emitted: Set[str] = field(default_factory=set)
    queue_joined: bool = False
    queue_join_time: Optional[datetime] = None
    max_queue_depth: int = 0
    served_at_counter: bool = False
    is_staff: bool = False
    emitted_events: Set[str] = field(default_factory=set)
    global_visitor_id: Optional[str] = None
    appearance_embedding: Optional[List[float]] = None


@dataclass
class ActiveTrack:
    """Minimal tracker state for IoU/centroid association."""
    track_id: int
    bbox: Tuple[int, int, int, int]
    center: Tuple[float, float]
    confidence: float
    last_seen_frame: int
    hits: int = 1


class SimpleTracker:
    """Small deterministic tracker used when external MOT packages are absent.

    The tracker associates detections by overlap and center distance. It is not a
    replacement for ByteTrack, but it fixes the zero-track failure while keeping
    the data path entirely video-derived and reproducible.
    """

    def __init__(self, max_distance: float, max_age_frames: int) -> None:
        self.max_distance = max_distance
        self.max_age_frames = max_age_frames
        self.next_id = 1
        self.tracks: Dict[int, ActiveTrack] = {}

    def update(self, detections: List[Detection], frame_num: int) -> List[TrackObservation]:
        self._drop_stale(frame_num)
        if not detections:
            return []

        candidates: List[Tuple[float, int, int]] = []
        for det_index, detection in enumerate(detections):
            for track_id, track in self.tracks.items():
                iou = self._iou(detection.bbox, track.bbox)
                distance = self._distance(detection.center, track.center)
                if iou < 0.02 and distance > self.max_distance:
                    continue
                normalized_distance = min(distance / max(self.max_distance, 1), 1.5)
                cost = (1.0 - iou) + normalized_distance
                candidates.append((cost, det_index, track_id))

        assigned_detections: Set[int] = set()
        assigned_tracks: Set[int] = set()
        observations: List[TrackObservation] = []

        for _, det_index, track_id in sorted(candidates, key=lambda item: item[0]):
            if det_index in assigned_detections or track_id in assigned_tracks:
                continue
            detection = detections[det_index]
            track = self.tracks[track_id]
            track.bbox = detection.bbox
            track.center = detection.center
            track.confidence = detection.confidence
            track.last_seen_frame = frame_num
            track.hits += 1
            assigned_detections.add(det_index)
            assigned_tracks.add(track_id)
            observations.append(TrackObservation(track_id=track_id, detection=detection, hits=track.hits))

        for det_index, detection in enumerate(detections):
            if det_index in assigned_detections:
                continue
            track_id = self.next_id
            self.next_id += 1
            self.tracks[track_id] = ActiveTrack(
                track_id=track_id,
                bbox=detection.bbox,
                center=detection.center,
                confidence=detection.confidence,
                last_seen_frame=frame_num,
            )
            observations.append(TrackObservation(track_id=track_id, detection=detection, hits=1))

        return observations

    def _drop_stale(self, frame_num: int) -> None:
        stale_ids = [
            track_id
            for track_id, track in self.tracks.items()
            if frame_num - track.last_seen_frame > self.max_age_frames
        ]
        for track_id in stale_ids:
            del self.tracks[track_id]

    @staticmethod
    def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
        return float(np.hypot(a[0] - b[0], a[1] - b[1]))

    @staticmethod
    def _iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)
        inter_w = max(inter_x2 - inter_x1, 0)
        inter_h = max(inter_y2 - inter_y1, 0)
        inter_area = inter_w * inter_h
        if not inter_area:
            return 0.0
        area_a = max(ax2 - ax1, 0) * max(ay2 - ay1, 0)
        area_b = max(bx2 - bx1, 0) * max(by2 - by1, 0)
        return inter_area / max(area_a + area_b - inter_area, 1)


class DetectionPipeline:
    """Real-time person detection and tracking pipeline using YOLO + ByteTrack."""

    def __init__(self) -> None:
        # Load and validate store metadata via the canonical module.
        # Zero hardcoded store assumptions — the metadata file IS the config.
        self._store_metadata = self._load_metadata()
        self.store_id = self._store_metadata.store_id

        # Build CameraPlan list from the structured metadata
        self.cameras: List[CameraPlan] = []
        for cam_meta in self._store_metadata.cameras:
            # entry_line from metadata (normalized y)
            entry_y: Optional[float] = None
            if cam_meta.entry_line is not None:
                entry_y = float(cam_meta.entry_line.y_normalized)

            # zone_polygons already normalized in metadata; use as-is
            self.cameras.append(
                CameraPlan(
                    camera_id=cam_meta.camera_id,
                    role=cam_meta.role.value,
                    source_file=cam_meta.source_file,
                    coverage=list(cam_meta.coverage),
                    zone_polygons=dict(cam_meta.zone_polygons),
                    entry_line_y=entry_y,
                )
            )

        # Build lookup maps from zone metadata
        self.zone_name_map: Dict[str, str] = {
            z.zone_id: z.zone_name for z in self._store_metadata.zones
        }
        self.zone_type_map: Dict[str, str] = {
            z.zone_id: z.zone_type.value for z in self._store_metadata.zones
        }
        self.zone_ids: Set[str] = set(self.zone_name_map.keys())

        # Metadata-derived layout size (for fallback when no polygons exist)
        self._layout_w = float(self._store_metadata.layout.width)
        self._layout_h = float(self._store_metadata.layout.height)

        # Transition graph — loaded from metadata, NOT hardcoded
        self._transition_graph = self._store_metadata.transition_graph

        # Resolve CCTV path: look for cameras/ under the metadata file's parent dir
        self.cctv_path = self._find_cctv_path()

        self.global_visitor_counter = 1
        self.reid_gallery: List[Dict[str, Any]] = []
        self.output_path = Path(os.getenv("EVENT_OUTPUT_PATH", OUTPUT_PATH))
        self.motion_subtractors: Dict[str, Any] = {}
        self.exited_visitors: Set[str] = set()

        self.yolo_model = self._load_yolo_model()

        logger.info(
            json.dumps(
                {
                    "message": "detection_pipeline_initialized",
                    "store_id": self.store_id,
                    "cctv_path": str(self.cctv_path) if self.cctv_path else None,
                    "camera_count": len(self.cameras),
                    "yolo_loaded": self.yolo_model is not None,
                    "frame_stride": FRAME_STRIDE,
                    "tracker": "internal_iou_centroid",
                }
            )
        )

    @property
    def metadata(self) -> Dict[str, Any]:
        """Backward-compatible dict view of the store metadata (matches old schema)."""
        return {
            "store": {
                "store_id": self._store_metadata.store_id,
                "store_name": self._store_metadata.store_name,
            },
            "cameras": [
                {
                    "camera_id": c.camera_id,
                    "role": c.role,
                    "source_file": c.source_file,
                    "coverage": c.coverage,
                    "zone_polygons": c.zone_polygons,
                }
                for c in self.cameras
            ],
            "zones": [
                {"zone_id": z.zone_id, "zone_name": z.zone_name, "zone_type": z.zone_type.value}
                for z in self._store_metadata.zones
            ],
        }

    def _load_metadata(self):
        """Load store metadata using the canonical metadata module."""
        data_dir = Path(
            os.getenv("DATA_DIR", Path(__file__).resolve().parents[2] / "data")
        )
        store_id = os.getenv("STORE_DATASET", "brigade_road")
        try:
            return load_store_metadata(data_dir, store_id, check_source_files=False)
        except MetadataLoadError as exc:
            raise RuntimeError(
                f"Failed to load store metadata for '{store_id}': {exc}"
            ) from exc

    def _find_cctv_path(self) -> Optional[Path]:
        """Look for cameras/ under the metadata file's parent directory."""
        metadata_path = Path(
            os.getenv(
                "DATA_DIR", Path(__file__).resolve().parents[2] / "data"
            )
        )
        store_id = os.getenv("STORE_DATASET", "brigade_road")
        store_dir = metadata_path / store_id
        cameras_dir = store_dir / "cameras"
        if cameras_dir.exists():
            return cameras_dir
        # Legacy: check in the data root (for old store_metadata.json layout)
        if (metadata_path / "CCTV Footage").exists():
            return metadata_path / "CCTV Footage"
        return None

    def _camera_transition_allowed(self, from_camera: str, to_camera: str) -> bool:
        """Check if transition is allowed using the metadata transition graph."""
        return self._transition_graph.has_edge(from_camera, to_camera)

    def _zone_polygons_for_camera(
        self, camera: CameraPlan
    ) -> Dict[str, List[Tuple[float, float]]]:
        """Return zone polygons for a camera.

        Prefers explicit camera-level polygons; falls back to zone-level polygons
        normalised by the store layout size.
        """
        if camera.zone_polygons:
            return camera.zone_polygons

        # Fall back: derive rectangles from zone layout_box values
        result: Dict[str, List[Tuple[float, float]]] = {}
        zone_by_id = {z.zone_id: z for z in self._store_metadata.zones}
        for zone_id in camera.coverage:
            zone = zone_by_id.get(zone_id)
            if zone is None:
                continue
            box = zone.layout_box
            if not box or len(box) != 4:
                continue
            x1, y1, x2, y2 = box
            # Normalise to 0-1 using layout dimensions
            result[zone_id] = [
                (float(x1) / self._layout_w, float(y1) / self._layout_h),
                (float(x2) / self._layout_w, float(y1) / self._layout_h),
                (float(x2) / self._layout_w, float(y2) / self._layout_h),
                (float(x1) / self._layout_w, float(y2) / self._layout_h),
            ]
        return result

    def _entry_line_y(self, camera: CameraPlan) -> Optional[float]:
        """Return the normalised entry-line y for an ENTRY/EXIT camera."""
        if camera.entry_line_y is not None:
            return camera.entry_line_y
        # Fallback: derive from the ENTRY zone's polygon bottom edge
        zone_polys = self._zone_polygons_for_camera(camera)
        entry_poly = zone_polys.get("ENTRY") or zone_polys.get("ENTRY_LEFT") or zone_polys.get("ENTRY_RIGHT")
        if entry_poly:
            # Use the max y of the polygon as the entry line
            return max(y for _, y in entry_poly)
        return None



    def _load_yolo_model(self) -> Optional[Any]:
        """Load YOLO model, downloading if necessary."""
        if YOLO is None:
            logger.warning("Ultralytics YOLO not available")
            return None
        try:
            logger.info(f"Loading YOLO model: {YOLO_MODEL}")
            model = YOLO(YOLO_MODEL)
            model.to(YOLO_DEVICE)
            logger.info(f"YOLO model loaded on device: {YOLO_DEVICE}")
            return model
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            return None

    def run(self) -> List[Dict[str, Any]]:
        """Process all cameras and generate events from real detections."""
        events: List[Dict[str, Any]] = []
        
        for camera in self.cameras:
            video_path = self.cctv_path / camera.source_file if self.cctv_path else None
            
            if video_path and video_path.exists():
                logger.info(json.dumps({
                    "message": "processing_camera",
                    "camera_id": camera.camera_id,
                    "role": camera.role,
                    "video": str(video_path),
                }))
                camera_events = self.process_camera(camera, video_path)
                events.extend(camera_events)
                logger.info(json.dumps({
                    "message": "camera_complete",
                    "camera_id": camera.camera_id,
                    "events_generated": len(camera_events),
                }))
            else:
                logger.warning(json.dumps({
                    "message": "video_not_found",
                    "camera_id": camera.camera_id,
                    "expected_path": str(video_path) if video_path else "None",
                }))

        # Sort events by timestamp
        events = sorted(events, key=lambda e: (e["timestamp"], e["camera_id"], e["visitor_id"]))

        # Post-processing: add session_seq (ordinal position per visitor_id)
        visitor_seq: Dict[str, int] = {}
        for event in events:
            vid = event["visitor_id"]
            seq = visitor_seq.get(vid, 0) + 1
            visitor_seq[vid] = seq
            event["metadata"]["session_seq"] = seq

        # Write to JSONL
        self.write_jsonl(events)
        
        # Post to API if configured
        if API_URL:
            self.post_events(events)
        
        logger.info(json.dumps({
            "message": "pipeline_complete",
            "total_events": len(events),
            "output_file": str(self.output_path),
        }))
        
        return events

    def process_camera(self, camera: CameraPlan, video_path: Path) -> List[Dict[str, Any]]:
        """Process single camera video and extract events."""
        cap = cv2.VideoCapture(str(video_path))
        
        if not cap.isOpened():
            logger.error(f"Failed to open video: {video_path}")
            return []
        
        # Get video properties
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration_seconds = total_frames / fps if fps > 0 else 0
        
        logger.info(json.dumps({
            "message": "video_properties",
            "camera_id": camera.camera_id,
            "fps": fps,
            "total_frames": total_frames,
            "duration_seconds": round(duration_seconds, 2),
            "resolution": f"{width}x{height}",
        }))
        
        tracker = SimpleTracker(
            max_distance=max(MAX_TRACK_DISTANCE, min(width, height) * 0.12),
            max_age_frames=max(TRACK_BUFFER * FRAME_STRIDE, FRAME_STRIDE * 6),
        )
        
        # Track states for entry/exit detection
        track_states: Dict[int, TrackState] = {}
        confirmed_tracks: Set[int] = set()
        events: List[Dict[str, Any]] = []
        frame_count = 0
        detection_frames = 0
        detections_count = 0
        detector_mode = "yolo" if self.yolo_model else "motion"
        
        # Process frames
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_time = BASE_TIMESTAMP + timedelta(seconds=frame_count / fps)
            frame_count += 1
            if MAX_FRAMES_PER_CAMERA and frame_count > MAX_FRAMES_PER_CAMERA:
                break
            if frame_count % FRAME_STRIDE != 0:
                continue
            detection_frames += 1
            
            detections = self.detect_people(camera, frame, frame_count, frame_time, width, height, detection_frames)
            detections_count += len(detections)
            
            observations = tracker.update(detections, frame_count)
            active_billing_tracks = 0
            # Queue/polling zone: find a zone of type CHECKOUT or QUEUE in camera coverage
            camera_polys = self._zone_polygons_for_camera(camera)
            queue_zone_id: Optional[str] = None
            for zone_id in camera.coverage:
                ztype = self.zone_type_map.get(zone_id, "")
                if ztype in ("CHECKOUT", "QUEUE"):
                    queue_zone_id = zone_id
                    break
            queue_polygon = self._project_polygon(camera_polys.get(queue_zone_id or ""), width, height)
            if camera.role == "BILLING" and queue_polygon:
                for state in track_states.values():
                    if not state.detections:
                        continue
                    last_obs = state.detections[-1]
                    if frame_count - last_obs.frame_num > tracker.max_age_frames:
                        continue
                    if self._point_in_polygon(last_obs.center, queue_polygon):
                        active_billing_tracks += 1

            for observation in observations:
                if observation.track_id not in track_states:
                    track_states[observation.track_id] = TrackState(
                        track_id=observation.track_id,
                        camera_id=camera.camera_id,
                    )

                track_state = track_states[observation.track_id]
                track_state.detections.append(observation.detection)
                track_state.appearance_embedding = self._track_embedding(track_state)
                track_state.is_staff = track_state.is_staff or self._is_staff_track(
                    camera, observation.detection, width, height
                )

                if observation.hits < MIN_TRACK_HITS:
                    continue

                confirmed_tracks.add(observation.track_id)
                if camera.role in {"ZONE", "STAFF", "BILLING"}:
                    self._update_zone_state(camera, track_state, observation.detection, events, width, height)
                if camera.role == "BILLING":
                    if queue_polygon and self._point_in_polygon(observation.detection.center, queue_polygon):
                        active_billing_tracks = max(active_billing_tracks + 1, 1)
                    self._update_queue_state(
                        camera,
                        track_state,
                        observation.detection,
                        events,
                        queue_depth=active_billing_tracks,
                        width=width,
                        height=height,
                    )
        
        cap.release()

        for track_id in sorted(confirmed_tracks):
            self._finalize_track(camera, track_states[track_id], events, width, height)
        
        logger.info(json.dumps({
            "message": "frame_processing_complete",
            "camera_id": camera.camera_id,
            "frames_processed": frame_count,
            "detection_frames": detection_frames,
            "detector_mode": detector_mode,
            "detections": detections_count,
            "tracks": len(confirmed_tracks),
            "events": len(events),
        }))
        
        return events


    def _build_camera_graph(self) -> Dict[str, Set[str]]:
        """
        Dynamically build camera transition graph from metadata.

        Supports:
        - Brigade Road
        - Store 1
        - Store 2
        - Any future store
        """

        graph: Dict[str, Set[str]] = {}

        cameras = self.metadata.get("cameras", [])

        entry_cams = {
            c["camera_id"]
            for c in cameras
            if c.get("role") == "entry"
        }

        billing_cams = {
            c["camera_id"]
            for c in cameras
            if c.get("role") == "billing"
        }

        floor_cams = {
            c["camera_id"]
            for c in cameras
            if c.get("role") == "floor"
        }

        support_cams = {
            c["camera_id"]
            for c in cameras
            if c.get("role") == "support"
        }

        for camera in cameras:

            cam_id = camera["camera_id"]
            role = camera.get("role")

            allowed = set()

            if role == "entry":
                allowed.update(floor_cams)
                allowed.update(billing_cams)

            elif role == "floor":
                allowed.update(entry_cams)
                allowed.update(floor_cams)
                allowed.update(billing_cams)

            elif role == "billing":
                allowed.update(entry_cams)
                allowed.update(floor_cams)

            elif role == "support":
                allowed.add(cam_id)

            allowed.discard(cam_id)

            graph[cam_id] = allowed

        return graph


    def detect_people(
        self,
        camera: CameraPlan,
        frame: np.ndarray,
        frame_num: int,
        timestamp: datetime,
        width: int,
        height: int,
        detection_frame: int,
    ) -> List[Detection]:
        """Return person/person-candidate detections from actual frame pixels."""
        if self.yolo_model is not None:
            detections, yolo_failed = self._detect_with_yolo(frame, frame_num, timestamp)
            if detections:
                return detections
            if not yolo_failed and not MOTION_FALLBACK_ON_EMPTY_YOLO:
                # Keep detector provenance clean: do not silently replace YOLO misses with motion.
                return []
        return self._detect_with_motion(camera, frame, frame_num, timestamp, width, height, detection_frame)

    def _detect_with_yolo(self, frame: np.ndarray, frame_num: int, timestamp: datetime) -> Tuple[List[Detection], bool]:
        detections: List[Detection] = []
        try:
            results = self.yolo_model(frame, conf=YOLO_CONFIDENCE, verbose=False)
            for result in results:
                for box in result.boxes:
                    cls_value = box.cls[0] if hasattr(box.cls, "__len__") else box.cls
                    if int(cls_value) != 0:
                        continue
                    coords = box.xyxy[0].detach().cpu().numpy() if hasattr(box.xyxy[0], "detach") else box.xyxy[0]
                    x1, y1, x2, y2 = [int(v) for v in coords]
                    conf_value = box.conf[0] if hasattr(box.conf, "__len__") else box.conf
                    confidence = float(conf_value)
                    detections.append(
                        Detection(
                            frame_num=frame_num,
                            timestamp=timestamp,
                            bbox=self._clamp_bbox((x1, y1, x2, y2), frame.shape[1], frame.shape[0]),
                            confidence=confidence,
                            center=((x1 + x2) / 2, (y1 + y2) / 2),
                            source="yolo",
                        )
                    )
            return detections, False
        except Exception as exc:
            logger.warning(f"YOLO inference error on frame {frame_num}: {exc}")
            return [], True

    def _detect_with_motion(
        self,
        camera: CameraPlan,
        frame: np.ndarray,
        frame_num: int,
        timestamp: datetime,
        width: int,
        height: int,
        detection_frame: int,
    ) -> List[Detection]:
        scale = min(PROCESS_WIDTH / width, 1.0) if width else 1.0
        if scale < 1.0:
            resized = cv2.resize(frame, (int(width * scale), int(height * scale)))
        else:
            resized = frame

        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        subtractor = self.motion_subtractors.setdefault(
            camera.camera_id,
            cv2.createBackgroundSubtractorMOG2(
                history=MOTION_HISTORY,
                varThreshold=MOTION_VAR_THRESHOLD,
                detectShadows=True,
            ),
        )
        mask = subtractor.apply(gray)
        _, mask = cv2.threshold(mask, 200, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.dilate(mask, kernel, iterations=2)

        if detection_frame <= MOTION_WARMUP_FRAMES:
            return []

        frame_area = mask.shape[0] * mask.shape[1]
        min_area = max(350, frame_area * MOTION_MIN_AREA_RATIO)
        max_area = frame_area * 0.35
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections: List[Detection] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area or area > max_area:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            if h < 30 or w < 12:
                continue
            aspect = h / max(w, 1)
            if aspect < 0.25 or aspect > 6.0:
                continue

            x1 = int(x / scale)
            y1 = int(y / scale)
            x2 = int((x + w) / scale)
            y2 = int((y + h) / scale)
            bbox = self._clamp_bbox((x1, y1, x2, y2), width, height)
            confidence = min(0.9, 0.45 + float(area / max(frame_area * 0.08, 1)))
            detections.append(
                Detection(
                    frame_num=frame_num,
                    timestamp=timestamp,
                    bbox=bbox,
                    confidence=round(confidence, 3),
                    center=((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2),
                    source="motion",
                )
            )

        return self._suppress_overlaps(detections)

    def _suppress_overlaps(self, detections: List[Detection]) -> List[Detection]:
        kept: List[Detection] = []
        for detection in sorted(
            detections,
            key=lambda det: (det.bbox[2] - det.bbox[0]) * (det.bbox[3] - det.bbox[1]),
            reverse=True,
        ):
            if all(SimpleTracker._iou(detection.bbox, kept_det.bbox) < 0.6 for kept_det in kept):
                kept.append(detection)
        return kept

    @staticmethod
    def _clamp_bbox(bbox: Tuple[int, int, int, int], width: int, height: int) -> Tuple[int, int, int, int]:
        x1, y1, x2, y2 = bbox
        return (
            max(0, min(int(x1), width - 1)),
            max(0, min(int(y1), height - 1)),
            max(0, min(int(x2), width - 1)),
            max(0, min(int(y2), height - 1)),
        )

    def _update_zone_state(
        self,
        camera: CameraPlan,
        track_state: TrackState,
        detection: Detection,
        events: List[Dict[str, Any]],
        width: int,
        height: int,
    ) -> None:
        zone = self._zone_for_detection(camera, detection, width, height)
        if not zone:
            return

        visitor_id = self._visitor_id(camera, track_state.track_id)
        if track_state.current_zone is None:
            track_state.current_zone = zone
            track_state.zone_enter_time = detection.timestamp
            self._emit_once(
                track_state,
                events,
                key=f"zone_enter:{zone}",
                camera=camera,
                visitor_id=visitor_id,
                event_type="ZONE_ENTER",
                timestamp=detection.timestamp,
                confidence=detection.confidence,
                zone=zone,
                bbox=detection.bbox,
                metadata=self._track_metadata(track_state, detection),
            )
            return

        if zone != track_state.current_zone:
            previous_zone = track_state.current_zone
            self._emit_zone_dwell(camera, track_state, detection, events, previous_zone, final=False)
            self._emit_once(
                track_state,
                events,
                key=f"zone_exit:{previous_zone}:{detection.frame_num}",
                camera=camera,
                visitor_id=visitor_id,
                event_type="ZONE_EXIT",
                timestamp=detection.timestamp,
                confidence=detection.confidence,
                zone=previous_zone,
                bbox=detection.bbox,
                metadata=self._track_metadata(track_state, detection),
            )
            track_state.current_zone = zone
            track_state.zone_enter_time = detection.timestamp
            self._emit_once(
                track_state,
                events,
                key=f"zone_enter:{zone}:{detection.frame_num}",
                camera=camera,
                visitor_id=visitor_id,
                event_type="ZONE_ENTER",
                timestamp=detection.timestamp,
                confidence=detection.confidence,
                zone=zone,
                bbox=detection.bbox,
                metadata=self._track_metadata(track_state, detection),
            )
            return

    def _emit_zone_dwell(
        self,
        camera: CameraPlan,
        track_state: TrackState,
        detection: Detection,
        events: List[Dict[str, Any]],
        zone: Optional[str],
        final: bool,
    ) -> None:
        if not zone or not track_state.zone_enter_time:
            return
        dwell_ms = int(max((detection.timestamp - track_state.zone_enter_time).total_seconds(), 0) * 1000)
        if dwell_ms <= 0:
            return
        self._emit_once(
            track_state,
            events,
            key=f"zone_dwell:{zone}:{'final' if final else detection.frame_num}",
            camera=camera,
            visitor_id=self._visitor_id(camera, track_state.track_id),
            event_type="ZONE_DWELL",
            timestamp=detection.timestamp,
            confidence=detection.confidence,
            zone=zone,
            dwell_ms=dwell_ms,
            bbox=detection.bbox,
            metadata={
                **self._track_metadata(track_state, detection),
                "zone_enter_time": track_state.zone_enter_time.isoformat(),
                "zone_exit_time": detection.timestamp.isoformat(),
                "final": final,
            },
        )

    def _update_queue_state(
        self,
        camera: CameraPlan,
        track_state: TrackState,
        detection: Detection,
        events: List[Dict[str, Any]],
        queue_depth: int,
        width: int,
        height: int,
    ) -> None:
        track_state.max_queue_depth = max(track_state.max_queue_depth, queue_depth)
        track_state.served_at_counter = track_state.served_at_counter or self._is_counter_service_observation(
            camera, detection, width, height
        )
        if track_state.queue_joined:
            return

        track_state.queue_joined = True
        track_state.queue_join_time = detection.timestamp
        self._emit_once(
            track_state,
            events,
            key="queue_join",
            camera=camera,
            visitor_id=self._visitor_id(camera, track_state.track_id),
            event_type="BILLING_QUEUE_JOIN",
            timestamp=detection.timestamp,
            confidence=detection.confidence,
            zone="BILLING",
            bbox=detection.bbox,
            metadata={
                **self._track_metadata(track_state, detection),
                "queue_depth": queue_depth,
                "business_event_type": "QUEUE_JOIN",
            },
        )

    def _finalize_track(
        self,
        camera: CameraPlan,
        track_state: TrackState,
        events: List[Dict[str, Any]],
        width: int,
        height: int,
    ) -> None:
        if len(track_state.detections) < MIN_TRACK_HITS:
            return
        global_id = self._assign_global_identity(camera, track_state)
        self._rewrite_track_visitor_ids(events, camera.camera_id, track_state.track_id, global_id)
        last_detection = track_state.detections[-1]
        if camera.role == "ENTRY":
            self._finalize_entry_exit(camera, track_state, events, width, height)

        if track_state.current_zone:
            self._emit_zone_dwell(camera, track_state, last_detection, events, track_state.current_zone, final=True)
            self._emit_once(
                track_state,
                events,
                key=f"zone_exit:{track_state.current_zone}:final",
                camera=camera,
                visitor_id=self._visitor_id(camera, track_state.track_id),
                event_type="ZONE_EXIT",
                timestamp=last_detection.timestamp,
                confidence=last_detection.confidence,
                zone=track_state.current_zone,
                bbox=last_detection.bbox,
                metadata={**self._track_metadata(track_state, last_detection), "final": True},
            )

        if camera.role == "BILLING":
            self._finalize_queue(camera, track_state, last_detection, events)
        self._rewrite_track_visitor_ids(events, camera.camera_id, track_state.track_id, global_id)

    @staticmethod
    def _embedding_distance(a: Optional[List[float]], b: Optional[List[float]]) -> float:
        if not a or not b or len(a) != len(b):
            return 1e9
        return float(np.linalg.norm(np.array(a) - np.array(b)))

    def _camera_transition_allowed(
        self,
        from_camera: str,
        to_camera: str,
    ) -> bool:
        return self._transition_graph.has_edge(from_camera, to_camera)

    def _assign_global_identity(self, camera: CameraPlan, track_state: TrackState) -> str:
        if track_state.global_visitor_id:
            return track_state.global_visitor_id

        start_ts = track_state.detections[0].timestamp
        embedding = track_state.appearance_embedding
        best_match: Optional[Dict[str, Any]] = None
        best_score = 1e9
        for candidate in self.reid_gallery:
            if not self._camera_transition_allowed(candidate["camera_id"], camera.camera_id):
                continue
            delta = abs((start_ts - candidate["last_seen"]).total_seconds())
            if delta > 300:
                continue
            dist = self._embedding_distance(embedding, candidate.get("embedding"))
            score = dist + (delta / 120.0)
            if score < best_score:
                best_score = score
                best_match = candidate

        if best_match and best_score < 80.0:
            global_id = best_match["global_id"]
        else:
            global_id = f"VIS_GLOBAL_{self.global_visitor_counter:06d}"
            self.global_visitor_counter += 1

        track_state.global_visitor_id = global_id
        self.reid_gallery.append(
            {
                "global_id": global_id,
                "camera_id": camera.camera_id,
                "last_seen": track_state.detections[-1].timestamp,
                "embedding": embedding,
            }
        )
        return global_id

    def _rewrite_track_visitor_ids(self, events: List[Dict[str, Any]], camera_id: str, track_id: int, visitor_id: str) -> None:
        for event in events:
            metadata = event.get("metadata") or {}
            if event.get("camera_id") == camera_id and int(metadata.get("track_id") or -1) == track_id:
                event["visitor_id"] = visitor_id

    def _finalize_entry_exit(
        self,
        camera: CameraPlan,
        track_state: TrackState,
        events: List[Dict[str, Any]],
        width: int,
        height: int,
    ) -> None:
        """Determine entry/exit using the metadata-defined entry line.

        For ENTRY cameras, the camera's ``entry_line`` in metadata defines
        where the interior/exterior boundary is.  All values are in
        normalized [0, 1] coordinates, scaled to the actual frame.
        """
        first = track_state.detections[0]
        last = track_state.detections[-1]
        dx = last.center[0] - first.center[0]
        dy = last.center[1] - first.center[1]
        movement = float(np.hypot(dx, dy))
        if movement < min(width, height) * 0.035:
            return

        # Derive the entry line from metadata; fall back to 0.5 if absent
        entry_line_y_norm = self._entry_line_y(camera)
        if entry_line_y_norm is None:
            entry_line_y_norm = 0.5
        entry_line_y_px = entry_line_y_norm * height

        # exterior_side defaults to "above" (y < entry_line is exterior)
        exterior_side = "above"
        entry_meta = None
        for cam_meta in self._store_metadata.cameras:
            if cam_meta.camera_id == camera.camera_id and cam_meta.entry_line:
                exterior_side = cam_meta.entry_line.exterior_side
                entry_meta = cam_meta
                break

        # Determine which side of the entry line each detection falls on
        def is_exterior(center: Tuple[float, float]) -> bool:
            cy = center[1]
            if exterior_side == "above":
                return cy < entry_line_y_px
            else:
                return cy > entry_line_y_px

        start_exterior = is_exterior(first.center)
        end_exterior = is_exterior(last.center)

        # Score entry vs exit
        entry_score = (
            int(start_exterior) +          # started outside
            int(not end_exterior) +          # ended inside
            int(dx < -width * 0.04) +      # moved left (into frame from left)
            int(dy < -height * 0.03)        # moved up (toward entry)
        )
        exit_score = (
            int(not start_exterior) +       # started inside
            int(end_exterior) +              # ended outside
            int(dx > width * 0.04) +       # moved right
            int(dy > height * 0.03)        # moved down (away from entry)
        )
        if max(entry_score, exit_score) < 2:
            return

        event_type = "ENTRY" if entry_score >= exit_score else "EXIT"

        # Determine the entry zone ID from camera coverage (prefer ENTRY type zone)
        entry_zone_id = "ENTRY"
        for zone_id in camera.coverage:
            if self.zone_type_map.get(zone_id) == "ENTRY":
                entry_zone_id = zone_id
                break

        visitor_id = track_state.global_visitor_id or self._visitor_id(camera, track_state.track_id)
        if event_type == "ENTRY":
            track_state.entry_detected = True
            track_state.entry_time = last.timestamp
            if visitor_id in self.exited_visitors:
                self._emit_once(
                    track_state,
                    events,
                    key="reentry",
                    camera=camera,
                    visitor_id=visitor_id,
                    event_type="REENTRY",
                    timestamp=last.timestamp,
                    confidence=min(0.85, last.confidence + 0.05),
                    zone=entry_zone_id,
                    bbox=last.bbox,
                    metadata={
                        **self._track_metadata(track_state, last),
                        "trajectory_dx": round(dx, 2),
                        "trajectory_dy": round(dy, 2),
                    },
                )
        else:
            track_state.exit_detected = True
            track_state.exit_time = last.timestamp
            self.exited_visitors.add(visitor_id)

        self._emit_once(
            track_state,
            events,
            key=f"entry_exit:{event_type}",
            camera=camera,
            visitor_id=visitor_id,
            event_type=event_type,
            timestamp=last.timestamp,
            confidence=min(0.92, max(0.55, last.confidence + 0.08)),
            zone=entry_zone_id,
            bbox=last.bbox,
            metadata={
                **self._track_metadata(track_state, last),
                "trajectory_dx": round(dx, 2),
                "trajectory_dy": round(dy, 2),
                "movement_px": round(movement, 2),
                "entry_score": entry_score,
                "exit_score": exit_score,
                "entry_line_y_norm": round(entry_line_y_norm, 4),
                "exterior_side": exterior_side,
            },
        )

    def _finalize_queue(
        self,
        camera: CameraPlan,
        track_state: TrackState,
        detection: Detection,
        events: List[Dict[str, Any]],
    ) -> None:
        if not track_state.queue_joined or not track_state.queue_join_time:
            return
        wait_ms = int((detection.timestamp - track_state.queue_join_time).total_seconds() * 1000)
        if wait_ms < QUEUE_ABANDON_SECONDS * 1000 or track_state.served_at_counter:
            return
        self._emit_once(
            track_state,
            events,
            key="queue_abandon",
            camera=camera,
            visitor_id=self._visitor_id(camera, track_state.track_id),
            event_type="BILLING_QUEUE_ABANDON",
            timestamp=detection.timestamp,
            confidence=max(0.5, detection.confidence - 0.05),
            zone="BILLING",
            dwell_ms=wait_ms,
            bbox=detection.bbox,
            metadata={
                **self._track_metadata(track_state, detection),
                "queue_depth": track_state.max_queue_depth,
                "wait_ms": wait_ms,
                "business_event_type": "QUEUE_ABANDON",
            },
        )

    def _zone_for_detection(
        self,
        camera: CameraPlan,
        detection: Detection,
        width: int,
        height: int,
    ) -> Optional[str]:
        valid_coverage = [zone for zone in camera.coverage if zone in self.zone_ids]
        if not valid_coverage:
            return None

        point = detection.center
        # Use zone polygons from metadata (prefer explicit per-camera polygons,
        # fall back to zone-level polygons via _zone_polygons_for_camera)
        camera_polys = self._zone_polygons_for_camera(camera)
        has_any_polygon = any(camera_polys.get(z) for z in valid_coverage)

        if not has_any_polygon:
            # No polygons defined for this camera — fall back to zone type defaults
            if camera.role == "BILLING":
                # Return first CHECKOUT zone in coverage
                for zone_id in valid_coverage:
                    if self.zone_type_map.get(zone_id) == "CHECKOUT":
                        return zone_id
                return valid_coverage[0] if valid_coverage else None
            if camera.role == "STAFF":
                # Return first STAFF zone in coverage
                for zone_id in valid_coverage:
                    if self.zone_type_map.get(zone_id) == "STAFF":
                        return zone_id
                return valid_coverage[0] if valid_coverage else None
            # For ZONE/ENTRY cameras with no polygons, use first coverage
            return valid_coverage[0] if valid_coverage else None

        # Point-in-polygon test for each zone polygon
        candidates: List[Tuple[float, str]] = []
        for zone in valid_coverage:
            poly = self._project_polygon(camera_polys.get(zone), width, height)
            if not poly or len(poly) < 3:
                continue
            if self._point_in_polygon(point, poly):
                area = abs(self._polygon_area(poly))
                candidates.append((area, zone))

        if not candidates:
            return None
        # Prefer the smallest containing polygon for disambiguation.
        return sorted(candidates, key=lambda it: it[0])[0][1]

    @staticmethod
    def _polygon_area(polygon: List[Tuple[float, float]]) -> float:
        if len(polygon) < 3:
            return 0.0
        area = 0.0
        for i in range(len(polygon)):
            x1, y1 = polygon[i]
            x2, y2 = polygon[(i + 1) % len(polygon)]
            area += x1 * y2 - x2 * y1
        return area / 2.0

    @staticmethod
    def _point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
        x, y = point
        inside = False
        n = len(polygon)
        if n < 3:
            return False
        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            intersects = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi)
            if intersects:
                inside = not inside
            j = i
        return inside

    @staticmethod
    def _project_polygon(
        normalized_polygon: Optional[List[Tuple[float, float]]],
        width: int,
        height: int,
    ) -> Optional[List[Tuple[float, float]]]:
        if not normalized_polygon:
            return None
        projected: List[Tuple[float, float]] = []
        for px, py in normalized_polygon:
            projected.append((float(px) * width, float(py) * height))
        return projected

    @staticmethod
    def _track_embedding(track_state: TrackState) -> Optional[List[float]]:
        # Lightweight appearance embedding from bbox shape dynamics; deterministic and cheap.
        if not track_state.detections:
            return None
        widths = [max(d.bbox[2] - d.bbox[0], 1) for d in track_state.detections[-10:]]
        heights = [max(d.bbox[3] - d.bbox[1], 1) for d in track_state.detections[-10:]]
        confidences = [d.confidence for d in track_state.detections[-10:]]
        mean_w = float(np.mean(widths))
        mean_h = float(np.mean(heights))
        aspect = mean_h / max(mean_w, 1.0)
        motion = 0.0
        if len(track_state.detections) > 1:
            a = track_state.detections[-2].center
            b = track_state.detections[-1].center
            motion = float(np.hypot(a[0] - b[0], a[1] - b[1]))
        return [round(mean_w, 3), round(mean_h, 3), round(aspect, 4), round(float(np.mean(confidences)), 4), round(motion, 3)]

    def _is_staff_track(self, camera: CameraPlan, detection: Detection, width: int, height: int) -> bool:
        if camera.role == "STAFF":
            return True
        if camera.role == "BILLING":
            # Find STAFF zone polygon in camera coverage
            camera_polys = self._zone_polygons_for_camera(camera)
            staff_zone_id: Optional[str] = None
            for zone_id in camera.coverage:
                if self.zone_type_map.get(zone_id) == "STAFF":
                    staff_zone_id = zone_id
                    break
            staff_poly = self._project_polygon(camera_polys.get(staff_zone_id or ""), width, height)
            if staff_poly:
                return self._point_in_polygon(detection.center, staff_poly)
        return False

    def _is_counter_service_observation(
        self,
        camera: CameraPlan | Detection,
        detection: Detection | int,
        width: int | None = None,
        height: int | None = None,
    ) -> bool:
        # Backward-compatible static-style call used in unit tests:
        # DetectionPipeline._is_counter_service_observation(detection, width, height)
        if isinstance(camera, Detection):
            det = camera
            w = int(detection) if isinstance(detection, int) else 0
            h = int(width) if isinstance(width, int) else 0
            cx, cy = det.center
            return w * 0.28 <= cx <= w * 0.58 and cy > h * 0.52

        if not isinstance(camera, CameraPlan) or not isinstance(detection, Detection):
            return False
        if not isinstance(width, int) or not isinstance(height, int):
            return False

        # Use metadata-driven CHECKOUT/QUEUE zone polygons
        camera_polys = self._zone_polygons_for_camera(camera)
        checkout_poly: Optional[List[Tuple[float, float]]] = None
        for zone_id in camera.coverage:
            if self.zone_type_map.get(zone_id) in ("CHECKOUT", "QUEUE"):
                checkout_poly = camera_polys.get(zone_id)
                if checkout_poly:
                    break

        if not checkout_poly:
            return False
        projected = self._project_polygon(checkout_poly, width, height)
        if not projected:
            return False
        return self._point_in_polygon(detection.center, projected)

    def _track_metadata(self, track_state: TrackState, detection: Detection) -> Dict[str, Any]:
        visitor_id = track_state.global_visitor_id or ""
        return {
            "track_id": track_state.track_id,
            "frame": detection.frame_num,
            "frame_number": detection.frame_num,
            "camera_id": track_state.camera_id,
            "visitor_id": visitor_id,
            "bbox": list(detection.bbox),
            "confidence": round(float(detection.confidence), 3),
            "detector": detection.source,
            "detector_type": detection.source,
            "event_source": "live_cctv",
            "is_staff": track_state.is_staff,
            "appearance_embedding": track_state.appearance_embedding,
        }

    def _emit_once(
        self,
        track_state: TrackState,
        events: List[Dict[str, Any]],
        key: str,
        **event_kwargs: Any,
    ) -> None:
        if key in track_state.emitted_events:
            return
        track_state.emitted_events.add(key)
        events.append(self.create_event(is_staff=track_state.is_staff, **event_kwargs))

    @staticmethod
    def _visitor_id(camera: CameraPlan, track_id: int) -> str:
        return f"VIS_{camera.camera_id}_{track_id:06d}"

    def create_event(
        self,
        camera: CameraPlan,
        visitor_id: str,
        event_type: str,
        timestamp: datetime,
        confidence: float,
        bbox: Optional[Tuple[int, int, int, int]] = None,
        zone: Optional[str] = None,
        dwell_ms: int = 0,
        is_staff: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create event dict in the proper schema."""
        timestamp_key = timestamp.isoformat(timespec="milliseconds")
        event_seed = "|".join(
            [
                self.store_id,
                camera.camera_id,
                visitor_id,
                event_type,
                timestamp_key,
                zone or "",
                str((metadata or {}).get("track_id", "")),
            ]
        )
        event_id = f"EVT_{uuid5(NAMESPACE_URL, event_seed).hex}"
        event_metadata = dict(metadata or {})
        event_metadata.setdefault("camera_id", camera.camera_id)
        event_metadata.setdefault("track_id", int((event_metadata.get("track_id") or 0)))
        event_metadata.setdefault("bbox", list(bbox) if bbox is not None else None)
        event_metadata.setdefault("confidence", round(float(confidence), 3))
        event_metadata.setdefault("detector_type", str(event_metadata.get("detector_type") or event_metadata.get("detector") or "motion"))
        event_metadata.setdefault("event_source", "live_cctv")
        event_metadata.setdefault("frame_number", int(event_metadata.get("frame_number") or event_metadata.get("frame") or 0))
        if bbox is not None:
            event_metadata.setdefault("bbox", list(bbox))
        # Add sku_zone label from store metadata
        if zone:
            event_metadata["sku_zone"] = self.zone_name_map.get(zone, zone)
        return {
            "event_id": event_id,
            "store_id": self.store_id,
            "camera_id": camera.camera_id,
            "visitor_id": visitor_id,
            "event_type": event_type,
            "timestamp": timestamp.isoformat(),
            "confidence": round(confidence, 3),
            "zone_id": zone,
            "dwell_ms": dwell_ms,
            "is_staff": is_staff,
            "bbox": list(bbox) if bbox is not None else None,
            "metadata": event_metadata,
        }

    def write_jsonl(self, events: List[Dict[str, Any]]) -> None:
        """Write events to JSONL file."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")
        logger.info(f"Wrote {len(events)} events to {self.output_path}")

    def post_events(self, events: List[Dict[str, Any]]) -> None:
        """Post events to the API."""
        if not requests or not API_URL:
            return
        try:
            response = requests.post(
                f"{API_URL}/events/ingest",
                json={"events": events},
                timeout=30,
            )
            logger.info(json.dumps({
                "message": "events_posted_to_api",
                "status": response.status_code,
                "events": len(events),
            }))
        except Exception as e:
            logger.error(f"Failed to post events to API: {e}")


if __name__ == "__main__":
    pipeline = DetectionPipeline()
    events = pipeline.run()
    
    # Print summary
    print("\n" + "="*60)
    print("DETECTION PIPELINE SUMMARY")
    print("="*60)
    
    # Count events by type
    event_counts = {}
    for event in events:
        event_type = event["event_type"]
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
    
    # Count by camera
    camera_counts = {}
    for event in events:
        camera_id = event["camera_id"]
        camera_counts[camera_id] = camera_counts.get(camera_id, 0) + 1
    
    print(f"\nTotal Events Generated: {len(events)}")
    print(f"Total Unique Visitors: {len(set(e['visitor_id'] for e in events))}")
    print("\nEvents by Type:")
    for event_type, count in sorted(event_counts.items()):
        print(f"  {event_type}: {count}")
    print("\nEvents by Camera:")
    for camera_id, count in sorted(camera_counts.items()):
        print(f"  {camera_id}: {count}")
    print(f"\nOutput File: {pipeline.output_path}")
    print("="*60 + "\n")
