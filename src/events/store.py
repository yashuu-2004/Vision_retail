"""
JSONL-based event store.

The detection pipeline writes canonical events to disk in JSONL format
(one event per line).  The store is append-only, deterministic, and
replayable — perfect for dataset generation and offline analytics.

The store intentionally does NOT require a database.  It works in
containerized environments, local dev, and CI without external state.

Layout::

    datasets/events/<store_id>/<YYYY-MM-DD>/<camera_id>.jsonl

Each line is a JSON-serialised :class:`CanonicalEvent` envelope.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, List, Optional

# Imported lazily inside the methods to avoid a circular import with
# ``src.events.__init__``.  The schema is defined in the package __init__.
_CanonicalEvent: Any = None


def _canonical_event_class():
    global _CanonicalEvent
    if _CanonicalEvent is None:
        from . import CanonicalEvent  # local import, breaks the cycle
        _CanonicalEvent = CanonicalEvent
    return _CanonicalEvent


class EventStore:
    """Append-only JSONL event store keyed by (store, date, camera).

    The store is intentionally simple — it is *not* a database.  It is
    used as the canonical output of the detection pipeline and as the
    primary input to dataset generation and the identity graph builder.
    """

    def __init__(self, root: Path | str = "datasets/events") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, store_id: str, timestamp: datetime, camera_id: str) -> Path:
        day = timestamp.strftime("%Y-%m-%d")
        out = self.root / store_id / day
        out.mkdir(parents=True, exist_ok=True)
        return out / f"{camera_id}.jsonl"

    def append(self, event: CanonicalEvent) -> None:
        if not event.camera_id:
            # Events without a camera (e.g. POS-attributed PURCHASE) go to a
            # shared "_system" file so they are still discoverable.
            camera_id = "_system"
        else:
            camera_id = event.camera_id
        path = self._path(event.store_id, event.timestamp, camera_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), default=str) + "\n")

    def append_many(self, events: Iterable[CanonicalEvent]) -> int:
        count = 0
        for ev in events:
            self.append(ev)
            count += 1
        return count

    def iter_events(
        self,
        store_id: str,
        date: Optional[str] = None,
    ) -> Iterator[CanonicalEvent]:
        """Iterate all events for a store (optionally for a single day).

        ``date`` is a ``YYYY-MM-DD`` string.  When omitted, iterates the
        whole tree under ``datasets/events/<store_id>/``.
        """
        base = self.root / store_id
        if not base.exists():
            return
        if date is not None:
            candidates = [base / date]
        else:
            candidates = sorted(p for p in base.iterdir() if p.is_dir())
        for day_dir in candidates:
            if not day_dir.exists():
                continue
            for jsonl in sorted(day_dir.glob("*.jsonl")):
                with jsonl.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        yield _canonical_event_class().model_validate_json(line)

    def list_dates(self, store_id: str) -> List[str]:
        base = self.root / store_id
        if not base.exists():
            return []
        return sorted(p.name for p in base.iterdir() if p.is_dir())

    def count(self, store_id: str) -> int:
        total = 0
        for _ in self.iter_events(store_id):
            total += 1
        return total


__all__ = ["EventStore"]
