<div align="center">

# 🖥️ project-menu

### The modern **Win + P** display switcher for Linux, crafted with Apple-level elegance.

[![CI](https://github.com/your-username/project-menu/actions/workflows/ci.yml/badge.svg)](https://github.com/your-username/project-menu/actions)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Wayland%20%7C%20X11-2ea44f.svg)]()
[![Code style: clean](https://img.shields.io/badge/code%20style-PEP%208-black.svg)](https://peps.python.org/pep-0008/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

<p align="center">
  <a href="#-features">Features</a> •
  <a href="#-visual-tour">Visual Tour</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-keyboard-shortcuts">Shortcuts</a> •
  <a href="#-support-matrix">Support Matrix</a> •
  <a href="#-cli-power-tools">CLI Guide</a> •
  <a href="#-testing--diagnostics">Testing</a> •
  <a href="#-extensibility">Add a Backend</a>
</p>

---

</div>

Press **<kbd>Super</kbd> + <kbd>P</kbd>** from anywhere on Linux to bring up a gorgeous, frosted-glass display projection card:

* 💻 **PC screen only** — Disconnect external monitors and save battery.
* 🪞 **Duplicate** — Mirror your primary screen at optimal resolution.
* 🖥️ **Extend** — Expand your workspace horizontally or vertically.
* 📺 **Second screen only** — Turn off your laptop screen and dock to external displays.

**Zero configuration required.** `project-menu` inspects your desktop environment and display server at runtime, seamlessly routing calls to **Mutter D-Bus**, **KScreen**, **swaymsg**, **hyprctl**, **wlr-randr**, **cosmic-randr**, or **xrandr**.

---

## 🎨 Visual Tour

### Apple-Style Glassmorphic Popup
Crafted with frosted translucency, vibrant squircle icons, San Francisco-inspired typography, and glowing active-mode states.

```text
  ┌─────────────────────────────────────────────────────────────┐
  │                        Display Modes                        │
  │     Choose how to project or arrange connected screens      │
  │                                                             │
  │   ╭─────────────────────────────────────────────────────╮   │
  │   │  ┌──────┐                                           │   │
  │   │  │  💻  │   PC screen only                    [ 1 ] │   │
  │   │  └──────┘   Disconnect external monitors            │   │
  │   ╰─────────────────────────────────────────────────────╯   │
  │   ╭─────────────────────────────────────────────────────╮   │
  │   │  ┌──────┐                                           │   │
  │   │  │  🪞  │   Duplicate                         [ 2 ] │   │
  │   │  └──────┘   Mirror primary display contents         │   │
  │   ╰─────────────────────────────────────────────────────╯   │
  │   ╭─────────────────────────────────────────────────────╮   │
  │   │  ┌──────┐                                    ACTIVE │   │
  │   │  │  🖥️  │   Extend                            [ 3 ] │   │
  │   │  └──────┘   Expand your desktop workspace           │   │
  │   ╰─────────────────────────────────────────────────────╯   │
  │   ╭─────────────────────────────────────────────────────╮   │
  │   │  ┌──────┐                                           │   │
  │   │  │  📺  │   Second screen only                [ 4 ] │   │
  │   │  └──────┘   Turn off the internal display           │   │
  │   ╰─────────────────────────────────────────────────────╯   │
  │                                                             │
  │      ↑/↓/Tab: Navigate   •   Enter: Apply   •   Esc: Exit   │
  └─────────────────────────────────────────────────────────────┘
```

### 15-Second Black-Screen Safety Revert Sheet
Never worry about bad display modes, disconnected cables, or unsupported refresh rates locking you out.

```text
  ┌─────────────────────────────────────────────────────────────┐
  │                       Keep Displays?                        │
  │          Reverting to previous layout in 14 seconds         │
  │                                                             │
  │              [ Keep Changes ]      [ Revert Now ]           │
  └─────────────────────────────────────────────────────────────┘
```

---

## ✨ Features

* 🍏 **Apple macOS Aesthetics**: Frosted glass blur background, squircle gradient glyph tiles, active mode accent badges, and native dark/light theme tracking.
* ⚡ **Runtime Environment Detection**: Automatically picks the best backend using `$XDG_SESSION_TYPE`, `$XDG_CURRENT_DESKTOP`, `$WAYLAND_DISPLAY`, `$HYPRLAND_INSTANCE_SIGNATURE`, and `$SWAYSOCK`.
* 🛡️ **15-Second Revert Protection**: Automatic rollback timer prevents black-screen lockouts whenever modes are switched.
* 🔁 **Win+P Cycling**: Single-instance architecture via `Gio.Application` allows pressing <kbd>Super</kbd> + <kbd>P</kbd> repeatedly to cycle through modes smoothly.
* 🖥️ **Smart Multi-Monitor Routing**:
  * **1 Monitor**: Clean alert notifying that no external screen is attached.
  * **2 Monitors**: Instant zero-click switching.
  * **3+ Monitors**: Interactive target screen picker and configurable extend orientation (`right`, `left`, `above`, `below`).
* 🪞 **Intelligent Mirroring**: Automatically negotiates the highest common resolution between displays and warns if refresh rates diverge.
* ⌨️ **Keyboard-Driven & Accessible**: Full arrow key navigation, Tab navigation, numeric direct triggers (`1`–`4`), and focus-loss dismissal.
* 🧰 **Scriptable CLI**: Standalone mode commands for window manager shortcuts, dotfiles, or terminal scripts.
* 📦 **Universal Linux Installer**: Dependency auto-resolution across `apt` (Ubuntu/Debian), `dnf` (Fedora), `pacman` (Arch), and `zypper` (openSUSE).

---

## 🚀 Quick Start

### 1. One-Line Installer (Recommended)

Clone the repository and run the automated installer. It detects your package manager, installs only the required libraries for your current desktop, sets up icons, and registers global hotkeys:

```bash
git clone https://github.com/your-username/project-menu.git
cd project-menu
./install.sh
```

> [!TIP]
> On tiling compositors (Sway, Hyprland, i3), `install.sh` never touches your dotfiles without permission. It prints the exact config snippet or accepts `--append-config` to write it automatically.

### 2. Using pipx

If you prefer managing Python applications via `pipx`:

```bash
pipx install .
project-menu --list
```

*(Note: pipx installs the Python executable. Run `./install.sh` or consult your package manager to set up system packages like `python3-gi`, `gir1.2-gtk-3.0`, and desktop hotkeys).*

### 3. Uninstalling

To cleanly remove binaries, icons, state files, and unregister global hotkeys:

```bash
./uninstall.sh
```

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action | Description |
|---|---|---|
| <kbd>Super</kbd> + <kbd>P</kbd> | **Launch / Cycle** | Opens the menu; pressing again while open cycles selection |
| <kbd>↑</kbd> / <kbd>↓</kbd> | **Navigate** | Move focus between display modes |
| <kbd>Tab</kbd> / <kbd>Shift</kbd>+<kbd>Tab</kbd> | **Navigate** | Move focus forwards or backwards |
| <kbd>1</kbd>, <kbd>2</kbd>, <kbd>3</kbd>, <kbd>4</kbd> | **Quick Select** | Direct select: 1=PC only, 2=Duplicate, 3=Extend, 4=Second only |
| <kbd>Enter</kbd> / <kbd>Space</kbd> | **Apply** | Apply the selected display configuration |
| <kbd>Escape</kbd> | **Dismiss** | Close popup without making changes |
| *Click outside / blur* | **Dismiss** | Closes popup on focus loss |

---

## 📊 Support Matrix

`project-menu` provides first-class support for every major Linux desktop and compositor:

| Desktop Environment / WM | Session | Display Backend | Overlay Presentation | Hotkey Mechanism | Status |
|---|---|---|---|---|:---:|
| **GNOME / Ubuntu** | Wayland | Mutter D-Bus API (`org.gnome.Mutter.DisplayConfig`) | Centered Window¹ | `gsettings` custom keybinding | ✅ Full |
| **GNOME / Ubuntu** | X11 | `xrandr` | Always-on-top overlay | `gsettings` custom keybinding | ✅ Full |
| **KDE Plasma** | Wayland | `kscreen-doctor` / KScreen D-Bus | `gtk-layer-shell` overlay | `kglobalaccel` shortcut | ✅ Full |
| **KDE Plasma** | X11 | `xrandr` | Always-on-top overlay | `kglobalaccel` shortcut | ✅ Full |
| **Sway** | Wayland | `swaymsg` output engine | `gtk-layer-shell` overlay | Sway config snippet² | ✅ Full |
| **Hyprland** | Wayland | `hyprctl` keyword monitor | `gtk-layer-shell` overlay | Hyprland config snippet² | ✅ Full |
| **wlroots** *(river, labwc, Wayfire)* | Wayland | `wlr-randr` | `gtk-layer-shell` overlay | WM config snippet² | ✅ Full |
| **COSMIC** | Wayland | `cosmic-randr` | `gtk-layer-shell` overlay | Desktop shortcut / CLI | ✅ Full |
| **XFCE** | X11 | `xrandr` | Always-on-top overlay | `xfconf-query` | ✅ Full |
| **Cinnamon / MATE** | X11 | `xrandr` | Always-on-top overlay | `dconf` / `gsettings` | ✅ Full |
| **i3 / bspwm / Openbox** | X11 | `xrandr` | Always-on-top overlay | Python-Xlib `XGrabKey` daemon | ✅ Full |

<small>
¹ GNOME Wayland intentionally does not implement <code>wlr-layer-shell</code>; the popup opens as a standard focused floating window.<br>
² Tiling WMs provide configuration snippets to preserve your custom dotfile workflows (or pass <code>--append-config</code> during install).
</small>

---

## 🛠️ CLI Power Tools

`project-menu` isn't just a GUI; it's also a powerful CLI utility for custom scripts, stream decks, and custom keyboard bindings:

```bash
# Show the Apple-style interactive popup
project-menu

# Print all detected screens, active states, resolutions, and refresh rates
project-menu --list

# Switch display mode instantly without opening the UI
project-menu --mode extend
project-menu --mode duplicate
project-menu --mode internal
project-menu --mode external

# Position secondary displays arbitrarily (right, left, above, below)
project-menu --mode extend --position left
project-menu --mode extend --position above

# Multi-monitor targeting: choose which screen to project onto
project-menu --mode extend --output DP-2

# Test changes with the 15-second auto-revert countdown
project-menu --mode duplicate --confirm

# Dry-run: view exact compositor commands without applying
project-menu --mode extend --dry-run

# Troubleshoot and inspect environment detection
project-menu --debug

# Override backend detection manually
project-menu --backend hyprland
```

---

## 🧪 Testing & Diagnostics

### Headless & Mock Unit Tests
The test suite includes 100+ tests that mock all hardware calls, D-Bus interfaces, and command outputs, allowing you to test on any machine:

```bash
# Run complete test suite
python3 -m unittest discover -s tests -p "test_*.py" -v

# Or with pytest
python3 -m pytest -q
```

### Emulating Multi-Monitor Setups on a Single Laptop Screen
Don't have a second monitor handy? You can simulate multi-head setups in seconds:

<details>
<summary><b>Click to expand virtual display recipes</b></summary>

#### X11 (Virtual Monitor with xrandr)
```bash
# Create a virtual 1080p output side-by-side
xrandr --setmonitor VIRTUAL1 1920/520x1080/290+1920+0 none
project-menu --list
# To remove:
xrandr --delmonitor VIRTUAL1
```

#### X11 (Virtual Framebuffer with Xvfb)
```bash
Xvfb :99 -screen 0 1920x1080x24 &
DISPLAY=:99 project-menu --list
```

#### Sway (Virtual Wayland Output)
```bash
swaymsg create_output
swaymsg output HEADLESS-1 resolution 1920x1080
project-menu --list
```

#### Hyprland (Headless Wayland Output)
```bash
hyprctl output create headless
project-menu --list
```
</details>

---

## 🧩 Extensibility: How to Add a New Backend

Adding support for an upcoming compositor or window manager takes fewer than 50 lines of Python.

### Step 1: Create `backends/mywm.py`

Subclass `SubprocessBackend` (or `DisplayBackend` directly) and implement output discovery and mode command planning:

```python
from backends.base import SubprocessBackend
from interfaces import ApplyResult, Output, Selection
from core import infer_mode, primary_output

class MyWMBackend(SubprocessBackend):
    name = "mywm"
    priority = 45  # Lower number = higher evaluation priority

    @classmethod
    def can_handle(cls, env):
        return env.session_type == "wayland" and env.has_desktop("mywm")

    def list_outputs(self) -> list[Output]:
        code, stdout, _ = self._run(["mywmctl", "list-displays"])
        return self.parse_outputs(stdout)

    def plan(self, selection: Selection) -> list[str]:
        # Generate the command line strings to apply the mode
        if selection.mode.value == "internal":
            return ["mywmctl", "disable", "HDMI-1"]
        return ["mywmctl", "enable", "HDMI-1"]

    def apply(self, selection: Selection) -> ApplyResult:
        commands = self.plan(selection)
        # Execute commands via self._run(...)
        return ApplyResult(success=True, commands=commands)
```

### Step 2: Register in `backends/registry.py`

```python
from backends.mywm import MyWMBackend

BACKENDS.append(MyWMBackend)
ALIASES["mywm"] = "mywm"
```

### Step 3: Add unit tests in `tests/test_mywm_backend.py`

Use `make_runner(...)` from `tests/helpers.py` to test parsing, planning, and error handling without spawning processes.

---

## 📁 Project Architecture

```
project-menu/
├── backends/             # Pluggable display server drivers
│   ├── base.py           # Subprocess runner & revert snapshot base
│   ├── cosmic.py         # System76 COSMIC randr driver
│   ├── gnome.py          # Mutter DisplayConfig D-Bus driver
│   ├── hyprland.py       # Hyprland hyprctl driver
│   ├── kde.py            # KDE Plasma kscreen-doctor driver
│   ├── registry.py       # Auto-discovery priority pipeline
│   ├── sway.py           # Sway IPC driver
│   ├── wlroots.py        # Generic wlr-randr driver
│   └── x11.py            # X11 xrandr driver
├── hotkeys/              # Desktop environment shortcut hooks
│   ├── gnome.py          # GNOME / Cinnamon / MATE gsettings
│   ├── kde.py            # KDE kglobalaccel hook
│   ├── xfce.py           # XFCE xfconf-query hook
│   ├── wm.py             # Sway / Hyprland / i3 config generators
│   └── x11_grab.py       # Generic X11 XGrabKey listener daemon
├── ui/                   # User interface components
│   ├── gtk_ui.py         # Apple-inspired GTK 3/4 glassmorphism card
│   └── qt_ui.py          # High-fidelity Qt fallback interface
├── tests/                # 100+ comprehensive automated tests
├── install.sh            # Smart cross-distro package installer
├── uninstall.sh          # Complete uninstaller script
├── main.py               # Main CLI & single-instance controller
├── detect.py             # Environment detection heuristics
├── core.py               # Math, geometry, resolution & logger engine
└── pyproject.toml        # PEP 517/621 package metadata
```

---

## 🤝 Contributing

Contributions make the open-source community an inspiring place to learn, create, and build. Any contributions you make are **greatly appreciated**!

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Run test suites (`python3 -m unittest discover -s tests`)
4. Commit your Changes (`git commit -m 'feat: add AmazingFeature'`)
5. Push to the Branch (`git push origin feature/AmazingFeature`)
6. Open a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for full development guidelines.

---

## 📜 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for more information.

---

<div align="center">
  <sub>Built with ❤️ for the Linux Desktop Community. Inspired by macOS & Windows Win+P.</sub>
</div>
