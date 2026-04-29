"""Qdrant client and helper functions."""

from qdrant_client import QdrantClient

from lcars_mcp_server.settings import QDRANT_API_KEY, QDRANT_URL

qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, prefer_grpc=True)


def get_payload(point) -> dict:
    """Extract payload dict from a Qdrant point, handling SDK version differences."""
    return point.metadata if hasattr(point, "metadata") else point.payload


def format_result(point, metadata: dict | None = None) -> dict:
    """Format a Qdrant point into a clean result dict.

    Fields from qdrant: source_name, filename, language, content_type, chunk_location, chunk_text.
    Fields enriched from postgres metadata: url, tags.
    """
    payload = get_payload(point)
    meta = metadata or {}
    return {
        "score": round(point.score, 4) if hasattr(point, "score") else None,
        "source_name": payload.get("source_name"),
        "filename": payload.get("filename"),
        "url": meta.get("url"),
        "language": payload.get("language"),
        "content_type": payload.get("content_type"),
        "tags": meta.get("tags", []),
        "chunk_location": payload.get("chunk_location"),
        "chunk_text": payload.get("chunk_text"),
    }
