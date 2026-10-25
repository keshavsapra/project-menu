# Project Menu — Implementation & Architecture Log

This document provides a plain-English explanation of the architecture, design choices, and implementation details for `project-menu`, a cross-distro, cross-desktop Linux utility that mimics the Windows Win+P "Project" display-switch overlay.

---

## 1. Overview & Architecture

Windows provides a quick display mode switcher when pressing **Win+P** (Super+P):
1. **PC screen only** (internal display only)
2. **Duplicate** (mirror displays at highest common resolution)
3. **Extend** (expand the desktop, default right-of-primary)
4. **Second screen only** (external display only)

On Linux, display servers and desktop environments handle monitor configuration through vastly different APIs:
* X11 uses the RandR protocol (via `xrandr` or `python-xlib RandR`).
* GNOME Wayland uses Mutter's D-Bus interface `org.gnome.Mutter.DisplayConfig`. The legacy `gdctl` utility is absent on many distributions, so we speak D-Bus directly to Mutter.
* KDE Plasma Wayland uses `kscreen-doctor` for atomic multi-output configuration.
* Sway uses `swaymsg output ...` commands over its IPC socket.
* Hyprland uses `hyprctl keyword monitor ...` with native `mirror` support.
* Generic wlroots compositors (river, labwc, Wayfire) use `wlr-randr`.
* COSMIC (System76) uses `cosmic-randr`.

To support all these environments seamlessly without configuration, `project-menu` is designed around three pluggable abstract interfaces:
* **`DisplayBackend`**: Queries connected displays, inspects current mode, plans commands, and applies/restores configurations.
* **`HotkeyRegistrar`**: Registers/unregisters the global `Super+P` shortcut across desktop environments.
* **`PopupUI`**: Displays a centered, borderless, theme-aware overlay popup with keyboard navigation and single-instance cycling.

---

## 2. Environment Detection & Selection Logic

Runtime detection is performed by `detect.py`:
* Reads `$XDG_SESSION_TYPE` (`x11`, `wayland`).
* Inspects `$XDG_CURRENT_DESKTOP` and `$XDG_SESSION_DESKTOP` (case-insensitively).
* Checks compositor-specific variables:
  * `$WAYLAND_DISPLAY`
  * `$HYPRLAND_INSTANCE_SIGNATURE`
  * `$SWAYSOCK`
  * `$DISPLAY`
* **Smart Fallbacks**: If `$XDG_SESSION_TYPE` is unset (common in custom tiling WMs or tty startups), it automatically infers `wayland` if `$WAYLAND_DISPLAY`, `$HYPRLAND_INSTANCE_SIGNATURE`, or `$SWAYSOCK` is detected, or `x11` if `$DISPLAY` is set.
* Overriding is supported via `--backend <name>`.
* If no backend matches, a clear error message is displayed and logged, showing the detected environment details and instructions on how to implement and register a new backend.

---

## 3. Display Backends Implemented

Every backend implements:
* `list_outputs()`: returns physical output status, connection, modes, current mode, geometry, and scaling.
* `get_current_mode()`: infers whether the active setup is Internal, Duplicate, Extend, or External.
* `plan(mode, target_output, position)`: computes the exact commands or D-Bus payload without making changes.
* `apply(mode, target_output, position)`: applies the configuration and records snapshots for revert protection. Supports both positional arguments and a `Selection` object.
* `snapshot()` and `restore(snapshot)`: enables black-screen revert protection.

### Specific Backend Details:
1. **X11 Backend (`backends/x11.py`)**:
   * Uses `xrandr` as the primary path.
   * Includes a `python-xlib` RandR fallback if the `xrandr` CLI binary is missing.
   * Supports `INTERNAL`, `EXTERNAL`, `EXTEND` (left/right/above/below), and `DUPLICATE` (highest common resolution with refresh warning).

2. **GNOME Wayland Backend (`backends/gnome.py`)**:
   * Communicates directly with Mutter via D-Bus: `org.gnome.Mutter.DisplayConfig` (`GetCurrentState` and `ApplyMonitorsConfig`).
   * Avoids `gdctl` completely.
   * Discovers connected-but-disabled displays so a turned-off second monitor can still be selected.
   * Prevents `None` mode IDs to guarantee GLib.Variant serialization never crashes.
   * Applies configurations atomically using Mutter persistent method (2).

3. **KDE Plasma Wayland Backend (`backends/kde.py`)**:
   * Uses `kscreen-doctor` atomic CLI commands (`output.<name>.enable`, `output.<name>.mode.<id>`, `output.<name>.position.<x>,<y>`, `output.<name>.disable`).
   * Compatible with Plasma 5 and Plasma 6.

4. **Sway Backend (`backends/sway.py`)**:
   * Reads output state via `swaymsg -t get_outputs`.
   * Configures modes and positions via `swaymsg output <name> ...`.

5. **Hyprland Backend (`backends/hyprland.py`)**:
   * Reads state via `hyprctl -j monitors all` (including disabled outputs).
   * Configures outputs via `hyprctl keyword monitor <name>,<mode>,<pos>,<scale>[,mirror,<src>]`.
   * Uses native hardware mirroring for duplicate mode.

6. **Generic wlroots Backend (`backends/wlroots.py`)**:
   * Uses `wlr-randr` for river, labwc, Wayfire, and other wlroots compositors.

7. **COSMIC Backend (`backends/cosmic.py`)**:
   * Uses `cosmic-randr` with support for `enable`, `disable`, `mode`, `position`, and `mirror`.

8. **Single & Multi-Monitor Logic**:
   * **1 Monitor**: Shows "no second display detected" in the UI note and returns a clean error if multi-monitor modes are requested from the CLI.
   * **2 Monitors**: Standard dual-monitor switching.
   * **3+ Monitors**: Allows the user to select which display acts as the "second screen" (filtering out the primary display).
   * **Duplicate Mode**: Calculates the highest common resolution between screens and warns if refresh rates differ.
   * **Extend Mode**: Defaults to placing the secondary display to the right of primary, with options for left, above, or below.

---

## 4. Popup UI (Minimal Flat Design)

The UI is deliberately minimal — a flat, borderless card that gets out of the way:

1. **GTK UI (`ui/gtk_ui.py`)**:
   * **Flat Card**: Four plain text rows in a compact card (`alpha(@theme_bg_color, 0.9)`) with a hairline border (`alpha(@theme_fg_color, 0.14)`) and 10px rounded corners. True RGBA visual support in GTK 3/4 prevents black-corner artifacts.
   * **Theme-Aware**: All colors derive from `@theme_bg_color`/`@theme_fg_color`, so the card tracks the user's native dark/light theme with no hardcoded palette.
   * **Active-Mode Dot**: The current mode is marked with a small `●` prefix; the focused row gets a faint highlight via the `suggested-action` class with theme gradients suppressed (`background-image: none`).
   * **No Chrome**: No header, icons, subtitles, keycap badges, or hint footer — keyboard shortcuts still work (arrows/Tab/1–4/Enter/Esc).
   * **Confirmation Sheet**: A 15-second countdown dialog with plain `Keep` / `Revert` buttons and a "Reverting in Ns" label. On revert the backend replays the pre-change snapshot.
   * **Layer Shell & Desktop Integration**:
     * **X11**: Always-on-top, centered on the active monitor.
     * **Wayland with layer-shell**: Centered true overlay with `EXCLUSIVE` keyboard grab.
     * **GNOME Wayland**: Focused borderless window.
     * **Single Instance**: A second `Super+P` signals the running `Gio.Application` to cycle options.
   * **Silent Launch**: The CLI backgrounds a plain popup launch (double-fork + detach), so no terminal is spawned or left open; `--foreground`/`--debug` opt out. The popup window is registered via `Gtk.Application.add_window()` so the Gio main loop stays alive while shown.
   * **X11 parsing note**: xrandr emits the preferred-mode `+` marker as a standalone token for connected-but-disabled outputs (e.g. `60.00 +  50.00`); bare markers are skipped, not parsed as rates.

2. **Qt Fallback UI (`ui/qt_ui.py`)**:
   * Same flat card styling through Qt Style Sheets (QSS); used only when GTK is unavailable. Single-instance via `QLocalServer`/`QLocalSocket`.

---

## 5. Global Hotkey Registration (`hotkeys/`)


Handled per desktop environment:
* **GNOME / MATE**: Configures a custom keybinding via `gsettings` (`org.gnome.settings-daemon.plugins.media-keys` / MATE media-keys) and disables the built-in `switch-monitor` Super+P shortcut. Reversible on uninstall.
* **Cinnamon**: Uses Cinnamon's *own* custom-shortcut mechanism — `org.cinnamon.desktop.keybindings custom-list` plus a relocatable schema at `/org/cinnamon/desktop/keybindings/custom-keybindings/customN/` (name/command are plain strings, binding is an array of strings). Writing the GNOME media-keys path silently does nothing on Cinnamon. Also clears `org.cinnamon.desktop.keybindings.wm switch-monitor`.
* **KDE Plasma**: Installs a `.desktop` file with `X-KDE-GlobalAccel=true`, sets the shortcut with `kwriteconfig5`/`kwriteconfig6`, and reloads `kglobalaccel`.
* **XFCE**: Registers shortcut via `xfconf-query` on channel `xfce4-keyboard-shortcuts`.
* **Sway / Hyprland / i3**: Config files are never modified without explicit user opt-in. Prints the exact snippet, and appends to config only when `--append-config` is provided.
* **Generic X11 Fallback**: Background daemon using `python-xlib` (`project-menu --hotkey-daemon`) properly handling NumLock and CapsLock modifier masks, or `sxhkd` configuration.

---

## 6. Packaging & Portability

* **`install.sh`**:
  * Detects package manager: Debian/Ubuntu (`apt`), Fedora (`dnf`), Arch (`pacman`), openSUSE (`zypper`).
  * Installs only dependencies relevant to the detected environment.
  * Copies program to `~/.local/share/project-menu`, links executable to `~/.local/bin/project-menu`.
  * Installs high-resolution SVG icon and `.desktop` entry.
  * Registers global hotkey.
* **`uninstall.sh`**:
  * Unregisters hotkey, restores default system keybindings, and deletes program files, icon, and desktop entry.
* **`pyproject.toml`**:
  * Standards-compliant packaging config for direct installation via `pipx install .`.

---

## 7. Verification & Testing

* **102 Automated Unit Tests** (`python3 -m unittest discover -s tests -p "test_*.py"`):
  * Environment detection (`test_detect.py`)
  * Mode inference, primary selection, duplicate resolution math (`test_core.py`)
  * X11 backend with query parsing, duplicate warnings, and positional calls (`test_x11_backend.py`)
  * GNOME Wayland Mutter D-Bus backend (`test_gnome_backend.py`)
  * KDE Plasma kscreen-doctor backend (`test_kde_backend.py`)
  * Sway backend (`test_sway_backend.py`)
  * Hyprland backend (`test_hyprland_backend.py`)
  * Generic wlroots and COSMIC backends (`test_wlroots_cosmic.py`)
  * Hotkey registrars across all desktops (`test_hotkeys.py`)
  * CLI arguments, dry-run, output listings, and positional calls (`test_cli.py`)
  * Backend registry selection, overrides, and fallback message (`test_registry.py`)
* Verified bug-free with 100% test pass rate.
