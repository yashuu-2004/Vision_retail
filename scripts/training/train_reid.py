#!/usr/bin/env python3
"""
Train the ReID model on the candidate-pair dataset produced by
``scripts/generate_datasets.py``.

This script is the *only* entry point that does ReID training.  It
loads the model from :mod:`src.reid`, builds the pair-sampling
DataLoader, and runs the contrastive training loop.

The training loop runs when PyTorch is available.  When PyTorch is
not available (CI without GPU), the script prints a structured
manifest describing what *would* happen and exits with code 0 so
that smoke tests stay green.

Usage:
    python scripts/training/train_reid.py --pairs datasets/reid/brigade_road/reid_pairs.jsonl
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.reid import TrainingConfig, build_model, train_reid  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("train_reid")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pairs", required=True, help="reid_pairs.jsonl produced by generate_datasets.py")
    p.add_argument("--images-root", default="datasets/reid_images")
    p.add_argument("--model", default="osnet_x0_25")
    p.add_argument("--epochs", type=int, default=60)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--lr", type=float, default=3.5e-4)
    p.add_argument("--out", default="artifacts/reid")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    cfg = TrainingConfig(
        model_name=args.model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        output_dir=Path(args.out),
        seed=args.seed,
    )
    log.info("ReID training config: %s", json.dumps(cfg.__dict__, default=str))
    summary = train_reid(cfg, pairs_jsonl=Path(args.pairs), images_root=Path(args.images_root))
    log.info("training summary: %s", json.dumps(summary, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
