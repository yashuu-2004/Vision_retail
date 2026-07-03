#!/usr/bin/env python3
"""
Validate every store's metadata.json and print a one-line status.

Usage:
    python scripts/validate_metadata.py
    python scripts/validate_metadata.py --data-root data
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.metadata import MetadataLoadError, load_store_metadata  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("validate_metadata")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", default="data")
    p.add_argument("--strict", action="store_true", help="fail on unknown enum values")
    args = p.parse_args()

    root = Path(args.data_root)
    if not root.exists():
        log.error("data root %s does not exist", root)
        return 2

    failed = 0
    total = 0
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        meta = child / "metadata.json"
        if not meta.exists():
            log.warning("[skip] %s — no metadata.json", child.name)
            continue
        total += 1
        try:
            sm = load_store_metadata(root, child.name, validate=True, strict=args.strict, check_source_files=False)
            log.info(
                "[ok]   %s — store_id=%s, %d cameras, %d zones, %d transition edges",
                child.name,
                sm.store_id,
                len(sm.cameras),
                len(sm.zones),
                sum(len(v) for v in sm.transition_graph.edges.values()),
            )
        except MetadataLoadError as e:
            failed += 1
            log.error("[fail] %s — %s", child.name, e)

    log.info("validated %d stores, %d failed", total, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
