# Project Summary

VisionRetail AI is a runnable Store Intelligence Platform for the supplied Purplle challenge resources.

What is implemented:

- Normalized metadata from the actual Brigade Road layout image, five CCTV clips, and POS file.
- Replayable detection/event pipeline that emits 45 schema-valid events by default.
- FastAPI ingestion with idempotency and validation.
- Session reconstruction with re-entry, staff exclusion, zone dwell, billing queue, abandonment, and POS attribution.
- Computed metrics, funnel, heatmap, anomalies, journeys, predictions, queue analytics, opportunities, and digital-twin endpoints.
- PostgreSQL in Docker and SQLite fallback for tests.
- Streamlit dashboard, Prometheus endpoint, structured request logs, and Docker Compose.

Current verified local result:

- `python -m src.detection.pipeline` generates `data/events.generated.jsonl`.
- Ingesting that file produces 6 unique non-staff visitors, 1 POS-attributed purchase, 16.67% conversion, queue spike depth 4, and one billing abandonment.
- `python -m pytest tests/test_api.py -q` passes 21 tests.

Known limitation:

The default detection mode is a deterministic resource-aware fallback. The code is structured so a real YOLO/ByteTrack/OSNet implementation can replace `process_camera` without changing the event schema, API, or analytics layer.
