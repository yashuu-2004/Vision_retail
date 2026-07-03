"""
PROMPT: Mock Streamlit, Plotly and other heavy dashboard dependencies at
sys.modules level before importing the dashboard module, then exercise the
data-fetching helper and all display functions to drive coverage without
needing a live Streamlit server.
CHANGES MADE: Used passthrough decorator for st.cache_data and applied
side_effect stubs to requests.get so fetch_api paths (success, HTTP error,
network exception) are exercised independently.
"""

import sys
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Mock all heavy UI dependencies BEFORE the dashboard module is imported.
# This must be done at module level so pytest's import machinery picks it up.
# ---------------------------------------------------------------------------
_mock_st = MagicMock()
_mock_st.cache_data.return_value = lambda func: func   # pass-through decorator
_mock_st.cache_data.side_effect = None                  # reset side_effect

sys.modules.setdefault("streamlit", _mock_st)
sys.modules.setdefault("plotly", MagicMock())
sys.modules.setdefault("plotly.express", MagicMock())
sys.modules.setdefault("plotly.graph_objects", MagicMock())

# Now it is safe to import the dashboard
import src.dashboard.main as dashboard  # noqa: E402


# ---------------------------------------------------------------------------
# fetch_api helper
# ---------------------------------------------------------------------------

class TestFetchApi:
    def test_returns_json_on_200(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"total_visitors": 42}
        with patch("requests.get", return_value=mock_resp):
            result = dashboard.fetch_api("/stores/ST1008/metrics")
        assert result["total_visitors"] == 42

    def test_returns_none_on_non_200(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("requests.get", return_value=mock_resp):
            result = dashboard.fetch_api("/stores/BAD/metrics")
        assert result is None

    def test_returns_none_on_exception(self):
        with patch("requests.get", side_effect=ConnectionError("no route")):
            result = dashboard.fetch_api("/stores/ST1008/metrics")
        assert result is None


# ---------------------------------------------------------------------------
# fetch_metrics / fetch_funnel / fetch_heatmap convenience wrappers
# ---------------------------------------------------------------------------

def test_fetch_metrics_calls_fetch_api():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"total_visitors": 5}
    with patch("requests.get", return_value=mock_resp):
        result = dashboard.fetch_metrics(60)
    assert result == {"total_visitors": 5}


def test_fetch_funnel_calls_fetch_api():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"stages": []}
    with patch("requests.get", return_value=mock_resp):
        result = dashboard.fetch_funnel(60)
    assert result == {"stages": []}


def test_fetch_heatmap_calls_fetch_api():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"zones": []}
    with patch("requests.get", return_value=mock_resp):
        result = dashboard.fetch_heatmap("visitor_count", 60)
    assert result == {"zones": []}


# ---------------------------------------------------------------------------
# main() — exercise with mocked st and API responses
# ---------------------------------------------------------------------------

def _good_api_response(url, params=None, **kwargs):
    """Stub for requests.get that returns a valid API payload for every path."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    if "metrics" in url:
        payload = {
            "total_visitors": 100, "unique_visitors": 80, "conversion_rate": 5.0,
            "total_revenue": "4500.00", "avg_dwell_ms": 60000, "peak_occupancy": 20,
            "purchases": 5, "zones": [],
        }
    elif "funnel" in url:
        payload = {
            "overall_conversion_rate": 5.0,
            "stages": [
                {"stage": "entry", "count": 100, "previous_count": 100, "drop_off_percent": 0},
                {"stage": "zone_visit", "count": 60, "previous_count": 100, "drop_off_percent": 40},
                {"stage": "queue", "count": 30, "previous_count": 60, "drop_off_percent": 50},
                {"stage": "purchase", "count": 5, "previous_count": 30, "drop_off_percent": 83},
            ],
        }
    elif "heatmap" in url:
        payload = {"zones": [{"zone_name": "Billing", "value": 42}]}
    elif "anomalies" in url:
        payload = [{"anomaly_type": "QUEUE_SPIKE", "severity": "CRITICAL",
                    "description": "Queue", "suggested_action": "Help"}]
    elif "journeys" in url:
        payload = [{"journey_path": ["ENTRY", "FLOOR_CENTER"], "occurrence_count": 5,
                    "purchase_count": 1, "conversion_rate": 20.0, "avg_duration_ms": 60000}]
    elif "predictions" in url:
        payload = [{"visitor_id": "VIS_001", "prediction_score": 0.8, "confidence": 0.9,
                    "features_used": ["zone_visit"], "reasoning": "High dwell"}]
    elif "opportunities" in url:
        payload = [{"type": "UPSELL", "zone": "FLOOR_CENTER"}]
    else:
        payload = {"current_depth": 3, "max_depth": 8, "avg_depth": 4.5,
                   "abandonment_count": 1, "avg_wait_time_ms": 90000, "abandonment_rate": 5.0}
    mock_resp.json.return_value = payload
    return mock_resp


def test_main_runs_without_error():
    """Call main() with properly mocked Streamlit primitives and API responses."""
    # Ensure st.tabs returns exactly 7 context-manager-compatible mocks
    _mock_st.tabs.return_value = [MagicMock() for _ in range(7)]
    _mock_st.columns.side_effect = lambda n: [
        MagicMock() for _ in range(n if isinstance(n, int) else len(n))
    ]
    _mock_st.radio.return_value = "visitor_count"
    _mock_st.slider.return_value = 60
    _mock_st.selectbox.return_value = "5s"

    with patch("requests.get", side_effect=_good_api_response):
        # Should complete without raising
        dashboard.main()


# ---------------------------------------------------------------------------
# API_URL and STORE_ID constants
# ---------------------------------------------------------------------------

def test_api_url_has_default():
    assert dashboard.API_URL is not None


def test_store_id_has_default():
    assert dashboard.STORE_ID is not None
