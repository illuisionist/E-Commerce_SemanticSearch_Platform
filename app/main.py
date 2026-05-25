# app/main.py
from fastapi import FastAPI, Query, HTTPException
from typing import Optional
import uvicorn

from . import config
from .search import init_clients, close_clients, unified_search
from .schemas import SearchResponse

app = FastAPI(title="Distributed E-Commerce Unified Search (v0.4)")

@app.on_event("startup")
def startup_event():
    init_clients()

@app.on_event("shutdown")
def shutdown_event():
    close_clients()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/search", response_model=SearchResponse)
def search(q: str = Query(..., min_length=1),
           top_products: int = Query(config.DEFAULT_TOP_PRODUCTS, ge=1, le=50),
           top_reviews: int = Query(config.DEFAULT_TOP_REVIEWS, ge=1, le=50),
           faiss_k: int = Query(config.DEFAULT_FAISS_K, ge=1, le=1000),
           efSearch: int = Query(config.DEFAULT_EFSEARCH, ge=1, le=2000),
           filter_by_products: bool = Query(True)):
    try:
        resp = unified_search(q=q,
                              top_products=top_products,
                              top_reviews=top_reviews,
                              faiss_k=faiss_k,
                              efSearch=efSearch,
                              filter_by_products=filter_by_products)
        return resp
    except Exception as e:
        # surface a helpful message during local development
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
