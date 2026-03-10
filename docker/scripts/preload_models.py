"""Pre-download SentenceTransformer model into the image cache.

Run during Docker build (model-preload stage).
Uses sentence_transformers directly — no sentinel package import required.
"""

import os
import sys

MODEL_NAME = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
CACHE_DIR = os.environ.get("SENTENCE_TRANSFORMERS_HOME", "/app/.cache/sentence_transformers")

if __name__ == "__main__":
    print(f"Pre-loading model: {MODEL_NAME!r} into {CACHE_DIR!r}", flush=True)
    try:
        from sentence_transformers import SentenceTransformer
        SentenceTransformer(MODEL_NAME, cache_folder=CACHE_DIR)
        print("Model cached successfully.", flush=True)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
