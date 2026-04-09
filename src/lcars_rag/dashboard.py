"""LCARS Dashboard - web UI for status, reports, and index monitoring."""

import json
import os
from pathlib import Path

import requests as http_requests
from flask import Flask, render_template, request, jsonify

from lcars_rag.config import (
    BASE_DIR,
    COCOINDEX_DATABASE_URL,
    EMBEDDING_API_ADDRESS,
    LOGS_DIR,
    QDRANT_URL,
)

app = Flask(__name__, template_folder="../../templates")

REPORT_PATH = os.path.join(BASE_DIR, "skipped_files.json")


# ---------------------------------------------------------------------------
# Process management helpers
# ---------------------------------------------------------------------------


def check_process_status(pid_file):
    """Return (status, pid) tuple."""
    try:
        pid = int(open(pid_file).read().strip())
    except (FileNotFoundError, ValueError):
        return "not_started", None
    try:
        os.kill(pid, 0)
        return "running", pid
    except ProcessLookupError:
        return "stopped", pid
    except PermissionError:
        return "running", pid


def tail_log(log_file, lines=200, offset=0):
    """Return (content, new_offset) tuple."""
    try:
        with open(log_file, "r") as f:
            if offset > 0:
                f.seek(offset)
                content = f.read()
            else:
                all_lines = f.readlines()
                content = "".join(all_lines[-lines:])
            return content, f.tell()
    except FileNotFoundError:
        return "", 0


# ---------------------------------------------------------------------------
# Status page (default landing page)
# ---------------------------------------------------------------------------

COCOINDEX_PID_FILE = os.path.join(LOGS_DIR, "cocoindex.pid")
SYNC_WATCH_PID_FILE = os.path.join(LOGS_DIR, "sync_watch.pid")
SYNC_STATE_FILE = os.path.join(LOGS_DIR, "sync_state.json")


def _check_embedding():
    """Check if the embedding endpoint is reachable."""
    if not EMBEDDING_API_ADDRESS:
        return {"status": "unconfigured", "detail": "EMBEDDING_API_ADDRESS not set"}
    # TEI exposes model info at the base URL (strip /v1 suffix)
    base = EMBEDDING_API_ADDRESS.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    try:
        r = http_requests.get(f"{base}/info", timeout=5)
        if r.ok:
            return {"status": "ok", "detail": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:200]}
        return {"status": "error", "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _check_postgres():
    """Check if PostgreSQL is reachable."""
    if not COCOINDEX_DATABASE_URL:
        return {"status": "unconfigured", "detail": "COCOINDEX_DATABASE_URL not set"}
    try:
        import psycopg
        with psycopg.connect(COCOINDEX_DATABASE_URL, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"status": "ok", "detail": "connected"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _check_qdrant():
    """Check if Qdrant is reachable."""
    if not QDRANT_URL:
        return {"status": "unconfigured", "detail": "QDRANT_URL not set"}
    # QDRANT_URL is gRPC (e.g. http://qdrant:6334), REST is on 6333
    rest_url = QDRANT_URL.replace(":6334", ":6333")
    try:
        r = http_requests.get(f"{rest_url}/healthz", timeout=5)
        if r.ok:
            return {"status": "ok", "detail": "healthy"}
        return {"status": "error", "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _check_process(pid_file, name):
    """Check a background process by PID file."""
    status, pid = check_process_status(pid_file)
    return {"status": status, "pid": pid, "name": name}


@app.route("/")
def status_page():
    return render_template("status.html")


@app.route("/api/status")
def api_status():
    return jsonify({
        "embedding": _check_embedding(),
        "postgres": _check_postgres(),
        "qdrant": _check_qdrant(),
        "cocoindex": _check_process(COCOINDEX_PID_FILE, "cocoindex"),
        "sync": _get_sync_state(),
        "sync_watcher": _check_process(SYNC_WATCH_PID_FILE, "sync_watcher"),
    })


def _get_sync_state():
    """Read sync state from the JSON file written by entrypoint."""
    try:
        with open(SYNC_STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"status": "unknown", "last_completed": None, "sync_interval": None}


@app.route("/api/sync/state")
def sync_state():
    return jsonify(_get_sync_state())


@app.route("/api/sync/trigger", methods=["POST"])
def trigger_sync():
    """Write a trigger file so the sync watcher picks it up."""
    state = _get_sync_state()
    if state.get("status") == "running":
        return jsonify({"ok": False, "error": "Sync already running"}), 409
    Path("/tmp/sync_trigger").touch()
    return jsonify({"ok": True})


@app.route("/api/sync/interval", methods=["POST"])
def set_sync_interval():
    """Update the sync interval. Writes to sync_state.json so the watcher picks it up."""
    data = request.get_json()
    interval = data.get("interval")
    if interval is None or not isinstance(interval, (int, float)) or interval < 60:
        return jsonify({"error": "interval must be a number >= 60"}), 400
    interval = int(interval)
    # Read current state and update interval
    state = _get_sync_state()
    state["sync_interval"] = interval
    with open(SYNC_STATE_FILE, "w") as f:
        json.dump(state, f)
    return jsonify({"ok": True, "sync_interval": interval})


# ---------------------------------------------------------------------------
# Index monitor routes
# ---------------------------------------------------------------------------

COCOINDEX_LOG = os.path.join(LOGS_DIR, "cocoindex.log")
SYNC_LOG = os.path.join(LOGS_DIR, "sync.log")


@app.route("/sync-log")
def sync_log():
    return render_template("sync_log.html")


@app.route("/index")
def index_monitor():
    return render_template("index_monitor.html")


@app.route("/api/index/status")
def index_status():
    # Check if a one-shot update is running
    update_status, update_pid = check_process_status(COCOINDEX_UPDATE_PID_FILE)
    if update_status == "running":
        return jsonify({"status": "updating", "pid": update_pid})
    status, pid = check_process_status(COCOINDEX_PID_FILE)
    return jsonify({"status": status, "pid": pid})


COCOINDEX_UPDATE_PID_FILE = "/tmp/cocoindex_update.pid"


def _stop_cocoindex_daemon():
    """Stop the live cocoindex daemon if running."""
    status, pid = check_process_status(COCOINDEX_PID_FILE)
    if status == "running" and pid:
        import signal
        os.kill(pid, signal.SIGTERM)
        # Wait for it to exit
        for _ in range(50):  # up to 5 seconds
            import time
            time.sleep(0.1)
            s, _ = check_process_status(COCOINDEX_PID_FILE)
            if s != "running":
                break


def _start_cocoindex_daemon():
    """Restart the live cocoindex daemon."""
    import subprocess
    with open(COCOINDEX_LOG, "a") as log:
        proc = subprocess.Popen(
            ["uv", "run", "cocoindex", "update", "-L", "-f", "src/lcars_rag/flow.py"],
            stdout=log,
            stderr=subprocess.STDOUT,
            cwd="/app",
        )
    with open(COCOINDEX_PID_FILE, "w") as f:
        f.write(str(proc.pid))


def _run_oneshot_update():
    """Stop daemon, run one-shot update, restart daemon."""
    import subprocess
    _stop_cocoindex_daemon()
    with open(COCOINDEX_LOG, "a") as log:
        proc = subprocess.Popen(
            ["uv", "run", "cocoindex", "update", "-f", "src/lcars_rag/flow.py"],
            stdout=log,
            stderr=subprocess.STDOUT,
            cwd="/app",
        )
    with open(COCOINDEX_UPDATE_PID_FILE, "w") as f:
        f.write(str(proc.pid))
    proc.wait()
    try:
        os.remove(COCOINDEX_UPDATE_PID_FILE)
    except FileNotFoundError:
        pass
    _start_cocoindex_daemon()


@app.route("/api/index/update", methods=["POST"])
def trigger_index_update():
    """Stop the daemon, run a one-shot cocoindex update, then restart the daemon."""
    import threading
    # Check if a one-shot update is already running
    status, _ = check_process_status(COCOINDEX_UPDATE_PID_FILE)
    if status == "running":
        return jsonify({"ok": False, "error": "Update already running"}), 409
    threading.Thread(target=_run_oneshot_update, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/index/logs")
def index_logs():
    lines = int(request.args.get("lines", 200))
    offset = int(request.args.get("offset", 0))
    content, new_offset = tail_log(COCOINDEX_LOG, lines, offset)
    return jsonify({"content": content, "offset": new_offset})


@app.route("/api/sync/logs")
def sync_logs():
    lines = int(request.args.get("lines", 200))
    offset = int(request.args.get("offset", 0))
    content, new_offset = tail_log(SYNC_LOG, lines, offset)
    return jsonify({"content": content, "offset": new_offset})


# ---------------------------------------------------------------------------
# Report routes
# ---------------------------------------------------------------------------


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default or {}


@app.route("/skip-report")
def skip_report():
    return render_template("skip_report.html")


# Cache parsed skip report data (invalidated when file mtime changes)
_skip_cache = {"mtime": 0, "data": None, "rows": []}


def _load_skip_data():
    """Load and flatten skip report, with mtime-based caching."""
    try:
        mtime = os.path.getmtime(REPORT_PATH)
    except FileNotFoundError:
        return {"meta": {}, "rows": []}

    if mtime == _skip_cache["mtime"] and _skip_cache["data"] is not None:
        return _skip_cache["data"]

    raw = load_json(REPORT_PATH, {})
    rows = []
    for source, info in (raw.get("sources") or {}).items():
        for f in info.get("files") or []:
            reason = f.get("reason", "oversized")
            detail = ""
            if reason == "excluded" and f.get("matched_pattern"):
                detail = f["matched_pattern"]
            elif reason == "oversized" and f.get("max_file_size_needed"):
                detail = f"MAX_FILE_SIZE={f['max_file_size_needed']}"
            rows.append({
                "source": source,
                "file": f.get("file", ""),
                "reason": reason,
                "detail": detail,
                "size_bytes": f.get("size_bytes", 0),
                "size_human": f.get("size_human", ""),
            })

    result = {
        "meta": {
            "generated_at": raw.get("generated_at"),
            "max_file_size_default": raw.get("max_file_size_default", 0),
            "total_skipped": raw.get("total_skipped", 0),
            "counts_by_reason": raw.get("counts_by_reason", {}),
            "sources": {
                name: {"counts_by_reason": info.get("counts_by_reason", {})}
                for name, info in (raw.get("sources") or {}).items()
            },
        },
        "rows": rows,
    }
    _skip_cache["mtime"] = mtime
    _skip_cache["data"] = result
    return result


@app.route("/api/skip-report/meta")
def skip_report_meta():
    data = _load_skip_data()
    return jsonify(data["meta"])


@app.route("/api/skip-report/rows")
def skip_report_rows():
    data = _load_skip_data()
    rows = data["rows"]

    # Server-side filtering
    source = request.args.get("source", "")
    reason = request.args.get("reason", "")
    search = request.args.get("search", "").lower()
    pattern = request.args.get("pattern", "")

    if source:
        rows = [r for r in rows if r["source"] == source]
    if reason:
        rows = [r for r in rows if r["reason"] == reason]
    if search:
        rows = [r for r in rows if search in r["file"].lower()]
    if pattern:
        patterns = set(pattern.split(","))
        rows = [r for r in rows if r["detail"] in patterns or r["reason"] != "excluded"]

    # Sorting
    sort_col = request.args.get("sort", "size_bytes")
    sort_asc = request.args.get("asc", "0") == "1"
    if sort_col in ("source", "file", "reason", "detail", "size_bytes"):
        rows = sorted(rows, key=lambda r: r.get(sort_col, ""), reverse=not sort_asc)

    # Pagination
    offset = int(request.args.get("offset", 0))
    limit = int(request.args.get("limit", 200))
    total = len(rows)
    rows = rows[offset:offset + limit]

    return jsonify({"rows": rows, "total": total, "offset": offset, "limit": limit})


def main():
    port = int(os.environ.get("LCARS_DASHBOARD_PORT", os.environ.get("SKIP_REPORT_PORT", 5001)))
    print(f"Starting LCARS Dashboard on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)


if __name__ == "__main__":
    main()
