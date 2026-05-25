#!/usr/bin/env python3
"""
Generate embeddings for reviews_small.csv using sentence-transformers.
Outputs:
- data/faiss/review_embeddings.npy (float32, shape N x D)
- data/faiss/review_ids.npy (int64)    (same order as embeddings)
- sqlite DB data/faiss/faiss_metadata.db with table 'reviews'
"""
import os
import sys
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
from tqdm import tqdm

# embedding model
from sentence_transformers import SentenceTransformer

# Config
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = PROJECT_ROOT / "data" / "out" / "reviews_small.csv"
OUT_DIR = PROJECT_ROOT / "data" / "faiss"
DB_PATH = OUT_DIR / "faiss_metadata.db"
EMB_NPY = OUT_DIR / "review_embeddings.npy"
IDS_NPY = OUT_DIR / "review_ids.npy"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
BATCH_SIZE = 512  # tune based on memory

def ensure_out():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

def init_db(conn):
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        faiss_id INTEGER PRIMARY KEY,
        asin TEXT,
        reviewerID TEXT,
        reviewText TEXT,
        summary TEXT,
        unixReviewTime INTEGER
    );
    """)
    conn.commit()

def main():
    ensure_out()
    print("Loading model:", MODEL_NAME)
    model = SentenceTransformer(MODEL_NAME)
    model.max_seq_length = 256  # keep inference fast
    # determinism (best-effort)
    import torch, random
    torch.manual_seed(1234)
    np.random.seed(1234)
    random.seed(1234)

    print("Reading CSV:", CSV_PATH)
    df = pd.read_csv(CSV_PATH)
    # required columns depend on your CSV; adapt if different
    # recommended text field to embed:
    if "reviewText" in df.columns:
        texts = df["reviewText"].fillna("").astype(str).tolist()
    elif "text" in df.columns:
        texts = df["text"].fillna("").astype(str).tolist()
    else:
        raise SystemExit("CSV missing review text column (expect reviewText or text).")

    # prepare metadata fields
    asins = df["asin"].astype(str).tolist() if "asin" in df.columns else [""] * len(df)
    reviewerIDs = df["reviewerID"].astype(str).tolist() if "reviewerID" in df.columns else [""] * len(df)
    summaries = df["summary"].astype(str).tolist() if "summary" in df.columns else [""] * len(df)
    unixTimes = df["unixReviewTime"].astype(pd.Int64Dtype()).fillna(0).astype(int).tolist() if "unixReviewTime" in df.columns else [0]*len(df)

    N = len(texts)
    print(f"Found {N} reviews; computing embeddings in batches of {BATCH_SIZE}")

    embeddings = np.zeros((N, model.get_sentence_embedding_dimension()), dtype=np.float32)
    idx = 0
    for i in tqdm(range(0, N, BATCH_SIZE)):
        batch_texts = texts[i:i+BATCH_SIZE]
        emb = model.encode(batch_texts, batch_size=BATCH_SIZE, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True)
        embeddings[i:i+len(emb)] = emb
    # save embeddings and ids (faiss id will be 0..N-1)
    np.save(EMB_NPY, embeddings)
    np.save(IDS_NPY, np.arange(N, dtype=np.int64))
    print("Saved embeddings to", EMB_NPY)

    # write metadata to sqlite
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    cur = conn.cursor()
    print("Writing metadata to", DB_PATH)
    for fid, (asin, rid, txt, summ, ut) in enumerate(zip(asins, reviewerIDs, texts, summaries, unixTimes)):
        cur.execute("INSERT OR REPLACE INTO reviews (faiss_id, asin, reviewerID, reviewText, summary, unixReviewTime) VALUES (?, ?, ?, ?, ?, ?)",
                    (int(fid), asin, rid, txt, summ, int(ut)))
    conn.commit()
    conn.close()
    print("Done. Metadata rows:", N)

if __name__ == "__main__":
    main()
