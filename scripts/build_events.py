#!/usr/bin/env python3
"""
Build canonical events from the detection pipeline output and write
them to the on-disk EventStore.  Run this after a detection pass to
materialise the JSONL stream that the rest of the platform consumes.

Usage:
    python scripts/build_events.py --store brigade_road
    python scripts/build_events.py --store all
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.events import CanonicalEvent, CanonicalEventType, EventStore  # noqa: E402
from src.metadata import load_store_metadata  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("build_events")


def _coerce(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Try ISO 8601 first
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.utcnow()
    return datetime.utcnow()


def ingest_seeded_jsonl(store_id: str, src_path: Path, dest: EventStore) -> int:
    """Convert seeded events.generated.jsonl into the canonical store."""
    if not src_path.exists():
        log.info("no seeded events at %s — skipping", src_path)
        return 0
    n = 0
    with src_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            et_raw = r.get("event_type", "ZONE_ENTER")
            try:
                et = CanonicalEventType(et_raw)
            except ValueError:
                # Map legacy event types to canonical equivalents
                legacy_map = {
                    "BILLING_QUEUE_JOIN": CanonicalEventType.QUEUE_ENTER,
                    "BILLING_QUEUE_ABANDON": CanonicalEventType.QUEUE_ABANDON,
                    "BILLING_SERVICE": CanonicalEventType.CHECKOUT_SERVICE,
                    "QUEUE_JOIN": CanonicalEventType.QUEUE_ENTER,
                    "QUEUE_ABANDON": CanonicalEventType.QUEUE_ABANDON,
                    "QUEUE_CHECKOUT": CanonicalEventType.QUEUE_EXIT,
                    "QUEUE_EXIT": CanonicalEventType.QUEUE_EXIT,
                }
                et = legacy_map.get(et_raw, CanonicalEventType.ZONE_ENTER)
            store_meta = r.get("metadata") or {}
            ev = CanonicalEvent(
                event_id=r["event_id"],
                event_type=et,
                store_id=store_id,
                camera_id=r.get("camera_id"),
                visitor_id=r.get("visitor_id"),
                zone_id=r.get("zone_id"),
                timestamp=_coerce(r.get("timestamp")),
                confidence=float(r.get("confidence", 0.0) or 0.0),
                dwell_ms=r.get("dwell_ms"),
                is_staff=bool(r.get("is_staff", False)),
                bbox=r.get("bbox"),
                track_id=r.get("track_id"),
                frame_number=r.get("frame_number") or r.get("frame"),
                metadata=store_meta,
            )
            dest.append(ev)
            n += 1
    log.info("ingested %d events for %s from %s", n, store_id, src_path)
    return n


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--store", required=True, help="store_id or 'all'")
    p.add_argument("--data-root", default="data")
    p.add_argument("--events-root", default="datasets/events")
    p.add_argument("--src", default=None, help="source JSONL (default: data/<store>/events.jsonl)")
    args = p.parse_args()

    dest = EventStore(root=args.events_root)
    targets = (
        [s.name for s in Path(args.data_root).iterdir() if s.is_dir()]
        if args.store == "all"
        else [args.store]
    )
    total = 0
    for store_id in targets:
        src_path = (
            Path(args.src) if args.src else Path(args.data_root) / store_id / "events.jsonl"
        )
        # Validate the metadata for the store
        try:
            load_store_metadata(args.data_root, store_id, validate=True, check_source_files=False)
        except Exception as e:  # noqa: BLE001
            log.warning("skipping %s — metadata invalid: %s", store_id, e)
            continue
        total += ingest_seeded_jsonl(store_id, src_path, dest)
    log.info("done — %d total events ingested", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
