#!/usr/bin/env python3
"""
Generate every dataset (journeys, queues, purchases, ReID pairs,
conversion) for one store or every store.

Usage:
    python scripts/generate_datasets.py --store all
    python scripts/generate_datasets.py --store brigade_road
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.multi_store import default_analytics  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("generate_datasets")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--store", required=True, help="store_id or 'all'")
    p.add_argument("--data-root", default="data")
    p.add_argument("--events-root", default="datasets/events")
    p.add_argument("--datasets-root", default="datasets")
    p.add_argument("--out", default=None, help="optional path to write a JSON summary")
    args = p.parse_args()

    msa = default_analytics()
    if args.store == "all":
        results = msa.generate_datasets_for_all()
    else:
        results = {args.store: msa.generate_datasets(args.store)}
    summary = {
        "store_count": len(results),
        "stores": results,
    }
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(summary, indent=2, default=str))
        log.info("wrote summary to %s", args.out)
    log.info("done — %d stores processed", len(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
