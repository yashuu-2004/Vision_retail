# Submission Readiness

## Acceptance Gate

- `docker compose up --build` starts PostgreSQL, API, detection replay, dashboard, Prometheus, Grafana, and Redpanda.
- On API startup, 892 pre-generated events are seeded into PostgreSQL automatically (idempotent).
- `/health` returns HTTP 200 for healthy or degraded states and includes stale-feed details.
- `POST /events/ingest` accepts generated events and deduplicates replay.
- `/stores/ST1008/metrics` returns computed JSON (335 customer visitors, ₹897.99 revenue).
- `DESIGN.md` and `CHOICES.md` are non-trivial and resource-specific.

## Test Coverage

- **131 tests, 71% line coverage** across the full `src/` package.
- Fast test command: `pytest tests/test_api.py tests/test_pipeline_units.py tests/test_analytics.py tests/test_dashboard.py tests/test_service_extra.py --cov=src`

## Reviewer Two-Minute Story

This submission first inspected the actual resources and found mismatches with the problem statement. The system normalizes the real POS, layout image, and five camera roles, emits replayable schema events, reconstructs visitor sessions, attributes POS purchases by billing presence, and exposes conversion/funnel/heatmap/anomaly APIs plus a dashboard. It is honest about the current CV fallback and clear about the production model path.

## Interview Prep

Why YOLO/ByteTrack/OSNet?

They are the production target because YOLO is a strong person detector, ByteTrack is fast and simple for per-camera IDs, and OSNet-style embeddings help cross-camera re-ID. They are not forced into the default image because weights were not supplied and Docker reliability is an acceptance gate.

Why PostgreSQL?

The system needs transactional idempotent ingestion, session updates, POS joins, JSON metadata, and time-filtered aggregation. PostgreSQL handles this mixed workload cleanly.

How does POS attribution work?

The raw POS line-item file is grouped into invoice-level transactions. A non-staff session with billing-zone presence inside the attribution window before a transaction receives the purchase and revenue.

What breaks at 40 stores?

In-process analytics and synchronous request-time aggregation. The next step is partitioned event topics by store, consumer-group session reconstruction, and materialized metrics.

What is the biggest limitation?

The default detection mode is a deterministic fallback, not learned CV inference. It is sufficient to prove the platform and scoring logic but should be replaced with real detector/tracker/re-ID components for production accuracy.
