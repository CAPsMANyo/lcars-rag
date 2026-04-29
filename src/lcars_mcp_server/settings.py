"""Configuration loaded from environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6334")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY") or None
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "cocoindex")
EMBEDDING_API_ADDRESS = os.environ.get("EMBEDDING_API_ADDRESS", "http://localhost:11435/v1")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "qwen3-embedding:0.6b")
EMBEDDING_DIMENSION = int(os.environ.get("EMBEDDING_DIMENSION", "1024"))
# Accept POSTGRES_URL or fall back to COCOINDEX_DATABASE_URL for compatibility with lcars-rag
POSTGRES_URL = os.environ.get("POSTGRES_URL") or os.environ.get(
    "COCOINDEX_DATABASE_URL", "postgresql://user:password@localhost:5432/dbname"
)
METADATA_TABLE = os.environ.get("METADATA_TABLE", "source_metadata")
RERANK_ENABLED = os.environ.get("RERANK_ENABLED", "false").lower() == "true"
RERANK_API_ADDRESS = os.environ.get("RERANK_API_ADDRESS", "http://localhost:8787")
RERANK_MODEL = os.environ.get("RERANK_MODEL", "bge-reranker-v2-m3")
RERANK_TOP_N = int(os.environ.get("RERANK_TOP_N", "0"))
RERANK_OVERFETCH_MULTIPLIER = int(os.environ.get("RERANK_OVERFETCH_MULTIPLIER", "3"))
