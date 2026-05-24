#!/bin/bash
# yt-cap local launch script
# Handles: vanilla macOS, Homebrew Python, Anaconda, miniconda, pyenv
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$DIR/.venv"
PORT="${YTCAP_PORT:-8506}"
LOG_FILE="$DIR/data/ytcap.log"

echo "========================================="
echo "  yt-cap — YouTube Caption Archive"
echo "========================================="
echo ""

# ── Step 1: Find Python 3 ──────────────────────────────

PYTHON=""
for candidate in python3 python3.12 python3.11 python3.10 \
                 /usr/local/bin/python3 /opt/homebrew/bin/python3 \
                 /usr/bin/python3; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        if [ -n "$ver" ]; then
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
                PYTHON="$candidate"
                break
            fi
        fi
    fi
done

# Check Anaconda/miniconda
if [ -z "$PYTHON" ]; then
    for conda_path in "$HOME/anaconda3/bin/python" "$HOME/miniconda3/bin/python" \
                      "/opt/anaconda3/bin/python" "/opt/miniconda3/bin/python" \
                      "/usr/local/anaconda3/bin/python"; do
        if [ -f "$conda_path" ]; then
            PYTHON="$conda_path"
            break
        fi
    done
fi

# Check pyenv
if [ -z "$PYTHON" ] && command -v pyenv &>/dev/null; then
    PYTHON="$(pyenv root)/shims/python3"
    if [ ! -f "$PYTHON" ]; then
        PYTHON="$(pyenv root)/versions/3.12.*/bin/python3" 2>/dev/null
        PYTHON=$(ls $PYTHON 2>/dev/null | head -1)
    fi
fi

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.10+ not found."
    echo ""
    echo "Install it with one of:"
    echo "  brew install python@3.12"
    echo "  https://www.python.org/downloads/"
    echo "  https://www.anaconda.com/download"
    echo ""
    exit 1
fi

echo "✓ Python: $($PYTHON --version 2>&1)"

# ── Step 2: Create venv if missing or stale ────────────

if [ -f "$VENV/bin/python3" ]; then
    VENV_PYVER=$("$VENV/bin/python3" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    EXPECTED_PYVER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    if [ "$VENV_PYVER" != "$EXPECTED_PYVER" ]; then
        echo "Virtual environment Python version mismatch ($VENV_PYVER vs $EXPECTED_PYVER), recreating..."
        rm -rf "$VENV"
    fi
fi

if [ ! -d "$VENV" ]; then
    echo "Creating virtual environment..."
    "$PYTHON" -m venv "$VENV"
    echo "Installing dependencies..."
    "$VENV/bin/pip" install --upgrade pip -q 2>/dev/null
    "$VENV/bin/pip" install -q -r "$DIR/requirements.txt"
    echo "✓ Dependencies installed"
else
    echo "✓ Virtual environment found"
fi

# ── Step 3: Install yt-dlp if missing ──────────────────

if ! "$VENV/bin/yt-dlp" --version &>/dev/null 2>&1; then
    echo "Installing yt-dlp..."
    "$VENV/bin/pip" install -q yt-dlp
    echo "✓ yt-dlp installed"
fi

# ── Step 4: Install Playwright + Chromium if missing ────

if [ ! -f "$VENV/bin/playwright" ] || ! "$VENV/bin/playwright" install --dry-run chromium &>/dev/null 2>&1; then
    echo "Installing Playwright + Chromium (one-time, ~300MB)..."
    "$VENV/bin/pip" install -q playwright 2>/dev/null || true
    "$VENV/bin/playwright" install chromium 2>&1 | tail -1
    echo "✓ Playwright ready"
fi

# ── Step 5: Create data directory ──────────────────────

mkdir -p "$DIR/data"

# ── Step 6: Start server ───────────────────────────────

echo ""
echo "Starting on http://localhost:$PORT ..."
echo "Press Ctrl+C to stop"
echo ""

PYTHONPATH="$DIR" "$VENV/bin/uvicorn" app.main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    2>&1 | tee -a "$LOG_FILE"
