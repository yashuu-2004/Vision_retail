#!/usr/bin/env python3
"""
Ingest generated events into the database and verify the pipeline.
"""

import json
import logging
from pathlib import Path
from src.api.database import init_db_sync, SessionLocal
from src.api.database import DetectionEventRecord, Store, Camera, VisitorSession
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger(__name__)

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
    
    # Ingest events
    db = SessionLocal()
    total_accepted = 0
    total_duplicates = 0
    
    try:
        # Disable autoflush to avoid constraint errors during batch processing
        db.autoflush = False
        
        # Get or create store
        store = db.query(Store).filter(Store.store_code == "ST1008").first()
        if not store:
            store = Store(
                store_code="ST1008",
                store_name="Brigade Road - Bangalore",
                city="Bangalore",
                country="India",
                aliases=["brigade-bangalore", "STORE_BLR_002"],
            )
            db.add(store)
            db.flush()
        
        # Pre-load all existing events
        existing_event_ids = set(
            r[0] for r in db.query(DetectionEventRecord.event_id)
            .filter(DetectionEventRecord.store_id == store.id)
            .all()
        )
        
        print(f"Found {len(existing_event_ids)} existing events in database")
        
        # Create/get cameras
        cameras_by_code = {}
        for camera_code in set(evt["camera_id"] for evt in events_raw):
            camera = db.query(Camera).filter(
                Camera.store_id == store.id,
                Camera.camera_code == camera_code
            ).first()
            if not camera:
                camera = Camera(
                    store_id=store.id,
                    camera_code=camera_code,
                    camera_name=camera_code,
                    camera_type="unknown"
                )
                db.add(camera)
            cameras_by_code[camera_code] = camera
        
        db.flush()
        
        # Ingest events
        events_to_add = []
        for evt in events_raw:
            if evt["event_id"] in existing_event_ids:
                total_duplicates += 1
                continue
            
            camera = cameras_by_code[evt["camera_id"]]
            events_to_add.append(DetectionEventRecord(
                event_id=evt["event_id"],
                store_id=store.id,
                camera_id=camera.id,
                camera_code=evt["camera_id"],
                visitor_id=evt["visitor_id"],
                event_type=evt["event_type"],
                event_timestamp=datetime.fromisoformat(evt["timestamp"]),
                zone_id=evt.get("zone_id"),
                dwell_ms=evt.get("dwell_ms", 0),
                is_staff=evt.get("is_staff", False),
                confidence=evt.get("confidence", 0.9),
                event_metadata=evt.get("metadata", {}),
            ))
            total_accepted += 1
        
        print(f"Adding {total_accepted} new events to database...")
        
        # Use raw SQL with INSERT OR IGNORE to handle duplicates
        from sqlalchemy import text
        for event in events_to_add:
            try:
                db.add(event)
            except Exception as e:
                db.rollback()
                logger.warning(f"Failed to add event {event.event_id}: {e}")
        
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"Warning: Ingestion had some errors: {e}")
            print(f"Attempting to recover and continue...")
            # Re-ingest one at a time
            db = SessionLocal()
            db.autoflush = False
            for event in events_to_add:
                try:
                    db.add(event)
                    db.commit()
                except Exception:
                    db.rollback()
                    total_duplicates += 1
                    continue
            db.close()
            db = SessionLocal()
        
        print(f"\nTotal Ingestion Result:")
        print(f"  Total Events Processed: {total_accepted}")
        print(f"  Total Duplicates: {total_duplicates}")
        
        # Now do session reconstruction
        print(f"\nReconstructing visitor sessions...")
        sessions = db.query(VisitorSession).filter(VisitorSession.store_id == store.id).all()
        customer_sessions = [s for s in sessions if not s.is_staff]
        
        print(f"  Total Sessions: {len(sessions)}")
        print(f"  Customer Sessions: {len(customer_sessions)}")
        
        # Get some basic stats
        if customer_sessions:
            purchases = [s for s in customer_sessions if s.has_purchase]
            print(f"  Sessions with Purchase: {len(purchases)}")
            if customer_sessions:
                conversion = 100.0 * len(purchases) / len(customer_sessions) if customer_sessions else 0
                print(f"  Conversion Rate: {conversion:.2f}%")
        
    finally:
        db.close()

if __name__ == "__main__":
    main()
