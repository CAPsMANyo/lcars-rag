"""Symlink loop detection for directory traversal."""

import logging
import os

logger = logging.getLogger(__name__)


def is_symlink_loop(dir_path: str, root: str, source_root: str) -> bool:
    """Check if a symlinked directory creates a loop back to an ancestor."""
    if not os.path.islink(dir_path):
        return False
    try:
        real_target = os.path.realpath(dir_path)
    except OSError:
        return True
    real_root = os.path.realpath(root)
    real_source = os.path.realpath(source_root)
    for ancestor in (real_root, real_source):
        if ancestor == real_target or ancestor.startswith(real_target + os.sep):
            return True
    return False


def scan_symlink_loops(source_name: str, source_path: str) -> list[str]:
    """Walk a source directory and return glob patterns for symlink loops."""
    loops = []
    for root, dirs, _files in os.walk(source_path, followlinks=True):
        safe_dirs = []
        for d in dirs:
            dir_path = os.path.join(root, d)
            if is_symlink_loop(dir_path, root, source_path):
                rel = os.path.relpath(dir_path, source_path)
                logger.warning("Symlink loop detected in %s: %s", source_name, rel)
                loops.append(f"{rel}/**")
            else:
                safe_dirs.append(d)
        dirs[:] = safe_dirs
    return loops
