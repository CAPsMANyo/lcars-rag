# LCARS RAG

A fully self-hosted RAG embedding pipeline for code and documentation.

## Why

I was frustrated with the size limitations of Claude Projects and the reliance on Anthropic's infrastructure for knowledge bases. LLM web search and context libraries like Context7 are less token-efficient than a proper vector database, which matters when running VRAM-limited self-hosted models. They also depend on external API calls and are limited to whatever the community has indexed.

I decided to build a self-hosted alternative. Sources are defined in a config file, synced and embedded using any OpenAI-compatible endpoint, and queried through a local MCP server. The entire knowledge base is rebuildable from a single pipeline run and managed entirely in code.

## What It Does

Clones git repos, chunks content, and indexes it into Qdrant or PostgreSQL (pgvector). Paired with [lcars-mcp-server](https://github.com/CAPsMANyo/lcars-mcp-server), it provides semantic search over your codebase and docs from any MCP-compatible client. Includes a dashboard for status, sync logs, and skip reports.

## Prerequisites

- Python 3.12+
- PostgreSQL with pgvector extension
- Qdrant (optional, falls back to pgvector)
- An OpenAI-compatible embedding API

## Setup

1. Clone the repo
2. Copy `.env.example` to `.env` and configure
3. Install dependencies: `uv sync`
4. Start required services (see [Docker](#docker))

## Configuration

- `.env` -- runtime settings (database URLs, embedding API, filtering, chunking)
- `config.yml` -- git source repositories to sync and embed
- `patterns.yml` -- file include/exclude glob patterns

## Usage

Sync git repositories:

```
uv run lcars-sync-repos
```

Run the embedding pipeline (one-shot):

```
uv run cocoindex update src/lcars_rag/flow.py
```

Run with live monitoring (watches for file changes):

```
uv run cocoindex update -L src/lcars_rag/flow.py
```

Drop and rebuild:

```
uv run cocoindex drop src/lcars_rag/flow.py
```

Start the dashboard:

```
uv run lcars-dashboard
```

The dashboard runs at `http://localhost:5001` (configurable via `LCARS_DASHBOARD_PORT` env var) and provides:

- **Status** (`/`) -- health of embedding API, PostgreSQL, Qdrant, and background processes
- **Index Monitor** (`/index`) -- live status and logs from the cocoindex process, with a one-shot re-index button
- **Sync Log** (`/sync-log`) -- live tail of the repo sync log
- **Skip Report** (`/skip-report`) -- files excluded from embedding with reasons

## Docker

### Infrastructure Services

Start the backing services (PostgreSQL with pgvector and Qdrant):

```
docker compose up -d cocoindex-db qdrant
```

### Dashboard Container

Build and run the dashboard:

```
docker compose up -d lcars-app
```

The `lcars-app` container runs both the dashboard and `cocoindex update -L` for continuous live indexing. It mounts `data/` and `config.yml` from the host. To index local directories, add volume mounts matching your `local_sources` paths in `config.yml`. An embedding backend (e.g. Ollama, TEI, or any OpenAI-compatible endpoint) must be reachable from the container at the address set in `EMBEDDING_API_ADDRESS`.

### All Services

```
docker compose up -d
```

## Data Flow

```
sync_repos  -> clones/updates git repos into ./data/
flow.py     -> reads ./data/, chunks, embeds, exports to Qdrant or pgvector
dashboard   -> serves status, logs, and skip reports
```

## Project Structure

```
src/lcars_rag/
  config.py         - configuration loading and constants
  flow.py           - CocoIndex embedding flow definition
  chunking.py       - omnichunk integration
  metadata.py       - source metadata management (PostgreSQL)
  patterns.py       - file pattern matching utilities
  symlinks.py       - symlink loop detection
  scanning.py       - file scanning and skip reporting
  sync_repos.py     - git repository synchronization
  dashboard.py      - Flask web UI (status, logs, skip report)
  utils.py          - shared utilities
```

## Acknowledgments

Built on top of these great projects:

- [CocoIndex](https://github.com/cocoindex-io/cocoindex) -- embedding pipeline framework with live update support
- [omnichunk](https://github.com/oguzhankir/omnichunk) -- structure-aware chunking toolkit used by the pipeline
- [Qdrant](https://github.com/qdrant/qdrant) -- vector search engine
- [Qdrant MCP Server](https://github.com/qdrant/mcp-server-qdrant) -- official MCP server for Qdrant
- [FastMCP](https://github.com/jlowin/fastmcp) -- fast, Pythonic MCP server framework
