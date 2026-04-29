"""Embedding API client."""

import httpx

from lcars_mcp_server.settings import EMBEDDING_API_ADDRESS, EMBEDDING_MODEL


def embed_query(text: str) -> list[float]:
    """Embed query text using the OpenAI-compatible embedding API."""
    resp = httpx.post(
        f"{EMBEDDING_API_ADDRESS}/embeddings",
        json={"model": EMBEDDING_MODEL, "input": text},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]
