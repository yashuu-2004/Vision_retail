# Score Maximization and Production Credibility Report

Date: 2026-06-03
Scope: truth-first scoring improvements without adding new API surface

## Executive Outcome

Highest-ROI items were executed in this order:

1. Remove seed dependency and rebuild from live CCTV
2. Enforce explicit provenance for event source and detector
3. Complete explicit polygon coverage for every camera
4. Backfill attribution explainability to full purchased-session coverage

Result: the working dataset is now fully live-CCTV and fully YOLO-attributed.

## Before vs After (Measured)

Baseline (pre-change telemetry):
- Seeded share: 0.917
- Detector mix: motion 1303, yolo 694, unknown 180
- Polygon metadata: explicit 0, derived 4, missing 1 camera
- Attribution explainability: 0/1 purchased sessions

Current (post-change telemetry):
- Events in DB: 611
- Source counts: live_cctv 611
- Detector counts: yolo 611
- Seeded share: 0.0
- Live share: 1.0
- Visitors total: 53
- Multi-camera visitors: 17
- Purchased sessions with explainability: 1/1
- Polygon coverage: all camera coverage zones have explicit polygons

## What Was Changed

### 1) Seed Dependency Removed from Runtime Path
- Startup seeding is now explicitly controlled by `ENABLE_EVENT_SEED` (default off in API startup).
- Service seeding remains callable for tests and controlled flows.
- DB was rebuilt from regenerated CCTV events.

### 2) Detector Provenance Hardening
- Detection metadata now stamps:
  - `event_source` (live_cctv/live_ingest/seeded_jsonl*)
  - `detector_type`
  - normalized `camera_id`, `frame_number`, `track_id`, `bbox`, `confidence`
- Added source normalization backfill for historical rows.

### 3) Polygon Completeness
- Added explicit `zone_polygons` for CAM_1..CAM_5 in `data/store_metadata.json`.
- Added missing coverage zones referenced by cameras:
  - `STAFF_SUPPORT`
  - `EXTERIOR_THRESHOLD`
  - `CASH_COUNTER`
- Updated `BACK_ROOM` placeholder geometry to explicit non-zero box.

### 4) Attribution Explainability Backfill
- Added attribution backfill routine so purchased sessions always have:
  - `confidence`
  - `evidence`
  - `attribution_reason`
- Added `attribution_reason` to direct attribution writes as well.

### 5) Score Tracking in Existing Metrics Endpoint
- Added to metrics payload:
  - `live_event_ratio`
  - `seeded_event_ratio`
- Added event source breakdown in evidence payload.

## ReID Validation Status

Observed multi-camera linkage proxy now shows 17 multi-camera visitors from live-only data.
This indicates cross-camera continuity is present and non-trivial in the current corpus; ReID path should be retained and tuned rather than removed outright.

## Root Resource Audit

### Used (active in pipeline/API/docs path)
- `CCTV Footage/CAM 1.mp4` .. `CAM 5.mp4`
- `vision-retail-ai/data/store_metadata.json`
- `vision-retail-ai/data/events.generated.jsonl`
- `vision-retail-ai/data/pos_transactions_normalized.csv`
- `vision-retail-ai/src/**`
- `vision-retail-ai/tests/**`
- `vision-retail-ai/docs/**`

### Potentially Useful (not yet fully operationalized)
- `Store 1/` and `Store 2/` layout/video artifacts for additional geometry calibration
- Root sample files:
  - `Brigade_Bangalore_10_April_26 (1)bc6219c.csv`
  - `POS - sample transactionsb1e826f.csv`
  - `sample_eventsbe42122.jsonl`

### Currently Unused in Runtime
- `ml-models/` (no dedicated external model artifact loaded at runtime beyond YOLO weight path)
- Any root-level assets not referenced by `vision-retail-ai/data/*` loaders or scripts

## Risk Notes

- Test compatibility was preserved while introducing production toggles.
- Production strict mode is codified in `scripts/run_detection.sh`:
  - `MOTION_FALLBACK_ON_EMPTY_YOLO=false`
  - `MIN_TRACK_HITS=2`

## Verification

Validated test set after changes:
- `tests/test_api.py`
- `tests/test_pipeline_units.py`
- `tests/test_analytics.py`
- `tests/test_dashboard.py`
- `tests/test_service_extra.py`

Result: 131 passed.
