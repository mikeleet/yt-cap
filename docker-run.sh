#!/bin/bash
# yt-cap Docker quick-start
set -e
cd "$(dirname "$0")"

echo "=== yt-cap Docker ==="

# Copy .env if missing
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example"
fi

DOCKER_COMPOSE=""
if docker compose version &>/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    echo "ERROR: neither 'docker compose' nor 'docker-compose' found."
    exit 1
fi

echo "Building and starting..."
$DOCKER_COMPOSE up -d --build

echo ""
echo "Started. Open http://localhost:${YTCAP_PORT:-8506}"
echo ""
echo "Commands:"
echo "  $DOCKER_COMPOSE logs -f    — watch logs"
echo "  $DOCKER_COMPOSE down       — stop"
echo "  $DOCKER_COMPOSE restart    — restart"
