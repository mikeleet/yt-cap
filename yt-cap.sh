#!/bin/bash
# yt-cap Service Manager (macOS + Docker)
# Usage: bash yt-cap.sh [install|start|stop|restart|uninstall|status|logs]
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

LAUNCHD_NAME="com.ytcap.server"
LAUNCHD_PLIST="$HOME/Library/LaunchAgents/${LAUNCHD_NAME}.plist"

# ── Help ────────────────────────────────────────────────

show_help() {
    echo "yt-cap Service Manager"
    echo ""
    echo "  bash yt-cap.sh install    — install as launchd service (auto-start on boot)"
    echo "  bash yt-cap.sh uninstall  — remove launchd service"
    echo "  bash yt-cap.sh start      — start the server"
    echo "  bash yt-cap.sh stop       — stop the server"
    echo "  bash yt-cap.sh restart    — restart the server"
    echo "  bash yt-cap.sh status     — check if running"
    echo "  bash yt-cap.sh logs       — tail live logs"
    echo ""
}

# ── Docker or Local ─────────────────────────────────────

USE_DOCKER=false
DOCKER_COMPOSE=""
if [ -f "$DIR/docker-compose.yml" ]; then
    if docker compose version &>/dev/null 2>&1 && docker info &>/dev/null 2>&1; then
        USE_DOCKER=true
        DOCKER_COMPOSE="docker compose"
    elif command -v docker-compose &>/dev/null && docker info &>/dev/null 2>&1; then
        USE_DOCKER=true
        DOCKER_COMPOSE="docker-compose"
    fi
fi

# ── Status ──────────────────────────────────────────────

do_status() {
    if $USE_DOCKER; then
        if $DOCKER_COMPOSE ps --format json 2>/dev/null | grep -q '"State":"running"'; then
            echo "yt-cap: RUNNING (Docker)"
            $DOCKER_COMPOSE ps
        else
            echo "yt-cap: stopped (Docker)"
        fi
    else
        PID=$(pgrep -f "uvicorn app.main:app" 2>/dev/null || echo "")
        if [ -n "$PID" ]; then
            echo "yt-cap: RUNNING (PID $PID)"
            HEALTH=$(curl -s http://localhost:8506/health 2>/dev/null || echo "unreachable")
            echo "Health: $HEALTH"
        else
            echo "yt-cap: stopped"
        fi
    fi
}

# ── Start ───────────────────────────────────────────────

do_start() {
    echo "Starting yt-cap..."
    if $USE_DOCKER; then
        if [ ! -f .env ]; then cp .env.example .env; fi
        $DOCKER_COMPOSE up -d --build
        echo "Started (Docker). http://localhost:8506"
    else
        if pgrep -f "uvicorn app.main:app" &>/dev/null; then
            echo "Already running."
            return
        fi
        if [ ! -f .env ]; then cp .env.example .env; fi
        nohup bash start.sh > data/ytcap.log 2>&1 &
        sleep 3
        if pgrep -f "uvicorn app.main:app" &>/dev/null; then
            echo "Started. http://localhost:8506"
        else
            echo "Failed to start. Check data/ytcap.log"
            exit 1
        fi
    fi
}

# ── Stop ────────────────────────────────────────────────

do_stop() {
    echo "Stopping yt-cap..."
    if $USE_DOCKER; then
        $DOCKER_COMPOSE down
        echo "Stopped."
    else
        pkill -f "uvicorn app.main:app" 2>/dev/null || true
        pkill -f "chromium-headless"   2>/dev/null || true
        pkill -f "playwright/driver"   2>/dev/null || true
        sleep 1
        echo "Stopped."
    fi
}

# ── Restart ─────────────────────────────────────────────

do_restart() {
    do_stop
    sleep 2
    do_start
}

# ── Install as service ──────────────────────────────────

do_install() {
    echo "Installing yt-cap as launchd service..."

    if [ -f "$LAUNCHD_PLIST" ]; then
        echo "Already installed. Use 'uninstall' first to reinstall."
        exit 1
    fi

    mkdir -p "$(dirname "$LAUNCHD_PLIST")"

    cat > "$LAUNCHD_PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LAUNCHD_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${DIR}/start.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${DIR}/data/ytcap.log</string>
    <key>StandardErrorPath</key>
    <string>${DIR}/data/ytcap.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>YTCAP_PORT</key>
        <string>${YTCAP_PORT:-8506}</string>
        <key>YTCAP_API_KEY</key>
        <string>${YTCAP_API_KEY:-12345}</string>
        <key>YTCAP_UI_PIN</key>
        <string>${YTCAP_UI_PIN:-5580}</string>
    </dict>
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
PLIST

    launchctl load "$LAUNCHD_PLIST" 2>/dev/null || true
    launchctl enable "gui/$(id -u)/${LAUNCHD_NAME}" 2>/dev/null || true

    echo "Installed."
    echo "  Starts automatically on login/boot."
    echo "  Logs: data/ytcap.log"
}

# ── Uninstall service ───────────────────────────────────

do_uninstall() {
    echo "Uninstalling yt-cap launchd service..."
    do_stop
    launchctl bootout "gui/$(id -u)/${LAUNCHD_NAME}" 2>/dev/null || true
    launchctl disable "gui/$(id -u)/${LAUNCHD_NAME}" 2>/dev/null || true
    rm -f "$LAUNCHD_PLIST"
    echo "Uninstalled."
}

# ── Logs ────────────────────────────────────────────────

do_logs() {
    if $USE_DOCKER; then
        $DOCKER_COMPOSE logs -f
    else
        tail -f data/ytcap.log 2>/dev/null || echo "No log file yet."
    fi
}

# ── Main ────────────────────────────────────────────────

case "${1:-help}" in
    install)   do_install ;;
    uninstall) do_uninstall ;;
    start)     do_start ;;
    stop)      do_stop ;;
    restart)   do_restart ;;
    status)    do_status ;;
    logs)      do_logs ;;
    help|*)    show_help ;;
esac
