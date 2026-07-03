"""
PROMPT: Extend API test coverage by exercising every event_type branch in
_upsert_session (ENTRY, EXIT, REENTRY, ZONE_ENTER, ZONE_DWELL, ZONE_EXIT,
BILLING_QUEUE_JOIN, BILLING_QUEUE_ABANDON), all heatmap metric variants, the
journeys/predictions/queue-analytics endpoints, and the 404 fallback paths for
funnel and heatmap endpoints.
CHANGES MADE: Added dwell_ms non-zero payload to exercise total_dwell_ms
accumulation, and queue_depth metadata to cover max_queue_depth logic.
"""

import pytest
import pytest_asyncio
import uuid
from httpx import AsyncClient, ASGITransport

from src.api.main import app

STORE = "STORE_BLR_002"


@pytest_asyncio.fixture(scope="function")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _make_event(event_type: str, visitor_id: str = None,
                zone_id: str = "FLOOR_CENTER", dwell_ms: int = None,
                is_staff: bool = False, metadata: dict = None):
    """Create a unique ingest event payload — UUID event_id prevents duplicates across runs."""
    return {
        "event_id": str(uuid.uuid4()),
        "visitor_id": visitor_id or f"VIS_EXTRA_{uuid.uuid4().hex[:8]}",
        "event_type": event_type,
        "camera_id": "CAM-1",
        "store_id": STORE,
        "timestamp": "2026-04-10T20:20:30.000000",
        "zone_id": zone_id,
        "dwell_ms": dwell_ms,
        "confidence": 0.85,
        "is_staff": is_staff,
        "metadata": metadata or {},
    }


# ---------------------------------------------------------------------------
# All event types — exercises every _upsert_session branch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_entry_event(client):
    payload = {"events": [_make_event("ENTRY", zone_id="ENTRY")]}
    resp = await client.post("/events/ingest", json=payload)
    assert resp.status_code == 200
    assert resp.json()["events_accepted"] >= 1


@pytest.mark.asyncio
async def test_ingest_zone_enter_event(client):
    payload = {"events": [_make_event("ZONE_ENTER", zone_id="FLOOR_CENTER")]}
    resp = await client.post("/events/ingest", json=payload)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ingest_zone_dwell_event_with_dwell_ms(client):
    payload = {"events": [_make_event("ZONE_DWELL", zone_id="FLOOR_CENTER", dwell_ms=45000)]}
    resp = await client.post("/events/ingest", json=payload)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ingest_zone_exit_event(client):
    payload = {"events": [_make_event("ZONE_EXIT", zone_id="FLOOR_CENTER")]}
    resp = await client.post("/events/ingest", json=payload)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ingest_billing_queue_join_with_depth(client):
    payload = {"events": [_make_event(
        "BILLING_QUEUE_JOIN", visitor_id="VIS_EXTRA_002", zone_id="BILLING",
        metadata={"queue_depth": 5}
    )]}
    resp = await client.post("/events/ingest", json=payload)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ingest_billing_queue_abandon(client):
    payload = {"events": [_make_event(
        "BILLING_QUEUE_ABANDON", visitor_id="VIS_EXTRA_002", zone_id="BILLING"
    )]}
    resp = await client.post("/events/ingest", json=payload)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ingest_reentry_event(client):
    payload = {"events": [_make_event("REENTRY", zone_id="ENTRY")]}
    resp = await client.post("/events/ingest", json=payload)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ingest_exit_event(client):
    payload = {"events": [_make_event("EXIT", zone_id="ENTRY")]}
    resp = await client.post("/events/ingest", json=payload)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ingest_staff_event(client):
    payload = {"events": [_make_event("ENTRY", visitor_id="VIS_STAFF_001",
                                      zone_id="ENTRY", is_staff=True)]}
    resp = await client.post("/events/ingest", json=payload)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ingest_full_session_sequence(client):
    """Ingest a complete visitor session to exercise journey path building."""
    visitor = f"VIS_SESSION_{uuid.uuid4().hex[:8]}"
    sequence = [
        _make_event("ENTRY", visitor_id=visitor, zone_id="ENTRY"),
        _make_event("ZONE_ENTER", visitor_id=visitor, zone_id="FLOOR_CENTER"),
        _make_event("ZONE_DWELL", visitor_id=visitor, zone_id="FLOOR_CENTER", dwell_ms=60000),
        _make_event("BILLING_QUEUE_JOIN", visitor_id=visitor, zone_id="BILLING",
                    metadata={"queue_depth": 3}),
        _make_event("EXIT", visitor_id=visitor, zone_id="ENTRY"),
    ]
    payload = {"events": sequence}
    resp = await client.post("/events/ingest", json=payload)
    assert resp.status_code == 200
    assert resp.json()["events_accepted"] == 5


# ---------------------------------------------------------------------------
# Heatmap metric variants (covers metric routing branches)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_heatmap_dwell_time_metric(client):
    resp = await client.get(f"/stores/{STORE}/heatmap", params={"metric": "dwell_time"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_heatmap_conversion_rate_metric(client):
    resp = await client.get(f"/stores/{STORE}/heatmap", params={"metric": "conversion_rate"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Funnel / heatmap 404 paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_funnel_unknown_store_returns_404(client):
    resp = await client.get("/stores/DOES_NOT_EXIST_XYZ/funnel")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_heatmap_unknown_store_returns_404(client):
    resp = await client.get("/stores/DOES_NOT_EXIST_XYZ/heatmap")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Journeys, predictions, queue-analytics endpoints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_journeys_endpoint_returns_200(client):
    resp = await client.get(f"/stores/{STORE}/journeys")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_predictions_endpoint_returns_200(client):
    resp = await client.get(f"/stores/{STORE}/predictions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_queue_analytics_endpoint_returns_200(client):
    resp = await client.get(f"/stores/{STORE}/queue-analytics")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_opportunities_endpoint_returns_200(client):
    resp = await client.get(f"/stores/{STORE}/opportunities")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_journeys_with_min_visitors_param(client):
    resp = await client.get(f"/stores/{STORE}/journeys", params={"min_visitors": 2, "limit": 5})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_anomalies_severity_critical_filter(client):
    resp = await client.get(f"/stores/{STORE}/anomalies", params={"severity": "critical"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_anomalies_resolved_true(client):
    resp = await client.get(f"/stores/{STORE}/anomalies", params={"resolved": True})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# seed_events_from_jsonl — use a fresh in-memory SQLite DB to avoid shared state
# ---------------------------------------------------------------------------

def _make_isolated_service(tmp_path, monkeypatch, write_jsonl=True):
    """Return a StoreIntelligenceService backed by a fresh in-memory SQLite DB."""
    import json
    import sqlalchemy as _sa
    from sqlalchemy.orm import sessionmaker as _sm
    import src.api.database as db_mod
    import src.api.service as svc_mod

    # Fresh in-memory engine
    test_engine = _sa.create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    TestSession = _sm(autocommit=False, autoflush=False, bind=test_engine, future=True)
    db_mod.Base.metadata.create_all(bind=test_engine)

    # Patch BOTH database module AND service module references
    monkeypatch.setattr(db_mod, "engine", test_engine)
    monkeypatch.setattr(db_mod, "SessionLocal", TestSession)
    monkeypatch.setattr(svc_mod, "SessionLocal", TestSession)

    if write_jsonl:
        # Write a 2-event JSONL file (one valid, one with missing event_id)
        jsonl = tmp_path / "events.generated.jsonl"
        rows = [
            {
                "event_id": f"SEED_{uuid.uuid4().hex}",
                "store_id": "ST1008",
                "camera_id": "CAM_1",
                "visitor_id": f"VIS_S_{uuid.uuid4().hex[:8]}",
                "event_type": "ENTRY",
                "timestamp": "2026-04-10T20:20:01.000000",
                "confidence": 0.9,
                "zone_id": "ENTRY",
                "dwell_ms": 0,
                "is_staff": False,
                "metadata": {},
            },
            {
                # No event_id — exercises auto-generation path
                "store_id": "ST1008",
                "camera_id": "CAM_2",
                "visitor_id": f"VIS_S_{uuid.uuid4().hex[:8]}",
                "event_type": "ZONE_ENTER",
                "timestamp": "2026-04-10T20:20:05.000000",
                "confidence": 0.7,
                "zone_id": "FLOOR_CENTER",
                "dwell_ms": 1500,
                "is_staff": False,
                "metadata": {"track_id": 99},
            },
        ]
        with jsonl.open("w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
            f.write("\n")           # blank line — exercises skip
            f.write("not-json\n")   # invalid JSON — exercises skip
        monkeypatch.setattr(svc_mod, "DATA_DIR", tmp_path)
    else:
        # No file → missing path
        monkeypatch.setattr(svc_mod, "DATA_DIR", tmp_path)

    from src.api.service import StoreIntelligenceService
    return StoreIntelligenceService()


def test_seed_events_missing_file(tmp_path, monkeypatch):
    """Returns 0 and logs warning when JSONL file is missing."""
    service = _make_isolated_service(tmp_path, monkeypatch, write_jsonl=False)
    result = service.seed_events_from_jsonl()
    assert result == 0


def test_seed_events_inserts_events(tmp_path, monkeypatch):
    """Inserts events from JSONL when DB is empty; second call is a no-op."""
    service = _make_isolated_service(tmp_path, monkeypatch, write_jsonl=True)
    first = service.seed_events_from_jsonl()
    assert first == 2  # 2 valid event rows in the JSONL
    second = service.seed_events_from_jsonl()
    assert second == 0  # skipped — events already present
