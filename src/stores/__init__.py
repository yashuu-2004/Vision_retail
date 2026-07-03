"""
Multi-store registry.

Centralised discovery and validation of all stores under
``data/<store_id>/metadata.json``.  Every component of the platform
(API, dashboard, analytics, detection, training) goes through this
module to enumerate available stores — there is no other place where
the list of stores is hardcoded.

Onboarding a new store requires only:

1. Drop the store's ``metadata.json`` under ``data/<store_id>/``
2. Drop the camera files under ``data/<store_id>/cameras/``
3. Drop the POS data at ``data/<store_id>/pos.csv`` (optional)

No code changes anywhere.  This module will pick it up on the next
``registry.list_stores()`` call.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from ..metadata import MetadataLoadError, StoreMetadata, load_store_metadata


@dataclass
class StoreRecord:
    """A lightweight record describing a known store."""

    store_id: str  # the folder name under data/ (used as URL key)
    canonical_store_id: str  # the metadata's store_id
    store_name: str
    city: Optional[str]
    country: Optional[str]
    cameras: int
    zones: int
    has_cameras_dir: bool
    has_pos: bool
    layout: str  # "WIDTHxHEIGHT"


class StoreRegistry:
    """Enumerates, loads, and validates stores under a data root.

    A ``StoreRegistry`` is intentionally cheap to construct; it does
    not eagerly load metadata.  Use :meth:`get` to lazy-load a single
    store, or :meth:`iter_metadata` to iterate the full set.
    """

    def __init__(self, data_root: Path | str = "data") -> None:
        self.data_root = Path(data_root)

    def list_records(self) -> List[StoreRecord]:
        records: List[StoreRecord] = []
        if not self.data_root.exists():
            return records
        for child in sorted(self.data_root.iterdir()):
            if not child.is_dir():
                continue
            meta_path = child / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                sm = load_store_metadata(self.data_root, child.name, validate=True, check_source_files=False)
            except MetadataLoadError:
                # Skip stores that fail validation — they are reported by
                # the validator elsewhere, not by the discovery layer.
                continue
            cameras_dir = child / "cameras"
            has_cameras = cameras_dir.exists() and any(cameras_dir.iterdir()) if cameras_dir.exists() else False
            has_pos = (child / "pos.csv").exists()
            records.append(StoreRecord(
                store_id=child.name,
                canonical_store_id=sm.store_id,
                store_name=sm.store_name,
                city=sm.city,
                country=sm.country,
                cameras=len(sm.cameras),
                zones=len(sm.zones),
                has_cameras_dir=has_cameras,
                has_pos=has_pos,
                layout=f"{int(sm.layout.width)}x{int(sm.layout.height)}",
            ))
        return records

    def list_store_ids(self) -> List[str]:
        return [r.store_id for r in self.list_records()]

    def __iter__(self) -> Iterator[StoreRecord]:
        return iter(self.list_records())

    def __len__(self) -> int:
        return len(self.list_records())

    def get(self, store_id: str) -> StoreMetadata:
        """Load a single store's metadata.  Raises MetadataLoadError on failure."""
        return load_store_metadata(self.data_root, store_id, validate=True)

    def has(self, store_id: str) -> bool:
        return (self.data_root / store_id / "metadata.json").exists()

    def summary(self) -> Dict[str, object]:
        records = self.list_records()
        return {
            "data_root": str(self.data_root),
            "store_count": len(records),
            "stores": [
                {
                    "store_id": r.store_id,
                    "canonical_store_id": r.canonical_store_id,
                    "store_name": r.store_name,
                    "city": r.city,
                    "country": r.country,
                    "cameras": r.cameras,
                    "zones": r.zones,
                    "layout": r.layout,
                    "has_cameras_dir": r.has_cameras_dir,
                    "has_pos": r.has_pos,
                }
                for r in records
            ],
        }


def default_registry() -> StoreRegistry:
    """Return a registry rooted at the conventional ``data/`` directory."""
    override = os.environ.get("DATA_DIR")
    return StoreRegistry(data_root=override or "data")


__all__ = [
    "StoreRecord",
    "StoreRegistry",
    "default_registry",
]
