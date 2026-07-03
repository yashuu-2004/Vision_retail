#!/usr/bin/env python3
"""
Cross-camera visitor re-identification engine.

Problem: Same person visiting CAM_1 then CAM_2 gets VIS_CAM_1_000001 and VIS_CAM_2_000001.
Solution: Match visitors across cameras using temporal + spatial proximity.

Approach:
1. For each visitor in each camera, find when they EXIT
2. Look for similar visitors ENTERING other cameras within time window
3. Use entry/exit patterns + billing queue events to link
4. Create global visitor identity mapping
5. Rebuild all event records with unified visitor IDs
"""

import os

from src.api.database import SessionLocal, Store, Camera, DetectionEventRecord
from collections import defaultdict
from datetime import timedelta
import logging
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CrossCameraReIdentifier:
    def __init__(self, db, store):
        self.db = db
        self.store = store
        self.time_window = timedelta(seconds=30)  # 30 second window for re-entry
        self.global_visitor_map = {}  # per_camera_id -> global_id
        
    def run(self):
        """Execute cross-camera re-identification."""
        logger.info("Starting cross-camera re-identification...")
        
        # Step 1: Get all events for this store, grouped by visitor and camera
        events = self.db.query(DetectionEventRecord).filter(
            DetectionEventRecord.store_id == self.store.id
        ).order_by(DetectionEventRecord.event_timestamp).all()
        
        # Step 2: Build per-camera visitor timelines
        visitor_timelines = self._build_timelines(events)
        logger.info(f"Found {sum(len(v) for v in visitor_timelines.values())} visitors across {len(visitor_timelines)} cameras")
        
        # Step 3: Match visitors across cameras
        matches = self._match_visitors_across_cameras(visitor_timelines, events)
        logger.info(f"Found {len(matches)} cross-camera matches")
        
        # Step 4: Assign global visitor IDs
        global_visitor_id_counter = 1
        for per_camera_id in self.global_visitor_map:
            if per_camera_id not in self.global_visitor_map.values():
                self.global_visitor_map[per_camera_id] = f"GLOBAL_{global_visitor_id_counter:06d}"
                global_visitor_id_counter += 1
        
        # Add unmatched visitors
        all_per_camera_ids = set()
        for camera_visitors in visitor_timelines.values():
            all_per_camera_ids.update(camera_visitors.keys())
        
        for per_camera_id in all_per_camera_ids:
            if per_camera_id not in self.global_visitor_map:
                self.global_visitor_map[per_camera_id] = f"GLOBAL_{global_visitor_id_counter:06d}"
                global_visitor_id_counter += 1
        
        logger.info(f"Created {len(self.global_visitor_map)} global visitor IDs")
        
        return self.global_visitor_map
    
    def _build_timelines(self, events):
        """Build per-camera visitor timelines with entry/exit times."""
        timelines = defaultdict(lambda: defaultdict(list))
        
        for event in events:
            camera_code = event.camera_code
            visitor_id = event.visitor_id
            timelines[camera_code][visitor_id].append({
                'timestamp': event.event_timestamp,
                'event_type': event.event_type,
                'zone_id': event.zone_id,
                'event_id': event.event_id,
            })
        
        return timelines
    
    def _match_visitors_across_cameras(self, timelines, events):
        """Match visitors across cameras using temporal + spatial signals."""
        matches = []
        
        # For each visitor, try to find matches in other cameras
        all_cameras = list(timelines.keys())
        
        for i, camera1 in enumerate(all_cameras):
            for visitor1 in timelines[camera1]:
                events1 = timelines[camera1][visitor1]
                
                # Get visitor1's exit time
                exit_times1 = [e['timestamp'] for e in events1 if e['event_type'] == 'EXIT']
                if not exit_times1:
                    continue
                exit_time1 = max(exit_times1)  # Last exit
                
                # Look for entries in other cameras within time window
                for camera2 in all_cameras[i+1:]:
                    for visitor2 in timelines[camera2]:
                        events2 = timelines[camera2][visitor2]
                        
                        # Get visitor2's entry times
                        entry_times2 = [e['timestamp'] for e in events2 if e['event_type'] == 'ENTRY']
                        if not entry_times2:
                            continue
                        entry_time2 = min(entry_times2)  # First entry
                        
                        # Check temporal proximity
                        time_diff = (entry_time2 - exit_time1).total_seconds()
                        if 0 <= time_diff <= self.time_window.total_seconds():
                            # Possible match - record it
                            match = {
                                'visitor_camera1': f"{camera1}_{visitor1}",
                                'visitor_camera2': f"{camera2}_{visitor2}",
                                'exit_time_camera1': exit_time1,
                                'entry_time_camera2': entry_time2,
                                'time_diff': time_diff,
                                'confidence': 'high' if time_diff < 10 else 'medium',
                            }
                            matches.append(match)
                            
                            # Mark as same global visitor
                            if visitor1 not in self.global_visitor_map:
                                self.global_visitor_map[visitor1] = f"MATCHED_{camera1}_{visitor1}"
                            if visitor2 not in self.global_visitor_map:
                                self.global_visitor_map[visitor2] = self.global_visitor_map[visitor1]
        
        logger.info(f"Found {len(matches)} temporal matches")
        if matches:
            logger.info(f"  Avg time between exit→entry: {sum(m['time_diff'] for m in matches)/len(matches):.1f}s")
            high_conf = sum(1 for m in matches if m['confidence'] == 'high')
            logger.info(f"  High confidence matches: {high_conf}/{len(matches)}")
        
        return matches

def main():
    db = SessionLocal()
    store_id = os.getenv("STORE_ID")

    store = db.query(Store).filter(
        Store.store_code == store_id
    ).first()
    
    if not store:
        print("Store not found")
        return
    
    re_id_engine = CrossCameraReIdentifier(db, store)
    global_mapping = re_id_engine.run()
    
    # Show results
    print("\n" + "=" * 70)
    print("CROSS-CAMERA RE-IDENTIFICATION RESULTS")
    print("=" * 70)
    
    # Count by camera
    from collections import Counter
    per_camera_ids = Counter(vid.split('_')[1] for vid in global_mapping.keys())
    print(f"\nVisitors per camera:")
    for cam, count in sorted(per_camera_ids.items()):
        print(f"  CAM_{cam}: {count}")
    
    print(f"\nTotal unique visitors (globally): {len(set(global_mapping.values()))}")
    
    db.close()

if __name__ == "__main__":
    main()
