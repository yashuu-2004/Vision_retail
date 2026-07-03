# Local Setup Guide - VisionRetail AI

## Step 1: Create Virtual Environment

```bash
python3.10 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

## Step 2: Upgrade pip

```bash
pip install --upgrade pip
```

## Step 3: Install Dependencies

Install all dependencies in order of priority:

```bash
# Core dependencies
pip install python-dotenv==1.0.0
pip install fastapi==0.104.1 uvicorn==0.24.0 pydantic==2.5.0 pydantic-settings==2.1.0

# Database
pip install sqlalchemy==2.0.23 psycopg2-binary==2.9.9 alembic==1.13.0

# Computer Vision & Detection
pip install ultralytics==8.0.206
pip install torch==2.1.1 torchvision==0.16.1
pip install opencv-python-headless==4.8.1.78
pip install filterpy==1.4.2

# Data Processing
pip install pandas==2.1.3 numpy==1.26.2 scipy==1.11.4 scikit-learn==1.3.2

# Streaming (optional)
pip install confluent-kafka==2.3.0

# Monitoring
pip install prometheus-client==0.19.0 python-json-logger==2.0.7

# Dashboard
pip install streamlit==1.29.0 plotly==5.18.0 altair==5.1.0

# Utilities
pip install python-dateutil==2.8.2 requests==2.31.0 pyyaml==6.0.1

# Testing
pip install pytest==7.4.3 pytest-asyncio==0.21.1 pytest-cov==4.1.0 httpx==0.25.2

# Development
pip install black==23.12.0 flake8==6.1.0 mypy==1.7.1 isort==5.13.2
```

## Step 4: Environment Configuration

```bash
cp .env.example .env
```

Edit `.env` with your configuration.

## Step 5: Database Setup

```bash
# Initialize SQLite database
python -c "from src.api.database import init_db_sync; init_db_sync()"
```

## Step 6: Start Services

### Terminal 1 - API Server

```bash
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

API will be available at: http://localhost:8000
API Docs: http://localhost:8000/docs

### Terminal 2 - Streamlit Dashboard

```bash
streamlit run src/dashboard/main.py
```

Dashboard will be available at: http://localhost:8501

## Notes

- Default database is SQLite (`vision_retail.db` in repo root)
- For PostgreSQL, update `DATABASE_URL` in `.env`
- YOLO models will auto-download on first use
- Dashboard requires API to be running first
