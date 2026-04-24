"""Source metadata management in PostgreSQL."""

import json
import logging

import psycopg
from psycopg import sql

from lcars_rag.config import (
    BASE_DIR,
    COCOINDEX_DATABASE_URL,
    USE_EXCLUDE_PATTERNS,
    METADATA_TABLE,
    PATTERNS,
    load_all_sources,
)
from lcars_rag.scanning import count_source_files

logger = logging.getLogger(__name__)

_TABLE = sql.Identifier(METADATA_TABLE)


def init_metadata_table():
    """Create the source_metadata table if it doesn't exist."""
    with psycopg.connect(COCOINDEX_DATABASE_URL) as conn:
        conn.execute(sql.SQL("""
            CREATE TABLE IF NOT EXISTS {} (
                source_name TEXT PRIMARY KEY,
                source_type TEXT,
                url TEXT,
                path TEXT,
                tags JSONB,
                file_count INTEGER DEFAULT 0,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """).format(_TABLE))
        conn.execute(sql.SQL(
            "ALTER TABLE {} ADD COLUMN IF NOT EXISTS path TEXT"
        ).format(_TABLE))
        conn.commit()
    logger.info("Metadata table '%s' ready", METADATA_TABLE)


def sync_source_metadata():
    """Sync source metadata from config.yml into postgres."""
    init_metadata_table()
    sources = load_all_sources()
    with psycopg.connect(COCOINDEX_DATABASE_URL) as conn:
        for source in sources:
            source_name = source["name"]
            file_count = count_source_files(
                source, BASE_DIR, PATTERNS, USE_EXCLUDE_PATTERNS, PATTERNS,
            )
            conn.execute(sql.SQL("""
                INSERT INTO {}
                    (source_name, source_type, url, path, tags, file_count, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (source_name) DO UPDATE SET
                    source_type = EXCLUDED.source_type,
                    url = EXCLUDED.url,
                    path = EXCLUDED.path,
                    tags = EXCLUDED.tags,
                    file_count = EXCLUDED.file_count,
                    updated_at = NOW()
            """).format(_TABLE), (
                source_name,
                source.get("source_type", ""),
                source.get("url", ""),
                source.get("path", ""),
                json.dumps(source.get("tags", [])),
                file_count,
            ))
            logger.info("Metadata synced: %s (%d files)", source_name, file_count)

        current_names = [s["name"] for s in sources]
        conn.execute(
            sql.SQL("DELETE FROM {} WHERE source_name != ALL(%s)").format(_TABLE),
            (current_names,),
        )
        conn.commit()
    logger.info("Source metadata sync complete")


def drop_source_metadata():
    """Drop the source_metadata table."""
    try:
        with psycopg.connect(COCOINDEX_DATABASE_URL) as conn:
            conn.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(_TABLE))
            conn.commit()
        logger.info("Dropped metadata table '%s'", METADATA_TABLE)
    except Exception as e:
        logger.error("Failed to drop metadata table: %s", e)
