#!/usr/bin/env python3
"""
Ingest generated events into the database - simple approach with raw SQL.
"""

import json
import sqlite3
from pathlib import Path
from src.api.database import init_db_sync, SessionLocal
from src.api.database import Store, Camera
from datetime import datetime
import uuid

DB_PATH = Path("vision_retail.db")

def main():
    # Initialize database
    init_db_sync()
    
    # Load events
    events_path = Path("data/events.generated.jsonl")
    if not events_path.exists():
        print(f"ERROR: Events file not found at {events_path}")
        return
    
    events_raw = []
    with open(events_path, "r") as f:
        for line in f:
            if line.strip():
                events_raw.append(json.loads(line))
    
    print(f"Loaded {len(events_raw)} events from {events_path}")
    
    # Use SQLAlchemy to create store and cameras
    db = SessionLocal()
    store = Store(
        store_code="ST1008",
        store_name="Brigade Road - Bangalore",
        city="Bangalore",
        country="India",
        aliases=["brigade-bangalore", "STORE_BLR_002"],
    )
    db.add(store)
    db.commit()
    store_id = store.id
    print(f"Created store: {store_id}")
    
    # Create cameras
    cameras_by_code = {}
    for camera_code in sorted(set(evt["camera_id"] for evt in events_raw)):
        camera = Camera(
            store_id=store_id,
            camera_code=camera_code,
            camera_name=camera_code,
            camera_type="unknown"
        )
        db.add(camera)
        db.commit()
        cameras_by_code[camera_code] = camera.id
    
    print(f"Created {len(cameras_by_code)} cameras")
    db.close()
    
    # Now use raw SQL to insert events with ON CONFLICT IGNORE
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    total_accepted = 0
    total_duplicates = 0
    
    for evt in events_raw:
        try:
            cursor.execute("""
                INSERT INTO detection_events (
                    id, event_id, store_id, camera_id, camera_code, 
                    visitor_id, event_type, event_timestamp, zone_id, 
                    dwell_ms, is_staff, confidence, metadata, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()),  # id
                evt["event_id"],  # event_id
                store_id,  # store_id
                cameras_by_code[evt["camera_id"]],  # camera_id
                evt["camera_id"],  # camera_code
                evt["visitor_id"],  # visitor_id
                evt["event_type"],  # event_type
                evt["timestamp"],  # event_timestamp
                evt.get("zone_id"),  # zone_id
                evt.get("dwell_ms", 0),  # dwell_ms
                int(evt.get("is_staff", False)),  # is_staff
                evt.get("confidence", 0.9),  # confidence
                json.dumps(evt.get("metadata", {})),  # metadata
                datetime.now().isoformat(),  # ingested_at
            ))
            total_accepted += 1
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                total_duplicates += 1
            else:
                raise
    
    conn.commit()
    conn.close()
    
    print(f"\nTotal Ingestion Result:")
    print(f"  Total Events Inserted: {total_accepted}")
    print(f"  Total Duplicates Skipped: {total_duplicates}")
    
    # Verify
    db = SessionLocal()
    from src.api.database import DetectionEventRecord
    store = db.query(Store).filter(Store.store_code == "ST1008").first()
    if store:
        events_count = db.query(DetectionEventRecord).filter(DetectionEventRecord.store_id == store.id).count()
        print(f"\nVerification:")
        print(f"  Events in database: {events_count}")
    db.close()

if __name__ == "__main__":
    main()
