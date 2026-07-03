# Architecture

> VisionRetail AI — Purplle Tech Challenge 2026

This document is the architectural source of truth.  It explains the
data model, the runtime flow, and the metadata-driven boundaries
that make the platform multi-store-ready.

For the practical "how do I run it" walkthrough see
[QUICKSTART.md](QUICKSTART.md).  For onboarding a new store see
[MULTI_STORE_GUIDE.md](MULTI_STORE_GUIDE.md).

---

## 1. The non-negotiable: metadata is the source of truth

There is exactly one place where store-specific facts live:
`data/<store_id>/metadata.json`.  Every other module — the detection
pipeline, the analytics engine, the API, the dashboard, the dataset
generators, the ReID training pipeline — reads from this file and
from the canonical event stream it produces.  Nothing else.

### 1.1 What the metadata contains

```text
metadata.json
├── schema_version      1.0.0
├── store               identity (id, name, city, country, timezone, aliases)
├── layout              width × height in normalized units + image
├── zones[]             one entry per zone with normalized polygon
│   ├── zone_id
│   ├── zone_name
│   ├── zone_type       ENTRY | EXIT | AISLE | DISPLAY | BRAND |
│   │                   CHECKOUT | QUEUE | STAFF
│   ├── polygon         list of [x, y] in [0, 1]
│   ├── layout_box      optional [x1, y1, x2, y2] in original units
│   └── brands          list of brand codes anchored to the zone
├── cameras[]           one entry per camera
│   ├── camera_id
│   ├── role            ENTRY | EXIT | ZONE | BILLING | QUEUE | STAFF
│   ├── source_file     path under cameras/
│   ├── coverage[]      list of zone_ids
│   ├── zone_polygons   per-zone override polygons (optional)
│   ├── entry_line      { y_normalized, exterior_side } (optional)
│   └── adjacent_cameras[]  list of neighbour camera_ids
└── transition_graph    adjacency map: camera_id -> [camera_id, ...]
```

The `LEGACY_MAP` in `src/metadata/schema.py` normalises legacy
aliases (`FLOOR` → `ZONE`, `SUPPORT` → `STAFF`, `BILLING` →
`CHECKOUT`, `MAKEUP` → `BRAND`, etc.) so older metadata files keep
working without code changes.

### 1.2 How metadata is loaded

```mermaid
sequenceDiagram
    participant App
    participant Loader as MetadataLoader
    participant Schema as StoreMetadata
    participant Validator
    App->>Loader: load_store_metadata(data, "brigade_road")
    Loader->>Loader: resolve_metadata_path() — finds data/<id>/metadata.json
    Loader->>Schema: StoreMetadata.from_dict(payload)
    Schema->>Schema: LEGACY_MAP applied to roles + zone_types
    Loader->>Validator: validate_store_metadata(metadata)
    Validator->>Validator: structural + referential + polygon checks
    Validator-->>Loader: ok
    Loader-->>App: StoreMetadata
```

On failure the loader raises `MetadataLoadError` with a list of
human-readable problems.  The whole stack fails fast — no half-loaded
stores.

---

## 2. System architecture

```mermaid
flowchart TB
    subgraph DATA["data/ — per store"]
        Meta[metadata.json]
        Cams[cameras/*.mp4]
        Pos[pos.csv]
    end

    subgraph SRC["src/ — platform code"]
        direction TB

        subgraph META["Metadata layer"]
            ML[Metadata Loader]
            MS[Metadata Schema]
            MV[Metadata Validator]
        end

        subgraph DETECT["Detection layer"]
            DP[DetectionPipeline]
            CAM[CameraPlan]
            ZP[ZonePolygonResolver]
        end

        subgraph EVENT["Event layer"]
            CE[CanonicalEvent]
            ES[EventStore JSONL]
        end

        subgraph GRAPH["Identity layer"]
            IG[IdentityGraph]
        end

        subgraph DS["Dataset layer"]
            JOUR[Journeys]
            QUE[Queues]
            PUR[Purchases]
            REI[ReID pairs]
            CONV[Conversion records]
        end

        subgraph TRAIN["Training layer"]
            RID[ReID training skeleton]
        end

        subgraph ANA["Analytics layer"]
            CV[Conversion / funnel]
            ZA[Zone analytics]
            QA[Queue analytics]
            RA[Revenue analytics]
            JA[Journey analytics]
            SA[Staff analytics]
        end

        subgraph API["API layer"]
            APIF[FastAPI]
            REG[StoreRegistry]
            MSA[MultiStoreAnalytics]
        end

        subgraph DASH["Dashboard layer"]
            DSH[Streamlit]
        end

        subgraph DB["Persistence layer"]
            SQL[SQLite / Postgres]
            MATV[Materialised views]
        end
    end

    Meta --> ML
    Cams --> DP
    Pos --> APIF
    ML --> MS
    ML --> MV
    ML --> DP
    ML --> ANA
    DP --> CE
    CE --> ES
    ES --> IG
    IG --> DS
    ES --> ANA
    DS --> RID
    ANA --> APIF
    APIF --> SQL
    SQL --> MATV
    MATV --> APIF
    APIF --> DSH
    REG --> APIF
    MSA --> APIF
    APIF --> MSA
```

---

## 3. Data flow

The full lifecycle of one event, from CCTV pixel to dashboard tile.

```mermaid
flowchart LR
    A[CCTV mp4] --> B[DetectionPipeline]
    B --> C{Tracks cross a<br/>zone polygon or<br/>entry line?}
    C -- yes --> D[CanonicalEvent]
    C -- no --> E[Track updated]
    D --> F[EventStore JSONL]
    F --> G[IdentityGraph]
    G --> H[Dataset generators]
    G --> I[Analytics engine]
    I --> J[FastAPI /stores/.../analytics]
    F --> J
    H --> K[ReID training data]
    K --> L[ReID model]
    L --> B
    J --> M[Streamlit dashboard]
    J --> N[Postgres / SQLite]
    N --> O[Materialised views]
    O --> J
```

---

## 4. Detection pipeline

The detection pipeline is fully metadata-driven.  It does not know
what store it is running against, what cameras exist, or what zone a
detection belongs to — every decision is made by looking up
`StoreMetadata` at runtime.

```mermaid
flowchart TB
    A[Open CCTV mp4<br/>cameras/CAM_X.mp4] --> B[Frame loop]
    B --> C{YOLO available?}
    C -- yes --> D[YOLOv8 detector]
    C -- no  --> E[Motion-based fallback]
    D --> F[Detection list]
    E --> F
    F --> G[SimpleTracker<br/>IoU + centroid]
    G --> H[TrackState per camera]
    H --> I{Track crosses<br/>zone polygon?}
    I -- yes --> J[emit ZONE_ENTER / ZONE_EXIT / ZONE_DWELL]
    I -- no  --> K[update track]
    H --> L{camera.role<br/>== ENTRY?}
    L -- yes --> M[entry_line cross check]
    M -- above line --> N[emit ENTRY / REENTRY]
    M -- below line --> K
    H --> O{camera.role<br/>== BILLING?}
    O -- yes --> P[zone_type==CHECKOUT?]
    P -- yes --> Q[update queue depth<br/>+ emit QUEUE_* events]
    P -- no  --> K
    H --> R{camera.role<br/>== STAFF?}
    R -- yes --> S[mark track as staff]
    J --> T[EventStore]
    N --> T
    Q --> T
    S --> T
```

**Key design choices:**

1. **The pipeline holds no state across cameras** — every track is
   `per-camera-local`.  Cross-camera ReID is handled by the matching
   service that runs on top of the canonical event stream, not inside
   the pipeline.

2. **Zone polygons are normalised to [0, 1]** in the metadata.  The
   pipeline projects them onto the actual frame size at runtime, so
   the same metadata works for 1920×1080, 640×480, or any other
   resolution.

3. **The motion-based fallback** means the pipeline is useful on
   machines without a GPU.  It tracks connected components in the
   frame-difference image and runs the same zone / entry / exit
   logic.  This is what makes the demo runnable on a laptop.

---

## 5. Journey pipeline

After the event store is populated, the journey engine reads events
and constructs per-visitor journeys.

```mermaid
flowchart LR
    A[Canonical events] --> B[IdentityGraph]
    B --> C[build_journey_dataset]
    B --> D[build_queue_dataset]
    B --> E[build_purchase_dataset]
    B --> F[build_reid_pairs]
    B --> G[build_conversion_dataset]
    C --> H[datasets/journeys/*.jsonl]
    D --> I[datasets/queues/*.jsonl]
    E --> J[datasets/purchases/*.jsonl]
    F --> K[datasets/reid/*/reid_pairs.jsonl]
    G --> L[datasets/conversion/*/conversion.jsonl]
    K --> M[ReID trainer]
    L --> N[Conversion model]
    M --> O[artifacts/reid/*.pth]
    N --> P[artifacts/conversion/*.pkl]
```

---

## 6. Analytics pipeline

Analytics is *derived* from the event store and the identity graph.
There is no separate analytics database — every answer comes from
re-reading the canonical events.

```mermaid
flowchart TB
    A[EventStore] --> B[IdentityGraph]
    A --> C[Funnel metrics]
    B --> D[Conversion rate]
    B --> E[Revenue / visitor]
    B --> F[Revenue / zone]
    B --> G[Top journeys]
    B --> H[Queue abandonment]
    B --> I[Repeat visitors]
    B --> J[Staff interference]
    B --> K[Cross-camera journeys]
    A --> L[Hourly / daily aggregates]
    C --> M[FastAPI /stores/.../metrics]
    D --> M
    E --> M
    F --> M
    G --> M
    H --> M
    I --> M
    J --> M
    K --> M
    L --> M
    M --> N[Streamlit tiles]
    M --> O[Postgres store_metrics table]
```

The **north-star metric** (`Conversion Rate`) is computed in
`IdentityGraph.conversion_rate()` and surfaces on every analytics
endpoint, every dashboard tile, and every cross-store summary.

---

## 7. Training pipeline

The training pipeline is intentionally a skeleton.  It builds all
the surrounding infrastructure (datasets, model registry, evaluator,
embedding exporter) and triggers the actual training loop only when
PyTorch is available.

```mermaid
flowchart LR
    A[Canonical events] --> B[IdentityGraph]
    B --> C[ReID candidate pairs]
    C --> D[ReID DataLoader]
    D --> E{ReID model<br/>OSNet / FastReID / TorchReID}
    E --> F[Embeddings]
    F --> G[REID Evaluator]
    G --> H[rank-1, rank-5, rank-10, mAP]
    F --> I[export_embeddings]
    I --> J[embeddings.npz]
    B --> K[Conversion records]
    K --> L[Conversion model<br/>logistic / GBDT]
    L --> M[artifacts/conversion/*.pkl]
```

---

## 8. Store digital twin

The "digital twin" is the metadata plus the events that have been
collected against it.  Every analytics query is effectively
"ask the digital twin".

```mermaid
flowchart TB
    subgraph Twin["Store Digital Twin"]
        direction TB
        M[metadata.json]
        E[datasets/events/<store>/...]
        I[IdentityGraph in memory]
        M --> I
        E --> I
    end
    I --> A1[Visitors]
    I --> A2[Conversion rate]
    I --> A3[Revenue per zone]
    I --> A4[Queue depth]
    I --> A5[Top journeys]
    I --> A6[Staff tracks]
    A1 --> API
    A2 --> API
    A3 --> API
    A4 --> API
    A5 --> API
    A6 --> API
```

The `MultiStoreAnalytics` orchestrator (in `src/multi_store/`) is the
single surface that hosts every digital-twin query.  Both the API
and the dashboard go through it.

---

## 9. Customer identity graph

The identity graph is a directed graph of `Visitor` nodes and the
edges that connect them to zones, cameras, purchases, queues, and
other visitors.

```mermaid
flowchart LR
    V((Visitor)) -->|SeenInCamera| C[Camera]
    V -->|VisitedZone| Z[Zone]
    V -->|Queued| Q[Checkout zone]
    V -->|Purchased| T[Transaction]
    V -->|Exited| E[Camera]
    V -->|ReEntered| E2[Camera]
    V -->|StaffInteraction| S[Zone]
    V -->|CrossCameraMatch| V2((Other visitor))
```

Edges are timestamped and carry metadata.  The graph is a
**side-effect of the event stream** — it is not a separate database.
That means losing the graph is non-destructive: rebuilding it from
`EventStore` is O(events) and takes seconds.

---

## 10. Deployment architecture

```mermaid
flowchart TB
    subgraph HOST["Host machine (reviewer's laptop / CI / cloud VM)"]
        subgraph DC["docker compose"]
            API[API container]
            DASH[Dashboard container]
            DET[Detection worker<br/>profile: detection]
            PG[Postgres container]
        end
        V1[./data] ---|ro| API
        V1 ---|ro| DASH
        V2[./datasets] ---|rw| API
        V2 ---|rw| DASH
        V3[./artifacts] ---|rw| API
        V1 ---|ro| DET
        V2 ---|rw| DET
    end
    API --> PG
    DASH --> API
    DET --> API
    PG ---|volume| PGD[(postgres_data)]
```

The detection worker is a separate compose profile — by default only
the API and dashboard come up.  Reviewers who want to run the
detection pipeline invoke `docker compose --profile detection up`.

---

## 11. Failure modes and guarantees

| Failure | Detection | Recovery |
| --- | --- | --- |
| `metadata.json` missing | `MetadataLoadError` at load time | `python3 scripts/validate_metadata.py` |
| `metadata.json` has unknown role | `MetadataLoadError` (strict) or `LEGACY_MAP` (default) | Add the role to the canonical enum |
| Zone polygon malformed | Validator flags it | Edit metadata, re-validate |
| Camera source file missing | Validator flags it | Drop the file, re-validate |
| Camera transition invalid | Pipeline rejects the cross-camera match | Add the edge to `transition_graph` |
| Event has unknown type | Validator falls back to `ZONE_ENTER` | Add the type to `CanonicalEventType` |
| POS row has no visitor | Conversion model skips the row | Impute from nearest ENTRY timestamp (future) |
| Test fails on CI | pytest reports the failure | The tests are independent — fix the unit, not the suite |

The platform is designed so **no failure mode causes silent data
loss**.  Every error path either raises an exception (with a
descriptive message), writes a structured log entry, or appears in
the validation report.

---

## 12. Extension points

The platform has exactly three extension points, all metadata-driven:

1. **Add a new store.**  Drop `metadata.json` + `cameras/` + `pos.csv`
   under `data/<store>/`.  No code changes.
2. **Add a new event type.**  Add a member to `CanonicalEventType`
   and handle it in `IdentityGraph.add_event` and the dataset
   generators.  Old event types keep working.
3. **Add a new model.**  Subclass `ReIDModel` in `src/reid/`, register
   it in `MODEL_REGISTRY`.  Old models keep working.

Everything else is downstream of these three.
