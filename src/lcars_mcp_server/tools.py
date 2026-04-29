"""MCP tool definitions for LCARS search."""

import logging

import httpx
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchAny,
    MatchText,
    MatchValue,
)

from lcars_mcp_server.embeddings import embed_query
from lcars_mcp_server.postgres import (
    get_metadata_map,
    get_source_names_by_tags,
    get_sources,
    get_tags,
    search_sources as pg_search_sources,
)
from lcars_mcp_server.qdrant import format_result, get_payload, qdrant
from lcars_mcp_server.rerank import rerank
from lcars_mcp_server.server import mcp
from lcars_mcp_server.settings import QDRANT_COLLECTION, RERANK_ENABLED, RERANK_OVERFETCH_MULTIPLIER, RERANK_TOP_N

logger = logging.getLogger(__name__)


def _error(service: str, err: Exception) -> list[dict]:
    """Return a structured error response for MCP clients."""
    logger.error("%s error: %s", service, err, exc_info=True)
    return [{"error": f"{service} unavailable", "detail": str(err)}]


@mcp.tool()
def search(
    query: str,
    source_name: str | None = None,
    tags: list[str] | None = None,
    language: str | None = None,
    content_type: str | None = None,
    filename: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> list[dict]:
    """Search code and documentation embeddings.

    Args:
        query: Natural language search query.
        source_name: Filter by repository name (e.g. "cocoindex", "frigate").
        tags: Filter by tags (e.g. ["rag", "ai"]). All tags must match.
        language: Filter by programming language (e.g. "python", "rust").
        content_type: Filter by "code" or "docs".
        filename: Filter by filename substring (e.g. "src/main" matches "src/main.py").
        limit: Max results to return (default 10).
        offset: Number of results to skip for pagination (default 0).

    Examples:
        search("how to configure routes", language="python")
        search("frigate camera config", tags=["homelab"], content_type="docs")
        search("embedding pipeline", source_name="cocoindex")
        search("authentication middleware", limit=5, offset=10)
    """
    conditions = []

    if source_name:
        conditions.append(FieldCondition(key="source_name", match=MatchValue(value=source_name)))
    if language:
        conditions.append(FieldCondition(key="language", match=MatchValue(value=language)))
    if content_type:
        conditions.append(FieldCondition(key="content_type", match=MatchValue(value=content_type)))
    if filename:
        conditions.append(FieldCondition(key="filename", match=MatchText(text=filename)))

    # Tags live in postgres -- resolve to source_names, then filter qdrant
    if tags:
        try:
            matching_sources = get_source_names_by_tags(tags)
        except Exception as e:
            return _error("Postgres", e)
        if not matching_sources:
            return []
        if source_name:
            if source_name not in matching_sources:
                return []
        else:
            conditions.append(
                FieldCondition(key="source_name", match=MatchAny(any=matching_sources))
            )

    query_filter = Filter(must=conditions) if conditions else None

    try:
        vector = embed_query(query)
    except Exception as e:
        return _error("Embedding API", e)

    # Over-fetch when reranking to give the reranker a larger candidate pool
    fetch_limit = (limit + offset) * RERANK_OVERFETCH_MULTIPLIER if RERANK_ENABLED else limit + offset

    try:
        results = qdrant.query_points(
            collection_name=QDRANT_COLLECTION,
            query=vector,
            using="embedding",
            query_filter=query_filter,
            limit=fetch_limit,
            with_payload=True,
        )
    except Exception as e:
        return _error("Qdrant", e)

    points = results.points

    if RERANK_ENABLED and points:
        documents = [get_payload(p).get("chunk_text", "") for p in points]
        if any(documents):
            try:
                top_n = RERANK_TOP_N if RERANK_TOP_N > 0 else limit + offset
                reranked_indices = rerank(query, documents, top_n)
                points = [points[i] for i in reranked_indices]
            except httpx.HTTPError:
                logger.warning("Rerank API request failed, falling back to vector ordering", exc_info=True)
                points = points[:limit + offset]
        else:
            logger.warning("All documents have empty chunk_text, skipping rerank")
            points = points[:limit + offset]
    else:
        points = points[:limit + offset]

    points = points[offset:]

    # Enrich results with metadata from postgres (url, tags)
    source_names = list({get_payload(p).get("source_name") for p in points})
    meta_map = get_metadata_map(source_names)

    return [
        format_result(
            point,
            metadata=meta_map.get(get_payload(point).get("source_name"), {}),
        )
        for point in points
    ]


@mcp.tool()
def list_sources() -> list[dict]:
    """List all indexed source repositories.

    Returns list of dicts with: source_name, source_type, url, tags, file_count.

    Examples:
        list_sources()
    """
    try:
        return get_sources()
    except Exception as e:
        return _error("Postgres", e)


@mcp.tool()
def list_tags(source_name: str | None = None) -> list[str]:
    """List all unique tags across indexed sources.

    Args:
        source_name: Optionally filter to tags from a specific source.

    Examples:
        list_tags()
        list_tags(source_name="frigate")
    """
    try:
        return get_tags(source_name)
    except Exception as e:
        return _error("Postgres", e)


@mcp.tool()
def get_source(source_name: str) -> dict:
    """Get detailed info about a specific indexed source.

    Args:
        source_name: Repository name (e.g. "cocoindex", "frigate").

    Returns dict with: source_name, source_type, url, tags, file_count.
    Returns empty dict if source not found.

    Examples:
        get_source("frigate")
        get_source("cocoindex")
    """
    try:
        sources = get_sources(source_name)
        return sources[0] if sources else {}
    except Exception as e:
        return {"error": "Postgres unavailable", "detail": str(e)}


@mcp.tool()
def find_files(
    filename: str,
    source_name: str | None = None,
    language: str | None = None,
    content_type: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Find indexed files by filename pattern without semantic search.

    Useful for locating specific files across repos when you know
    part of the filename but don't need content-based search.

    Args:
        filename: Filename substring to match (e.g. "config", "main.py").
        source_name: Filter by repository name.
        language: Filter by language (e.g. "python", "yaml").
        content_type: Filter by "code" or "docs".
        limit: Max results (default 20).

    Returns list of unique {source_name, filename, language, content_type} dicts.

    Examples:
        find_files("docker-compose")
        find_files("config.py", source_name="frigate")
        find_files(".yml", language="yaml", content_type="docs")
    """
    conditions = [FieldCondition(key="filename", match=MatchText(text=filename))]
    if source_name:
        conditions.append(FieldCondition(key="source_name", match=MatchValue(value=source_name)))
    if language:
        conditions.append(FieldCondition(key="language", match=MatchValue(value=language)))
    if content_type:
        conditions.append(FieldCondition(key="content_type", match=MatchValue(value=content_type)))

    query_filter = Filter(must=conditions)

    # Over-fetch to account for deduplication across chunks
    try:
        results, _ = qdrant.scroll(
            collection_name=QDRANT_COLLECTION,
            scroll_filter=query_filter,
            limit=limit * 5,
            with_payload=True,
            with_vectors=False,
        )
    except Exception as e:
        return _error("Qdrant", e)

    # Deduplicate by (source_name, filename) since files are split into chunks
    seen = set()
    files = []
    for point in results:
        payload = get_payload(point)
        key = (payload.get("source_name"), payload.get("filename"))
        if key in seen:
            continue
        seen.add(key)
        files.append({
            "source_name": payload.get("source_name"),
            "filename": payload.get("filename"),
            "language": payload.get("language"),
            "content_type": payload.get("content_type"),
        })
        if len(files) >= limit:
            break

    return files


@mcp.tool()
def search_sources(
    tags: list[str] | None = None,
    source_type: str | None = None,
) -> list[dict]:
    """Search indexed sources by tags and/or type.

    Args:
        tags: Filter to sources matching ALL given tags.
        source_type: Filter by source type (e.g. "git", "crawl").

    Examples:
        search_sources(tags=["homelab"])
        search_sources(tags=["ai", "python"])
        search_sources(source_type="crawl")
    """
    try:
        return pg_search_sources(tags=tags, source_type=source_type)
    except Exception as e:
        return _error("Postgres", e)
