# app/search.py
import sqlite3
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from elasticsearch import Elasticsearch
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Tuple
from . import config


# ---------- Helpers (added) ----------
def safe_float(x):
    """
    Convert x to float if possible. Return None for None, empty strings, or invalid values.
    """
    if x is None:
        return None
    if isinstance(x, str):
        x = x.strip()
        if x == "":
            return None
    try:
        return float(x)
    except (ValueError, TypeError):
        return None


# Initialize global objects in startup
es_client: Elasticsearch = None
faiss_index = None
embed_model = None
sqlite_conn: sqlite3.Connection = None
psycopg_conn = None

def init_clients():
    global es_client, faiss_index, embed_model, sqlite_conn, psycopg_conn
    # ES client
    es_client = Elasticsearch(config.ES_HOST, request_timeout=30)

    # FAISS
    faiss_index = faiss.read_index(config.FAISS_INDEX_PATH)
    # Set a decent efSearch default for runtime (may be overwritten per-request)
    try:
        faiss_index.hnsw.efSearch = config.DEFAULT_EFSEARCH
    except Exception:
        faiss.ParameterSpace().set_index_parameter(faiss_index, "efSearch", str(config.DEFAULT_EFSEARCH))

    # embedding model
    embed_model = SentenceTransformer(config.EMBEDDING_MODEL)

    # sqlite for faiss metadata
    sqlite_conn = sqlite3.connect(config.SQLITE_FAISS_DB, check_same_thread=False)

    # CockroachDB (psycopg2)
    psyc_dsn = config.COCKROACH_DSN
    psycopg_conn = psycopg2.connect(psyc_dsn, cursor_factory=RealDictCursor)
    psycopg_conn.autocommit = True

def close_clients():
    global sqlite_conn, psycopg_conn
    try:
        if sqlite_conn:
            sqlite_conn.close()
    except Exception:
        pass
    try:
        if psycopg_conn:
            psycopg_conn.close()
    except Exception:
        pass

# ---------- Elasticsearch helpers ----------

def es_search_products(q: str, top_n: int) -> List[Dict]:
    """
    Run a simple multi_match BM25 query and return hits with asin and _score.
    """
    body = {
        "query": {
            "multi_match": {
                "query": q,
                "fields": ["title^3", "description", "brand", "category"],
                "type": "best_fields"
            }
        },
        "size": top_n
    }
    resp = es_client.search(index=config.ES_INDEX, body=body)
    hits = resp.get("hits", {}).get("hits", [])
    products = []
    for h in hits:
        src = h.get("_source", {})
        products.append({
            "asin": src.get("asin"),
            "title": src.get("title"),
            "brand": src.get("brand"),
            "category": src.get("category"),
            "price": src.get("price"),
            "bm25_score": h.get("_score")
        })
    return products

# ---------- FAISS helpers ----------

def make_query_embedding(q: str) -> np.ndarray:
    emb = embed_model.encode([q], convert_to_numpy=True, normalize_embeddings=True)
    return emb

def faiss_search(q_emb: np.ndarray, k: int, efSearch: int) -> Tuple[np.ndarray, np.ndarray]:
    # set efSearch if possible
    try:
        faiss_index.hnsw.efSearch = efSearch
    except Exception:
        faiss.ParameterSpace().set_index_parameter(faiss_index, "efSearch", str(efSearch))
    D, I = faiss_index.search(q_emb, k)
    return D, I

# ---------- Metadata helpers ----------

def lookup_review_meta_by_fid(fid: int) -> Dict:
    """
    SQLite table 'reviews' expected with columns: faiss_id, asin, reviewText, summary, unixReviewTime
    """
    cur = sqlite_conn.cursor()
    cur.execute("SELECT faiss_id, asin, reviewText, summary, unixReviewTime FROM reviews WHERE faiss_id = ?", (int(fid),))
    row = cur.fetchone()
    if not row:
        return None
    # sqlite returns a tuple for the row (unless row_factory is set). Map to keys:
    keys = ["faiss_id", "asin", "reviewText", "summary", "unixReviewTime"]
    return dict(zip(keys, row))

def fetch_products_from_cockroach(asins: List[str]) -> Dict[str, Dict]:
    """
    Given a list of ASINs, return a mapping asin -> product metadata (title, brand, category, price)
    """
    if not asins:
        return {}
    placeholders = ",".join(["%s"] * len(asins))
    sql = f"SELECT asin, title, brand, category, price FROM products WHERE asin IN ({placeholders})"
    with psycopg_conn.cursor() as cur:
        cur.execute(sql, tuple(asins))
        rows = cur.fetchall()
    result = {}
    for r in rows:
        # r is a RealDictRow from psycopg2.extras.RealDictCursor
        result[r["asin"]] = {
            "title": r.get("title"),
            "brand": r.get("brand"),
            "category": r.get("category"),
            "price": r.get("price")
        }
    return result

# ---------- Orchestration ----------

def unified_search(q: str,
                   top_products: int = config.DEFAULT_TOP_PRODUCTS,
                   top_reviews: int = config.DEFAULT_TOP_REVIEWS,
                   faiss_k: int = config.DEFAULT_FAISS_K,
                   efSearch: int = config.DEFAULT_EFSEARCH,
                   filter_by_products: bool = True) -> Dict:
    """
    Master orchestration routine:
     1) ES product search -> top_products
     2) FAISS search (oversample faiss_k)
     3) Filter FAISS results by product ASINs (if filter_by_products)
     4) Aggregate top reviews per product (top_reviews)
     5) Enrich product info from CockroachDB
    """
    # 1) ES
    es_products = es_search_products(q, top_products)
    es_asins = [p["asin"] for p in es_products if p.get("asin")]

    # 2) FAISS
    qemb = make_query_embedding(q)
    D, I = faiss_search(qemb, faiss_k, efSearch)

    # 3) collect candidate reviews, filter by asin if requested
    per_product_reviews: Dict[str, List[Dict]] = {}
    for dist_row, ids_row in zip(D, I):
        for score, fid in zip(dist_row, ids_row):
            if fid < 0:
                continue
            meta = lookup_review_meta_by_fid(int(fid))
            if not meta:
                continue
            asin = meta.get("asin")
            if filter_by_products and es_asins and (asin not in es_asins):
                continue
            per_product_reviews.setdefault(asin, []).append({
                "faiss_id": int(fid),
                "asin": asin,
                "reviewText": meta.get("reviewText"),
                "summary": meta.get("summary"),
                "unixReviewTime": meta.get("unixReviewTime"),
                "semantic_score": float(score)
            })

    # 4) pick top reviews per product
    products_out = []
    # fetch product metadata map from cockroach
    product_meta_map = fetch_products_from_cockroach(es_asins)

    for p in es_products:
        asin = p.get("asin")
        prod_meta = product_meta_map.get(asin, {})
        # sort reviews for this asin by semantic_score desc
        reviews = per_product_reviews.get(asin, [])
        reviews_sorted = sorted(reviews, key=lambda r: r["semantic_score"], reverse=True)[:top_reviews]
        product_entry = {
            "asin": asin,
            "title": prod_meta.get("title") or p.get("title"),
            "brand": prod_meta.get("brand") or p.get("brand"),
            "category": prod_meta.get("category") or p.get("category"),
            # <-- Use safe_float here to ensure empty strings / bad values become None
            "price": safe_float(prod_meta.get("price") or p.get("price")),
            "bm25_score": p.get("bm25_score"),
            "reviews": reviews_sorted
        }
        products_out.append(product_entry)

    return {"query": q, "products": products_out}
