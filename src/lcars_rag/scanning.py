"""File scanning, skip detection, and report generation."""

import json
import logging
import os
from datetime import datetime, timezone

from lcars_rag.config import BASE_DIR, MAX_FILE_SIZE, REPOS_DIR
from lcars_rag.patterns import first_matching_pattern, matches_any
from lcars_rag.symlinks import is_symlink_loop, scan_symlink_loops

logger = logging.getLogger(__name__)


def count_source_files(source: dict, base_dir: str, patterns: dict,
                       filter_exclude: bool, global_patterns: dict) -> int:
    """Count indexable files for a source using the same filtering logic as the flow."""
    from lcars_rag.patterns import build_patterns

    source_name = source["name"]
    if source.get("source_type") == "local":
        source_path = source["path"]
    else:
        source_path = os.path.join(REPOS_DIR, source_name)
    if not os.path.exists(source_path):
        return 0

    p = build_patterns(source, global_patterns, filter_exclude)
    symlink_loops = scan_symlink_loops(source_name, source_path)
    p["exclude"].extend(symlink_loops)

    max_size = source.get("max_file_size", MAX_FILE_SIZE)

    count = 0
    for root, dirs, files in os.walk(source_path, followlinks=True):
        dirs[:] = [d for d in dirs
                   if not is_symlink_loop(os.path.join(root, d), root, source_path)]
        for fname in files:
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, source_path)

            if p["exclude"] and matches_any(rel_path, p["exclude"]):
                continue
            if p["include"] and not matches_any(rel_path, p["include"]):
                continue
            try:
                if max_size > 0 and os.path.getsize(full_path) > max_size:
                    continue
            except OSError:
                logger.debug("Cannot stat file: %s", full_path)
                continue
            count += 1
    return count


def scan_skipped_files(source_name: str, source_path: str,
                       include_patterns: list[str],
                       exclude_patterns: list[str],
                       max_file_size: int | None = None) -> list[dict]:
    """Walk a source directory and find all files that will be skipped.

    Each entry includes a 'reason':
      - 'excluded': matches an exclude pattern (includes matched_pattern)
      - 'not_included': doesn't match per-source include patterns
      - 'oversized': exceeds max_file_size
    """
    limit = max_file_size if max_file_size is not None else MAX_FILE_SIZE
    skipped = []

    for root, dirs, files in os.walk(source_path, followlinks=True):
        dirs[:] = [d for d in dirs
                   if not is_symlink_loop(os.path.join(root, d), root, source_path)]
        for fname in files:
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, source_path)

            if exclude_patterns:
                matched = first_matching_pattern(rel_path, exclude_patterns)
                if matched:
                    skipped.append({
                        "source": source_name,
                        "file": rel_path,
                        "reason": "excluded",
                        "matched_pattern": matched,
                    })
                    continue

            if include_patterns and not matches_any(rel_path, include_patterns):
                skipped.append({
                    "source": source_name,
                    "file": rel_path,
                    "reason": "not_included",
                })
                continue

            if limit > 0:
                try:
                    size = os.path.getsize(full_path)
                except OSError:
                    logger.debug("Cannot stat file: %s", full_path)
                    continue
                if size > limit:
                    skipped.append({
                        "source": source_name,
                        "file": rel_path,
                        "reason": "oversized",
                        "size_bytes": size,
                        "size_human": f"{size / 1024:.1f}KB" if size < 1048576 else f"{size / 1048576:.1f}MB",
                        "max_file_size_needed": size,
                    })
                    continue

    return skipped


def write_skip_report(all_skipped: list[dict], source_limits: dict[str, int]):
    """Write skipped files report to skipped_files.json, grouped by source."""
    sources = {}
    reason_totals = {}

    for entry in all_skipped:
        src = entry["source"]
        reason = entry["reason"]
        if src not in sources:
            sources[src] = {
                "max_file_size": source_limits.get(src, MAX_FILE_SIZE),
                "count": 0,
                "counts_by_reason": {},
                "files": [],
            }
        sources[src]["count"] += 1
        sources[src]["counts_by_reason"][reason] = sources[src]["counts_by_reason"].get(reason, 0) + 1
        reason_totals[reason] = reason_totals.get(reason, 0) + 1

        file_entry = {"file": entry["file"], "reason": reason}
        if "matched_pattern" in entry:
            file_entry["matched_pattern"] = entry["matched_pattern"]
        if "size_bytes" in entry:
            file_entry["size_bytes"] = entry["size_bytes"]
            file_entry["size_human"] = entry["size_human"]
            file_entry["max_file_size_needed"] = entry["max_file_size_needed"]

        sources[src]["files"].append(file_entry)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "max_file_size_default": MAX_FILE_SIZE,
        "total_skipped": len(all_skipped),
        "counts_by_reason": reason_totals,
        "sources": sources,
    }

    report_path = os.path.join(BASE_DIR, "skipped_files.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info("Skipped %d files (see %s)", len(all_skipped), report_path)
