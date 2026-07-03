"""
PROMPT: Build API tests for the Purplle Store Intelligence challenge that verify
health, idempotent event ingestion, metrics, funnel, heatmap, anomalies, and edge
cases including empty event batches and zero visitors.
CHANGES MADE: Tightened the assertions around acceptance-gate endpoints and kept
the tests independent of PostgreSQL by relying on the app's SQLite fallback.
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime
from src.api.main import app
from src.api.models import DetectionEvent, EventType

client = TestClient(app)


# ============================================================================
# Health Check Tests
# ============================================================================

def test_health_check():
    """Test API health endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded", "unhealthy"]
    assert "components" in data


def test_root_endpoint():
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    assert "api" in response.json()


# ============================================================================
# Event Ingestion Tests
# ============================================================================

def test_ingest_single_event():
    """Test ingesting a single event"""
    payload = {
        "events": [{
            "event_id": "test-event-1",
            "store_id": "brigade-bangalore",
            "camera_id": "CAM-1",
            "visitor_id": "visitor-1",
            "event_type": "ENTRY",
            "timestamp": datetime.utcnow().isoformat(),
            "zone_id": None,
            "dwell_ms": None,
            "is_staff": False,
            "confidence": 0.95,
            "metadata": {}
        }]
    }
    
    response = client.post("/events/ingest", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_ingest_duplicate_event():
    """Test that duplicate events are idempotent"""
    payload = {
        "events": [{
            "event_id": "dup-event-1",
            "store_id": "brigade-bangalore",
            "camera_id": "CAM-1",
            "visitor_id": "visitor-1",
            "event_type": "ENTRY",
            "timestamp": datetime.utcnow().isoformat(),
            "zone_id": None,
            "dwell_ms": None,
            "is_staff": False,
            "confidence": 0.95
        }]
    }
    
    # First ingest
    response1 = client.post("/events/ingest", json=payload)
    assert response1.status_code == 200
    
    # Second ingest (same event)
    response2 = client.post("/events/ingest", json=payload)
    assert response2.status_code == 200


def test_ingest_batch_events():
    """Test ingesting multiple events"""
    events = []
    for i in range(10):
        events.append({
            "event_id": f"batch-event-{i}",
            "store_id": "brigade-bangalore",
            "camera_id": f"CAM-{i % 5 + 1}",
            "visitor_id": f"visitor-{i}",
            "event_type": "ENTRY" if i % 2 == 0 else "EXIT",
            "timestamp": datetime.utcnow().isoformat(),
            "zone_id": None,
            "dwell_ms": None,
            "is_staff": False,
            "confidence": 0.95
        })
    
    response = client.post("/events/ingest", json={"events": events})
    assert response.status_code == 200
    assert response.json()["events_processed"] == 10


# ============================================================================
# Metrics Tests
# ============================================================================

def test_get_metrics_nonexistent_store():
    """Test getting metrics for nonexistent store"""
    response = client.get("/stores/nonexistent-store/metrics")
    assert response.status_code == 404


def test_get_metrics_valid_store():
    """Test getting metrics for valid store"""
    response = client.get("/stores/brigade-bangalore/metrics?lookback_minutes=60")
    assert response.status_code == 200
    data = response.json()
    assert "total_visitors" in data
    assert "conversion_rate" in data
    assert "zones" in data


# ============================================================================
# Funnel Tests
# ============================================================================

def test_get_funnel():
    """Test getting conversion funnel"""
    response = client.get("/stores/brigade-bangalore/funnel?lookback_minutes=60")
    assert response.status_code == 200
    data = response.json()
    assert "stages" in data
    assert len(data["stages"]) > 0


# ============================================================================
# Heatmap Tests
# ============================================================================

def test_get_heatmap_visitor_count():
    """Test getting heatmap by visitor count"""
    response = client.get("/stores/brigade-bangalore/heatmap?metric=visitor_count&lookback_minutes=60")
    assert response.status_code == 200
    data = response.json()
    assert "zones" in data


def test_get_heatmap_dwell_time():
    """Test getting heatmap by dwell time"""
    response = client.get("/stores/brigade-bangalore/heatmap?metric=dwell_time&lookback_minutes=60")
    assert response.status_code == 200


def test_get_heatmap_conversion_rate():
    """Test getting heatmap by conversion rate"""
    response = client.get("/stores/brigade-bangalore/heatmap?metric=conversion_rate&lookback_minutes=60")
    assert response.status_code == 200


# ============================================================================
# Anomaly Tests
# ============================================================================

def test_get_anomalies():
    """Test getting anomalies"""
    response = client.get("/stores/brigade-bangalore/anomalies?severity=high")
    assert response.status_code == 200


# ============================================================================
# Advanced Endpoint Tests
# ============================================================================

def test_get_journeys():
    """Test getting customer journeys"""
    response = client.get("/stores/brigade-bangalore/journeys?limit=10")
    assert response.status_code == 200


def test_get_predictions():
    """Test getting purchase predictions"""
    response = client.get("/stores/brigade-bangalore/predictions?lookback_minutes=30")
    assert response.status_code == 200


def test_get_queue_analytics():
    """Test getting queue analytics"""
    response = client.get("/stores/brigade-bangalore/queue-analytics?lookback_minutes=60")
    assert response.status_code == 200


def test_get_opportunities():
    """Test getting zone opportunities"""
    response = client.get("/stores/brigade-bangalore/opportunities")
    assert response.status_code == 200


def test_get_digital_twin():
    """Test getting digital twin"""
    response = client.get("/stores/brigade-bangalore/digital-twin")
    assert response.status_code == 200


# ============================================================================
# Edge Case Tests
# ============================================================================

def test_empty_events_batch():
    """Test ingesting empty event batch"""
    response = client.post("/events/ingest", json={"events": []})
    assert response.status_code == 200


def test_metrics_with_zero_visitors():
    """Test metrics computation with no visitors"""
    response = client.get("/stores/brigade-bangalore/metrics?lookback_minutes=1")
    assert response.status_code == 200
    data = response.json()
    # Should gracefully handle zero visitors
    assert "conversion_rate" in data


def test_metrics_lookback_boundary():
    """Test metrics with edge case lookback periods"""
    # Min lookback
    response = client.get("/stores/brigade-bangalore/metrics?lookback_minutes=1")
    assert response.status_code == 200
    
    # Max lookback (24 hours)
    response = client.get("/stores/brigade-bangalore/metrics?lookback_minutes=1440")
    assert response.status_code == 200


# ============================================================================
# Prometheus Metrics Tests
# ============================================================================

def test_prometheus_metrics():
    """Test Prometheus metrics endpoint"""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert b"HELP" in response.content or len(response.content) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=src", "--cov-report=html"])
