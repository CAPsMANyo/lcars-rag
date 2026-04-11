# LCARS RAG

Self-hosted code/docs indexing pipeline: git repos + local sources → CocoIndex embedding flow → vector store (Qdrant or Postgres pgvector) → Flask dashboard + embedded MCP server for semantic search.

## Stack

- **Python ≥ 3.12**, managed with **uv** (frozen lockfile — always use `uv sync` / `uv run`, never bare `pip`).
- **Build:** Hatchling. Git dependencies require `tool.hatch.metadata.allow-direct-references = true` (already set) because `lcars-mcp-server` is pulled from GitHub.
- **No linter/formatter/test framework is configured** in `pyproject.toml`. Don't invent a `pytest` / `ruff` / `black` invocation — there's nothing to run. If you need to verify changes, exercise the code path directly.
- **Web:** Flask app composed under Starlette + uvicorn so the embedded FastMCP server can be mounted at `/mcp/http` and `/mcp/sse` alongside the dashboard routes.

## Layout

`src/lcars_rag/`:
- `config.py` — loads `.env`, `config.yml`, `patterns.yml`; exports constants.
- `flow.py` — CocoIndex flow: scan → chunk (omnichunk) → embed → export to Qdrant or pgvector.
- `sync_repos.py` — clones/pulls repos listed in `config.yml` (`lcars-sync-repos` entry point).
- `dashboard.py` — Flask UI (status, index monitor, sync log, skip report, MCP tools) + ASGI composition that mounts the MCP server (`lcars-dashboard` entry point).
- `chunking.py`, `scanning.py`, `patterns.py`, `symlinks.py`, `metadata.py`, `mcp_client.py`, `utils.py`.

Top-level:
- `config.yml` — declarative list of `git_sources` + `local_sources` to index.
- `patterns.yml` — include/exclude globs.
- `.env` — runtime secrets (DB URLs, embedding + optional reranking config, `LCARS_MCP_INTERNAL_URL`). See `.env.example`.
- `entrypoint.sh` — docker entrypoint; runs sync watcher, `cocoindex update -L`, and the dashboard as background processes.
- `docker-compose.yml` — services: `cocoindex-db` (postgres/pgvector), `qdrant`, `lcars-app`.

## Running

```bash
uv sync                                              # install
uv run lcars-sync-repos                              # one-shot repo sync
uv run cocoindex update src/lcars_rag/flow.py        # one-shot embed
uv run cocoindex update -L src/lcars_rag/flow.py     # live-watch embed
uv run cocoindex drop src/lcars_rag/flow.py          # drop index
uv run lcars-dashboard                               # dashboard on :5001 (LCARS_DASHBOARD_PORT)
```

Docker: `docker compose up -d` brings up the full stack.

## Conventions

- Flask routes live in `dashboard.py`; templates in `templates/`. When adding a page, wire it into the nav in the existing templates (`status.html`, `index_monitor.html`, `sync_log.html`, `skip_report.html`, `mcp_tools.html`).
- The dashboard is served through uvicorn/ASGI — don't reintroduce `app.run()` for production paths; it would break the mounted MCP server.
- Vector backend is selected by env (`VECTOR_BACKEND` / related settings in `.env.example`). Code that touches storage should handle both Qdrant and pgvector rather than assuming one.
- Configuration is declarative — prefer extending `config.yml` / `patterns.yml` / `.env` over hardcoding paths or sources.

## Workflow notes

- Treat `main` as protected. For features or refactors, cut a new branch first and leave changes uncommitted for review unless explicitly told otherwise.
- The embedded MCP server is a git dependency (`lcars-mcp-server @ git+https://github.com/CAPsMANyo/lcars-mcp-server.git@main`); bumping it requires `uv lock --upgrade-package lcars-mcp-server`.
