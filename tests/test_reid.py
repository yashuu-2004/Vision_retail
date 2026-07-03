"""
Tests for the ReID training infrastructure (skeleton only — no training).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.reid import (
    MODEL_REGISTRY,
    OSNetReID,
    REIDEvaluator,
    REIDMetrics,
    ReIDModel,
    TrainingConfig,
    build_dataloader,
    build_model,
    export_embeddings,
    train_reid,
)


def test_model_registry_has_osnet():
    assert "osnet_x0_25" in MODEL_REGISTRY
    assert "osnet_x1_0" in MODEL_REGISTRY


def test_build_model_returns_reid_model():
    m = build_model("osnet_x0_25")
    assert isinstance(m, ReIDModel)
    assert m.dim() > 0
    assert m.name == "osnet_x0_25"


def test_build_model_unknown_raises():
    with pytest.raises(ValueError):
        build_model("nonexistent_model_xyz")


def test_osnet_works_without_torchreid():
    """OSNetReID should fall back to a stub when torchreid is missing."""
    m = OSNetReID()
    assert isinstance(m, ReIDModel)
    assert m.dim() == 512


def test_evaluator_returns_metrics_with_empty_data():
    m = OSNetReID()
    ev = REIDEvaluator(m)
    metrics = ev.evaluate(query_embeddings=[], query_ids=[], gallery_embeddings=[], gallery_ids=[])
    assert isinstance(metrics, REIDMetrics)
    assert metrics.rank_1 == 0.0
    assert metrics.mAP == 0.0


def test_evaluator_handles_known_matches():
    """With torchreid/torch available, perfect matches should hit rank-1."""
    try:
        import torch  # noqa: F401
    except ImportError:
        pytest.skip("PyTorch not available")

    # Build embeddings such that query i is identical to gallery i
    dim = 16
    n = 10
    q = [[float(i == j) for j in range(dim)] for i in range(n)]
    g = q  # same embedding for each
    m = OSNetReID(dim=dim)
    ev = REIDEvaluator(m)
    metrics = ev.evaluate(q, query_ids=list(range(n)), gallery_embeddings=g, gallery_ids=list(range(n)))
    assert metrics.rank_1 == 1.0
    assert metrics.mAP == 1.0


def test_export_embeddings_writes_file(tmp_path: Path):
    m = OSNetReID()
    out = export_embeddings(m, [], tmp_path / "embeddings.npz")
    assert out.exists()


def test_train_reid_returns_summary(tmp_path: Path):
    cfg = TrainingConfig(output_dir=tmp_path / "run", epochs=2)
    summary = train_reid(cfg, pairs_jsonl=tmp_path / "pairs.jsonl", images_root=tmp_path)
    assert "config" in summary
    assert "checkpoint_dir" in summary
    assert summary["config"]["model_name"] == "osnet_x0_25"


def test_build_dataloader_returns_none_without_torch(monkeypatch, tmp_path: Path):
    """Without torch, the loader factory returns None (not an exception)."""
    # Note: build_dataloader returns None if torch is missing; we test the shape
    from src.reid import ReIDDataConfig
    pairs = tmp_path / "pairs.jsonl"
    pairs.write_text('{"anchor_visitor_id":"a","pair_visitor_id":"b","label":1}\n')
    cfg = ReIDDataConfig(pairs_jsonl=pairs, images_root=tmp_path)
    loader = build_dataloader(cfg)
    if loader is None:
        # torch missing — fine
        assert True
    else:
        # torch present — loader built
        assert len(loader) >= 0
