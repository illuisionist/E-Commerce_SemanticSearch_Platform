#!/usr/bin/env python3
"""
scripts/index_products_to_elasticsearch.py
Bulk index data/out/products_small.csv -> Elasticsearch index "products".
"""

import csv
import os
from elasticsearch import Elasticsearch, helpers

ES_HOST = os.environ.get("ES_HOST", "http://localhost:9200")
INDEX = os.environ.get("ES_INDEX", "products")
CSV_PATH = os.environ.get("CSV_PATH", "data/out/products_small.csv")
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "500"))

def gen_actions(csv_path):
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            asin = (row.get("asin") or "").strip()
            # ensure we have an id
            _id = asin if asin else None
            doc = {
                "_index": INDEX,
                "_id": _id,
                "_source": {
                    "asin": asin,
                    "title": row.get("title",""),
                    "brand": row.get("brand",""),
                    "price": row.get("price",""),
                    "category": row.get("category",""),
                    "description": row.get("description","")
                }
            }
            yield doc

def main():
    print("Connecting to Elasticsearch at", ES_HOST)
    client = Elasticsearch(ES_HOST, verify_certs=False, timeout=30)

    # test connection
    if not client.ping():
        raise SystemExit("Cannot connect to Elasticsearch at " + ES_HOST)

    print(f"Bulk-indexing CSV: {CSV_PATH} -> index: {INDEX}")
    success = 0
    failed = 0
    for ok, item in helpers.parallel_bulk(client, gen_actions(CSV_PATH), thread_count=4, chunk_size=BATCH_SIZE):
        if ok:
            success += 1
        else:
            failed += 1
    print(f"Finished. success={success} failed={failed}")

if __name__ == "__main__":
    main()
