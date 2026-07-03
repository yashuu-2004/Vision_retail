# VisionRetail AI

> Purplle Tech Challenge 2026 — Retail Intelligence Platform

VisionRetail AI transforms retail CCTV footage, store metadata, and POS transactions into actionable store analytics. The system detects visitors, tracks customer journeys across zones and cameras, identifies queue behavior, attributes purchases, excludes staff activity from customer analytics, and generates structured event logs for downstream intelligence.

The platform is metadata-driven: store layouts, camera coverage, zones, transitions, and business rules are defined through `metadata.json`, enabling onboarding of new stores with minimal engineering effort.

---

## Challenge Objectives Addressed

### Customer Detection & Tracking

* Person detection using YOLO-based vision pipeline
* Multi-camera visitor tracking
* Zone-aware movement analysis
* Customer journey reconstruction

### Staff Exclusion

* Staff sessions identified separately from customer sessions
* Staff activity excluded from conversion and customer analytics
* Support-area and behavioral heuristics incorporated into analytics pipeline

### Re-Entry Handling

* Global visitor identity assignment
* Cross-camera visitor association
* Repeat visitor and re-entry tracking
* Visitor session stitching across camera views

### Retail Analytics

* Conversion funnel analysis
* Zone performance analytics
* Queue analytics
* Customer journey analytics
* Purchase attribution
* Heatmaps and operational metrics

### Event Generation

The system generates canonical retail events including:

* ENTRY
* EXIT
* ZONE_ENTER
* ZONE_DWELL
* ZONE_EXIT
* BILLING_QUEUE_JOIN
* BILLING_QUEUE_ABANDON
* PURCHASE_ATTRIBUTED

---

## Repository Structure

```text
src/
├── api/
├── analytics/
├── dashboard/
├── datasets/
├── detection/
├── events/
├── identity_graph/
├── metadata/
├── multi_store/
├── reid/
└── stores/

data/
├── brigade_road/
├── store_1/
└── store_2/

scripts/
tests/
```

---

## Event Log Deliverable

Generated event log:

```text
data/events.generated.jsonl
```

Characteristics:

* JSONL format (one JSON object per line)
* Challenge-compliant schema
* CCTV-derived visitor events
* Zone transitions
* Queue events
* Cross-camera visitor identities
* Staff classification metadata
* Purchase attribution metadata

Example:

```json
{
  "event_id": "EVT_xxx",
  "store_id": "ST1008",
  "camera_id": "CAM_1",
  "visitor_id": "VIS_GLOBAL_000001",
  "event_type": "ZONE_ENTER",
  "timestamp": "2026-04-10T20:20:00.300300",
  "zone_id": "MAKEUP_UNIT"
}
```

---

## Quick Start

### 1. Clone Repository

```bash
git clone <repository-url>
cd vision-retail-ai
```

### 2. Create Environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Start API

```bash
python -m uvicorn src.api.main:app \
    --host 0.0.0.0 \
    --port 8000
```

API Documentation:

```text
http://localhost:8000/docs
```

### 4. Start Dashboard

```bash
streamlit run src/dashboard/main.py
```

Dashboard:

```text
http://localhost:8501
```

---

## Multi-Store Support

The platform supports multiple stores through metadata-driven configuration.

A new store can be onboarded by adding:

```text
data/new_store/
├── metadata.json
├── cameras/
└── pos.csv
```

Store discovery and analytics routing are handled automatically through the metadata registry.

---

## Available APIs

### Analytics

```text
GET /stores/{store_id}/metrics
GET /stores/{store_id}/funnel
GET /stores/{store_id}/heatmap
GET /stores/{store_id}/journeys
GET /stores/{store_id}/predictions
GET /stores/{store_id}/queue-analytics
GET /stores/{store_id}/opportunities
GET /stores/{store_id}/digital-twin
```

### Multi-Store

```text
GET /stores
GET /stores/{store_id}/analytics
GET /stores/cross/summary
```

### Events

```text
POST /events/ingest
```

---

## Testing

Run the test suite:

```bash
pytest tests/ -q
```

Current status:

```text
182 tests passed
1 test skipped
```

---

## AI-Assisted Development

AI tools were used to accelerate:

* architecture exploration
* metadata normalization workflows
* documentation drafting
* test generation assistance
* schema validation assistance

All final implementation decisions, debugging, validation, event verification, analytics review, and submission preparation were performed manually.

---

## Documentation

* README.md
* DESIGN.md
* CHOICES.md

Additional project documentation may be provided in supporting files.

---

## Submission Contents

This submission includes:

* Source code
* Event log (`events.generated.jsonl`)
* README.md
* DESIGN.md
* CHOICES.md
* Tests
* Metadata definitions
* API implementation
* Dashboard implementation

---

## License

Prepared for the Purplle Tech Challenge 2026.
