# System Design

## Objective

Build a production-aware, reviewer-runnable Store Intelligence Platform that converts CCTV activity, store layout information, and POS transactions into measurable retail business intelligence.

The design prioritizes the challenge rubric: working event generation, correct APIs, production readiness, reproducibility, and defensible engineering decisions.

## Resource Findings That Shaped The Design

Several observations from the provided repository materially influenced the architecture:

* The assessment framework explicitly rejects incomplete or non-functional submissions before scoring. This made Docker, API health, event generation, testing, and documentation the primary design constraints.
* The problem statement references resources such as `store_layout.json`, `sample_events.jsonl`, and simplified POS records. The actual repository instead contains an XLSX with an embedded layout image and a detailed line-item POS CSV.
* The actual store identifier present in the supplied resources is `ST1008`, which differs from some scaffold examples. The API therefore accepts `ST1008` and supported aliases.
* The CCTV package contains five recorded clips rather than the three twenty-minute videos described in portions of the challenge text.
* Camera roles were inferred from frame inspection and normalized into metadata for downstream analytics.

These findings required a normalization layer before analytics could be built.

## Architecture

```text
Challenge Resources
(CCTV + POS + Layout)
        │
        ▼
Detection Pipeline
        │
        ▼
Structured Events
        │
        ▼
Event Ingestion API
        │
        ▼
Session Reconstruction
        │
        ▼
POS Attribution
        │
        ▼
Analytics Engine
        │
        ▼
Business Intelligence APIs
        │
        ▼
Streamlit Dashboard
```

The system follows an event-driven architecture where raw observations become structured events, events become customer sessions, and sessions become business intelligence metrics.

## Storage Design

Docker deployments use PostgreSQL while local development and automated testing use SQLite.

This decision improves reviewer experience because the complete platform can run without requiring an external database server.

Core tables include:

* `stores`
* `cameras`
* `zones`
* `detection_events`
* `visitor_sessions`
* `transactions`
* `anomalies`

### Event Storage

The `detection_events` table stores immutable event facts.

Benefits:

* Replayability
* Auditability
* Event deduplication
* Historical analysis
* Reproducible metrics

### Session Storage

The `visitor_sessions` table stores derived state including:

* Journey path
* Dwell time
* Queue participation
* Re-entry count
* Purchase attribution
* Conversion outcome

Separating facts from derived state simplifies analytics while preserving traceability.

## Event And Session Logic

Events follow the required challenge schema:

```json
{
  "event_id": "EVT_...",
  "store_id": "ST1008",
  "camera_id": "CAM_3",
  "visitor_id": "VIS_001",
  "event_type": "ENTRY",
  "timestamp": "2026-04-10T20:20:00",
  "zone_id": null,
  "dwell_ms": 0,
  "is_staff": false,
  "confidence": 0.88,
  "metadata": {}
}
```

Event IDs are deterministic and derived from:

* Store ID
* Camera ID
* Visitor ID
* Event Type
* Timestamp
* Zone

This guarantees replay safety and idempotent ingestion.

Sessions are reconstructed from events and maintain:

* Journey order
* Zone history
* Queue state
* Re-entry count
* Dwell accumulation
* Purchase attribution
* Staff classification

Staff sessions are preserved for observability but excluded from customer analytics.

## POS Attribution

The supplied POS dataset is normalized into invoice-level transactions.

Attribution follows a configurable temporal window:

```text
Purchaser =
Visitor observed in billing zone
within N minutes before transaction
```

Default:

```text
ATTRIBUTION_WINDOW_MINUTES = 5
```

Because the challenge resources contain timeline inconsistencies between CCTV recordings and POS timestamps, the replay engine uses a configurable:

```text
CLIP_BASE_TIMESTAMP
```

This allows deterministic reproduction of analytics while documenting the resource mismatch.

## Detection Pipeline

### Production Target

The intended production stack is:

* YOLO for person detection
* ByteTrack for multi-object tracking
* Appearance embeddings (OSNet-style) for re-identification
* Polygon-based zone mapping

### Submission Implementation

The challenge repository does not provide model weights.

To guarantee reviewer execution, the runnable implementation:

* Loads real camera metadata
* Loads real zone definitions
* Uses OpenCV when available
* Generates deterministic replay events
* Produces schema-valid outputs
* Supports re-entry detection
* Supports queue events
* Supports billing abandonment
* Supports staff traffic
* Supports POS conversion attribution

This keeps the production path explicit while ensuring the evaluation environment remains functional.

## Analytics Design

The analytics layer computes business metrics directly from stored events and reconstructed sessions.

### North Star Metric

```text
Offline Store Conversion Rate =
POS-Attributed Purchasers
/
Unique Non-Staff Visitors
```

### Derived Metrics

Customer metrics:

* Total visitors
* Unique visitors
* Repeat visitors
* Group entries
* Dwell time

Revenue metrics:

* Conversion rate
* Revenue per visitor
* Revenue by zone
* Revenue attribution

Operational metrics:

* Queue depth
* Queue abandonment
* Zone utilization
* Dead zones

Predictive metrics:

* Purchase propensity
* Opportunity scores
* Revenue opportunity estimation

## API Design

### Mandatory Endpoints

* `POST /events/ingest`
* `GET /stores/{id}/metrics`
* `GET /stores/{id}/funnel`
* `GET /stores/{id}/heatmap`
* `GET /stores/{id}/anomalies`
* `GET /health`

### Advanced Endpoints

* `journeys`
* `predictions`
* `queue-analytics`
* `opportunities`
* `digital-twin`
* `metrics`

Endpoints compute values from persisted event and session data rather than returning static demonstration payloads.

## Dashboard Design

The Streamlit dashboard serves as an operational visualization layer.

Visualizations include:

* KPI overview
* Conversion funnel
* Zone heatmaps
* Customer journeys
* Queue analytics
* Opportunity recommendations
* Digital twin view
* Anomaly monitoring

The dashboard consumes live API endpoints rather than querying the database directly.

## Observability

Every request generates structured JSON logs containing:

* Trace ID
* Endpoint
* Store ID
* Status code
* Request latency

The `/health` endpoint reports:

* API health
* Database health
* POS availability
* Detection pipeline freshness

Detection lag is reported as degraded state rather than causing service failure.

## Scalability Considerations

The current implementation is optimized for challenge evaluation and replay workloads.

Current architecture scales comfortably to:

* Multiple cameras per store
* Thousands of events per day
* Concurrent dashboard consumers
* Historical replay analysis

For larger deployments:

* Event ingestion would be partitioned by store.
* Session reconstruction would become a stream-processing service.
* Analytics would be materialized into aggregate tables.
* Event storage would be partitioned by date and store.
* Cross-camera re-identification would become a dedicated inference service.
* Dashboards would consume precomputed metrics rather than raw event queries.

The architecture intentionally separates event generation, ingestion, attribution, and analytics to enable independent scaling.

## Engineering Tradeoffs

### Reliability vs Detection Accuracy

The production target includes YOLO, ByteTrack, and appearance embeddings.

However, the challenge acceptance gate rewards reliable execution. The submission therefore prioritizes deterministic replay behavior over dependency on unavailable model weights.

### Replayability vs Real-Time Processing

The supplied challenge resources are recorded CCTV clips.

Replay processing was prioritized because it directly aligns with the evaluation data while preserving compatibility with future live-stream ingestion.

### Simplicity vs Infrastructure Complexity

SQLite support remains available for testing and local execution while PostgreSQL powers Docker deployments.

This reduces reviewer setup effort without changing application behavior.

### Explainability vs Model Complexity

Business metrics are derived from explicit events, sessions, and attribution rules.

This improves auditability and makes analytics easier to validate against challenge requirements.

## AI-Assisted Decisions

### Detection Architecture

AI suggested a YOLO + ByteTrack + OSNet architecture.

This recommendation was retained as the production target but not enforced for challenge execution because model weights were not supplied.

### Resource Interpretation

AI initially assumed the challenge resources matched the problem statement.

After inspecting the repository, the implementation was adjusted to work with the actual assets:

* Embedded layout image
* Detailed POS CSV
* Five CCTV clips
* Store ID ST1008

### API Coverage

AI recommended broad endpoint coverage.

The recommendation was accepted, but endpoints were implemented using computed service logic rather than hardcoded responses to maintain analytical integrity.

## Failure Modes And Limitations

Current limitations include:

* Real detection accuracy depends on future model integration.
* Layout boundaries are approximations derived from image resources.
* POS attribution is probabilistic because customer identifiers are unavailable.
* Replay mode uses stable visitor identities rather than learned appearance embeddings.
* Cross-camera re-identification is simulated through deterministic visitor continuity.

These limitations are explicitly documented rather than hidden.

## Future Enhancements

Planned enhancements include:

* Full YOLO-based detection pipeline
* ByteTrack multi-camera tracking
* Appearance embedding re-identification
* Real-time RTSP camera ingestion
* SKU interaction analytics
* Staff scheduling recommendations
* Multi-store benchmarking
* Learned anomaly detection models
* Revenue forecasting models
* Regional performance analytics

## Reviewer FAQ

### Why not require YOLO inside Docker?

The repository does not provide model weights.

The challenge acceptance gate prioritizes runnable systems. A deterministic replay pipeline ensures reviewers can execute the complete solution without additional dependencies while preserving a clear upgrade path for production inference.

### Why process recorded footage instead of live cameras?

The challenge resources consist entirely of recorded CCTV clips.

The system is therefore optimized for reproducible analytics from supplied recordings while maintaining compatibility with future live-stream ingestion.

### What becomes the first bottleneck at scale?

Session reconstruction and analytics aggregation become the primary bottlenecks.

The next architectural evolution would introduce stream-processing infrastructure, event partitioning, and materialized analytics views to support multi-store deployments.
