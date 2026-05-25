#!/usr/bin/env python3
"""
Query FAISS index and return top-k semantic results with metadata from sqlite.
Usage:
python scripts/query_faiss.py "does this product have a long battery life?" --k 5
"""
import argparse
from pathlib import Path
import numpy as np
import sqlite3
from sentence_transformers import SentenceTransformer
import faiss
import json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMB_NPY = PROJECT_ROOT / "data" / "faiss" / "review_embeddings.npy"
INDEX_PATH = PROJECT_ROOT / "data" / "faiss" / "reviews_hnsw.index"
DB_PATH = PROJECT_ROOT / "data" / "faiss" / "faiss_metadata.db"

def load_index(path):
    idx = faiss.read_index(str(path))
    return idx

def query(index, model, text, k=5):
    q_emb = model.encode([text], convert_to_numpy=True, normalize_embeddings=True)
    D, I = index.search(q_emb, k)
    # D are similarity scores (inner product). If you want cosine, since normalized, IP ∈ [-1,1].
    return D[0].tolist(), I[0].tolist()

def fetch_metadata(faiss_ids):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    rows = []
    for fid in faiss_ids:
        cur.execute("SELECT asin, reviewerID, reviewText, summary, unixReviewTime FROM reviews WHERE faiss_id = ?", (int(fid),))
        r = cur.fetchone()
        if r:
            rows.append({"faiss_id": int(fid), "asin": r[0], "reviewerID": r[1], "reviewText": r[2], "summary": r[3], "unixReviewTime": r[4]})
        else:
            rows.append({"faiss_id": int(fid), "missing": True})
    conn.close()
    return rows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", type=str, help="Query text in quotes")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    model = SentenceTransformer(MODEL_NAME)
    idx = load_index(INDEX_PATH)
    sims, ids = query(idx, model, args.query, args.k)
    metas = fetch_metadata(ids)
    out = []
    for sim, m in zip(sims, metas):
        item = dict(m)
        item["score"] = float(sim)
        out.append(item)
    print(json.dumps({"query": args.query, "results": out}, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
