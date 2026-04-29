"""Reranking API client."""

import logging

import httpx

from lcars_mcp_server.settings import RERANK_API_ADDRESS, RERANK_MODEL

logger = logging.getLogger(__name__)


def rerank(query: str, documents: list[str], top_n: int) -> list[int]:
    """Rerank documents and return original indices sorted by relevance.

    Calls a Jina/Cohere-compatible rerank endpoint.

    Args:
        query: The search query.
        documents: List of document texts to rerank.
        top_n: Number of top results to return.

    Returns:
        List of original indices ordered by relevance score (descending).
    """
    resp = httpx.post(
        f"{RERANK_API_ADDRESS}/rerank",
        json={
            "model": RERANK_MODEL,
            "query": query,
            "texts": documents,
            "top_n": top_n,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    results = resp.json()
    return [r["index"] for r in sorted(results, key=lambda r: r["score"], reverse=True)]
