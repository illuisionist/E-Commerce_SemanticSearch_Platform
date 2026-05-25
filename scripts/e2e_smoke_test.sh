#!/usr/bin/env bash
# e2e_smoke_test.sh
# Quick smoke tests for Dist Ecom v0.3 (Cockroach, Elasticsearch, FAISS, scripts, optional API)
# Run from project root: ./scripts/e2e_smoke_test.sh

set -euo pipefail
ERR=0

echo "=== 0. environment ==="
echo "Project root: $(pwd)"
echo "Python: $(which python || echo 'python not found')"
echo "Docker: $(which docker || echo 'docker not found')"

echo
echo "=== 1. Docker containers (should show cockroach1..3 and elasticsearch) ==="
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' | { sed -n '1,200p'; } || true

# 2. Cockroach: table counts (fully-qualified to dist_ecom.public)
echo
echo "=== 2. Cockroach table counts (products, reviews) ==="
COCK_CONTAINER="cockroach1"
# Use fully-qualified table names to avoid database context mismatch
SQL="SELECT 'products' AS table_name, count(*) FROM dist_ecom.public.products UNION ALL SELECT 'reviews', count(*) FROM dist_ecom.public.reviews;"
if docker ps --format '{{.Names}}' | grep -q "^${COCK_CONTAINER}\$"; then
  docker compose exec ${COCK_CONTAINER} ./cockroach sql --insecure --host=cockroach1:26257 -e "${SQL}" || ERR=1
else
  echo "WARN: ${COCK_CONTAINER} not running; skipping Cockroach SQL checks"; ERR=1
fi

# 3. Elasticsearch health & index count
echo
echo "=== 3. Elasticsearch cluster health & products index count ==="
ES_URL="http://localhost:9200"
if curl -s "${ES_URL}/_cluster/health?pretty" | grep -q '"status"'; then
  curl -s "${ES_URL}/_cluster/health?pretty" || true
  echo
  echo "Indices:"
  curl -s "${ES_URL}/_cat/indices?v&s=index" || true
  # try count for products index (best-effort name: products)
  PROD_INDEX="products"
  if curl -s "${ES_URL}/${PROD_INDEX}/_count" >/dev/null 2>&1; then
    curl -s "${ES_URL}/${PROD_INDEX}/_count?pretty"
  else
    echo "WARN: products index not found at ${ES_URL}/${PROD_INDEX}; check index name in repo"
    ERR=1
  fi
else
  echo "ERROR: Elasticsearch not reachable at ${ES_URL}"
  ERR=1
fi

# 4. FAISS / Embeddings checks (files present and sizes)
echo
echo "=== 4. FAISS artifacts check ==="
EMB="data/faiss/review_embeddings.npy"
IDX="data/faiss/reviews_hnsw.index"
DB="data/faiss/faiss_metadata.db"
if [ -f "${EMB}" ]; then
  echo "Found embeddings: ${EMB} size=$(stat -f%z "${EMB}" 2>/dev/null || stat -c%s "${EMB}")"
else
  echo "ERROR: embeddings file missing: ${EMB}"; ERR=1
fi
if [ -f "${IDX}" ]; then
  echo "Found FAISS index: ${IDX} size=$(stat -f%z "${IDX}" 2>/dev/null || stat -c%s "${IDX}")"
else
  echo "ERROR: FAISS index file missing: ${IDX}"; ERR=1
fi
if [ -f "${DB}" ]; then
  echo "Found metadata DB: ${DB} size=$(stat -f%z "${DB}" 2>/dev/null || stat -c%s "${DB}")"
else
  echo "ERROR: metadata DB missing: ${DB}"; ERR=1
fi

# 5. Quick FAISS semantic query (uses your script)
echo
echo "=== 5. Quick FAISS query (semantic) ==="
if python -c "import importlib, sys; import faiss" 2>/dev/null; then
  if python scripts/query_faiss.py "long battery life" --k 3 --efSearch 200 >/dev/null 2>&1; then
    echo "FAISS query script ran (check results above)."
  else
    echo "ERROR: FAISS query failed (script returned non-zero)"; ERR=1
  fi
else
  echo "WARN: faiss not importable in current environment; skip FAISS runtime query; run 'pip install faiss-cpu sentence-transformers'"; ERR=1
fi

# 6. Optional: Unified API test
echo
echo "=== 6. Optional Unified API test (http://127.0.0.1:8000/search) ==="
API_URL="http://127.0.0.1:8000/search?q=long%20battery%20life"
if curl -s --max-time 5 "${API_URL}" | grep -q '"query"'; then
  echo "API reachable and returned a JSON 'query' field."
else
  echo "INFO: Unified API not reachable at ${API_URL} (run uvicorn app.search_api:app --reload) — this is OK if you didn't start it.";
fi

echo
if [ ${ERR} -eq 0 ]; then
  echo "ALL SMOKE TESTS PASSED ✅"
else
  echo "SOME TESTS FAILED (ERR=${ERR}). See messages above."
fi

exit ${ERR}
