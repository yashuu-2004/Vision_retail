#!/bin/bash
# Installation and setup script for VisionRetail AI

set -e

echo "=========================================="
echo "VisionRetail AI - Local Setup Script"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo -e "\n${YELLOW}Checking Python version...${NC}"
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
if [[ ! "$PYTHON_VERSION" =~ ^3.1[0-9] ]]; then
    echo -e "${RED}Error: Python 3.10+ required. Found: $PYTHON_VERSION${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python $PYTHON_VERSION found${NC}"

# Create virtual environment
echo -e "\n${YELLOW}Creating virtual environment...${NC}"
if [ -d ".venv" ]; then
    echo -e "${YELLOW}Virtual environment already exists. Skipping...${NC}"
else
    python3 -m venv .venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

# Activate virtual environment
echo -e "\n${YELLOW}Activating virtual environment...${NC}"
source .venv/bin/activate
echo -e "${GREEN}✓ Virtual environment activated${NC}"

# Upgrade pip
echo -e "\n${YELLOW}Upgrading pip...${NC}"
pip install --upgrade pip setuptools wheel > /dev/null 2>&1
echo -e "${GREEN}✓ Pip upgraded${NC}"

# Install dependencies
echo -e "\n${YELLOW}Installing dependencies...${NC}"
echo "This may take a few minutes (especially torch and ultralytics)..."

# Core
pip install python-dotenv==1.0.0 > /dev/null 2>&1

# FastAPI & Web
pip install fastapi==0.104.1 uvicorn==0.24.0 pydantic==2.5.0 pydantic-settings==2.1.0 > /dev/null 2>&1

# Database
pip install sqlalchemy==2.0.23 psycopg2-binary==2.9.9 alembic==1.13.0 > /dev/null 2>&1

# PyTorch (CPU - important!)
echo "  → Installing PyTorch (CPU)..."
pip install torch==2.1.1 torchvision==0.16.1 > /dev/null 2>&1

# Computer Vision
echo "  → Installing YOLO and OpenCV..."
pip install ultralytics==8.0.206 opencv-python-headless==4.8.1.78 filterpy==1.4.2 > /dev/null 2>&1

# Data Processing
echo "  → Installing data processing libraries..."
pip install pandas==2.1.3 numpy==1.26.2 scipy==1.11.4 scikit-learn==1.3.2 > /dev/null 2>&1

# Streaming
pip install confluent-kafka==2.3.0 > /dev/null 2>&1

# Monitoring
pip install prometheus-client==0.19.0 python-json-logger==2.0.7 > /dev/null 2>&1

# Dashboard
echo "  → Installing Streamlit and visualization..."
pip install streamlit==1.29.0 plotly==5.18.0 altair==5.1.0 > /dev/null 2>&1

# Utilities
pip install python-dateutil==2.8.2 requests==2.31.0 pyyaml==6.0.1 > /dev/null 2>&1

# Testing
pip install pytest==7.4.3 pytest-asyncio==0.21.1 pytest-cov==4.1.0 httpx==0.25.2 > /dev/null 2>&1

# Development
pip install black==23.12.0 flake8==6.1.0 mypy==1.7.1 isort==5.13.2 > /dev/null 2>&1

echo -e "${GREEN}✓ All dependencies installed${NC}"

# Create .env if it doesn't exist
echo -e "\n${YELLOW}Setting up environment variables...${NC}"
if [ -f ".env" ]; then
    echo -e "${YELLOW}.env file already exists. Skipping...${NC}"
else
    cp .env.example .env
    echo -e "${GREEN}✓ .env file created from .env.example${NC}"
fi

# Initialize database
echo -e "\n${YELLOW}Initializing database...${NC}"
python -c "from src.api.database import init_db_sync; init_db_sync()"
echo -e "${GREEN}✓ Database initialized (SQLite)${NC}"

# Verify installation
echo -e "\n${YELLOW}Verifying installation...${NC}"

# Check if key modules can be imported
python -c "import fastapi; print('  ✓ FastAPI')" 2>/dev/null || echo -e "  ${RED}✗ FastAPI${NC}"
python -c "import streamlit; print('  ✓ Streamlit')" 2>/dev/null || echo -e "  ${RED}✗ Streamlit${NC}"
python -c "import sqlalchemy; print('  ✓ SQLAlchemy')" 2>/dev/null || echo -e "  ${RED}✗ SQLAlchemy${NC}"
python -c "import pandas; print('  ✓ Pandas')" 2>/dev/null || echo -e "  ${RED}✗ Pandas${NC}"
python -c "import torch; print('  ✓ PyTorch')" 2>/dev/null || echo -e "  ${RED}✗ PyTorch${NC}"
python -c "import cv2; print('  ✓ OpenCV')" 2>/dev/null || echo -e "  ${RED}✗ OpenCV${NC}"
python -c "import ultralytics; print('  ✓ Ultralytics')" 2>/dev/null || echo -e "  ${RED}✗ Ultralytics${NC}"

echo -e "\n${GREEN}=========================================="
echo "Setup Complete! ✓"
echo "==========================================${NC}"

echo -e "\n${YELLOW}Next steps:${NC}"
echo "1. Start API server (Terminal 1):"
echo -e "   ${GREEN}python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload${NC}"
echo ""
echo "2. Start dashboard (Terminal 2):"
echo -e "   ${GREEN}streamlit run src/dashboard/main.py${NC}"
echo ""
echo "3. Access services:"
echo -e "   API: ${GREEN}http://localhost:8000${NC}"
echo -e "   Docs: ${GREEN}http://localhost:8000/docs${NC}"
echo -e "   Dashboard: ${GREEN}http://localhost:8501${NC}"
echo ""
echo "4. Run tests:"
echo -e "   ${GREEN}pytest tests/ -v${NC}"
echo ""
echo "For more information, see SETUP_LOCAL.md"
