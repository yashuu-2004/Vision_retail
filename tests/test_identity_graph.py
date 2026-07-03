"""
Tests for the customer identity graph.
"""

from __future__ import annotations

from datetime import datetime

from src.events import CanonicalEvent, CanonicalEventType
from src.identity_graph import (
    EDGE_CROSS_CAMERA_MATCH,
    EDGE_EXITED,
    EDGE_PURCHASED,
    EDGE_QUEUED,
    EDGE_REENTERED,
    EDGE_SEEN_IN_CAMERA,
    EDGE_VISITED_ZONE,
    IdentityGraph,
)


def _event(
    ev_type: CanonicalEventType,
    *,
    visitor: str,
    camera: str = "CAM_1",
    zone: str | None = None,
    store: str = "ST_TEST",
    ts: datetime | None = None,
    is_staff: bool = False,
    **metadata: object,
) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=f"EVT_{visitor}_{ev_type.value}_{camera}_{zone or 'na'}",
        event_type=ev_type,
        store_id=store,
        camera_id=camera,
        visitor_id=visitor,
        zone_id=zone,
        timestamp=ts or datetime(2026, 4, 10, 12, 0, 0),
        confidence=0.9,
        is_staff=is_staff,
        metadata=metadata,
    )


def test_graph_aggregates_visits_per_visitor():
    g = IdentityGraph("ST_TEST")
    g.add_event(_event(CanonicalEventType.ENTRY, visitor="V1", camera="CAM_1"))
    g.add_event(_event(CanonicalEventType.ZONE_ENTER, visitor="V1", zone="FLOOR_CENTER", camera="CAM_1"))
    g.add_event(_event(CanonicalEventType.ZONE_ENTER, visitor="V1", zone="MAKEUP_UNIT", camera="CAM_1"))
    g.add_event(_event(CanonicalEventType.EXIT, visitor="V1", camera="CAM_1"))

    assert g.total_visitors() == 1
    v = g.visitor("V1")
    assert v is not None
    assert v.zones_visited == {"FLOOR_CENTER", "MAKEUP_UNIT"}
    edge_types = {e.edge_type for e in v.edges}
    assert EDGE_SEEN_IN_CAMERA in edge_types
    assert EDGE_VISITED_ZONE in edge_types
    assert EDGE_EXITED in edge_types


def test_graph_tracks_purchase_and_revenue():
    g = IdentityGraph("ST_TEST")
    g.add_event(_event(CanonicalEventType.ENTRY, visitor="V1"))
    g.add_event(_event(
        CanonicalEventType.PURCHASE, visitor="V1", amount=250.0, transaction_id="TXN1"
    ))
    g.add_event(_event(CanonicalEventType.ENTRY, visitor="V2"))
    g.add_event(_event(
        CanonicalEventType.PURCHASE, visitor="V2", amount=120.0, transaction_id="TXN2"
    ))

    assert g.total_purchases() == 2
    assert g.total_revenue() == 370.0
    assert g.conversion_rate() == 1.0
    assert g.revenue_per_visitor() == 185.0


def test_graph_staff_filtering():
    g = IdentityGraph("ST_TEST")
    g.add_event(_event(CanonicalEventType.ENTRY, visitor="V_STAFF", is_staff=True))
    g.add_event(_event(CanonicalEventType.ENTRY, visitor="V_CUSTOMER"))
    g.add_event(_event(
        CanonicalEventType.PURCHASE, visitor="V_CUSTOMER", amount=100.0
    ))
    assert g.total_visitors() == 2
    assert g.total_staff() == 1
    assert g.non_staff_visitors() == 1
    assert g.conversion_rate() == 1.0  # 1 purchaser / 1 non-staff


def test_graph_revenue_per_zone():
    g = IdentityGraph("ST_TEST")
    g.add_event(_event(CanonicalEventType.ENTRY, visitor="V1"))
    g.add_event(_event(CanonicalEventType.ZONE_ENTER, visitor="V1", zone="BRAND_A"))
    g.add_event(_event(CanonicalEventType.PURCHASE, visitor="V1", amount=200.0))
    g.add_event(_event(CanonicalEventType.ENTRY, visitor="V2"))
    g.add_event(_event(CanonicalEventType.ZONE_ENTER, visitor="V2", zone="BRAND_B"))
    g.add_event(_event(CanonicalEventType.PURCHASE, visitor="V2", amount=300.0))
    rpz = g.revenue_per_zone()
    assert rpz == {"BRAND_A": 200.0, "BRAND_B": 300.0}


def test_graph_visitors_in_zone_and_camera():
    g = IdentityGraph("ST_TEST")
    g.add_event(_event(CanonicalEventType.ENTRY, visitor="V1", camera="CAM_1"))
    g.add_event(_event(CanonicalEventType.ZONE_ENTER, visitor="V1", zone="Z1"))
    g.add_event(_event(CanonicalEventType.ENTRY, visitor="V2", camera="CAM_1"))
    g.add_event(_event(CanonicalEventType.ZONE_ENTER, visitor="V2", zone="Z1"))
    g.add_event(_event(CanonicalEventType.ENTRY, visitor="V3", camera="CAM_2"))
    assert len(g.visitors_in_zone("Z1")) == 2
    assert len(g.visitors_in_camera("CAM_1")) == 2
    assert len(g.visitors_in_camera("CAM_2")) == 1


def test_graph_cross_camera_match_provenance():
    g = IdentityGraph("ST_TEST")
    g.add_event(_event(
        CanonicalEventType.CROSS_CAMERA_MATCH,
        visitor="V1", camera="CAM_1",
        from_visitor_id="V_RAW_42",
    ))
    v = g.visitor("V1")
    assert v is not None
    cross_edges = [e for e in v.edges if e.edge_type == EDGE_CROSS_CAMERA_MATCH]
    assert len(cross_edges) == 1
    assert cross_edges[0].target == "V_RAW_42"


def test_graph_save_and_load(tmp_path):
    g = IdentityGraph("ST_TEST")
    g.add_event(_event(CanonicalEventType.ENTRY, visitor="V1"))
    g.add_event(_event(CanonicalEventType.PURCHASE, visitor="V1", amount=99.0))
    out = tmp_path / "graph.json"
    g.save(out)
    data = out.read_text()
    assert "ST_TEST" in data
    assert "V1" in data
    assert "99.0" in data


def test_graph_reentry_edge():
    g = IdentityGraph("ST_TEST")
    g.add_event(_event(CanonicalEventType.ENTRY, visitor="V1", camera="CAM_1"))
    g.add_event(_event(CanonicalEventType.EXIT, visitor="V1", camera="CAM_1"))
    g.add_event(_event(CanonicalEventType.REENTRY, visitor="V1", camera="CAM_1"))
    v = g.visitor("V1")
    edge_types = [e.edge_type for e in v.edges]
    assert EDGE_REENTERED in edge_types


def test_graph_queue_edge():
    g = IdentityGraph("ST_TEST")
    g.add_event(_event(CanonicalEventType.QUEUE_ENTER, visitor="V1", zone="CHECKOUT"))
    g.add_event(_event(CanonicalEventType.QUEUE_EXIT, visitor="V1", zone="CHECKOUT"))
    v = g.visitor("V1")
    queue_edges = [e for e in v.edges if e.edge_type == EDGE_QUEUED]
    assert len(queue_edges) == 1
