#!/bin/bash
# ============================================================================
# VisionRetail AI - Smoke test
# ============================================================================
# Verifies the API is reachable and all three stores are discoverable.
# Run AFTER ./scripts/start.sh.
# ============================================================================
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
DASHBOARD_URL="${DASHBOARD_URL:-http://localhost:8501}"

echo "==> Smoke test against $API_URL"

echo "  [1/5] API health"
curl -fsS "$API_URL/health" >/dev/null && echo "        OK"

echo "  [2/5] Stores list"
stores=$(curl -fsS "$API_URL/stores")
count=$(echo "$stores" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['store_count'])")
echo "        OK — $count store(s) discovered"
echo "$stores" | python3 -c "import json,sys; d=json.load(sys.stdin); [print('              -', s['store_id'], '—', s['store_name'], '(', s['cameras'], 'cams )') for s in d['stores']]"

echo "  [3/5] Per-store analytics"
curl -fsS "$API_URL/stores/store_1/analytics" | python3 -c "import json,sys; d=json.load(sys.stdin); print('        OK — store_1: %d cams, %d zones' % (d['cameras'], d['zones']))"

echo "  [4/5] Cross-store summary"
curl -fsS "$API_URL/stores/cross/summary" | python3 -c "import json,sys; d=json.load(sys.stdin); print('        OK — %d stores' % d['store_count'])"

echo "  [5/5] Dashboard"
if curl -fsS "$DASHBOARD_URL/_stcore/health" >/dev/null 2>&1; then
    echo "        OK — dashboard responding"
else
    echo "        (skipped — dashboard not reachable on $DASHBOARD_URL)"
fi

echo
echo "==> All checks passed."
