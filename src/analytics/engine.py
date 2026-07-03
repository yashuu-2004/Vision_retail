"""
Analytics Engine - Core metrics computation
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class AnalyticsEngine:
    """Computes analytics metrics"""
    
    def __init__(self):
        logger.info("Initializing Analytics Engine...")
    
    def compute_conversion_funnel(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute conversion funnel metrics"""
        return {
            "entry": len([e for e in events if e.get("event_type") == "ENTRY"]),
            "zone_visit": len([e for e in events if e.get("event_type") == "ZONE_ENTER"]),
            "queue": len([e for e in events if e.get("event_type") == "BILLING_QUEUE_JOIN"]),
            "purchase": len([e for e in events if e.get("event_type") == "PURCHASE"])
        }
    
    def detect_anomalies(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect anomalies in metrics"""
        anomalies = []
        
        # Check for queue spike
        if metrics.get("queue_depth", 0) > 10:
            anomalies.append({
                "type": "QUEUE_SPIKE",
                "severity": "high",
                "message": "Queue depth exceeds threshold"
            })
        
        return anomalies
    
    def compute_purchase_probability(self, visitor_data: Dict[str, Any]) -> float:
        """Compute purchase probability score"""
        score = 0.5  # Base score
        
        # Factors
        if visitor_data.get("zone_visit_count", 0) > 2:
            score += 0.1
        
        if visitor_data.get("dwell_time_ms", 0) > 300000:  # 5 minutes
            score += 0.15
        
        if visitor_data.get("queue_join", False):
            score += 0.2
        
        return min(score, 0.95)
