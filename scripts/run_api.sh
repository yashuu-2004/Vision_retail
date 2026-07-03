#!/bin/bash
# Start VisionRetail AI API Server

set -e

echo "Starting VisionRetail AI API Server..."
echo "API will be available at http://localhost:8000"
echo "API Documentation: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop"
echo ""

source .venv/bin/activate 2>/dev/null || true
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
