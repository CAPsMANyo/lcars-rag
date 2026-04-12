# LCARS RAG

Self-hosted code/docs indexing pipeline: git repos + local sources → CocoIndex embedding flow → vector store (Qdrant or Postgres pgvector) → Flask dashboard for monitoring and management.

## Stack

- **Python ≥ 3.12**, managed with **uv** (frozen lockfile — always use `uv sync` / `uv run`, never bare `pip`).
- **Build:** Hatchling.
- **No linter/formatter/test framework is configured** in `pyproject.toml`. Don't invent a `pytest` / `ruff` / `black` invocation — there's nothing to run. If you need to verify changes, exercise the code path directly.
- **Web:** Flask app served via uvicorn (ASGI via `WsgiToAsgi` wrapper). The MCP server runs externally — the dashboard connects to it as a client for the MCP tools test page.

## Layout

`src/lcars_rag/`:
- `config.py` — loads `.env`, `config.yml`, `patterns.yml`; exports constants. Has `reload_config()` for live config updates.
- `flow.py` — CocoIndex flow: scan → chunk (omnichunk) → embed → export to Qdrant or pgvector.
- `sync_repos.py` — clones/pulls repos listed in `config.yml` (`lcars-sync-repos` entry point).
- `dashboard.py` — Flask UI (status, index monitor, sync log, skip report, config editor, MCP tools) served via uvicorn (`lcars-dashboard` entry point).
- `chunking.py`, `scanning.py`, `patterns.py`, `symlinks.py`, `metadata.py`, `mcp_client.py`, `utils.py`.

Top-level:
- `config.yml` — declarative list of `git_sources` + `local_sources` to index, plus `settings:` block for tunable parameters (embedding endpoint/model, chunk size, MCP server URL, etc.).
- `patterns.yml` — include/exclude globs.
- `.env` — runtime secrets only (DB URLs, API keys). See `.env.example`.
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

- Flask routes live in `dashboard.py`; templates in `templates/`. When adding a page, wire it into the nav in all existing templates (`status.html`, `index_monitor.html`, `sync_log.html`, `skip_report.html`, `config.html`, `mcp_tools.html`).
- The dashboard is served through uvicorn/ASGI — don't reintroduce `app.run()` for production paths.
- Vector backend is selected by env (`VECTOR_BACKEND` / related settings in `.env.example`). Code that touches storage should handle both Qdrant and pgvector rather than assuming one.
- Configuration is declarative — tunable settings live in `config.yml`, secrets in `.env`. Prefer extending `config.yml` / `patterns.yml` over hardcoding.

## Workflow notes

- Treat `main` as protected. For features or refactors, cut a new branch first and leave changes uncommitted for review unless explicitly told otherwise.
