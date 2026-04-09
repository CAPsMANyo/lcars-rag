"""Custom chunking using omnichunk for structure-aware text splitting."""

import dataclasses

import cocoindex
from omnichunk import Chunker


@dataclasses.dataclass
class ChunkResult:
    location: cocoindex.Range
    text: str


_chunker_cache: dict[tuple[int, int], Chunker] = {}


def _get_chunker(chunk_size: int, chunk_overlap: int) -> Chunker:
    key = (chunk_size, chunk_overlap)
    if key not in _chunker_cache:
        _chunker_cache[key] = Chunker(
            max_chunk_size=chunk_size,
            overlap=chunk_overlap,
            size_unit="chars",
        )
    return _chunker_cache[key]


@cocoindex.op.function(
    arg_relationship=(cocoindex.op.ArgRelationship.CHUNKS_BASE_TEXT, "content"),
)
def omnichunk_split(
    content: str,
    filename: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[ChunkResult]:
    """Split content using omnichunk's structure-aware chunking."""
    chunker = _get_chunker(chunk_size, chunk_overlap)
    chunks = chunker.chunk(filename, content)
    return [
        ChunkResult(
            location=(c.byte_range.start, c.byte_range.end),
            text=c.text,
        )
        for c in chunks
    ]
