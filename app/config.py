# app/config.py
from os import getenv

# Elasticsearch
ES_HOST = getenv("ES_HOST", "http://localhost:9200")
ES_INDEX = getenv("ES_INDEX", "products")

# CockroachDB (Postgres-compatible connection string)
# Example: postgresql://root@localhost:26257/dist_ecom?sslmode=disable
COCKROACH_DSN = getenv("COCKROACH_DSN", "postgresql://root@localhost:26257/dist_ecom?sslmode=disable")

# SQLite metadata (faiss review meta)
SQLITE_FAISS_DB = getenv("SQLITE_FAISS_DB", "data/faiss/faiss_metadata.db")

# FAISS index path
FAISS_INDEX_PATH = getenv("FAISS_INDEX_PATH", "data/faiss/reviews_hnsw.index")

# Sentence transformer model
EMBEDDING_MODEL = getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# Defaults for the API
DEFAULT_TOP_PRODUCTS = int(getenv("DEFAULT_TOP_PRODUCTS", "5"))
DEFAULT_TOP_REVIEWS = int(getenv("DEFAULT_TOP_REVIEWS", "5"))
DEFAULT_FAISS_K = int(getenv("DEFAULT_FAISS_K", "50"))
DEFAULT_EFSEARCH = int(getenv("DEFAULT_EFSEARCH", "200"))
