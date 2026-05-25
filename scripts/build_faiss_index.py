#!/usr/bin/env python3
"""
Build FAISS HNSW index from saved embeddings.
Outputs:
- data/faiss/reviews_hnsw.index
- data/faiss/faiss_index_config.json (small metadata)
"""
import os, json
from pathlib import Path
import numpy as np
import faiss

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EMB_NPY = PROJECT_ROOT / "data" / "faiss" / "review_embeddings.npy"
INDEX_PATH = PROJECT_ROOT / "data" / "faiss" / "reviews_hnsw.index"
CONFIG_PATH = PROJECT_ROOT / "data" / "faiss" / "faiss_index_config.json"

# parameters
M = 32   # HNSW connectivity (tradeoff: higher=M => better recall, slower build & search)
ef_construction = 200
ef_search_default = 50

def main():
    emb = np.load(EMB_NPY)
    N, D = emb.shape
    print(f"Loaded embeddings: N={N}, D={D}")

    # Using inner product (IP) for cosine similarity on normalized vectors.
    # If embeddings already normalized (we normalized in generation), IP ~ cosine.
    index = faiss.IndexHNSWFlat(D, M, faiss.METRIC_INNER_PRODUCT)
    index.hnsw.efConstruction = ef_construction
    index.verbose = True

    print("Adding embeddings to index (this may take a while)...")
    index.add(emb)  # emb should be float32
    print("ntotal:", index.ntotal)

    # set default ef_search for queries
    index.hnsw.efSearch = ef_search_default

    print("Writing index to", INDEX_PATH)
    faiss.write_index(index, str(INDEX_PATH))

    # write small config
    cfg = {"index_path": str(INDEX_PATH), "ntotal": int(index.ntotal), "d": D, "M": M, "ef_construction": ef_construction, "ef_search_default": ef_search_default}
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    print("Wrote config:", CONFIG_PATH)
    print("Done.")

if __name__ == "__main__":
    main()
