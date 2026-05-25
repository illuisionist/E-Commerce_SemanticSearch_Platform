#!/usr/bin/env python3
"""
convert_meta_reviews.py
Streaming two-pass preprocessing + sampling for large Amazon JSONL files.

Usage (example):
python scripts/convert_meta_reviews.py \
  --products-json ../data/raw/products.json \
  --reviews-json  ../data/raw/reviews.json \
  --out-products ../data/out/products_small.csv \
  --out-reviews  ../data/out/reviews_small.csv \
  --asin-list    ../data/out/asin_sample_list.txt \
  --sample-products 10000 \
  --sample-reviews  50000 \
  --per-product-cap 5 \
  --seed 42

Notes:
- Two-pass approach:
  1) Reservoir sample product ASINs (P)
  2) Stream products.json again, write selected product rows (cleaned) -> products_small.csv
  3) Stream reviews.json and accept up to per_product_cap reviews per sampled ASIN until R reached
  4) If global R not reached after first pass, second pass will accept additional reviews (no per-product cap)
"""
import argparse
import csv
import json
import random
import time
import re
import html
import sys
from pathlib import Path
from collections import defaultdict

try:
    import orjson as jsonlib
    def loads(s): return jsonlib.loads(s)
except Exception:
    try:
        import ujson as jsonlib
        def loads(s): return jsonlib.loads(s)
    except Exception:
        def loads(s): return json.loads(s)


# ---------- cleaning helpers ----------
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")

def strip_html_and_unescape(text):
    if not isinstance(text, str):
        return ""
    text = TAG_RE.sub(" ", text)             # remove tags
    text = html.unescape(text)               # unescape entities
    text = WHITESPACE_RE.sub(" ", text)     # collapse whitespace/newlines
    return text.strip()

def normalize_category(cat):
    """
    Normalize category into a single pipe-separated string.
    cat can be: list, string, or None.
    """
    if cat is None:
        return ""
    if isinstance(cat, list):
        safe = [str(x).strip() for x in cat if x]
        return "|".join(safe)
    if isinstance(cat, str):
        c = cat.strip()
        # sometimes it's literally a json-like list string: try to parse
        if (c.startswith("[") and c.endswith("]")):
            try:
                parsed = json.loads(c)
                if isinstance(parsed, list):
                    return "|".join(str(x).strip() for x in parsed if x)
            except Exception:
                pass
        return c
    return str(cat)

def normalize_price(value):
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value).strip()
    # extract first number like 1234.56
    m = re.search(r"(\d{1,3}(?:[,]\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)", s)
    if not m:
        return s
    num = m.group(1).replace(",", "")
    return num

def safe_get(obj, *keys):
    """Try multiple keys, return first non-empty string-like value"""
    for k in keys:
        if k in obj and obj[k] not in (None, "", [], {}):
            return obj[k]
    return ""


# ---------- reservoir sampling for ASINs (streamed) ----------
def reservoir_sample_asins(products_path, k, seed=42, log_every=500_000):
    random.seed(seed)
    reservoir = []
    total = 0
    with open(products_path, "r", encoding="utf-8", errors="replace") as fh:
        for line_num, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = loads(line)
            except Exception:
                continue
            asin = obj.get("asin")
            if not asin:
                continue
            total += 1
            if len(reservoir) < k:
                reservoir.append(asin)
            else:
                j = random.randint(1, total)
                if j <= k:
                    reservoir[j-1] = asin
            if line_num % log_every == 0:
                print(f"[reservoir] lines {line_num:,} processed, reservoir size {len(reservoir)}", flush=True)
    print(f"[reservoir] finished; total product lines seen: {total:,}; sampled {len(reservoir)} asins")
    return set(reservoir)


# ---------- write products CSV for sampled ASINs ----------
def write_sampled_products(products_path, asin_set, out_path, log_every=200_000, max_description_len=32000):
    header = ["asin","title","brand","price","category","description"]
    seen = set()
    written = 0
    start = time.time()
    with open(products_path, "r", encoding="utf-8", errors="replace") as fin, \
         open(out_path, "w", encoding="utf-8", newline="") as fout:
        writer = csv.writer(fout, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(header)
        for line_num, line in enumerate(fin, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = loads(line)
            except Exception:
                continue
            asin = obj.get("asin")
            if not asin or asin not in asin_set:
                continue
            if asin in seen:
                continue
            title = strip_html_and_unescape(safe_get(obj, "title"))
            brand = safe_get(obj, "brand") or safe_get(obj, "manufacturer") or ""
            brand = strip_html_and_unescape(brand)
            price = normalize_price(safe_get(obj, "price"))
            category = normalize_category(safe_get(obj, "category") or safe_get(obj, "main_cat") or "")
            desc_raw = safe_get(obj, "description") or safe_get(obj, "tech1") or safe_get(obj, "feature") or ""
            # description may be list
            if isinstance(desc_raw, list):
                desc_raw = " ".join(str(x) for x in desc_raw if x)
            description = strip_html_and_unescape(desc_raw)[:max_description_len]
            writer.writerow([asin, title, brand, price, category, description])
            seen.add(asin)
            written += 1
            if line_num % log_every == 0:
                print(f"[products] lines {line_num:,} processed, written {written:,}", flush=True)
    elapsed = time.time() - start
    print(f"[products] finished. wrote {written:,} products to {out_path} in {elapsed:.1f}s")
    return written


# ---------- sample/write reviews ----------
def write_sampled_reviews(reviews_path, asin_set, out_path, target_reviews, per_product_cap, log_every=500_000):
    header = ["reviewerID","asin","overall","reviewText","summary","unixReviewTime"]
    written = 0
    counters = defaultdict(int)
    dedupe = set()
    start = time.time()

    # FIRST PASS: accept up to per_product_cap per product
    with open(reviews_path, "r", encoding="utf-8", errors="replace") as fin, \
         open(out_path, "w", encoding="utf-8", newline="") as fout:
        writer = csv.writer(fout, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(header)
        for line_num, line in enumerate(fin, start=1):
            if written >= target_reviews:
                break
            line = line.strip()
            if not line:
                continue
            try:
                obj = loads(line)
            except Exception:
                continue
            asin = obj.get("asin")
            if not asin or asin not in asin_set:
                continue
            if counters[asin] >= per_product_cap:
                continue
            reviewer = obj.get("reviewerID") or f"anon_{line_num}"
            unix_time = obj.get("unixReviewTime")
            if unix_time is None:
                # try to parse reviewTime (format like "07 17, 2002") -> fallback to 0
                unix_time = obj.get("unixReviewTime", 0)
            key = (reviewer, asin, unix_time)
            if key in dedupe:
                continue
            overall = obj.get("overall", "")
            reviewText = strip_html_and_unescape(obj.get("reviewText","") or "")
            summary = strip_html_and_unescape(obj.get("summary","") or "")
            writer.writerow([reviewer, asin, overall, reviewText, summary, unix_time])
            dedupe.add(key)
            counters[asin] += 1
            written += 1
            if line_num % log_every == 0:
                print(f"[reviews-firstpass] lines {line_num:,} processed, written {written:,}", flush=True)

    elapsed = time.time() - start
    print(f"[reviews-firstpass] done first pass: wrote {written:,}/{target_reviews} reviews in {elapsed:.1f}s")
    if written >= target_reviews:
        return written

    # SECOND PASS: fill remaining reviews without per-product cap, but avoid duplicates
    needed = target_reviews - written
    print(f"[reviews-secondpass] starting second pass to collect {needed:,} additional reviews")
    start2 = time.time()
    with open(reviews_path, "r", encoding="utf-8", errors="replace") as fin, \
        open(out_path, "a", encoding="utf-8", newline="") as fout:
        writer = csv.writer(fout, quoting=csv.QUOTE_MINIMAL)
        for line_num, line in enumerate(fin, start=1):
            if needed <= 0:
                break
            line = line.strip()
            if not line:
                continue
            try:
                obj = loads(line)
            except Exception:
                continue
            asin = obj.get("asin")
            if not asin or asin not in asin_set:
                continue
            reviewer = obj.get("reviewerID") or f"anon_{line_num}"
            unix_time = obj.get("unixReviewTime", 0)
            key = (reviewer, asin, unix_time)
            if key in dedupe:
                continue
            overall = obj.get("overall", "")
            reviewText = strip_html_and_unescape(obj.get("reviewText","") or "")
            summary = strip_html_and_unescape(obj.get("summary","") or "")
            writer.writerow([reviewer, asin, overall, reviewText, summary, unix_time])
            dedupe.add(key)
            written += 1
            needed -= 1
            if line_num % log_every == 0:
                print(f"[reviews-secondpass] lines {line_num:,} processed, written {written:,}", flush=True)

    elapsed2 = time.time() - start2
    print(f"[reviews-secondpass] finished. total written {written:,}. took {elapsed2:.1f}s")
    return written


# ---------- top-level CLI ----------
def main():
    parser = argparse.ArgumentParser(description="Preprocess and sample Amazon products + reviews (streaming).")
    parser.add_argument("--products-json", required=True, help="Path to raw products.json (JSONL)")
    parser.add_argument("--reviews-json", required=True, help="Path to raw reviews.json (JSONL)")
    parser.add_argument("--out-products", required=True, help="Path to write products CSV")
    parser.add_argument("--out-reviews", required=True, help="Path to write reviews CSV")
    parser.add_argument("--asin-list", required=True, help="Path to write sampled ASINs (text)")
    parser.add_argument("--sample-products", type=int, default=10000, help="Number of products to sample")
    parser.add_argument("--sample-reviews", type=int, default=50000, help="Number of reviews to sample")
    parser.add_argument("--per-product-cap", type=int, default=5, help="Max reviews per sampled product (first pass)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    products_path = Path(args.products_json)
    reviews_path = Path(args.reviews_json)
    out_products = Path(args.out_products)
    out_reviews = Path(args.out_reviews)
    asin_list_path = Path(args.asin_list)

    print("Starting preprocessing with parameters:")
    print(f" products_json: {products_path}")
    print(f" reviews_json : {reviews_path}")
    print(f" out_products : {out_products}")
    print(f" out_reviews  : {out_reviews}")
    print(f" asin_list    : {asin_list_path}")
    print(f" sample_products={args.sample_products}, sample_reviews={args.sample_reviews}, per_product_cap={args.per_product_cap}")

    start_total = time.time()

    # Step 1: reservoir sample asins
    asin_set = reservoir_sample_asins(products_path, args.sample_products, seed=args.seed)
    asin_list_path.parent.mkdir(parents=True, exist_ok=True)
    with open(asin_list_path, "w", encoding="utf-8") as f:
        for a in sorted(asin_set):
            f.write(a + "\n")
    print(f"Wrote sampled ASIN list to {asin_list_path}")

    # Step 2: write sampled products CSV
    out_products.parent.mkdir(parents=True, exist_ok=True)
    written_products = write_sampled_products(products_path, asin_set, out_products)

    # Step 3: write sampled reviews CSV
    out_reviews.parent.mkdir(parents=True, exist_ok=True)
    written_reviews = write_sampled_reviews(reviews_path, asin_set, out_reviews, args.sample_reviews, args.per_product_cap)

    total_elapsed = time.time() - start_total
    print("=== Summary ===")
    print(f"Products written: {written_products}")
    print(f"Reviews written : {written_reviews}")
    print(f"Total time: {total_elapsed:.1f}s")

if __name__ == "__main__":
    main()
