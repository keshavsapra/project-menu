#!/usr/bin/env bash
# Build a Debian .deb for project-menu (no arch deps -> Architecture: all).
#
# Layout (system-wide, mirrors install.sh's ~/.local layout):
#   /usr/lib/project-menu/          the Python application
#   /usr/bin/project-menu           console launcher
#   /usr/share/applications/        .desktop entry
#   /usr/share/icons/.../           app icon
#   /usr/share/doc/project-menu/    README + copyright
#
# Output: dist/project-menu_<version>_all.deb
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="$(python3 "$ROOT/packaging/read_version.py")"
DIST="$ROOT/dist"
PKG="usr/lib/project-menu"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK" || exit 1

# --- application files ----------------------------------------------------
install -D -m 0644 "$ROOT"/main.py "$WORK/$PKG/main.py"
for f in cli.py interfaces.py core.py detect.py; do
  install -m 0644 "$ROOT/$f" "$WORK/$PKG/$f"
done
cp -r "$ROOT"/backends "$ROOT"/hotkeys "$ROOT"/ui "$WORK/$PKG/"
find "$WORK/$PKG" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# --- console launcher -------------------------------------------------------
install -d -m 0755 "$WORK/usr/bin"
cat > "$WORK/usr/bin/project-menu" <<EOF
#!/bin/sh
exec python3 /usr/lib/project-menu/main.py "\$@"
EOF
chmod 0755 "$WORK/usr/bin/project-menu"

# --- desktop entry + icon ---------------------------------------------------
cat > "$WORK/project-menu.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Project Menu
Comment=Switch display mode (Win+P style)
Exec=project-menu
Icon=project-menu
Terminal=false
Categories=Settings;Utility;
EOF
install -D -m 0644 "$WORK/project-menu.desktop" "$WORK/usr/share/applications/project-menu.desktop"
rm "$WORK/project-menu.desktop"
install -D -m 0644 "$ROOT/assets/project-menu.svg" \
  "$WORK/usr/share/icons/hicolor/scalable/apps/project-menu.svg"

# --- docs -------------------------------------------------------------------
install -D -m 0644 "$ROOT/README.md" "$WORK/usr/share/doc/project-menu/README"
install -D -m 0644 "$ROOT/LICENSE" "$WORK/usr/share/doc/project-menu/copyright"

# --- package metadata -------------------------------------------------------
install -d -m 0755 "$WORK/DEBIAN"
cat > "$WORK/DEBIAN/control" <<'EOF'
Package: project-menu
Version: @VERSION@
Section: utils
Priority: optional
Architecture: all
Maintainer: keshavsapra <keshavsapra@users.noreply.github.com>
Depends: python3 (>= 3.9)
Recommends: python3-gi, gir1.2-gtk-3.0
Suggests: python3-xlib, x11-xserver-utils, libnotify-bin
Homepage: https://github.com/keshavsapra/project-menu
Description: Win+P display mode switcher for Linux
 Pop up a Win+P style projection menu on Super+P and switch between
 PC screen only, Duplicate, Extend, and Second screen only on any Linux
 desktop. Auto-detects the right backend for GNOME, KDE, Cinnamon, MATE,
 XFCE, COSMIC, Sway, Hyprland, wlroots compositors, or X11/xrandr, and
 registers the hotkey for you. Includes a CLI (`project-menu --list`,
 `--mode`, `--dry-run`) and a 15-second safety revert on every change.
Built-Using: python-source @VERSION@
EOF
sed -i "s/@VERSION@/$VERSION/g" "$WORK/DEBIAN/control"

# best-effort menus/cache refresh on install (never fail the build)
cat > "$WORK/DEBIAN/postinst" <<'EOF'
#!/bin/sh
update-desktop-database /usr/share/applications 2>/dev/null || true
exit 0
EOF
chmod 0755 "$WORK/DEBIAN/postinst"

# --- build -------------------------------------------------------------------
mkdir -p "$DIST"
OUT="$DIST/project-menu_${VERSION}_all.deb"
rm -f "$OUT"
dpkg-deb --root-owner-group -b "$WORK" "$OUT"
echo "built: $OUT"
