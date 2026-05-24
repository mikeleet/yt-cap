#!/bin/bash
# yt-cap macOS .app launcher
# Opens Terminal, runs setup, starts server, opens browser

DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
PORT="${YTCAP_PORT:-8506}"

osascript -e "
tell application \"Terminal\"
    activate
    do script \"
clear
echo '========================================='
echo '  yt-cap — YouTube Caption Archive'
echo '  First launch may take a few minutes'
echo '  (installing Python packages + Playwright)'
echo '========================================='
echo ''

cd '$DIR'

# Check if we need to create a venv
if [ ! -d '.venv' ]; then
    echo 'First launch — installing dependencies...'
fi

bash start.sh

echo ''
echo '========================================='
echo '  Server stopped.'
echo '  Close this window or press ↑ to restart.'
echo '========================================='
\"
end tell
"

sleep 5
open "http://localhost:$PORT"
