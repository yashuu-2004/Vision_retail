"""
PROMPT: Write unit tests for the analytics engine, cross-camera re-identification
helpers, and the POS attribution VisitorSession model. Cover all three compute
methods, anomaly thresholds, purchase probability scoring, and session-building
edge cases.
CHANGES MADE: Added threshold boundary tests for queue spike (10 vs 11) and
purchase probability capping at 0.95.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.analytics.engine import AnalyticsEngine


# ---------------------------------------------------------------------------
# AnalyticsEngine.compute_conversion_funnel
# ---------------------------------------------------------------------------

class TestComputeConversionFunnel:
    @pytest.fixture
    def engine(self):
        return AnalyticsEngine()

    def test_empty_events_all_zeros(self, engine):
        result = engine.compute_conversion_funnel([])
        assert result["entry"] == 0
        assert result["zone_visit"] == 0
        assert result["queue"] == 0
        assert result["purchase"] == 0

    def test_counts_entry_events(self, engine):
        events = [{"event_type": "ENTRY"}, {"event_type": "ENTRY"}, {"event_type": "EXIT"}]
        result = engine.compute_conversion_funnel(events)
        assert result["entry"] == 2

    def test_counts_zone_enter_events(self, engine):
        events = [
            {"event_type": "ZONE_ENTER"},
            {"event_type": "ZONE_ENTER"},
            {"event_type": "ZONE_DWELL"},
        ]
        result = engine.compute_conversion_funnel(events)
        assert result["zone_visit"] == 2

    def test_counts_billing_queue_join(self, engine):
        events = [{"event_type": "BILLING_QUEUE_JOIN"}] * 3
        result = engine.compute_conversion_funnel(events)
        assert result["queue"] == 3

    def test_counts_purchase_events(self, engine):
        events = [{"event_type": "PURCHASE"}, {"event_type": "PURCHASE"}]
        result = engine.compute_conversion_funnel(events)
        assert result["purchase"] == 2

    def test_mixed_events_correct_counts(self, engine):
        events = [
            {"event_type": "ENTRY"},
            {"event_type": "ZONE_ENTER"},
            {"event_type": "BILLING_QUEUE_JOIN"},
            {"event_type": "PURCHASE"},
            {"event_type": "EXIT"},
        ]
        result = engine.compute_conversion_funnel(events)
        assert result["entry"] == 1
        assert result["zone_visit"] == 1
        assert result["queue"] == 1
        assert result["purchase"] == 1


# ---------------------------------------------------------------------------
# AnalyticsEngine.detect_anomalies
# ---------------------------------------------------------------------------

class TestDetectAnomalies:
    @pytest.fixture
    def engine(self):
        return AnalyticsEngine()

    def test_no_anomalies_when_queue_below_threshold(self, engine):
        result = engine.detect_anomalies({"queue_depth": 5})
        assert result == []

    def test_queue_spike_at_threshold(self, engine):
        result = engine.detect_anomalies({"queue_depth": 10})
        # Threshold is > 10, so 10 should not trigger
        assert result == []

    def test_queue_spike_above_threshold(self, engine):
        result = engine.detect_anomalies({"queue_depth": 11})
        assert len(result) == 1
        assert result[0]["type"] == "QUEUE_SPIKE"

    def test_queue_spike_severity_is_high(self, engine):
        result = engine.detect_anomalies({"queue_depth": 15})
        assert result[0]["severity"] == "high"

    def test_empty_metrics_no_anomaly(self, engine):
        result = engine.detect_anomalies({})
        assert result == []


# ---------------------------------------------------------------------------
# AnalyticsEngine.compute_purchase_probability
# ---------------------------------------------------------------------------

class TestComputePurchaseProbability:
    @pytest.fixture
    def engine(self):
        return AnalyticsEngine()

    def test_base_score_is_0_5(self, engine):
        score = engine.compute_purchase_probability({})
        assert score == 0.5

    def test_zone_visit_count_increases_score(self, engine):
        score = engine.compute_purchase_probability({"zone_visit_count": 3})
        assert score > 0.5

    def test_long_dwell_increases_score(self, engine):
        score = engine.compute_purchase_probability({"dwell_time_ms": 400000})
        assert score > 0.5

    def test_queue_join_increases_score(self, engine):
        score = engine.compute_purchase_probability({"queue_join": True})
        assert score > 0.5

    def test_all_factors_combine(self, engine):
        score = engine.compute_purchase_probability({
            "zone_visit_count": 5,
            "dwell_time_ms": 500000,
            "queue_join": True,
        })
        assert score == pytest.approx(0.95)

    def test_score_never_exceeds_0_95(self, engine):
        score = engine.compute_purchase_probability({
            "zone_visit_count": 100,
            "dwell_time_ms": 9_000_000,
            "queue_join": True,
        })
        assert score <= 0.95

    def test_score_is_between_zero_and_one(self, engine):
        for data in [{}, {"zone_visit_count": 1}, {"dwell_time_ms": 100}, {"queue_join": True}]:
            score = engine.compute_purchase_probability(data)
            assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# POSAttributionEngine.VisitorSession (no DB required)
# ---------------------------------------------------------------------------

class TestVisitorSession:
    def test_initial_state(self):
        from src.analytics.pos_attribution import VisitorSession

        session = VisitorSession("VIS_001", datetime(2026, 4, 10, 20, 20, 0))
        assert session.visitor_id == "VIS_001"
        assert session.entry_time == datetime(2026, 4, 10, 20, 20, 0)
        assert session.exit_time is None
        assert session.zones_visited == []
        assert session.has_purchase is False
        assert session.pos_transaction is None

    def test_add_zone_enter_event(self):
        from src.analytics.pos_attribution import VisitorSession

        session = VisitorSession("VIS_001", datetime(2026, 4, 10, 20, 20, 0))
        event = MagicMock()
        event.event_type = "ZONE_ENTER"
        event.zone_id = "FLOOR_CENTER"
        event.event_timestamp = datetime(2026, 4, 10, 20, 20, 10)
        session.add_event(event)
        assert "FLOOR_CENTER" in session.zones_visited
        assert len(session.events) == 1

    def test_add_exit_event_sets_exit_time(self):
        from src.analytics.pos_attribution import VisitorSession

        session = VisitorSession("VIS_001", datetime(2026, 4, 10, 20, 20, 0))
        event = MagicMock()
        event.event_type = "EXIT"
        event.zone_id = "ENTRY"
        event.event_timestamp = datetime(2026, 4, 10, 20, 22, 0)
        session.add_event(event)
        assert session.exit_time == datetime(2026, 4, 10, 20, 22, 0)

    def test_add_multiple_events(self):
        from src.analytics.pos_attribution import VisitorSession

        session = VisitorSession("VIS_001", datetime(2026, 4, 10, 20, 20, 0))
        for event_type, zone in [("ZONE_ENTER", "Z1"), ("ZONE_ENTER", "Z2"), ("EXIT", "ENTRY")]:
            ev = MagicMock()
            ev.event_type = event_type
            ev.zone_id = zone
            ev.event_timestamp = datetime(2026, 4, 10, 20, 21, 0)
            session.add_event(ev)
        assert len(session.zones_visited) == 2
        assert len(session.events) == 3


# ---------------------------------------------------------------------------
# CrossCameraReIdentifier — unit tests with mock DB
# ---------------------------------------------------------------------------

class TestCrossCameraReIdentifier:
    def _make_mock_db(self, events):
        db = MagicMock()
        query_mock = MagicMock()
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.all.return_value = events
        db.query.return_value = query_mock
        return db

    def _make_store(self):
        store = MagicMock()
        store.id = "store-uuid"
        return store

    def test_init_sets_time_window(self):
        from src.analytics.cross_camera_reid import CrossCameraReIdentifier
        from datetime import timedelta

        db = self._make_mock_db([])
        store = self._make_store()
        reid = CrossCameraReIdentifier(db, store)
        assert reid.time_window == timedelta(seconds=30)
        assert reid.global_visitor_map == {}

    def test_run_with_empty_events(self):
        from src.analytics.cross_camera_reid import CrossCameraReIdentifier

        db = self._make_mock_db([])
        store = self._make_store()
        reid = CrossCameraReIdentifier(db, store)
        # Should not raise even with no events
        reid.run()

    def test_build_timelines_groups_by_camera_and_visitor(self):
        from src.analytics.cross_camera_reid import CrossCameraReIdentifier

        events = []
        for cam, vis in [("CAM_1", "VIS_A"), ("CAM_1", "VIS_A"), ("CAM_2", "VIS_B")]:
            ev = MagicMock()
            ev.camera_code = cam  # _build_timelines uses camera_code
            ev.visitor_id = vis
            ev.event_type = "ZONE_ENTER"
            ev.zone_id = "Z1"
            ev.event_id = f"EVT_{cam}_{vis}"
            ev.event_timestamp = datetime(2026, 4, 10, 20, 20, 0)
            events.append(ev)

        db = self._make_mock_db(events)
        store = self._make_store()
        reid = CrossCameraReIdentifier(db, store)
        timelines = reid._build_timelines(events)
        assert "CAM_1" in timelines
        assert "CAM_2" in timelines
        assert "VIS_A" in timelines["CAM_1"]
        assert "VIS_B" in timelines["CAM_2"]


# ---------------------------------------------------------------------------
# AnalyticsEngine initialization logging
# ---------------------------------------------------------------------------

def test_analytics_engine_initializes():
    engine = AnalyticsEngine()
    assert engine is not None
