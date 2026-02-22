#!/usr/bin/env bash
# setup_autostart.sh — install Kindling daemon as a macOS launchd agent.
# Run once after install: bash setup_autostart.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$SCRIPT_DIR/com.kindling.daemon.plist.template"
PLIST_DEST="$HOME/Library/LaunchAgents/com.kindling.daemon.plist"
DAEMON_PATH="$SCRIPT_DIR/daemon.py"

# Resolve the absolute Python binary path (works with pyenv)
if command -v pyenv &>/dev/null; then
    PYTHON_PATH="$(pyenv which python3 2>/dev/null || which python3)"
else
    PYTHON_PATH="$(which python3)"
fi

echo "Using Python: $PYTHON_PATH"
echo "Daemon:       $DAEMON_PATH"
echo "Project dir:  $SCRIPT_DIR"

# Build PATH value (launchd doesn't source shell profiles)
PATH_VALUE="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
if command -v pyenv &>/dev/null; then
    PYENV_BIN="$(pyenv root)/shims"
    PATH_VALUE="$PYENV_BIN:$PATH_VALUE"
fi

# Ensure LaunchAgents directory exists
mkdir -p "$HOME/Library/LaunchAgents"

# Substitute placeholders
sed \
    -e "s|__PYTHON_PATH__|$PYTHON_PATH|g" \
    -e "s|__DAEMON_PATH__|$DAEMON_PATH|g" \
    -e "s|__PROJECT_DIR__|$SCRIPT_DIR|g" \
    -e "s|__PATH_VALUE__|$PATH_VALUE|g" \
    "$TEMPLATE" > "$PLIST_DEST"

echo "Plist written to: $PLIST_DEST"

# Unload existing agent (ignore error if not loaded)
launchctl unload "$PLIST_DEST" 2>/dev/null || true

# Load and enable the agent
launchctl load -w "$PLIST_DEST"

echo ""
echo "Done. Verify with:"
echo "  launchctl list | grep kindling"
