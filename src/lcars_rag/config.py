"""Configuration loading and constants."""

import os
import logging

import yaml
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def load_config():
    """Load configuration from config.yml."""
    with open("config.yml", "r") as f:
        return yaml.safe_load(f)


def load_patterns():
    """Load file include/exclude patterns from patterns.yml."""
    if os.path.exists("patterns.yml"):
        with open("patterns.yml", "r") as f:
            return yaml.safe_load(f)
    return {"docs": [], "exclude": []}


CONFIG = load_config()
SETTINGS = CONFIG.get("settings", {})
PATTERNS = load_patterns()


def load_all_sources():
    """Merge git_sources and local_sources into a single list."""
    sources = []
    for s in CONFIG.get("git_sources", []):
        s.setdefault("source_type", "git")
        sources.append(s)
    for s in CONFIG.get("local_sources", []):
        s.setdefault("source_type", "local")
        sources.append(s)
    return sources


BASE_DIR = os.environ.get("BASE_DIR", "./data")
REPOS_DIR = os.path.join(BASE_DIR, "git")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

for _d in (REPOS_DIR, LOGS_DIR):
    os.makedirs(_d, exist_ok=True)

# Secrets and connection strings from .env
QDRANT_URL = os.environ.get("QDRANT_URL")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL")
EMBEDDING_API_ADDRESS = os.environ.get("EMBEDDING_API_ADDRESS")
COCOINDEX_DATABASE_URL = os.environ.get("COCOINDEX_DATABASE_URL", "")

# Tunable settings from config.yml
EMBEDDING_DIMENSION = int(SETTINGS.get("embedding_dimension", 1024))
USE_EXCLUDE_PATTERNS = bool(SETTINGS.get("use_exclude_patterns", True))
MAX_FILE_SIZE = int(SETTINGS.get("max_file_size", 100000))
CHUNK_SIZE = int(SETTINGS.get("chunk_size", 1000))
CHUNK_OVERLAP = int(SETTINGS.get("chunk_overlap", 200))
REFRESH_INTERVAL = int(SETTINGS.get("refresh_interval", 30))
SYNC_INTERVAL = int(SETTINGS.get("sync_interval", 3600))
METADATA_TABLE = SETTINGS.get("metadata_table", "source_metadata")

LANGUAGE_MAP = {
    ".py": "python", ".rs": "rust", ".js": "javascript", ".ts": "typescript",
    ".jsx": "javascript", ".tsx": "typescript",
    ".java": "java", ".go": "go", ".rb": "ruby", ".cpp": "cpp", ".c": "c",
    ".cs": "csharp", ".php": "php", ".swift": "swift", ".kt": "kotlin",
    ".sh": "bash", ".zsh": "bash",
    ".yml": "yaml", ".yaml": "yaml", ".json": "json", ".xml": "xml",
    ".html": "html", ".css": "css", ".sql": "sql",
    ".md": "markdown", ".mdx": "markdown", ".adoc": "asciidoc",
    ".txt": "text", ".toml": "toml", ".ini": "ini",
}
