# VisionRetail AI - Implementation Summary

## Project Overview

**VisionRetail AI** is a production-grade retail intelligence platform built for the Purplle Tech Challenge 2026. It transforms CCTV footage, store metadata, and POS transactions into actionable analytics through a sophisticated multi-layer architecture.

### Key Capabilities

✅ **Vision & Detection**
- YOLO-based person detection (YOLOv8/v11)
- Multi-camera visitor tracking across store zones
- Cross-camera re-identification (ReID) for repeat visitor tracking
- Automatic staff/customer classification

✅ **Analytics Engine**
- Real-time conversion funnel analysis (Entry → Zone → Queue → Purchase)
- Zone-level performance metrics and heatmaps
- Queue depth tracking with abandonment detection
- Customer journey path analysis and pattern identification
- Purchase probability predictions using behavioral features
- Anomaly detection (queue spikes, conversion drops, dead zones)

✅ **Multi-Store Support**
- Metadata-driven store configuration
- Dynamic store discovery from `data/` directory
- Per-store analytics isolation
- Cross-store aggregation and comparison

✅ **Event System**
- Canonical event generation (ENTRY, EXIT, ZONE_ENTER, ZONE_EXIT, BILLING_QUEUE_JOIN, PURCHASE_ATTRIBUTED)
- JSONL format output (`data/events.generated.jsonl`)
- Idempotent event ingestion
- Full event traceability

---

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|----------|
| **Language** | Python | 3.10+ |
| **API** | FastAPI | 0.104.1 |
| **Web Server** | Uvicorn | 0.24.0 |
| **UI** | Streamlit | 1.29.0 |
| **Database** | SQLite/PostgreSQL | SQLAlchemy 2.0.23 |
| **Computer Vision** | YOLOv8 + OpenCV | ultralytics 8.0.206, cv2 4.8.1.78 |
| **ML Frameworks** | PyTorch | 2.1.1 |
| **Data Processing** | Pandas + NumPy | 2.1.3, 1.26.2 |
| **Testing** | Pytest | 7.4.3 |
| **Containerization** | Docker | docker-compose |

---

## Architecture

### Layered Design

```
┌─────────────────────────────────────┐
│  Streamlit Dashboard (UI Layer)     │
│  - Metrics, Funnel, Heatmap         │
│  - Queue, Journeys, Predictions     │
│  - Anomalies, Digital Twin          │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│    FastAPI Application (API)        │
│  - RESTful endpoints                │
│  - Request/response validation      │
│  - Authentication & tracing         │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  Service Layer                      │
│  - StoreIntelligenceService         │
│  - AnalyticsEngine                  │
│  - EventProcessor                   │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  Data Models (ORM)                  │
│  - Stores, Cameras, Zones           │
│  - Events, Sessions, Transactions   │
│  - Anomalies                        │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  Database Layer                     │
│  SQLite (default) or PostgreSQL     │
└─────────────────────────────────────┘
```

### Data Flow

```
CCTV Footage + POS Data + Metadata
         │
         ▼
   Detection Pipeline (YOLO)
   - Person detection
   - Multi-object tracking
   - Re-identification
         │
         ▼
   Event Generation
   - Canonical events (ENTRY, EXIT, ZONE_ENTER, etc.)
   - Timestamps and metadata enrichment
         │
         ▼
   Event Ingestion API (/events/ingest)
   - Idempotent processing
   - Database persistence
         │
         ▼
   Analytics Engine
   - Funnel calculation
   - Zone heatmaps
   - Journey extraction
   - Anomaly detection
         │
         ▼
   API Endpoints + Dashboard
   - Real-time metrics
   - Historical analysis
   - Visualization
```

---

## API Endpoints

### Core Mandatory Endpoints

```
POST /events/ingest
  → Ingest detection events (idempotent)

GET /stores/{store_id}/metrics
  → Real-time KPIs: visitors, conversion, revenue

GET /stores/{store_id}/funnel
  → Conversion funnel with drop-off analysis

GET /stores/{store_id}/heatmap
  → Zone-level heatmap (visitor_count, dwell_time, conversion_rate)

GET /health
  → System health check
```

### Advanced Analytics Endpoints

```
GET /stores/{store_id}/journeys
  → Top customer journey paths with conversion analysis

GET /stores/{store_id}/predictions
  → Purchase probability predictions for active visitors

GET /stores/{store_id}/queue-analytics
  → Queue depth, wait times, abandonment patterns

GET /stores/{store_id}/anomalies
  → Detected anomalies with root causes

GET /stores/{store_id}/opportunities
  → Improvement opportunities and recommendations

GET /stores/{store_id}/digital-twin
  → Live occupancy map with real-time data
```

### Multi-Store Endpoints

```
GET /stores
  → List all discovered stores

GET /stores/{store_id}/analytics
  → Per-store analytics summary

GET /stores/cross/summary
  → Cross-store aggregate metrics

POST /stores/{store_id}/datasets/generate
  → Generate analytical datasets (JSONL format)
```

---

## Database Schema

### Core Tables

**stores** - Store master data
```
id (UUID), store_code (unique), store_name, city, country, 
layout_file_path, aliases (JSON), created_at, updated_at
```

**cameras** - Camera configuration
```
id (UUID), store_id (FK), camera_code, camera_name, camera_type,
source_file, fps, status, last_heartbeat, created_at
```

**zones** - Store zones/departments
```
id (UUID), store_id (FK), zone_code, zone_name, zone_type,
polygon (JSON), area_sqm, created_at
```

**detection_events** - Raw vision events
```
id (UUID), event_id (unique per store), store_id (FK), camera_id (FK),
visitor_id, event_type, event_timestamp, zone_id, dwell_ms,
is_staff, confidence, metadata (JSON), ingested_at
```

**visitor_sessions** - Customer sessions
```
id (UUID), store_id (FK), visitor_id, session_start, session_end,
total_dwell_ms, is_staff, has_purchase, purchase_amount,
purchase_time, transaction_id, confidence, journey_path (JSON),
metadata (JSON), created_at, updated_at
```

**transactions** - POS transactions
```
id (UUID), store_id (FK), transaction_id (unique per store),
transaction_timestamp, basket_value_inr, item_count,
line_count, primary_department, created_at
```

**anomalies** - Detected anomalies
```
id (UUID), store_id (FK), anomaly_type, severity, confidence,
detected_at, description, reason, suggested_action,
zone_id, metric_value, baseline_value, deviation_percent,
acknowledged, resolved, metadata (JSON), created_at
```

---

## Installation & Setup

### Quick Start (Automated)

```bash
# Run the setup script
bash scripts/setup.sh

# Start API (Terminal 1)
bash scripts/run_api.sh

# Start Dashboard (Terminal 2)
bash scripts/run_dashboard.sh
```

### Manual Setup

```bash
# Create virtual environment
python3.10 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Initialize database
python -c "from src.api.database import init_db_sync; init_db_sync()"

# Start API
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

# Start Dashboard (new terminal)
streamlit run src/dashboard/main.py
```

### Docker Setup

```bash
# Build and run with docker-compose
docker compose up --build

# Services available at:
# - API: http://localhost:8000
# - Dashboard: http://localhost:8501
```

---

## Configuration

### Environment Variables (.env)

```dotenv
# Database
DATABASE_URL=sqlite:///./vision_retail.db

# API
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO

# Store
STORE_ID=brigade-bangalore
STORE_LAYOUT_FILE=./data/brigade_road/metadata.json
POS_DATA_FILE=./data/brigade_road/pos.csv
CCTV_FEED_PATH=./data/brigade_road/cameras

# Models
DEVICE=cpu
MODEL_YOLO_PATH=./models/yolov11n.pt

# Environment
ENVIRONMENT=local
SUBMISSION_MODE=false
```

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=src --cov-report=html

# Run specific test
pytest tests/test_api.py -v

# Current status
# ✓ 182 tests passing
# ⊘ 1 test skipped
```

---

## File Structure

```
Vision_retail/
├── RUN_REPORT.md              # Comprehensive setup & architecture
├── SETUP_LOCAL.md             # Local development setup
├── IMPLEMENTATION_SUMMARY.md  # This file
├── README.md                  # Main documentation
├── ARCHITECTURE.md            # Deep-dive architecture
├── QUICKSTART.md              # Quick start guide
├── Dockerfile                 # Container image
├── docker-compose.yml         # Multi-service orchestration
├── requirements.txt           # Python dependencies
├── pyproject.toml            # Project metadata
├── .env.example              # Environment template
│
├── scripts/
│   ├── setup.sh              # Automated setup
│   ├── run_api.sh            # Start API
│   └── run_dashboard.sh      # Start dashboard
│
├── src/
│   ├── api/                  # FastAPI application
│   ├── analytics/            # Analytics engine
│   ├── dashboard/            # Streamlit UI
│   ├── detection/            # Vision pipeline
│   ├── events/               # Event system
│   ├── identity_graph/       # Cross-camera tracking
│   ├── metadata/             # Store metadata
│   ├── multi_store/          # Multi-store support
│   ├── reid/                 # Re-identification
│   └── stores/               # Store management
│
├── data/
│   ├── brigade_road/         # Sample store data
│   └── events.generated.jsonl # Event log
│
├── datasets/                 # Generated analytics
├── db/                       # Database initialization
├── tests/                    # Test suite
└── docs/                     # Additional documentation
```

---

## Key Features & Highlights

### 1. Metadata-Driven Architecture
- Store configuration defined in `metadata.json`
- No code changes needed to add new stores
- Automatic discovery and registration

### 2. Production-Ready Deployment
- Docker containerization with docker-compose
- SQLite for development, PostgreSQL for production
- Health checks and service dependencies
- Prometheus metrics and structured logging

### 3. Comprehensive Analytics
- Real-time KPI dashboard
- Historical trend analysis
- Predictive modeling (purchase probability)
- Anomaly detection with root cause analysis

### 4. Robust Event Processing
- Canonical event schema
- Idempotent ingestion
- Full audit trail
- Event-driven architecture

### 5. Scalability
- Multi-camera support
- Cross-store aggregation
- Horizontal scaling ready
- Kafka-ready event streaming

---

## Known Limitations & Future Work

### Current Limitations
- Vision pipeline requires CPU/GPU (not included in API-only deployment)
- Dashboard hard-coded to single store (can be extended)
- No authentication/authorization in default setup
- Kafka integration is opt-in

### Future Enhancements
- Real-time WebSocket updates
- Multi-user authentication
- Advanced ReID models (OSNet, MarginFace)
- Custom ML model support
- Advanced forecasting
- Mobile app integration

---

## Support & Documentation

- **Main README**: `README.md` - Project overview
- **Quick Start**: `QUICKSTART.md` - 5-minute setup
- **Architecture**: `ARCHITECTURE.md` - Deep technical dive
- **Local Setup**: `SETUP_LOCAL.md` - Development setup
- **Run Report**: `RUN_REPORT.md` - Complete analysis
- **API Docs**: `http://localhost:8000/docs` - Interactive Swagger UI
- **Tests**: `tests/` - Usage examples and edge cases

---

## Status

✅ **Production Ready**
- 182 tests passing
- All mandatory endpoints implemented
- All advanced analytics endpoints implemented
- Multi-store support verified
- Docker deployment tested

---

## Contact & Attribution

**Project**: VisionRetail AI - Purplle Tech Challenge 2026
**Language**: Python 3.10+
**Frameworks**: FastAPI, Streamlit, SQLAlchemy
**AI/ML**: PyTorch, YOLO, scikit-learn
**License**: MIT
