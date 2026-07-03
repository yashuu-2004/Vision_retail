# Engineering Choices

This document explains the major engineering decisions made during the development of VisionRetail AI, the alternatives considered, tradeoffs evaluated, AI recommendations received, and the final implementation choices.

---

# Decision 1: Detection Architecture

## Objective

Generate reliable retail intelligence events from CCTV footage while ensuring the solution remains runnable in the challenge evaluation environment.

## Options Considered

### Option A: Full YOLO + ByteTrack + OSNet Pipeline

Pros:

* Production-grade architecture
* Better tracking accuracy
* Strong cross-camera re-identification

Cons:

* Model weights not provided
* Longer startup time
* Increased reviewer setup complexity
* Higher resource requirements

### Option B: OpenCV Motion-Based Detection

Pros:

* Lightweight
* No external models required

Cons:

* Weak identity tracking
* Poor retail analytics quality
* Limited extensibility

### Option C: Deterministic Replay Pipeline

Pros:

* Guaranteed execution
* Reproducible outputs
* Acceptance-gate friendly
* Preserves complete event architecture

Cons:

* Not true CV inference
* Limited detection realism

## AI Recommendation

AI recommended a YOLO + ByteTrack + OSNet architecture as the long-term production design.

## Final Choice

Deterministic replay pipeline with explicit extension points for YOLO, ByteTrack, and appearance embeddings.

## Reasoning

The challenge acceptance gate rewards working systems. Since no model weights were supplied, the replay pipeline provides a reliable, reviewer-runnable implementation while preserving a clear upgrade path.

---

# Decision 2: Store Metadata Normalization

## Objective

Create structured layout metadata from the actual challenge resources.

## Options Considered

### Option A

Assume `store_layout.json` exists.

### Option B

Attempt to infer layout solely from CCTV.

### Option C

Normalize the supplied XLSX layout image into structured metadata.

## AI Recommendation

AI initially assumed the problem statement resources existed as described.

## Final Choice

Create `data/store_metadata.json`.

## Reasoning

Repository inspection showed that the layout information exists as an embedded image inside the workbook rather than as machine-readable JSON.

The normalized metadata layer provides:

* Camera roles
* Zone definitions
* Store aliases
* Layout mappings

This enables heatmaps, dwell analysis, funnels, and journey reconstruction.

---

# Decision 3: Event Schema Design

## Objective

Maintain replayability, auditability, and idempotent ingestion.

## Options Considered

### Option A

Store only aggregated metrics.

### Option B

Store sessions directly.

### Option C

Store immutable event facts and derive sessions.

## AI Recommendation

AI recommended event-driven architecture for analytics reproducibility.

## Final Choice

Immutable event storage with derived sessions.

## Reasoning

Benefits:

* Replay capability
* Audit trail
* Easier debugging
* Historical analytics
* Future model retraining support

The event table becomes the system of record.

---

# Decision 4: Database Architecture

## Objective

Balance production realism with reviewer convenience.

## Options Considered

### Option A

PostgreSQL only

### Option B

SQLite only

### Option C

PostgreSQL with SQLite fallback

## AI Recommendation

AI recommended PostgreSQL for production workloads.

## Final Choice

PostgreSQL in Docker and SQLite for local execution.

## Reasoning

Advantages:

* Production-grade deployment path
* Fast local testing
* Reduced reviewer friction
* Shared ORM implementation

SQLAlchemy ensures application logic remains unchanged across both databases.

---

# Decision 5: API Architecture

## Objective

Ensure analytical integrity and avoid static demonstration responses.

## Options Considered

### Option A

Precomputed API responses

### Option B

Static mock payloads

### Option C

Computed analytics from persisted events

## AI Recommendation

AI recommended broad endpoint coverage.

## Final Choice

Compute all metrics from stored events, sessions, and transactions.

## Reasoning

This preserves:

* Analytical correctness
* Data traceability
* Replay consistency
* Challenge integrity

All major endpoints derive values from underlying data rather than returning hardcoded responses.

---

# Decision 6: Event Ingestion Strategy

## Objective

Support both replay processing and future production deployment.

## Options Considered

### Option A

Kafka-only ingestion

### Option B

HTTP-only ingestion

### Option C

HTTP ingestion with event-bus upgrade path

## AI Recommendation

AI recommended event-driven streaming architecture.

## Final Choice

HTTP ingestion for the runnable submission and Redpanda as the future event-bus path.

## Reasoning

HTTP provides the simplest reviewer experience while maintaining compatibility with future streaming deployments.

---

# Decision 7: Recorded Video vs Live Streaming

## Objective

Align the implementation with the challenge resources.

## Options Considered

### Option A

Build exclusively for live RTSP streams.

### Option B

Build exclusively for challenge recordings.

### Option C

Support both while optimizing for recorded footage.

## AI Recommendation

AI recommended supporting both ingestion modes.

## Final Choice

Recorded footage is the primary execution mode with architecture compatible with future live streams.

## Reasoning

The challenge resources consist entirely of recorded CCTV clips.

The system therefore prioritizes reproducibility while preserving compatibility with future live deployments.

---

# Decision 8: Dashboard Technology

## Objective

Provide reviewer-friendly visualization with minimal operational complexity.

## Options Considered

### Option A

React frontend

### Option B

Grafana-only dashboards

### Option C

Streamlit analytics dashboard

## AI Recommendation

AI suggested Streamlit because it provides rapid development and simple deployment.

## Final Choice

Streamlit dashboard.

## Reasoning

Benefits:

* Fast implementation
* Reviewer-friendly
* Minimal setup
* Native Python integration
* Direct API consumption

---

# AI-Assisted Development Summary

AI was used as an engineering assistant throughout the project.

AI contributions included:

* Architecture brainstorming
* Detection stack recommendations
* API design suggestions
* Database architecture alternatives
* Test generation assistance
* Documentation drafting

Human engineering judgment was used to:

* Reconcile differences between the challenge description and actual repository contents
* Choose deterministic replay over unavailable model dependencies
* Normalize layout and POS resources
* Prioritize reviewer-runnable execution
* Implement production-aware tradeoffs

Final architectural decisions were based on challenge constraints, repository inspection, execution reliability, and scoring criteria rather than AI recommendations alone.

---

# If Given Three Additional Weeks

Priority improvements would include:

1. Full YOLO integration.
2. ByteTrack multi-camera tracking.
3. Appearance embedding re-identification.
4. Camera-to-layout calibration.
5. Ground-truth evaluation dataset creation.
6. Streaming session reconstruction using Redpanda consumers.
7. Grafana dashboards and alerting.
8. Learned anomaly detection models.
9. Real-time RTSP camera ingestion.
10. Multi-store analytics and benchmarking.
