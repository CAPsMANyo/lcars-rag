"""CLI entry point for lcars-rag."""

import sys

import cocoindex

from lcars_rag.metadata import drop_source_metadata, sync_source_metadata


def main():
    cocoindex.init()

    if len(sys.argv) > 1 and sys.argv[1] == "drop":
        drop_source_metadata()
    else:
        sync_source_metadata()


if __name__ == "__main__":
    main()
