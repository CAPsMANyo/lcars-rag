#!/bin/bash
set -e

# Ensure sync lock is always cleaned up
trap 'rm -f /tmp/sync.lock' EXIT

LOGS_DIR="/app/data/logs"
mkdir -p "$LOGS_DIR"

SYNC_LOG="$LOGS_DIR/sync.log"
SYNC_STATE_FILE="$LOGS_DIR/sync_state.json"
SYNC_WATCH_PID_FILE="$LOGS_DIR/sync_watch.pid"
COCOINDEX_LOG="$LOGS_DIR/cocoindex.log"
COCOINDEX_PID_FILE="$LOGS_DIR/cocoindex.pid"

# Read sync_interval from config.yml (default: 1 hour)
SYNC_INTERVAL=$(grep 'sync_interval:' /app/config.yml 2>/dev/null | awk '{print $2}')
SYNC_INTERVAL="${SYNC_INTERVAL:-3600}"

touch "$SYNC_LOG" "$COCOINDEX_LOG"

# --- Write sync state as JSON ---
write_sync_state() {
    local status="$1"
    local now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    # Read existing last_completed if present
    local last_completed=""
    if [ -f "$SYNC_STATE_FILE" ]; then
        last_completed=$(grep -o '"last_completed":"[^"]*"' "$SYNC_STATE_FILE" | cut -d'"' -f4)
    fi
    if [ "$status" = "completed" ]; then
        last_completed="$now"
    fi
    cat > "$SYNC_STATE_FILE" <<EOJSON
{"status":"$status","updated_at":"$now","last_completed":"${last_completed}","sync_interval":${SYNC_INTERVAL}}
EOJSON
}

write_sync_state "starting"

# --- Start/restart cocoindex ---
start_cocoindex() {
    # Kill existing if running
    if [ -f "$COCOINDEX_PID_FILE" ]; then
        OLD_PID=$(cat "$COCOINDEX_PID_FILE")
        if kill -0 "$OLD_PID" 2>/dev/null; then
            echo "[entrypoint] Stopping cocoindex (PID $OLD_PID)..."
            kill "$OLD_PID" 2>/dev/null || true
            wait "$OLD_PID" 2>/dev/null || true
        fi
    fi
    echo "[entrypoint] Starting cocoindex live updater..."
    uv run cocoindex update -L -f src/lcars_rag/flow.py > "$COCOINDEX_LOG" 2>&1 &
    COCOINDEX_PID=$!
    echo "$COCOINDEX_PID" > "$COCOINDEX_PID_FILE"
    echo "[entrypoint] cocoindex started with PID $COCOINDEX_PID"
}

# --- Run repo sync (with lock) ---
SYNC_LOCK="/tmp/sync.lock"

run_sync() {
    if [ -f "$SYNC_LOCK" ]; then
        echo "[sync-watch] Sync already running, skipping." >> "$SYNC_LOG"
        return 1
    fi
    touch "$SYNC_LOCK"
    write_sync_state "running"
    echo "[sync-watch] Running repo sync..." >> "$SYNC_LOG"
    # Don't let a single repo failure kill the whole sync
    uv run lcars-sync-repos >> "$SYNC_LOG" 2>&1 || true
    write_sync_state "completed"
    rm -f "$SYNC_LOCK"
    return 0
}

# --- Sync watcher: watches config.yml + periodic sync ---
sync_watch() {
    SOURCES=/app/config.yml
    HASH=$(md5sum "$SOURCES" 2>/dev/null | cut -d' ' -f1)
    LAST_PERIODIC_SYNC=$(date +%s)

    # Initial sync
    run_sync

    while true; do
        sleep 10

        NEED_COCOINDEX_RESTART=false

        # Check for manual trigger from GUI
        if [ -f "/tmp/sync_trigger" ]; then
            rm -f "/tmp/sync_trigger"
            echo "[sync-watch] Manual sync triggered via GUI..." >> "$SYNC_LOG"
            run_sync
            LAST_PERIODIC_SYNC=$(date +%s)
        fi

        # Check if config.yml changed
        NEW_HASH=$(md5sum "$SOURCES" 2>/dev/null | cut -d' ' -f1)
        if [ "$NEW_HASH" != "$HASH" ]; then
            echo "[sync-watch] config.yml changed, syncing..." >> "$SYNC_LOG"
            HASH="$NEW_HASH"
            if run_sync; then
                NEED_COCOINDEX_RESTART=true
            fi
            LAST_PERIODIC_SYNC=$(date +%s)
        fi

        # Re-read interval from state file (GUI may have changed it)
        if [ -f "$SYNC_STATE_FILE" ]; then
            NEW_INTERVAL=$(grep -o '"sync_interval":[0-9]*' "$SYNC_STATE_FILE" | cut -d: -f2)
            if [ -n "$NEW_INTERVAL" ] && [ "$NEW_INTERVAL" -ge 60 ] 2>/dev/null; then
                SYNC_INTERVAL="$NEW_INTERVAL"
            fi
        fi

        # Periodic sync to pull upstream changes in existing repos
        NOW=$(date +%s)
        ELAPSED=$((NOW - LAST_PERIODIC_SYNC))
        if [ "$ELAPSED" -ge "$SYNC_INTERVAL" ]; then
            echo "[sync-watch] Periodic sync (every ${SYNC_INTERVAL}s)..." >> "$SYNC_LOG"
            run_sync
            LAST_PERIODIC_SYNC=$(date +%s)
        fi

        # Restart cocoindex if config.yml changed (new/removed sources)
        if [ "$NEED_COCOINDEX_RESTART" = true ]; then
            echo "[sync-watch] Restarting cocoindex to pick up new sources..." >> "$SYNC_LOG"
            start_cocoindex
        fi
    done
}

echo "[entrypoint] Starting sync watcher (periodic sync every ${SYNC_INTERVAL}s)..."
sync_watch &
SYNC_WATCH_PID=$!
echo "$SYNC_WATCH_PID" > "$SYNC_WATCH_PID_FILE"
echo "[entrypoint] sync watcher started with PID $SYNC_WATCH_PID"

# --- Initial cocoindex start ---
start_cocoindex

# --- Dashboard (foreground) ---
echo "[entrypoint] Starting LCARS dashboard..."
exec uv run lcars-dashboard
