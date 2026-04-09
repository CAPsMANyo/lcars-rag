"""CocoIndex embedding flow definition."""

import datetime
import logging
import os
import sys
from pathlib import Path

import cocoindex

from lcars_rag.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBEDDING_API_ADDRESS,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    REFRESH_INTERVAL,
    REPOS_DIR,
    USE_EXCLUDE_PATTERNS,
    LANGUAGE_MAP,
    MAX_FILE_SIZE,
    PATTERNS,
    QDRANT_API_KEY,
    QDRANT_URL,
    load_all_sources,
)
from lcars_rag.chunking import omnichunk_split
from lcars_rag.metadata import drop_source_metadata, sync_source_metadata
from lcars_rag.patterns import build_patterns
from lcars_rag.scanning import scan_skipped_files, write_skip_report
from lcars_rag.symlinks import scan_symlink_loops

logger = logging.getLogger(__name__)

if QDRANT_URL:
    QDRANT_CONN = cocoindex.add_auth_entry(
        "QdrantConnection",
        cocoindex.storages.QdrantConnection(
            grpc_url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
        ),
    )


@cocoindex.op.function()
def get_content_type(filename: str) -> str:
    """Determine if file is 'docs' or 'code' based on doc patterns."""
    doc_patterns = PATTERNS.get("docs", [])
    if not doc_patterns:
        return "code"
    basename = Path(filename).name
    for pat in doc_patterns:
        import fnmatch
        simple = pat.removeprefix("**/")
        if fnmatch.fnmatch(basename, simple):
            return "docs"
    return "code"


@cocoindex.op.function()
def get_language(filename: str) -> str:
    """Determine programming language from file extension."""
    ext = Path(filename).suffix.lower()
    return LANGUAGE_MAP.get(ext, "other")


@cocoindex.transform_flow()
def text_to_embedding(text: cocoindex.DataSlice[str]) -> cocoindex.DataSlice[list[float]]:
    """Embed text using OpenAI-compatible endpoint."""
    return text.transform(
        cocoindex.functions.EmbedText(
            api_type=cocoindex.LlmApiType.OPENAI,
            model=EMBEDDING_MODEL,
            address=EMBEDDING_API_ADDRESS,
            output_dimension=EMBEDDING_DIMENSION,
        )
    )


@cocoindex.op.function()
def log_file(filename: str) -> str:
    """Log which file is being processed."""
    logger.info("Processing: %s", filename)
    return filename


@cocoindex.flow_def(name="lcars_embeddings")
def embedding_flow(flow_builder: cocoindex.FlowBuilder, data_scope: cocoindex.DataScope):
    """Embed all sources from config.yml."""

    embeddings = data_scope.add_collector()
    all_skipped = []
    source_limits = {}
    sources_added = 0

    for source in load_all_sources():
        source_name = source["name"]
        if source.get("source_type") == "local":
            path = source["path"]
        else:
            path = os.path.join(REPOS_DIR, source_name)

        if not os.path.exists(path):
            logger.warning("Skipping %s, path does not exist: %s", source_name, path)
            continue

        sources_added += 1
        logger.info("Adding source: %s from %s", source_name, path)

        patterns = build_patterns(source, PATTERNS, USE_EXCLUDE_PATTERNS)

        # Detect and exclude symlink loops before scanning
        symlink_loops = scan_symlink_loops(source_name, path)
        if symlink_loops:
            patterns["exclude"].extend(symlink_loops)
            logger.info("Excluding %d symlink loop(s) in %s", len(symlink_loops), source_name)

        # Scan for skipped files and add oversized files to excludes
        source_max = source.get("max_file_size", MAX_FILE_SIZE)
        source_limits[source_name] = source_max
        skipped = scan_skipped_files(
            source_name, path, patterns["include"], patterns["exclude"],
            max_file_size=source_max,
        )
        if skipped:
            for entry in skipped:
                if entry["reason"] == "oversized":
                    patterns["exclude"].append(entry["file"])
            logger.info("Skipping %d files in %s", len(skipped), source_name)
            all_skipped.extend(skipped)

        logger.info("Starting to process source: %s", source_name)
        data_scope[f"source_{source_name}"] = flow_builder.add_source(
            cocoindex.sources.LocalFile(
                path=path,
                included_patterns=patterns["include"] or None,
                excluded_patterns=patterns["exclude"] or None,
            ),
            refresh_interval=datetime.timedelta(seconds=REFRESH_INTERVAL),
        )

        with data_scope[f"source_{source_name}"].row() as file:
            file["_logged"] = file["filename"].transform(log_file)
            file["content_type"] = file["filename"].transform(get_content_type)
            file["language"] = file["filename"].transform(get_language)

            file["chunks"] = file["content"].transform(
                omnichunk_split,
                file["filename"],
                chunk_size=CHUNK_SIZE,
                chunk_overlap=CHUNK_OVERLAP,
            )
            with file["chunks"].row() as chunk:
                chunk["embedding"] = text_to_embedding(chunk["text"])
                collect_args = {
                    "source_name": source_name,
                    "content_type": file["content_type"],
                    "language": file["language"],
                    "filename": file["filename"],
                    "chunk_location": chunk["location"],
                    "chunk_text": chunk["text"],
                    "embedding": chunk["embedding"],
                }

                if QDRANT_URL:
                    collect_args["id"] = cocoindex.GeneratedField.UUID

                embeddings.collect(**collect_args)

    if all_skipped:
        write_skip_report(all_skipped, source_limits)

    if sources_added == 0:
        logger.warning("No sources found on disk. Skipping export.")
        return

    if QDRANT_URL:
        embeddings.export(
            "embeddings",
            cocoindex.storages.Qdrant(
                collection_name="cocoindex",
                connection=QDRANT_CONN,
            ),
            primary_key_fields=["id"],
        )
    else:
        embeddings.export(
            "embeddings",
            cocoindex.targets.Postgres(table_name="lcars_embeddings"),
            primary_key_fields=["source_name", "filename", "chunk_location"],
            vector_indexes=[
                cocoindex.VectorIndexDef(
                    field_name="embedding",
                    metric=cocoindex.VectorSimilarityMetric.COSINE_SIMILARITY,
                )
            ],
        )


# CocoIndex CLI imports this module (not as __main__), so module-level
# hooks are the only way to run metadata logic alongside cocoindex operations.
if __name__ != "__main__":
    if "drop" in sys.argv:
        drop_source_metadata()
    else:
        sync_source_metadata()
