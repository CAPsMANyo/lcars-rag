"""Shared utility functions."""

import re
from urllib.parse import urlparse

MAX_FILENAME_LENGTH = 200


def sanitize_filename(url: str) -> str:
    """Convert a URL path into a safe filename."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if parsed.query:
        path += "_" + parsed.query
    if not path:
        path = "index"
    path = re.sub(r"[^a-zA-Z0-9_\-]", "_", path)
    path = re.sub(r"_+", "_", path).strip("_")
    if len(path) > MAX_FILENAME_LENGTH:
        path = path[:MAX_FILENAME_LENGTH]
    return path + ".md"
