## Project Status
- A production-style, distributed e-commerce semantic search platform built incrementally with a focus on scalability and correctness.


### v0.1 – Data Ingestion & Distributed Storage (Completed)
- Dockerized preprocessing pipeline for large-scale Amazon datasets
- 3-node CockroachDB cluster running locally
- Schema design for products and reviews
- Bulk data ingestion using CockroachDB IMPORT
- Verified replication and range distribution across nodes

### v0.2 – Product Search Infrastructure (Completed)

- Elasticsearch-based BM25 product search
- Official Elasticsearch (ARM64-compatible) running via Docker Compose
- Product index with optimized mappings
- ~10,000 products indexed successfully
- Verified relevance ranking using multi_match queries and field boosting

Upcoming

- v0.3 – FAISS-based semantic review search
- v0.4 – Unified FastAPI query gateway

