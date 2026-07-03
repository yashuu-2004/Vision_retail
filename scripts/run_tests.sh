#!/bin/bash
# Run test suite

set -e

echo "Running test suite..."

# Ensure we're using the current Python environment
python -m pip install -q pytest pytest-cov pytest-asyncio httpx

echo "Python: $(python --version)"
echo "Pytest: $(python -m pytest --version | head -n 1)"
echo "Executable: $(which python)"

# Run fast tests (excludes slow real-video pipeline tests)
# Pass --all to include everything
if [[ "$1" == "--all" ]]; then
    echo "Running ALL tests including slow video pipeline tests..."

    python -m pytest tests/ \
        -v \
        --cov=src \
        --cov-report=html \
        --cov-report=term-missing

else
    echo "Running fast tests (use --all to include slow video pipeline tests)..."

    python -m pytest \
        tests/test_api.py \
        tests/test_pipeline_units.py \
        tests/test_analytics.py \
        tests/test_dashboard.py \
        tests/test_service_extra.py \
        tests/test_cross_camera_reid.py \
        tests/test_pos_attribution.py \
        -v \
        --cov=src \
        --cov-report=html \
        --cov-report=term-missing
fi

echo ""
echo "==========================================================="
echo "Tests completed"
echo "Coverage report: htmlcov/index.html"
echo "==========================================================="