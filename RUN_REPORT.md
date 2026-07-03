# VisionRetail AI - Complete Project Analysis

## ======================== STEP 1: PROJECT ARCHITECTURE ========================

### Overview
**VisionRetail AI** is a production-grade retail intelligence platform for the Purplle Tech Challenge 2026. It transforms CCTV footage, store metadata, and POS transactions into actionable analytics.

### Core Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          API Layer (FastAPI)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ /events/...  │  │ /stores/...  │  │ /anomalies, /health  │  │
│  │ (Ingest)     │  │ (Analytics)  │  │ (System)             │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────────┐
│              Analytics Engine + Service Layer                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ StoreIntell  │  │ Analytics    │  │ Visitor/Session      │  │
│  │ Service      │  │ Engine       │  │ Management           │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────────┐
│              Data Models (SQLAlchemy ORM)                       │
│  ┌──────────┐  ┌────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Stores   │  │Cameras │  │ Zones    │  │DetectionEvents   │  │
│  ├──────────┤  ├────────┤  ├──────────┤  ├──────────────────┤  │
│  │ Sessions │  │ Txns   │  │Anomalies │  │ (Multi-store)    │  │
│  └──────────┘  └────────┘  └──────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────────┐
│         Database Layer (SQLite/PostgreSQL)                      │
│  Default: SQLite (vision_retail.db)                             │
│  Production: PostgreSQL with schema support                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              Visualization Layer (Streamlit)                    │
│  ┌──────────┐  ┌────────────┐  ┌──────────────────────────────┐│
│  │Overview  │  │Conversion  │  │Heatmap, Queue, Journeys,    ││
│  │Metrics   │  │Funnel      │  │Predictions, Anomalies       ││
│  └──────────┘  └────────────┘  └──────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| **Language** | Python | 3.10+ |
| **API Framework** | FastAPI | 0.104.1 |
| **Web Server** | Uvicorn | 0.24.0 |
| **Dashboard** | Streamlit | 1.29.0 |
| **Database** | SQLite/PostgreSQL | 2.0.23 (SQLAlchemy) |
| **Data Processing** | Pandas, NumPy, SciPy | Latest (2.1.3, 1.26.2, 1.11.4) |
| **Computer Vision** | YOLOv8, OpenCV | 8.0.206, 4.8.1.78 |
| **ML Frameworks** | PyTorch, Scikit-learn | 2.1.1, 1.3.2 |
| **Monitoring** | Prometheus | 0.19.0 |
| **Testing** | Pytest | 7.4.3 |

### Key Features

**Vision & Detection:**
- YOLO-based person detection (YOLOv8/v11)
- Multi-camera visitor tracking
- Cross-camera re-identification
- Staff/customer classification

**Analytics:**
- Conversion funnel analysis (Entry → Zone → Queue → Purchase)
- Zone-level performance metrics
- Queue depth & abandonment tracking
- Customer journey path analysis
- Purchase probability predictions
- Heatmap visualization
- Anomaly detection (queue spikes, conversion drops, dead zones)

**Multi-Store Support:**
- Metadata-driven store configuration
- Dynamic store discovery
- Per-store analytics
- Cross-store aggregation

**Event System:**
- Canonical event generation (ENTRY, EXIT, ZONE_ENTER, ZONE_EXIT, BILLING_QUEUE_JOIN, PURCHASE_ATTRIBUTED)
- JSONL format output
- Idempotent event ingestion
- Event traceability

---

## ======================== STEP 2: REPOSITORY STRUCTURE ========================

```
Vision_retail/
├── README.md                          # Main project documentation
├── SETUP_LOCAL.md                     # Local setup instructions (NEW)
├── ARCHITECTURE.md                    # Architecture deep-dive
├── PHASE_2_REPORT.md                  # Phase 2 challenge report
├── PROJECT_SUMMARY.md                 # Quick project summary
├── QUICKSTART.md                      # Quick start guide
├── pyproject.toml                     # Python project metadata
├── requirements.txt                   # All dependencies
├── requirements.api.txt               # API-only dependencies
├── requirements.dashboard.txt         # Dashboard dependencies
├── requirements.detection.txt         # Detection pipeline dependencies
├── Dockerfile                         # API/Dashboard image
├── docker-compose.yml                 # Multi-service orchestration
│
├── src/                               # Source code
│   ├── __init__.py
│   ├── api/                           # FastAPI application
│   │   ├── main.py                    # API endpoints & FastAPI app
│   │   ├── database.py                # ORM models & DB setup
│   │   ├── models.py                  # Pydantic request/response models
│   │   ├── service.py                 # Business logic & services
│   │   └── dependencies.py            # Dependency injection
│   │
│   ├── analytics/                     # Analytics engine
│   │   ├── engine.py                  # Analytics computation
│   │   ├── funnel.py                  # Conversion funnel logic
│   │   ├── heatmap.py                 # Zone heatmaps
│   │   ├── journeys.py                # Journey path analysis
│   │   └── predictions.py             # Purchase predictions
│   │
│   ├── dashboard/                     # Streamlit UI
│   │   ├── main.py                    # Dashboard app
│   │   ├── pages/                     # Multi-page app (if used)
│   │   └── components/                # Reusable UI components
│   │
│   ├── detection/                     # Vision pipeline
│   │   ├── yolo_detector.py           # YOLO integration
│   │   ├── tracker.py                 # Multi-object tracking
│   │   ├── reid.py                    # Re-identification
│   │   └── pipeline.py                # Detection orchestration
│   │
│   ├── events/                        # Event generation & ingestion
│   │   ├── models.py                  # Event schema
│   │   ├── generator.py               # Event generation logic
│   │   └── processor.py               # Event processing
│   │
│   ├── identity_graph/                # Cross-camera identity management
│   │   ├── graph.py                   # Identity graph structure
│   │   └── matcher.py                 # Visitor matching logic
│   │
│   ├── metadata/                      # Store metadata handling
│   │   ├── loader.py                  # Metadata loading
│   │   ├── validator.py               # Metadata validation
│   │   └── models.py                  # Metadata schemas
│   │
│   ├── multi_store/                   # Multi-store support
│   │   ├── analytics.py               # Cross-store analytics
│   │   ├── registry.py                # Store registry
│   │   └── manager.py                 # Multi-store management
│   │
│   ├── reid/                          # Re-identification models
│   │   ├── osnet.py                   # OSNet model
│   │   └── embeddings.py              # Embedding computation
│   │
│   └── stores/                        # Store management
│       ├── registry.py                # Store discovery
│       └── loader.py                  # Store data loading
│
├── data/                              # Store data & artifacts
│   ├── brigade_road/                  # Brigade Road Bangalore
│   │   ├── metadata.json              # Store layout & zones
│   │   ├── cameras/                   # Camera footage
│   │   └── pos.csv                    # POS transaction data
│   ├── store_1/                       # Additional stores
│   ├── store_2/
│   └── events.generated.jsonl         # Generated event log
│
├── datasets/                          # Generated datasets
│   ├── journeys/
│   ├── queues/
│   ├── predictions/
│   └── reid/
│
├── db/                                # Database initialization
│   └── schema.sql                     # PostgreSQL schema
│
├── docker/                            # Docker configurations
│   ├── Dockerfile.detection           # Detection worker image
│   └── Dockerfile.api                 # API image
│
├── scripts/                           # Helper scripts
│   ├── setup.sh                       # Development setup
│   ├── run_api.sh                     # Start API
│   └── run_dashboard.sh               # Start dashboard
│
├── tests/                             # Test suite
│   ├── test_api.py                    # API endpoint tests
│   ├── test_analytics.py              # Analytics engine tests
│   ├── test_detection.py              # Detection pipeline tests
│   ├── test_events.py                 # Event system tests
│   └── test_models.py                 # Model tests
│
├── .env.example                       # Environment variables template
├── .gitignore                         # Git ignore rules
├── .dockerignore                      # Docker ignore rules
├── ingest_events.py                   # Event ingestion script
├── ingest_events_v2.py                # Event ingestion v2
├── verify_phase2.py                   # Phase 2 verification
│
└── docs/                              # Additional documentation
    ├── API.md                         # API documentation
    ├── MODELS.md                      # Model documentation
    └── DEPLOYMENT.md                  # Deployment guide
```

---

## ======================== STEP 3: DEPENDENCIES ========================

### Core Dependencies (All)

```
python-dotenv==1.0.0              # Environment variables

# Web Framework
fastapi==0.104.1                  # API framework
uvicorn==0.24.0                   # ASGI server
pydantic==2.5.0                   # Data validation
pydantic-settings==2.1.0          # Settings management

# Database
sqlalchemy==2.0.23                # ORM
psycopg2-binary==2.9.9            # PostgreSQL driver
alembic==1.13.0                   # Database migrations

# Computer Vision
ultralytics==8.0.206              # YOLO detection
opencv-python-headless==4.8.1.78  # Image processing
torch==2.1.1                       # PyTorch (CPU/GPU)
torchvision==0.16.1               # Vision utilities
filterpy==1.4.2                   # Tracking filters
scikit-learn==1.3.2               # ML utilities

# Data Processing
pandas==2.1.3                      # Tabular data
numpy==1.26.2                      # Numerical computing
scipy==1.11.4                      # Scientific functions

# Streaming
confluent-kafka==2.3.0             # Kafka client

# Dashboard
streamlit==1.29.0                  # Web UI framework
plotly==5.18.0                     # Interactive plots
altair==5.1.0                      # Statistical visualization

# Monitoring
prometheus-client==0.19.0          # Prometheus metrics
python-json-logger==2.0.7          # JSON logging

# Utilities
python-dateutil==2.8.2             # Date utilities
requests==2.31.0                   # HTTP client
pyyaml==6.0.1                      # YAML parsing

# Testing
pytest==7.4.3                      # Testing framework
pytest-asyncio==0.21.1             # Async test support
pytest-cov==4.1.0                  # Coverage reporting
httpx==0.25.2                      # Async HTTP client

# Development
black==23.12.0                     # Code formatter
flake8==6.1.0                      # Linter
mypy==1.7.1                        # Type checker
isort==5.13.2                      # Import sorter
```

### Installation Order (CRITICAL)

1. **Python Core** → setuptools, wheel
2. **Core Web** → fastapi, uvicorn, pydantic
3. **Database** → sqlalchemy, psycopg2-binary
4. **ML/CV (heavy)** → torch, torchvision, ultralytics
5. **Data** → pandas, numpy, scipy
6. **UI** → streamlit, plotly
7. **Utilities** → remaining packages
8. **Testing/Dev** → pytest, black, etc.

---

## ======================== STEP 4: ENVIRONMENT VARIABLES ========================

### Local Development (.env)

```dotenv
# Database
DATABASE_URL=sqlite:///./vision_retail.db
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=vision_retail

# API
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=1
LOG_LEVEL=INFO
DEBUG=true

# Storage
STORAGE_TYPE=local
STORAGE_PATH=./data/storage

# Store Configuration
STORE_ID=brigade-bangalore
STORE_LAYOUT_FILE=./data/brigade_road/metadata.json
POS_DATA_FILE=./data/brigade_road/pos.csv
CCTV_FEED_PATH=./data/brigade_road/cameras

# Models
MODEL_YOLO_PATH=./models/yolov11n.pt
DEVICE=cpu

# Environment
ENVIRONMENT=local
SUBMISSION_MODE=false
ENABLE_EVENT_SEED=true
```

### Docker Production (.env.docker)

```dotenv
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/vision_retail
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
STORAGE_PATH=/data/storage
DEVICE=cpu
ENVIRONMENT=production
```

---

## ======================== STEP 5: DATABASE SCHEMA ========================

### SQLite (Default)

```sql
-- Auto-created by SQLAlchemy on startup
CREATE TABLE stores (
    id TEXT PRIMARY KEY,
    store_code TEXT UNIQUE NOT NULL,
    store_name TEXT NOT NULL,
    city TEXT,
    country TEXT,
    layout_file_path TEXT,
    aliases JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE cameras (
    id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL,
    camera_code TEXT NOT NULL,
    camera_name TEXT,
    camera_type TEXT,
    source_file TEXT,
    fps REAL,
    status TEXT DEFAULT 'active',
    last_heartbeat TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(store_id) REFERENCES stores(id),
    UNIQUE(store_id, camera_code)
);

CREATE TABLE zones (
    id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL,
    zone_code TEXT NOT NULL,
    zone_name TEXT,
    zone_type TEXT,
    polygon JSON,
    area_sqm REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(store_id) REFERENCES stores(id),
    UNIQUE(store_id, zone_code)
);

CREATE TABLE detection_events (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    camera_id TEXT,
    camera_code TEXT,
    visitor_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_timestamp TIMESTAMP NOT NULL,
    zone_id TEXT,
    dwell_ms INTEGER DEFAULT 0,
    is_staff BOOLEAN DEFAULT 0,
    confidence REAL DEFAULT 0.95,
    metadata JSON,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(store_id) REFERENCES stores(id),
    FOREIGN KEY(camera_id) REFERENCES cameras(id),
    UNIQUE(store_id, event_id)
);

CREATE TABLE visitor_sessions (
    id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL,
    visitor_id TEXT NOT NULL,
    session_start TIMESTAMP NOT NULL,
    session_end TIMESTAMP,
    total_dwell_ms INTEGER DEFAULT 0,
    is_staff BOOLEAN DEFAULT 0,
    has_purchase BOOLEAN DEFAULT 0,
    purchase_amount DECIMAL(10,2) DEFAULT 0,
    purchase_time TIMESTAMP,
    transaction_id TEXT,
    confidence REAL DEFAULT 0.95,
    journey_path JSON,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(store_id) REFERENCES stores(id),
    UNIQUE(store_id, visitor_id)
);

CREATE TABLE transactions (
    id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL,
    transaction_id TEXT NOT NULL,
    transaction_timestamp TIMESTAMP NOT NULL,
    basket_value_inr DECIMAL(10,2) NOT NULL,
    item_count INTEGER DEFAULT 0,
    line_count INTEGER DEFAULT 0,
    primary_department TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(store_id) REFERENCES stores(id),
    UNIQUE(store_id, transaction_id)
);

CREATE TABLE anomalies (
    id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL,
    anomaly_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence REAL DEFAULT 0.8,
    detected_at TIMESTAMP NOT NULL,
    description TEXT,
    reason TEXT,
    suggested_action TEXT,
    zone_id TEXT,
    metric_value REAL,
    baseline_value REAL,
    deviation_percent REAL,
    acknowledged BOOLEAN DEFAULT 0,
    resolved BOOLEAN DEFAULT 0,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(store_id) REFERENCES stores(id)
);
```

---

## ======================== STEP 6: API ENDPOINTS ========================

### Mandatory Endpoints (30% of scoring)

```
POST /events/ingest
├─ Description: Ingest detection events from vision pipeline
├─ Body: { "events": [{ "event_id", "store_id", "visitor_id", "event_type", ... }] }
└─ Response: { "status", "events_processed", "events_accepted", "duplicates", "trace_id" }

GET /stores/{store_id}/metrics?lookback_minutes=60
├─ Description: Real-time KPIs (visitors, conversion, revenue)
├─ Response: { "total_visitors", "unique_visitors", "conversion_rate", "total_revenue", "zones": [...] }
└─ Evidence: Traceability for metrics calculation

GET /stores/{store_id}/funnel?lookback_minutes=60
├─ Description: Conversion funnel (Entry → Zone → Queue → Purchase)
├─ Response: { "overall_conversion_rate", "stages": [{ "stage", "count", "drop_off_percent" }] }
└─ Evidence: Detailed funnel breakdown

GET /stores/{store_id}/heatmap?metric=visitor_count&lookback_minutes=60
├─ Description: Zone-level heatmap (visitor_count, dwell_time, conversion_rate)
├─ Response: { "metric", "zones": [{ "zone_name", "value" }] }
└─ Metrics: visitor_count | dwell_time | conversion_rate

GET /health
├─ Description: System health check (API, DB, events, detection, cameras)
└─ Response: { "status": "healthy|degraded|unhealthy", "components": {...} }
```

### Advanced Endpoints (35% of scoring)

```
GET /stores/{store_id}/journeys?limit=10&min_visitors=5
├─ Description: Top customer journey paths with conversion analysis
└─ Response: [{ "journey_path", "occurrence_count", "purchase_count", "conversion_rate", "avg_duration_ms" }]

GET /stores/{store_id}/predictions?lookback_minutes=30
├─ Description: Purchase probability predictions for active visitors
└─ Response: [{ "visitor_id", "prediction_score", "abandonment_probability", "confidence", "features_used" }]

GET /stores/{store_id}/queue-analytics?lookback_minutes=60
├─ Description: Queue depth, wait times, abandonment patterns
└─ Response: { "current_depth", "max_depth", "avg_depth", "avg_wait_time_ms", "abandonment_rate" }

GET /stores/{store_id}/anomalies?severity=low&resolved=false
├─ Description: Detected anomalies (queue spikes, conversion drops, dead zones)
└─ Response: [{ "anomaly_type", "severity", "confidence", "description", "reason", "suggested_action" }]

GET /stores/{store_id}/opportunities
├─ Description: Identify high-value improvement opportunities
└─ Response: [{ "type", "zone_id", "current_value", "potential_improvement", "recommendation" }]

GET /stores/{store_id}/digital-twin
├─ Description: Live occupancy map (customers per zone, queue status, heatmap)
└─ Response: { "zones": [{ "zone_id", "current_occupancy", "capacity", "heatmap_value" }], "queue_status": {...} }
```

### Multi-Store Endpoints

```
GET /stores
├─ Description: List all stores under data/ with camera/zone counts
└─ Response: { "store_count", "stores": [{ "store_id", "store_name", "camera_count", "zone_count" }] }

GET /stores/{store_id}/analytics
├─ Description: Per-store analytics summary
└─ Response: { "visitors", "revenue", "conversion", "zones" }

GET /stores/cross/summary
├─ Description: Aggregate metrics across all stores
└─ Response: { "total_stores", "total_visitors", "avg_conversion", "total_revenue" }

POST /stores/{store_id}/datasets/generate
├─ Description: Generate journey/queue/purchase/ReID datasets (idempotent)
└─ Response: { "status", "datasets_generated", "output_path" }
```

### System Endpoints

```
GET /metrics
├─ Description: Prometheus metrics endpoint
└─ Response: Prometheus-formatted metrics

POST /anomalies/{anomaly_id}/acknowledge
├─ Description: Mark anomaly as acknowledged
└─ Response: { "status": "acknowledged" }

GET / (root)
├─ Description: API documentation link
└─ Response: { "api", "version", "docs", "health" }
```

---

## ======================== STEP 7: RUNNING THE APPLICATION ========================

### Option 1: Docker (Recommended)

```bash
# Build and start all services
docker compose up --build

# Access services
# API: http://localhost:8000/docs
# Dashboard: http://localhost:8501
```

### Option 2: Manual (Local Development)

```bash
# 1. Create virtual environment
python3.10 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Initialize database
python -c "from src.api.database import init_db_sync; init_db_sync()"

# 4. Start API (Terminal 1)
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

# 5. Start Dashboard (Terminal 2)
streamlit run src/dashboard/main.py
```

### Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=src --cov-report=html

# Run specific test file
pytest tests/test_api.py -v
```

---

## ======================== STEP 8: KNOWN ISSUES & FIXES ========================

### Issue 1: Torch Installation on CPU
**Error:** `RuntimeError: CUDA not available`
**Fix:** Already configured for CPU in requirements. Ensure torch==2.1.1 without cuda.

### Issue 2: PostgreSQL Connection (Docker)
**Error:** `psycopg2.OperationalError: could not connect to server`
**Fix:** Ensure postgres service is healthy before starting API:
```bash
docker compose logs postgres
docker compose restart postgres
```

### Issue 3: YOLO Model Download
**Error:** `FileNotFoundError: [Errno 2] No such file or directory: 'yolov11n.pt'`
**Fix:** Models auto-download on first use. Ensure:
- Internet connection active
- `~/.cache/yolov8` is writable
- Ultralytics library properly installed

### Issue 4: Streamlit Port Already in Use
**Error:** `Address already in use`
**Fix:**
```bash
lsof -i :8501
kill -9 <PID>
streamlit run src/dashboard/main.py --server.port 8502
```

### Issue 5: Database Lock (SQLite)
**Error:** `sqlite3.OperationalError: database is locked`
**Fix:**
```bash
rm vision_retail.db
python -c "from src.api.database import init_db_sync; init_db_sync()"
```

---

## ======================== VERIFICATION CHECKLIST ========================

- ✅ Python 3.10+ installed
- ✅ Virtual environment created and activated
- ✅ All dependencies installed without errors
- ✅ `.env` file created from `.env.example`
- ✅ Database initialized (SQLite created)
- ✅ API starts at http://localhost:8000
- ✅ API docs accessible at http://localhost:8000/docs
- ✅ Dashboard starts at http://localhost:8501
- ✅ All endpoints return 200 status
- ✅ Test suite passes: `pytest tests/ -q`

---

## ======================== ADDITIONAL RESOURCES ========================

- **README.md** — Main project documentation
- **ARCHITECTURE.md** — Detailed architecture
- **QUICKSTART.md** — Quick start guide
- **API Documentation** — http://localhost:8000/docs (Swagger UI)
- **Tests** — See `tests/` directory for usage examples

---

## ======================== PROJECT STATUS ========================

**Current:** 182 tests passing, 1 test skipped
**Build:** Stable and production-ready
**Deployment:** Docker and local development supported
**Documentation:** Complete with code examples
