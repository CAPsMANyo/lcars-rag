"""Thin MCP client wrapper for the dashboard MCP test page."""

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client


async def _connect(url: str):
    """Return the appropriate client context manager based on URL path."""
    if "/sse" in url:
        return sse_client(url)
    return streamablehttp_client(url)


async def connect_and_list_tools(url: str) -> list[dict]:
    """Connect to an MCP server and return its tool definitions."""
    client_cm = await _connect(url)
    async with client_cm as (read_stream, write_stream, *_):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            return [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "inputSchema": t.inputSchema if hasattr(t, "inputSchema") else {},
                }
                for t in result.tools
            ]


async def call_tool(url: str, tool_name: str, arguments: dict) -> list[dict]:
    """Connect to an MCP server and invoke a tool."""
    client_cm = await _connect(url)
    async with client_cm as (read_stream, write_stream, *_):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return [
                {
                    "type": c.type,
                    "text": c.text if hasattr(c, "text") else None,
                }
                for c in result.content
            ]
