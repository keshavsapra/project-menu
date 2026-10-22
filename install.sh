#!/usr/bin/env bash
# install.sh — install project-menu for the current user.
#
#   * Detects the package manager (apt/dnf/pacman/zypper) and the session
#     (X11/Wayland + desktop) to install only the relevant dependencies.
#   * Copies the program to ~/.local/share/project-menu and links a wrapper
#     into ~/.local/bin.
#   * Installs a .desktop file + icon.
#   * Registers the Super+P hotkey (per environment).
#
# Usage:  ./install.sh [--append-config] [--no-hotkey]
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/project-menu"
BIN_DIR="${HOME}/.local/bin"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"

APPEND_CONFIG=0
REGISTER_HOTKEY=1
INSTALL_DEPS=1
while [ $# -gt 0 ]; do
  case "$1" in
    --append-config) APPEND_CONFIG=1 ;;
    --no-hotkey) REGISTER_HOTKEY=0 ;;
    --no-deps) INSTALL_DEPS=0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

SESSION_TYPE="${XDG_SESSION_TYPE:-}"
DESKTOP="$(printf '%s' "${XDG_CURRENT_DESKTOP:-}" | tr '[:upper:]' '[:lower:]')"

# ---------------------------------------------------------------------------
# 1. Detect the package manager.
# ---------------------------------------------------------------------------
detect_pm() {
  if command -v apt-get >/dev/null 2>&1; then echo apt
  elif command -v dnf >/dev/null 2>&1; then echo dnf
  elif command -v pacman >/dev/null 2>&1; then echo pacman
  elif command -v zypper >/dev/null 2>&1; then echo zypper
  else echo none; fi
}

PM="$(detect_pm)"
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi
fi

# Map a logical dependency token to package names for the detected PM.
pkg() {
  case "$PM:$1" in
    apt:python-gi)    echo python3-gi ;;
    dnf:python-gi)    echo python3-gobject ;;
    pacman:python-gi) echo python-gobject ;;
    zypper:python-gi) echo python3-gobject ;;

    apt:gtk3)    echo gir1.2-gtk-3.0 ;;
    dnf:gtk3)    echo gtk3 ;;
    pacman:gtk3) echo gtk3 ;;
    zypper:gtk3) echo gtk3 ;;

    apt:layer-shell)    echo gir1.2-gtklayershell-0.1 ;;
    dnf:layer-shell)    echo gtk-layer-shell ;;
    pacman:layer-shell) echo gtk-layer-shell ;;
    zypper:layer-shell) echo gtk-layer-shell ;;

    apt:xrandr)    echo x11-xserver-utils ;;
    dnf:xrandr)    echo xrandr ;;
    pacman:xrandr) echo xorg-xrandr ;;
    zypper:xrandr) echo xrandr ;;

    apt:xlib)    echo python3-xlib ;;
    dnf:xlib)    echo python3-xlib ;;
    pacman:xlib) echo python-xlib ;;
    zypper:xlib) echo python3-xlib ;;

    apt:kscreen)    echo libkscreen-bin ;;
    dnf:kscreen)    echo libkscreen ;;
    pacman:kscreen) echo libkscreen ;;
    zypper:kscreen) echo libkscreen ;;

    apt:sway)    echo sway ;;
    dnf:sway)    echo sway ;;
    pacman:sway) echo sway ;;
    zypper:sway) echo sway ;;

    apt:hyprland)    echo hyprland ;;
    dnf:hyprland)    echo hyprland ;;
    pacman:hyprland) echo hyprland ;;
    zypper:hyprland) echo hyprland ;;

    apt:wlr-randr)    echo wlr-randr ;;
    dnf:wlr-randr)    echo wlr-randr ;;
    pacman:wlr-randr) echo wlr-randr ;;
    zypper:wlr-randr) echo wlr-randr ;;

    apt:cosmic)    echo cosmic-randr ;;
    dnf:cosmic)    echo cosmic-randr ;;
    pacman:cosmic) echo cosmic-randr ;;
    zypper:cosmic) echo cosmic-randr ;;

    apt:xfconf)    echo xfconf ;;
    dnf:xfconf)    echo xfconf ;;
    pacman:xfconf) echo xfconf ;;
    zypper:xfconf) echo xfconf ;;
  esac
}

# ---------------------------------------------------------------------------
# 2. Build the list of dependencies for the detected environment.
# ---------------------------------------------------------------------------
TOKENS=(python-gi gtk3)

case "$DESKTOP" in
  *gnome*|*ubuntu*|*cinnamon*|*mate*) : ;;          # uses python-gi/gtk already
  *kde*|*plasma*) TOKENS+=(kscreen layer-shell) ;;
  *sway*)         TOKENS+=(sway layer-shell) ;;
  *hyprland*)     TOKENS+=(hyprland layer-shell) ;;
  *river*|*labwc*|*wayfire*) TOKENS+=(wlr-randr layer-shell) ;;
  *cosmic*)       TOKENS+=(cosmic layer-shell) ;;
  *xfce*)         TOKENS+=(xrandr xfconf) ;;
  *)              TOKENS+=(xrandr) ;;
esac

# X11 session: ensure xrandr (+ xlib for the optional hotkey daemon).
if [ "$SESSION_TYPE" = "x11" ]; then
  TOKENS+=(xrandr xlib)
fi

install_packages() {
  local pkgs=()
  for t in "$@"; do
    local p; p="$(pkg "$t")"
    [ -n "$p" ] && pkgs+=("$p")
  done
  [ ${#pkgs[@]} -eq 0 ] && return
  echo ">> Installing: ${pkgs[*]}"
  case "$PM" in
    apt)    ($SUDO apt-get update && $SUDO apt-get install -y "${pkgs[@]}") || echo "!! Package installation skipped or failed; continuing with user install." ;;
    dnf)    $SUDO dnf install -y "${pkgs[@]}" || echo "!! Package installation skipped or failed; continuing with user install." ;;
    pacman) $SUDO pacman -S --needed --noconfirm "${pkgs[@]}" || echo "!! Package installation skipped or failed; continuing with user install." ;;
    zypper) $SUDO zypper --non-interactive install "${pkgs[@]}" || echo "!! Package installation skipped or failed; continuing with user install." ;;
    none)   echo "!! Could not detect a package manager; install manually:"; printf '    %s\n' "${pkgs[@]}" ;;
  esac
}

if [ "$PM" != "none" ] && [ "$INSTALL_DEPS" = "1" ]; then
  install_packages "${TOKENS[@]}"
fi

# ---------------------------------------------------------------------------
# 3. Install the program files.
# ---------------------------------------------------------------------------
echo ">> Installing program to $DEST_DIR"
mkdir -p "$DEST_DIR"
cp -r "$SRC_DIR"/{main.py,cli.py,interfaces.py,core.py,detect.py,backends,hotkeys,ui} "$DEST_DIR/"

mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/project-menu" <<EOF
#!/usr/bin/env bash
exec python3 "$DEST_DIR/main.py" "\$@"
EOF
chmod +x "$BIN_DIR/project-menu"

# ---------------------------------------------------------------------------
# 4. Desktop entry + icon.
# ---------------------------------------------------------------------------
mkdir -p "$APP_DIR" "$ICON_DIR"
cat > "$ICON_DIR/project-menu.svg" <<'SVG'
<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
  <rect x="6" y="12" width="52" height="32" rx="3" fill="#3584e4"/>
  <rect x="11" y="17" width="42" height="22" rx="2" fill="#ffffff"/>
  <rect x="4" y="44" width="22" height="4" rx="2" fill="#777"/>
  <rect x="4" y="51" width="30" height="4" rx="2" fill="#777"/>
</svg>
SVG

cat > "$APP_DIR/project-menu.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Project Menu
Comment=Switch display mode (Win+P style)
Exec=$BIN_DIR/project-menu
Icon=project-menu
Terminal=false
Categories=Settings;Utility;
EOF

# ---------------------------------------------------------------------------
# 5. Register the hotkey.
# ---------------------------------------------------------------------------
if [ "$REGISTER_HOTKEY" = "1" ]; then
  echo ">> Registering Super+P hotkey"
  ARGS=(--register-hotkey)
  [ "$APPEND_CONFIG" = "1" ] && ARGS+=(--append-config)
  python3 "$DEST_DIR/main.py" "${ARGS[@]}" || echo "!! Hotkey registration failed (see above for manual instructions)."
fi

cat <<EOF

Project Menu installed successfully.

  Binary:   $BIN_DIR/project-menu
  Try:      project-menu --list   or   project-menu --debug
  Hotkey:   Super+P  (or run 'project-menu' manually)

Make sure $BIN_DIR is on your PATH (log out/in if needed).
EOF
