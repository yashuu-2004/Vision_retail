"""
PROMPT: Write tests for POS attribution covering session reconstruction,
zone tracking, exit handling, POS matching windows, and attribution
results using synthetic visitor activity and mocked transaction data.

CHANGES MADE: Added attribution-window edge cases, visitor session
construction coverage, and purchase flag verification without requiring
real CSV files or database records.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pandas as pd

from src.analytics.pos_attribution import (
    VisitorSession,
    POSAttributionEngine,
)


class FakeEvent:
    def __init__(
        self,
        visitor_id,
        event_type,
        timestamp,
        zone_id=None,
    ):
        self.visitor_id = visitor_id
        self.event_type = event_type
        self.event_timestamp = timestamp
        self.zone_id = zone_id


def test_visitor_session_initial_state():
    now = datetime.utcnow()

    session = VisitorSession("VIS_001", now)

    assert session.visitor_id == "VIS_001"
    assert session.entry_time == now
    assert session.exit_time is None
    assert session.has_purchase is False


def test_visitor_session_add_zone_enter():
    now = datetime.utcnow()

    session = VisitorSession("VIS_001", now)

    session.add_event(
        FakeEvent(
            "VIS_001",
            "ZONE_ENTER",
            now,
            "ZONE_A",
        )
    )

    assert "ZONE_A" in session.zones_visited


def test_visitor_session_exit_sets_exit_time():
    now = datetime.utcnow()

    session = VisitorSession("VIS_001", now)

    session.add_event(
        FakeEvent(
            "VIS_001",
            "EXIT",
            now + timedelta(minutes=5),
        )
    )

    assert session.exit_time is not None


def test_build_visitor_sessions():
    now = datetime.utcnow()

    events = [
        FakeEvent("VIS_1", "ENTRY", now),
        FakeEvent("VIS_1", "ZONE_ENTER", now + timedelta(seconds=5), "A"),
        FakeEvent("VIS_1", "EXIT", now + timedelta(seconds=10)),
    ]

    query = MagicMock()
    query.filter.return_value.order_by.return_value.all.return_value = events

    db = MagicMock()
    db.query.return_value = query

    store = MagicMock()
    store.id = 1

    engine = POSAttributionEngine(db, store)

    sessions = engine._build_visitor_sessions()

    assert len(sessions) == 1
    assert sessions[0].visitor_id == "VIS_1"
    assert sessions[0].exit_time is not None


def test_attribute_pos_to_visitors_success():
    now = datetime.utcnow()

    session = VisitorSession("VIS_1", now)
    session.exit_time = now

    db = MagicMock()
    store = MagicMock()

    engine = POSAttributionEngine(db, store)

    pos_data = pd.DataFrame(
        {
            "timestamp": [now + timedelta(minutes=1)],
            "basket_value_inr": [1200],
        }
    )

    attributed = engine._attribute_pos_to_visitors(
        [session],
        pos_data,
    )

    assert len(attributed) == 1
    assert session.has_purchase is True
    assert session.pos_transaction is not None


def test_attribute_pos_to_visitors_outside_window():
    now = datetime.utcnow()

    session = VisitorSession("VIS_1", now)
    session.exit_time = now

    db = MagicMock()
    store = MagicMock()

    engine = POSAttributionEngine(db, store)

    pos_data = pd.DataFrame(
        {
            "timestamp": [now + timedelta(hours=1)],
            "basket_value_inr": [1200],
        }
    )

    attributed = engine._attribute_pos_to_visitors(
        [session],
        pos_data,
    )

    assert attributed == []


def test_run_executes_pipeline():
    db = MagicMock()
    store = MagicMock()

    engine = POSAttributionEngine(db, store)

    engine._load_pos_data = MagicMock(
        return_value=pd.DataFrame(
            {
                "timestamp": [datetime.utcnow()],
                "basket_value_inr": [1000],
            }
        )
    )

    session = VisitorSession(
        "VIS_1",
        datetime.utcnow(),
    )

    engine._build_visitor_sessions = MagicMock(
        return_value=[session]
    )

    engine._attribute_pos_to_visitors = MagicMock(
        return_value=[]
    )

    result = engine.run()

    assert "sessions" in result
    assert "attributed" in result
    assert "pos_data" in result