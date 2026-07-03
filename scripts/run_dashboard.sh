#!/bin/bash
# Start VisionRetail AI Streamlit Dashboard

set -e

echo "Starting VisionRetail AI Streamlit Dashboard..."
echo "Dashboard will be available at http://localhost:8501"
echo ""
echo "Note: API must be running on http://localhost:8000"
echo "Press Ctrl+C to stop"
echo ""

source .venv/bin/activate 2>/dev/null || true
streamlit run src/dashboard/main.py
