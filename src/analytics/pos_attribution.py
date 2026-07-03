#!/usr/bin/env python3
"""
POS Attribution Engine - Link visitor sessions to actual POS transactions.

This converts raw event-based tracking into business intelligence by:
1. Building visitor sessions from entry→zone visits→exit
2. Matching sessions to POS transactions (within time window + location)
3. Computing real business metrics (conversion, revenue, etc)
"""
import os
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from src.api.database import SessionLocal, Store, DetectionEventRecord
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VisitorSession:
    def __init__(self, visitor_id, entry_time):
        self.visitor_id = visitor_id
        self.entry_time = entry_time
        self.exit_time = None
        self.zones_visited = []
        self.events = []
        self.has_purchase = False
        self.pos_transaction = None
        
    def add_event(self, event):
        self.events.append(event)
        if event.event_type == "ZONE_ENTER":
            self.zones_visited.append(event.zone_id)
        elif event.event_type == "EXIT":
            self.exit_time = event.event_timestamp

class POSAttributionEngine:
    def __init__(self, db, store, pos_file="data/pos_transactions_normalized.csv"):
        self.db = db
        self.store = store
        self.pos_file = pos_file
        self.attribution_window = timedelta(minutes=5)  # Match within 5 minutes
        
    def run(self):
        """Execute POS attribution pipeline."""
        logger.info("Starting POS attribution engine...")
        
        # Step 1: Load POS data
        pos_data = self._load_pos_data()
        logger.info(f"Loaded {len(pos_data)} POS transactions")
        
        # Step 2: Build visitor sessions from events
        sessions = self._build_visitor_sessions()
        logger.info(f"Built {len(sessions)} visitor sessions")
        
        # Step 3: Attribute POS to visitors
        attributed = self._attribute_pos_to_visitors(sessions, pos_data)
        logger.info(f"Attributed {len(attributed)} sessions to POS transactions")
        
        return {
            'sessions': sessions,
            'attributed': attributed,
            'pos_data': pos_data,
        }
    
    def _load_pos_data(self):
        """Load POS transactions from CSV."""
        df = pd.read_csv(self.pos_file)
        # Ensure timestamp is datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    
    def _build_visitor_sessions(self):
        """Reconstruct visitor sessions from events."""
        events = (
            self.db.query(DetectionEventRecord)
            .filter(DetectionEventRecord.store_id == self.store.id)
            .order_by(DetectionEventRecord.event_timestamp)
            .all()
        )

        # Group events by visitor
        visitor_events = {}
        for event in events:
            visitor_events.setdefault(event.visitor_id, []).append(event)

        sessions = []

        for visitor_id, events_list in visitor_events.items():
            entry_events = [e for e in events_list if e.event_type == "ENTRY"]

            if not entry_events:
                continue

            entry_time = min(e.event_timestamp for e in entry_events)

            session = VisitorSession(
                visitor_id=visitor_id,
                entry_time=entry_time,
            )

            # IMPORTANT:
            # Iterate over a sorted copy of events_list.
            # Do NOT iterate over session.events because
            # add_event() appends into session.events.
            for event in sorted(
                events_list,
                key=lambda e: e.event_timestamp,
            ):
                session.add_event(event)

            sessions.append(session)

        return sessions
    
    def _attribute_pos_to_visitors(self, sessions, pos_data):
        """Match sessions to POS transactions."""
        attributed = []
        
        for session in sessions:
            if not session.exit_time:
                # Session still ongoing, use latest event time
                session_time = max(e.event_timestamp for e in session.events)
            else:
                session_time = session.exit_time
            
            # Find POS transactions within attribution window
            time_window_start = session_time - self.attribution_window
            time_window_end = session_time + self.attribution_window
            
            matching_pos = pos_data[
                (pos_data['timestamp'] >= time_window_start) &
                (pos_data['timestamp'] <= time_window_end)
            ]
            
            if len(matching_pos) > 0:
                # Take most likely transaction (closest in time)
                pos_idx = (matching_pos['timestamp'] - session_time).abs().idxmin()
                pos_tx = matching_pos.loc[pos_idx]
                
                session.has_purchase = True
                session.pos_transaction = pos_tx
                attributed.append((session, pos_tx))
        
        return attributed

def main():
    db = SessionLocal()
    store_id = os.getenv("STORE_ID")

    store = db.query(Store).filter(
        Store.store_code == store_id
    ).first()
    
    if not store:
        print("Store not found")
        return
    
    engine = POSAttributionEngine(db, store)
    result = engine.run()
    
    # Display results
    print("\n" + "=" * 70)
    print("POS ATTRIBUTION RESULTS")
    print("=" * 70)
    
    sessions = result['sessions']
    attributed = result['attributed']
    pos_data = result['pos_data']
    
    print(f"\nVisitor Sessions: {len(sessions)}")
    print(f"POS Transactions: {len(pos_data)}")
    print(f"Attributed Conversions: {len(attributed)}")
    
    if len(sessions) > 0:
        conversion_rate = 100.0 * len(attributed) / len(sessions)
        print(f"Conversion Rate: {conversion_rate:.2f}%")
    
    # Analyze zones
    all_zones = set()
    for session in sessions:
        all_zones.update(session.zones_visited)
    print(f"Zones Visited: {len(all_zones)}")
    
    # Analyze revenue
    if len(attributed) > 0:
        total_revenue = pos_data['basket_value_inr'].sum()
        print(f"Total Revenue (matched): ₹{total_revenue:,.0f}")
        print(f"Avg Revenue per Customer: ₹{total_revenue / len(sessions):,.0f}")
    
    # Show sample conversions
    print(f"\nSample Conversions:")
    for session, pos_tx in attributed[:5]:
        print(f"  {session.visitor_id:20s} | Zones: {len(session.zones_visited)} | Revenue: ₹{pos_tx['basket_value_inr']:.0f}")
    
    db.close()

if __name__ == "__main__":
    main()
