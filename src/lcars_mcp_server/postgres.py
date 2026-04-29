"""Postgres connection and source metadata queries."""

import json

from psycopg import sql
from psycopg_pool import ConnectionPool

from lcars_mcp_server.settings import POSTGRES_URL, METADATA_TABLE

pool = ConnectionPool(POSTGRES_URL, min_size=1, max_size=5)

_TABLE = sql.Identifier(METADATA_TABLE)
_SELECT_COLS = sql.SQL("source_name, source_type, url, tags, file_count")


def get_sources(source_name: str | None = None) -> list[dict]:
    """Return source metadata rows, optionally filtered by name."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            if source_name:
                cur.execute(
                    sql.SQL("SELECT {} FROM {} WHERE source_name = %s ORDER BY source_name").format(
                        _SELECT_COLS, _TABLE
                    ),
                    (source_name,),
                )
            else:
                cur.execute(
                    sql.SQL("SELECT {} FROM {} ORDER BY source_name").format(
                        _SELECT_COLS, _TABLE
                    )
                )
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            return [_row_to_dict(columns, row) for row in rows]


def get_tags(source_name: str | None = None) -> list[str]:
    """Return sorted unique tags, optionally filtered by source."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            if source_name:
                cur.execute(
                    sql.SQL(
                        "SELECT DISTINCT jsonb_array_elements_text(tags) AS tag "
                        "FROM {} WHERE source_name = %s ORDER BY tag"
                    ).format(_TABLE),
                    (source_name,),
                )
            else:
                cur.execute(
                    sql.SQL(
                        "SELECT DISTINCT jsonb_array_elements_text(tags) AS tag "
                        "FROM {} ORDER BY tag"
                    ).format(_TABLE)
                )
            return [row[0] for row in cur.fetchall()]


def get_source_names_by_tags(tags: list[str]) -> list[str]:
    """Return source_names where ALL given tags are present."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT source_name FROM {} WHERE tags @> %s ORDER BY source_name").format(
                    _TABLE
                ),
                (json.dumps(tags),),
            )
            return [row[0] for row in cur.fetchall()]


def get_metadata_map(source_names: list[str]) -> dict[str, dict]:
    """Batch-fetch metadata for a list of source_names. Returns {name: {...}}."""
    if not source_names:
        return {}
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT {} FROM {} WHERE source_name = ANY(%s)").format(
                    _SELECT_COLS, _TABLE
                ),
                (source_names,),
            )
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            return {row[0]: _row_to_dict(columns, row) for row in rows}


def search_sources(tags: list[str] | None = None, source_type: str | None = None) -> list[dict]:
    """Filter sources by tags and/or type."""
    clauses = []
    params = []
    if tags:
        clauses.append("tags @> %s")
        params.append(json.dumps(tags))
    if source_type:
        clauses.append("source_type = %s")
        params.append(source_type)

    where = sql.SQL(" WHERE " + " AND ".join(clauses)) if clauses else sql.SQL("")
    query = sql.SQL("SELECT {} FROM {}").format(_SELECT_COLS, _TABLE) + where + sql.SQL(" ORDER BY source_name")

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params if params else None)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            return [_row_to_dict(columns, row) for row in rows]


def _row_to_dict(columns: list[str], row: tuple) -> dict:
    d = dict(zip(columns, row))
    if isinstance(d.get("tags"), str):
        try:
            d["tags"] = json.loads(d["tags"])
        except (json.JSONDecodeError, TypeError):
            d["tags"] = []
    elif d.get("tags") is None:
        d["tags"] = []
    return d
