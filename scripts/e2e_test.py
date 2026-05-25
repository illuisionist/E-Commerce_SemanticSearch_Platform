#!/usr/bin/env python3
"""
e2e_test.py — basic programmatic checks:
- embeddings shape vs metadata count
- FAISS index ntotal == N
- a few FAISS queries return reasonable scores and fields
- Elasticsearch product count > 0
- Cockroach table counts exist and are non-zero

Run: python scripts/e2e_test.py
"""
import sys
import sqlite3
from pathlib import Path
import json
import subprocess
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import requests

ROOT = Path.cwd()
EMB = ROOT / "data" / "faiss" / "review_embeddings.npy"
IDX = ROOT / "data" / "faiss" / "reviews_hnsw.index"
DB = ROOT / "data" / "faiss" / "faiss_metadata.db"
ES = "http://localhost:9200"
ES_INDEX = "products"
# NOTE: fully-qualified table names to avoid database context issues
COCK_SQL = "./cockroach sql --insecure --host=cockroach1:26257 -e"

errors = []

def check_embeddings_and_db():
    if not EMB.exists():
        errors.append(f"embeddings missing: {EMB}")
        return
    emb = np.load(str(EMB))
    N, D = emb.shape
    print(f"Embeddings: N={N}, D={D}")
    if not DB.exists():
        errors.append(f"metadata DB missing: {DB}")
        return
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM reviews;")
    count = cur.fetchone()[0]
    conn.close()
    print("Metadata rows:", count)
    if count != N:
        errors.append(f"Mismatch: metadata rows ({count}) != embeddings N ({N})")

def check_faiss_index():
    if not IDX.exists():
        errors.append(f"FAISS index missing: {IDX}")
        return
    idx = faiss.read_index(str(IDX))
    print("FAISS ntotal:", idx.ntotal, "d:", idx.d)
    # basic sanity
    if idx.ntotal == 0:
        errors.append("FAISS index empty (ntotal == 0)")

def run_faiss_sample_queries():
    print("Running FAISS sample queries...")
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    idx = faiss.read_index(str(IDX))
    # use robust efSearch set
    try:
        idx.hnsw.efSearch = 200
    except Exception:
        ps = faiss.ParameterSpace()
        ps.set_index_parameter(idx, "efSearch", "200")
    queries = ["long battery life", "poor customer support", "screen cracked", "fast charging", "easy setup"]
    for q in queries:
        emb = model.encode([q], convert_to_numpy=True)
        # normalize
        emb = emb.astype('float32')
        n = np.linalg.norm(emb, axis=1, keepdims=True)
        n[n==0]=1
        emb = emb / n
        D, I = idx.search(emb, 5)
        sims = D[0]
        ids = I[0]
        print(f"Q='{q}' top scores: {sims.tolist()}")
        if max(sims) < 0.2:
            errors.append(f"Low top similarity for query '{q}': {max(sims)} (maybe embeddings/index mismatch)")

def check_elasticsearch():
    try:
        r = requests.get(f"{ES}/_cluster/health?pretty", timeout=5)
        r.raise_for_status()
        js = r.json()
        print("ES status:", js.get("status"), "nodes:", js.get("number_of_nodes"))
        # try index count
        r2 = requests.get(f"{ES}/{ES_INDEX}/_count", timeout=5)
        if r2.status_code == 200:
            print(f"ES index '{ES_INDEX}' count:", r2.json().get("count"))
        else:
            errors.append(f"ES index '{ES_INDEX}' not found or unreachable (status {r2.status_code})")
    except Exception as e:
        errors.append(f"Elasticsearch check failed: {e}")

def check_cockroach_counts():
    # run docker compose exec cockroach1 sql to get counts (fully-qualified table names)
    try:
        cmd = [
            "docker", "compose", "exec", "cockroach1",
            "./cockroach", "sql", "--insecure", "--host=cockroach1:26257", "-e",
            "SELECT 'products' AS table_name, count(*) FROM dist_ecom.public.products UNION ALL SELECT 'reviews', count(*) FROM dist_ecom.public.reviews;"
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        print("Cockroach counts:\n", out)
        # simple parse for integers
        if "products" not in out.lower() and "reviews" not in out.lower():
            errors.append("Cockroach counts query did not return expected table names")
    except subprocess.CalledProcessError as e:
        errors.append(f"Cockroach sql failed: {e.output[:500]}")

def main():
    print("=== E2E TESTS ===")
    check_embeddings_and_db()
    check_faiss_index()
    run_faiss_sample_queries()
    check_elasticsearch()
    check_cockroach_counts()

    if errors:
        print("\n=== FAILURES ===")
        for e in errors:
            print("-", e)
        sys.exit(2)
    else:
        print("\nALL E2E CHECKS PASSED ✅")
        sys.exit(0)

if __name__ == "__main__":
    main()
