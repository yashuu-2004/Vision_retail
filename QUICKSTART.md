# Quickstart — 5 minutes to a running stack

This is the fastest path from a fresh clone to a working API + dashboard.
For the architectural deep dive see [ARCHITECTURE.md](ARCHITECTURE.md).
For the reviewer-oriented script see [REVIEWER_GUIDE.md](REVIEWER_GUIDE.md).

---

## 0. Prerequisites

| Tool | Version |
| --- | --- |
| Python | 3.10+ |
| pip | latest |
| Docker Desktop | 24+ (only for the docker path) |
| curl | any |

No GPU is required to run the platform end-to-end — the detection
pipeline includes a motion-based fallback and the ReID module has a
deterministic stub.

---

## 1. Local dev (no docker, ~2 minutes)

```bash
# 1.1 — install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 1.2 — validate all three stores
python3 scripts/validate_metadata.py
# expected:
#   [ok]   brigade_road — store_id=ST1008, 5 cameras, 23 zones, ...
#   [ok]   store_1      — store_id=STORE_1, 4 cameras, 4 zones, ...
#   [ok]   store_2      — store_id=STORE_2, 4 cameras, 4 zones, ...
#   validated 3 stores, 0 failed

# 1.3 — run the API
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
# in another terminal:

# 1.4 — list stores
curl http://localhost:8000/stores
# {"store_count": 3, "stores": [...]}

# 1.5 — run the dashboard
streamlit run src/dashboard/main.py
```

---

## 2. Docker path (reviewer path, ~3 minutes)

```bash
./scripts/start.sh
# 1. validates metadata
# 2. builds images
# 3. brings up api, dashboard, postgres
# 4. waits for /health to be green

./scripts/smoke_test.sh
# 1. /health
# 2. /stores
# 3. /stores/store_1/analytics
# 4. /stores/cross/summary
# 5. dashboard /_stcore/health
```

Then open:

- API:     http://localhost:8000/docs
- Dashboard: http://localhost:8501

To stop:

```bash
docker compose down
```

---

## 3. Run the tests

```bash
# 3.1 — fast suite (skips the integration tests that need a GPU)
pytest tests/ -q --ignore=tests/test_integration.py
# 182 passed, 1 skipped in ~30s

# 3.2 — full suite (requires pytorch + heavy deps)
pytest tests/ -q
```

Coverage report is written to `htmlcov/index.html`.

---

## 4. Generate datasets

Once events exist in `datasets/events/`, you can derive every other
dataset in one command:

```bash
# 4.1 — for one store
python3 scripts/generate_datasets.py --store brigade_road

# 4.2 — for every store
python3 scripts/generate_datasets.py --store all --out datasets/_summary.json
```

Outputs:

- `datasets/journeys/<store>/journeys.jsonl`
- `datasets/queues/<store>/queues.jsonl`
- `datasets/purchases/<store>/purchases.jsonl`
- `datasets/reid/<store>/reid_pairs.jsonl`
- `datasets/conversion/<store>/conversion.jsonl`

---

## 5. Re-train ReID (skeleton, no GPU needed)

```bash
python3 scripts/training/train_reid.py \
  --pairs datasets/reid/brigade_road/reid_pairs.jsonl \
  --images-root datasets/reid_images \
  --model osnet_x0_25 \
  --epochs 60
```

When PyTorch is available the script runs the contrastive loop and
saves checkpoints to `artifacts/reid/`.  When PyTorch is missing the
script writes a structured manifest describing what *would* happen
and exits with code 0 — so it is safe to wire into CI.

---

## 6. The two-second mental model

```
metadata.json     -- the digital twin, source of truth
       |
       v
Detection         -- produces canonical events
       |
       v
EventStore        -- JSONL on disk, append-only, replayable
       |
       v
IdentityGraph     -- visitor x zone x camera x purchase
       |
       v
Datasets          -- journeys, queues, purchases, reid, conversion
       |
       v
ReID / Conversion -- trained on the datasets, fed back into the pipeline
```

Every box on that diagram is metadata-driven: no store IDs, no
camera IDs, no zone IDs are hardcoded in business logic.
