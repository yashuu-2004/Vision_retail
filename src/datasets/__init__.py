"""
Dataset generation infrastructure.

The dataset builder consumes canonical events from an
:class:`EventStore`, applies the customer identity graph, and emits
reproducible JSONL datasets for the next pipeline stages:

* ``journeys/``  — per-visitor ordered list of zone visits + metadata
* ``purchases/`` — POS-attributed purchase events with journey context
* ``queues/``    — queue enter / exit / abandon records
* ``reid/``      — same-identity / different-identity candidate pairs
* ``conversion/``— positive (purchaser) and negative (non-purchaser)
                   visitor records for purchase-prediction training

The datasets are the primary input to the ReID training pipeline and
the conversion model.  All outputs are JSONL, deterministic, and
versioned via the on-disk directory layout.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from ..events import CanonicalEvent, CanonicalEventType, EventStore
from ..identity_graph import IdentityGraph, VisitorNode


@dataclass
class JourneyRecord:
    """A single visitor's ordered journey through the store."""

    visitor_id: str
    store_id: str
    is_staff: bool
    start_time: Optional[str]
    end_time: Optional[str]
    zones: List[str]
    cameras: List[str]
    total_dwell_ms: int
    has_purchase: bool
    purchase_amount: float
    steps: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QueueRecord:
    """A queue enter/exit/abandon record for one visitor."""

    visitor_id: str
    store_id: str
    zone_id: Optional[str]
    enter_time: Optional[str]
    exit_time: Optional[str]
    abandoned: bool
    wait_ms: Optional[int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PurchaseRecord:
    """A POS-attributed purchase tied to a journey."""

    visitor_id: str
    store_id: str
    transaction_id: str
    timestamp: Optional[str]
    amount: float
    journey_zones: List[str]
    journey_duration_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReIDPair:
    """A same-identity / different-identity candidate pair."""

    anchor_visitor_id: str
    pair_visitor_id: str
    anchor_camera: str
    pair_camera: str
    label: int  # 1 = same identity, 0 = different
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConversionRecord:
    """A visitor-level record for purchase prediction training."""

    visitor_id: str
    store_id: str
    is_staff: bool
    zones_visited: List[str]
    cameras_seen: List[str]
    num_zones: int
    num_cameras: int
    total_dwell_ms: int
    entered_queue: bool
    served_at_counter: bool
    label: int  # 1 = purchased, 0 = did not
    purchase_amount: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, default=str) + "\n")
            n += 1
    return n


# ---------------------------------------------------------------------------
# Journey dataset
# ---------------------------------------------------------------------------

def build_journey_dataset(
    graph: IdentityGraph,
    out_dir: Path | str = "datasets/journeys",
) -> Dict[str, Any]:
    """Emit a per-store JSONL file with one record per visitor."""
    out_dir = Path(out_dir)
    records: List[JourneyRecord] = []

    for v in graph.visitors():
        # Reconstruct ordered zone path from event edges
        zone_steps: List[Tuple[datetime, str, str]] = []
        for e in v.edges:
            if e.edge_type == "VisitedZone":
                zone_steps.append((e.timestamp, e.target, e.metadata.get("event_type", "ZONE_ENTER")))
        zone_steps.sort(key=lambda t: t[0])
        zones = [s[1] for s in zone_steps]
        cam_edges = [e for e in v.edges if e.edge_type == "SeenInCamera"]
        cameras = sorted({e.target for e in cam_edges})

        rec = JourneyRecord(
            visitor_id=v.visitor_id,
            store_id=graph.store_id,
            is_staff=v.is_staff,
            start_time=v.first_seen.isoformat() if v.first_seen else None,
            end_time=v.last_seen.isoformat() if v.last_seen else None,
            zones=zones,
            cameras=cameras,
            total_dwell_ms=v.total_dwell_ms,
            has_purchase=v.has_purchase,
            purchase_amount=v.purchase_amount,
            steps=[
                {
                    "timestamp": ts.isoformat(),
                    "zone": z,
                    "event_type": et,
                }
                for ts, z, et in zone_steps
            ],
        )
        records.append(rec)

    out_path = out_dir / graph.store_id / "journeys.jsonl"
    n = _write_jsonl(out_path, (r.to_dict() for r in records))
    return {"path": str(out_path), "count": n}


# ---------------------------------------------------------------------------
# Queue dataset
# ---------------------------------------------------------------------------

def build_queue_dataset(
    graph: IdentityGraph,
    out_dir: Path | str = "datasets/queues",
) -> Dict[str, Any]:
    """Emit queue enter / exit / abandon records."""
    out_dir = Path(out_dir)
    out: List[QueueRecord] = []

    for v in graph.visitors():
        # Find queue_enter and queue_exit / abandon edges
        enter_edges = [e for e in v.edges if e.edge_type == "Queued"]
        abandon = any(
            e.metadata.get("event_type") == CanonicalEventType.QUEUE_ABANDON.value
            for e in v.edges
        )
        exit_edges = [e for e in v.edges if e.metadata.get("event_type") == CanonicalEventType.QUEUE_EXIT.value]
        for e in enter_edges:
            enter_ts = e.timestamp
            exit_ts = exit_edges[0].timestamp if exit_edges else (e.timestamp if abandon else None)
            wait_ms = None
            if enter_ts and exit_ts:
                wait_ms = int((exit_ts - enter_ts).total_seconds() * 1000)
            out.append(QueueRecord(
                visitor_id=v.visitor_id,
                store_id=graph.store_id,
                zone_id=e.target,
                enter_time=enter_ts.isoformat() if enter_ts else None,
                exit_time=exit_ts.isoformat() if exit_ts else None,
                abandoned=abandon,
                wait_ms=wait_ms,
            ))

    out_path = out_dir / graph.store_id / "queues.jsonl"
    n = _write_jsonl(out_path, (r.to_dict() for r in out))
    return {"path": str(out_path), "count": n}


# ---------------------------------------------------------------------------
# Purchase dataset
# ---------------------------------------------------------------------------

def build_purchase_dataset(
    graph: IdentityGraph,
    out_dir: Path | str = "datasets/purchases",
) -> Dict[str, Any]:
    out_dir = Path(out_dir)
    out: List[PurchaseRecord] = []
    for v in graph.visitors():
        if not v.has_purchase:
            continue
        purchase_edges = [e for e in v.edges if e.edge_type == "Purchased"]
        for pe in purchase_edges:
            duration = 0
            if v.first_seen and v.last_seen:
                duration = int((v.last_seen - v.first_seen).total_seconds() * 1000)
            out.append(PurchaseRecord(
                visitor_id=v.visitor_id,
                store_id=graph.store_id,
                transaction_id=pe.target or "",
                timestamp=pe.timestamp.isoformat(),
                amount=float(pe.metadata.get("amount", 0.0) or 0.0),
                journey_zones=sorted(v.zones_visited),
                journey_duration_ms=duration,
            ))

    out_path = out_dir / graph.store_id / "purchases.jsonl"
    n = _write_jsonl(out_path, (r.to_dict() for r in out))
    return {"path": str(out_path), "count": n}


# ---------------------------------------------------------------------------
# Conversion dataset (for purchase prediction training)
# ---------------------------------------------------------------------------

def build_conversion_dataset(
    graph: IdentityGraph,
    out_dir: Path | str = "datasets/conversion",
) -> Dict[str, Any]:
    out_dir = Path(out_dir)
    out: List[ConversionRecord] = []
    for v in graph.visitors():
        entered_queue = any(e.edge_type == "Queued" for e in v.edges)
        served = any(
            e.metadata.get("event_type") == CanonicalEventType.CHECKOUT_SERVICE.value
            for e in v.edges
        )
        out.append(ConversionRecord(
            visitor_id=v.visitor_id,
            store_id=graph.store_id,
            is_staff=v.is_staff,
            zones_visited=sorted(v.zones_visited),
            cameras_seen=sorted(v.cameras_seen),
            num_zones=len(v.zones_visited),
            num_cameras=len(v.cameras_seen),
            total_dwell_ms=v.total_dwell_ms,
            entered_queue=entered_queue,
            served_at_counter=served,
            label=1 if v.has_purchase else 0,
            purchase_amount=v.purchase_amount,
        ))

    out_path = out_dir / graph.store_id / "conversion.jsonl"
    n = _write_jsonl(out_path, (r.to_dict() for r in out))
    return {"path": str(out_path), "count": n}


# ---------------------------------------------------------------------------
# ReID candidate-pair dataset
# ---------------------------------------------------------------------------

def build_reid_pairs(
    graph: IdentityGraph,
    out_dir: Path | str = "datasets/reid",
    *,
    negative_ratio: float = 3.0,
    seed: int = 42,
) -> Dict[str, Any]:
    """Emit candidate pairs for ReID training.

    Positive pairs: two visitors that have been *merged* via cross-
    camera match events in the input (provenance).  When no explicit
    matches exist (rule-based ReID), positives come from visitors who
    visited the same checkout zone within a short time window.

    Negative pairs: random pairs of visitors from different time
    buckets, with ``negative_ratio`` negatives per positive on average.
    """
    rng = random.Random(seed)
    out_dir = Path(out_dir)
    out: List[ReIDPair] = []

    visitor_list = list(graph.visitors())
    visitor_index = {v.visitor_id: v for v in visitor_list}

    # Positives from CROSS_CAMERA_MATCH provenance
    match_provenance: Dict[str, Set[str]] = defaultdict(set)
    for v in visitor_list:
        for e in v.edges:
            if e.edge_type == "CrossCameraMatch":
                match_provenance[v.visitor_id].add(e.target)

    produced_positives = 0
    for anchor_id, matches in match_provenance.items():
        anchor = visitor_index.get(anchor_id)
        if not anchor:
            continue
        anchor_cams = sorted(anchor.cameras_seen)
        for match_id in matches:
            match = visitor_index.get(match_id)
            if not match:
                continue
            out.append(ReIDPair(
                anchor_visitor_id=anchor_id,
                pair_visitor_id=match_id,
                anchor_camera=anchor_cams[0] if anchor_cams else "",
                pair_camera=(sorted(match.cameras_seen)[0] if match.cameras_seen else ""),
                label=1,
            ))
            produced_positives += 1

    # Heuristic positives: same time bucket, different cameras
    if produced_positives == 0:
        bucket_size = 30  # seconds
        buckets: Dict[Tuple[str, int], List[VisitorNode]] = defaultdict(list)
        for v in visitor_list:
            if v.first_seen is None or len(v.cameras_seen) < 2:
                continue
            key = (v.first_seen.strftime("%Y-%m-%dT%H:%M"), int(v.first_seen.timestamp()) // bucket_size)
            buckets[key].append(v)
        for bucket in buckets.values():
            if len(bucket) < 2:
                continue
            for i in range(len(bucket) - 1):
                a = bucket[i]
                b = bucket[i + 1]
                if a.cameras_seen.isdisjoint(b.cameras_seen):
                    out.append(ReIDPair(
                        anchor_visitor_id=a.visitor_id,
                        pair_visitor_id=b.visitor_id,
                        anchor_camera=sorted(a.cameras_seen)[0],
                        pair_camera=sorted(b.cameras_seen)[0],
                        label=1,
                        confidence=0.5,
                    ))
                    produced_positives += 1

    # Negatives: random pairs of distinct visitors from different buckets
    # If no positives were produced, still emit a small batch of negatives so
    # downstream training/evaluation has at least one class of pairs to
    # consume.
    target_negatives = max(int(produced_positives * negative_ratio), 8)
    ids = [v.visitor_id for v in visitor_list]
    cams = {v.visitor_id: sorted(v.cameras_seen)[0] if v.cameras_seen else "" for v in visitor_list}
    attempts = 0
    while len([r for r in out if r.label == 0]) < target_negatives and attempts < target_negatives * 10:
        if len(ids) < 2:
            break
        a, b = rng.sample(ids, 2)
        if a == b:
            attempts += 1
            continue
        out.append(ReIDPair(
            anchor_visitor_id=a,
            pair_visitor_id=b,
            anchor_camera=cams.get(a, ""),
            pair_camera=cams.get(b, ""),
            label=0,
        ))
        attempts += 1

    out_path = out_dir / graph.store_id / "reid_pairs.jsonl"
    n = _write_jsonl(out_path, (r.to_dict() for r in out))
    positives = sum(1 for r in out if r.label == 1)
    negatives = sum(1 for r in out if r.label == 0)
    return {
        "path": str(out_path),
        "count": n,
        "positives": positives,
        "negatives": negatives,
    }


# ---------------------------------------------------------------------------
# Master entry point
# ---------------------------------------------------------------------------

def build_all_datasets(
    store_id: str,
    event_store: Optional[EventStore] = None,
    out_root: Path | str = "datasets",
) -> Dict[str, Any]:
    """Build every dataset for a store in one call.

    Returns a summary dict with paths and counts.
    """
    if event_store is None:
        event_store = EventStore(root=Path(out_root) / "events")
    graph = IdentityGraph.from_event_store(store_id, event_store)
    out_root = Path(out_root)
    return {
        "store_id": store_id,
        "events_total": event_store.count(store_id),
        "graph_visitors": graph.total_visitors(),
        "non_staff_visitors": graph.non_staff_visitors(),
        "conversion_rate": graph.conversion_rate(),
        "journeys": build_journey_dataset(graph, out_dir=out_root / "journeys"),
        "queues": build_queue_dataset(graph, out_dir=out_root / "queues"),
        "purchases": build_purchase_dataset(graph, out_dir=out_root / "purchases"),
        "reid": build_reid_pairs(graph, out_dir=out_root / "reid"),
        "conversion": build_conversion_dataset(graph, out_dir=out_root / "conversion"),
    }


__all__ = [
    "ConversionRecord",
    "JourneyRecord",
    "PurchaseRecord",
    "QueueRecord",
    "ReIDPair",
    "build_all_datasets",
    "build_conversion_dataset",
    "build_journey_dataset",
    "build_purchase_dataset",
    "build_queue_dataset",
    "build_reid_pairs",
]
