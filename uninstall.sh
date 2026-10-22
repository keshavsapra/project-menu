#!/usr/bin/env bash
# uninstall.sh — reverse everything install.sh did.
set -euo pipefail

DEST_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/project-menu"
BIN_DIR="${HOME}/.local/bin"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"

# 1. Unregister the hotkey (best-effort).
if [ -x "$BIN_DIR/project-menu" ]; then
  echo ">> Unregistering hotkey"
  python3 "$DEST_DIR/main.py" --unregister-hotkey 2>/dev/null || true
fi

# 2. Remove installed files.
echo ">> Removing program files"
rm -rf "$DEST_DIR"
rm -f "$BIN_DIR/project-menu"
rm -f "$APP_DIR/project-menu.desktop"
rm -f "$ICON_DIR/project-menu.svg"

echo "Project Menu uninstalled."
