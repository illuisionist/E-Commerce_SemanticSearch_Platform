# app/schemas.py
from typing import List, Optional
from pydantic import BaseModel

class ReviewOut(BaseModel):
    faiss_id: int
    asin: str
    reviewText: str
    summary: Optional[str] = None
    unixReviewTime: Optional[int] = None
    semantic_score: float

class ProductOut(BaseModel):
    asin: str
    title: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    bm25_score: Optional[float] = None
    reviews: List[ReviewOut] = []

class SearchResponse(BaseModel):
    query: str
    products: List[ProductOut]
