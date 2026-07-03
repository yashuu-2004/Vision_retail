#!/bin/bash
# Run detection pipeline

set -e

echo "Starting detection pipeline..."

mkdir -p ml-models data

# Run pipeline
export MOTION_FALLBACK_ON_EMPTY_YOLO=false
export MIN_TRACK_HITS=2
python -m src.detection.pipeline

echo "Detection pipeline completed. Events: data/events.generated.jsonl"
