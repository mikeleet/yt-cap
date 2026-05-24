#!/bin/bash
# yt-cap permissions fix — run this after AirDrop on any Mac
# Usage: bash fix.sh
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "Fixing permissions for yt-cap..."

# Remove macOS quarantine (blocks unsigned apps from launching)
if command -v xattr &>/dev/null; then
    xattr -dr com.apple.quarantine . 2>/dev/null && echo "✓ Quarantine cleared" || echo "  (no quarantine found)"
fi

# Make all scripts executable
chmod +x start.sh
chmod +x fix-permissions.sh
chmod +x yt-cap.app/Contents/MacOS/launcher.sh 2>/dev/null || true

echo "✓ Permissions fixed"
echo ""
echo "Now you can:"
echo "  Double-click yt-cap.app"
echo "  — or —"
echo "  Run:  bash start.sh"
echo ""
