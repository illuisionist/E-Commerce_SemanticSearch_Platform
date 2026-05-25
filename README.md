# Distributed E-Commerce Semantic Search Platform

A production-style, distributed e-commerce semantic search system built incrementally with a strong focus on **correctness, scalability, and clean engineering practices**.

The project is intentionally developed in milestones, where each layer is validated independently before moving to the next.

---

## Each milestone

- v0.1 — Data Ingestion & Distributed Storage 
- v0.2 — Product Search Infrastructure (BM25) 
- v0.3 — Semantic Review Search (FAISS) 
- v0.4 — Unified FastAPI Query Gateway 

---

## v0.1 — Data Ingestion & Distributed Storage (Completed)

**Goal:**  
Build a reliable, reproducible data ingestion and distributed storage foundation using real-world, large-scale Amazon datasets.

This milestone focuses entirely on **infrastructure correctness and data hygiene** before introducing any search or retrieval layers.

### What’s included
- **Streaming preprocessing pipeline**
  - `scripts/convert_meta_reviews.py`
  - Two-pass, memory-safe design (no full dataset loading)
  - Deterministic reservoir sampling (seeded) for reproducibility  
    - ~10,000 products  
    - ~50,000 reviews
  - Cleans HTML artifacts, malformed text, whitespace, and missing fields
- **Cleaned outputs for downstream systems**
  - `data/out/products_small.csv`
  - `data/out/reviews_small.csv`
  - `data/out/asin_sample_list.txt`
- **Distributed SQL storage**
  - 3-node CockroachDB cluster running locally via Docker Compose
  - Schema design for `products` and `reviews`
  - Bulk ingestion using CockroachDB `IMPORT`
- **Verification and validation**
  - Row counts verified after import
  - Cluster health checks
  - Replication and range distribution across nodes validated
- **Dockerized environment**
  - Fully reproducible local setup
  - No dependency on host Python environment
- **Repository hygiene**
  - Removed virtual environments and large binaries from Git history
  - Clean `.gitignore` and `.dockerignore`
  - Recruiter-grade, lightweight repository

### Design decisions
- Raw Amazon datasets (20+ GB total) are intentionally excluded from the repository.
- All preprocessing is streaming to avoid memory pressure.
- No search, embeddings, or APIs are introduced at this stage by design.

### Outcome
- A stable, distributed storage layer ready to support search and retrieval workloads.
- Deterministic sample datasets that can be regenerated at any time.

### How to run (short)
```bash
python scripts/convert_meta_reviews.py
docker compose up -d
cockroach sql --insecure --host=localhost:26257

```
## v0.2 — Product Search Infrastructure (Completed)

**Goal:**  
Introduce a robust lexical product search layer using Elasticsearch (BM25) while intentionally deferring APIs and semantic retrieval.

This milestone focuses on validating **search relevance, indexing correctness, and integration with distributed storage** before adding semantic capabilities.

**What’s included**
- Elasticsearch integration:
  - Official Elasticsearch 8.x image (ARM64-compatible)
  - Runs locally via Docker Compose alongside CockroachDB
- Product indexing pipeline:
  - `scripts/index_products_to_elasticsearch.py`
  - Bulk indexing of ~10,000 products from `products_small.csv`
- Index design and relevance tuning:
  - Explicit mappings for product fields
  - BM25 similarity (default Elasticsearch ranking)
  - Field boosting (e.g., `title^3`) to improve ranking quality
- Verification and validation:
  - Index document counts verified
  - Search correctness tested via `_search`
  - Ranking behavior inspected using `_score`
- Infrastructure-first design:
  - No FastAPI endpoints added (intentional)
  - No semantic embeddings or vector search at this stage

**Design decisions**
- Lexical search is introduced before semantic retrieval to:
  - Establish a strong and explainable baseline
  - Validate indexing and ranking independently
- API layer is deferred until both product and review retrieval layers are complete.

**Outcome**
- A production-style product search layer capable of fast and relevant keyword-based retrieval.
- Clean separation between distributed storage (CockroachDB) and search infrastructure (Elasticsearch).

**How to run (short)**
```bash
# start services (CockroachDB + Elasticsearch)
docker compose up -d

# index products into Elasticsearch
python scripts/index_products_to_elasticsearch.py

# test a sample query
curl "http://localhost:9200/products/_search?q=wireless"
```
---



## v0.3 — FAISS-based Semantic Review Search (Completed)

**Goal:** Add a semantic retrieval layer for product reviews using sentence-transformer embeddings + FAISS HNSW.

**What’s included**
- `scripts/generate_embeddings.py` — streaming, memory-safe embedding generation for `data/out/reviews_small.csv` using `sentence-transformers/all-MiniLM-L6-v2`.
- `scripts/build_faiss_index.py` — builds an HNSW FAISS index (`IndexHNSWFlat`) and writes `data/faiss/reviews_hnsw.index` and a small JSON config.
  - Editable build-time HNSW params at top of file: `M` (connectivity) and `ef_construction` (build depth).
- `scripts/query_faiss.py` — CLI for semantic queries with:
  - `--k` (number of results),
  - `--efSearch` (runtime efSearch to trade recall/latency),
  - `--asin` (optional per-product filtering with oversampling).
- `data/faiss/faiss_metadata.db` — SQLite mapping `faiss_id → asin,reviewText,summary,unixReviewTime`.
- `scripts/e2e_smoke_test.sh` and `scripts/e2e_test.py` — smoke & programmatic E2E checks (Cockroach, Elasticsearch, FAISS artifacts, sample queries).
- Manifest & reproducibility notes:
  - Model: `sentence-transformers/all-MiniLM-L6-v2` (384d)
  - Index: `IndexHNSWFlat`, default `M=32`, `ef_construction=200`
  - Runtime `efSearch` recommended: `200` for demos
**How to run (short)**
```bash
# generate embeddings
python scripts/generate_embeddings.py

# build FAISS index
python scripts/build_faiss_index.py

# query
python scripts/query_faiss.py "long battery life" --k 5 --efSearch 200
```
---
## v0.4 — Unified FastAPI Query Gateway (Completed)

**Goal:**  
Expose a single, clean API endpoint that **orchestrates lexical search, semantic retrieval, and authoritative metadata** into one unified response.

This milestone integrates all prior layers into a production-style query service.

### What’s included
- **FastAPI service**
  - `/search` — unified search endpoint
  - `/health` — service health check
  - Interactive OpenAPI docs (`/docs`)
- **Hybrid retrieval pipeline**
  - Elasticsearch (BM25) for product candidate generation
  - FAISS (HNSW) for semantic review retrieval
  - CockroachDB for authoritative product metadata
- **Human-style query support**
  - Accepts natural language queries (e.g.  
    *“I want a phone with long battery life and fast charging”*)
- **Configurable ranking**
  - `top_products`, `top_reviews`
  - `faiss_k` oversampling
  - Runtime `efSearch` tuning
  - Optional filtering of semantic reviews by top-N product ASINs
- **Defensive API design**
  - Strict response validation via Pydantic
  - Safe type coercion for real-world data inconsistencies
- **Local-first, reproducible setup**
  - All components run locally via Docker and Python
  - Generated artifacts excluded from git

### Outcome
- A fully functional, production-style **unified search API**
- Clean separation of responsibilities:
  - CockroachDB → system of record
  - Elasticsearch → lexical retrieval
  - FAISS → semantic similarity
  - FastAPI → orchestration layer

---
## Conclusion

This project demonstrates a production-style approach to building a distributed search system by validating each layer independently before integration.

Rather than relying on a single technology, the platform intentionally separates concerns:
- CockroachDB serves as the strongly consistent system of record,
- Elasticsearch handles fast lexical retrieval,
- FAISS enables semantic similarity search,
- FastAPI acts as a lightweight orchestration layer.

The incremental milestone-based design ensures correctness, reproducibility, and extensibility, while keeping each component replaceable as system requirements evolve.

Future milestones build on this foundation to introduce intelligent ranking, retrieval-augmented generation, and personalization.
