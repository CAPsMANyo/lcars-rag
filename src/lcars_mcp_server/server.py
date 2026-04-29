"""LCARS MCP Server - Search code and doc embeddings in Qdrant."""

import logging

from fastmcp import FastMCP
from fastmcp.server.lifespan import lifespan

logger = logging.getLogger(__name__)


@lifespan
async def app_lifespan(server):
    from lcars_mcp_server.postgres import pool
    from lcars_mcp_server.qdrant import qdrant
    from lcars_mcp_server.settings import QDRANT_COLLECTION

    # Validate postgres connection
    try:
        with pool.connection() as conn:
            conn.execute("SELECT 1")
        logger.info("Postgres connection verified")
    except Exception as e:
        logger.error("Postgres connection failed: %s", e)

    # Validate qdrant connection
    try:
        qdrant.get_collection(QDRANT_COLLECTION)
        logger.info("Qdrant collection '%s' verified", QDRANT_COLLECTION)
    except Exception as e:
        logger.error("Qdrant connection failed: %s", e)

    yield

    pool.close()
    logger.info("Postgres pool closed")


mcp = FastMCP("lcars-mcp-server", lifespan=app_lifespan)

import lcars_mcp_server.tools  # noqa: E402, F401
