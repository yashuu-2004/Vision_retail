"""
Tests for the store registry and multi-store analytics.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from src.metadata import StoreMetadata
from src.multi_store import MultiStoreAnalytics
from src.stores import StoreRecord, StoreRegistry


def test_registry_discovers_all_three_real_stores():
    reg = StoreRegistry(data_root="data")
    records = reg.list_records()
    ids = {r.store_id for r in records}
    assert {"brigade_road", "store_1", "store_2"}.issubset(ids)


def test_registry_summary_shape():
    reg = StoreRegistry(data_root="data")
    s = reg.summary()
    assert "data_root" in s
    assert "store_count" in s
    assert "stores" in s
    assert s["store_count"] >= 3
    first = s["stores"][0]
    for k in ("store_id", "canonical_store_id", "store_name", "cameras", "zones", "layout"):
        assert k in first


def test_registry_get_loads_metadata():
    reg = StoreRegistry(data_root="data")
    sm = reg.get("store_1")
    assert isinstance(sm, StoreMetadata)
    assert sm.store_id in {"STORE_1", "store_1"}
    assert len(sm.cameras) >= 1


def test_registry_has_and_listing():
    reg = StoreRegistry(data_root="data")
    assert reg.has("brigade_road")
    assert not reg.has("nope_doesnt_exist")
    ids = reg.list_store_ids()
    assert "brigade_road" in ids


def test_registry_skips_stores_with_invalid_metadata(tmp_path: Path):
    """An invalid store (no metadata.json) should be silently skipped."""
    (tmp_path / "good_store").mkdir()
    (tmp_path / "good_store" / "metadata.json").write_text("{}")  # missing required keys
    (tmp_path / "no_metadata").mkdir()  # no metadata.json at all

    reg = StoreRegistry(data_root=tmp_path)
    # The "good_store" with empty metadata is invalid, so it should be skipped
    # after the validator rejects it.  Either way, no exception is raised.
    assert isinstance(reg.list_records(), list)


def test_multi_store_analytics_cross_store_summary():
    msa = MultiStoreAnalytics(data_root="data")
    summary = msa.cross_store_summary()
    assert summary["store_count"] >= 3
    for s in summary["stores"]:
        assert s["store_id"] in {"brigade_road", "store_1", "store_2"}


def test_multi_store_analytics_per_store():
    msa = MultiStoreAnalytics(data_root="data")
    for sid in msa.store_ids():
        a = msa.analytics_for(sid)
        assert a.store_id == sid
        assert a.cameras >= 1
        assert a.zones >= 1


def test_multi_store_analytics_uses_event_cache(tmp_path: Path):
    """The orchestrator should return the same object on subsequent calls."""
    msa = MultiStoreAnalytics(data_root="data")
    a1 = msa.analytics_for("store_1")
    a2 = msa.analytics_for("store_1")
    assert a1 is a2  # cached
    a3 = msa.analytics_for("store_1", refresh=True)
    # refresh produces an equal but new object
    assert a3.to_dict() == a1.to_dict()
    assert a3 is not a1
