"""File pattern matching utilities."""

import fnmatch
import os


def matches_any(filepath: str, patterns: list[str]) -> bool:
    """Check if a relative filepath matches any glob pattern."""
    return first_matching_pattern(filepath, patterns) is not None


def first_matching_pattern(filepath: str, patterns: list[str]) -> str | None:
    """Return the first pattern that matches the filepath, or None."""
    for pat in patterns:
        if fnmatch.fnmatch(filepath, pat):
            return pat
        # fnmatch doesn't handle **/ at root level -- strip prefix
        # so "foo.png" matches "**/*.png"
        if pat.startswith("**/") and fnmatch.fnmatch(filepath, pat[3:]):
            return pat
        # Check just the filename for non-path patterns
        if "/" not in pat and fnmatch.fnmatch(os.path.basename(filepath), pat):
            return pat
    return None


def build_patterns(source: dict, global_patterns: dict, filter_exclude: bool) -> dict:
    """Build combined include/exclude pattern lists for a source.

    Merges per-source patterns with global patterns from patterns.yml.
    """
    patterns = {"include": [], "exclude": []}

    if "include" in source:
        patterns["include"].extend(source["include"])

    if filter_exclude and global_patterns.get("exclude"):
        patterns["exclude"].extend(global_patterns["exclude"])

    if "exclude" in source:
        patterns["exclude"].extend(source["exclude"])

    return patterns
