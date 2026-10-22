# project-menu

A cross-distro, cross-desktop Linux utility that mimics Windows' **Win+P** "Project"
menu. Press **Super+P** and choose:

* **PC screen only**
* **Duplicate**
* **Extend**
* **Second screen only**

It auto-detects your environment at runtime and picks the right display backend,
hotkey registrar and popup UI — no configuration required.

---

## Features

* **Pluggable backends**, auto-detected via `$XDG_SESSION_TYPE`, `$XDG_CURRENT_DESKTOP`,
  `$WAYLAND_DISPLAY`, `$HYPRLAND_INSTANCE_SIGNATURE` and `$SWAYSOCK`. Override with
  `--backend NAME`.
* **Display backends** for X11 (`xrandr`), GNOME Wayland (Mutter D-Bus — no `gdctl`),
  KDE Plasma (`kscreen-doctor`), Sway, Hyprland, generic wlroots (`wlr-randr`) and COSMIC.
* **1 / 2 / 3+ monitor handling**: shows "no second display detected" on a single
  screen, and lets you pick which display is the "second screen" when three or more
  are connected.
* **Extend position**: right (default), left, above or below.
* **Duplicate** uses the highest common resolution and warns when refresh rates differ.
* **Revert protection**: a 15-second "Keep changes?" confirmation (or Revert) so a
  bad config can never leave you with a black screen.
* **Popup UI** in Python 3 + GTK (3 or 4), with a Qt fallback only when GTK is missing.
  Borderless, centered, theme-aware, keyboard-driven (`↑/↓/Tab`, `Enter`, `Esc`, `1-4`),
  highlights the active mode, and cycles on a second Super+P press.
* **Global hotkey registration** per desktop, with clear manual instructions when a
  desktop can't be configured automatically.
* **CLI** for scripting: `--list`, `--mode`, `--dry-run`, `--debug`, `--backend`.
* **Logging** to `~/.local/state/project-menu/log`, plus `notify-send` on failure.

---

## Installation

### From this repository

```bash
./install.sh                 # detects apt/dnf/pacman/zypper, installs deps + hotkey
./uninstall.sh               # reverses everything
```

`install.sh` installs only the dependencies relevant to your detected environment
(e.g. `libkscreen` on KDE, `sway` on Sway, `gtk-layer-shell` on wlroots compositors).

Options: `--append-config` (Sway/Hyprland/i3: append the hotkey snippet to your WM
config instead of just printing it), `--no-hotkey` (skip hotkey registration).

### Via pipx

```bash
pipx install .
pipx run project-menu --list
```

Note: pipx installs the Python code but does **not** install system dependencies
(`xrandr`, `kscreen-doctor`, GTK bindings, …) or register the hotkey. Use
`install.sh` for a fully wired install, or install those manually.

---

## Usage

```
project-menu              # show the popup
project-menu --list       # list detected outputs
project-menu --mode extend|duplicate|internal|external   # apply without popup
project-menu --mode extend --position left               # extend to the left
project-menu --mode extend --output DP-1                 # choose the second screen (or --target-output)
project-menu --mode extend --confirm                     # apply with 15s auto-revert prompt
project-menu --dry-run --mode duplicate                  # print commands only
project-menu --debug                                     # print environment + backend
project-menu --backend sway                              # force a backend
project-menu --register-hotkey | --unregister-hotkey
```

`--mode` is ideal for binding manually (e.g. a WM keybind per mode). To revert a
CLI-applied change: `project-menu --mode internal` (or the original mode).

---

## Architecture

```
main.py                 entry point
cli.py                  argparse + dispatch
detect.py               environment detection ($XDG_SESSION_TYPE, desktop, …)
interfaces.py           DisplayBackend / HotkeyRegistrar / PopupUI + data types
core.py                 logging, notify-send, mode inference, output selection
backends/               one module per backend + registry
hotkeys/                per-desktop Super+P registrars + registry
ui/                     GTK popup (gtk_ui.py) + Qt fallback (qt_ui.py)
```

### Detection order

1. If `--backend` is given, use it (after alias resolution).
2. Otherwise iterate the backend registry in priority order; the first backend whose
   `can_handle(env)` passes **and** whose required tool/API is available wins.
3. If nothing matches, print an error naming the detected environment and explaining
   how to add a backend.

The environment is normalized into a small `Environment` dataclass (see
`detect.py`) and passed to every backend/hotkey registrar.

### Backend contract

Each backend implements `list_outputs()`, `get_current_mode()`,
`plan(selection) -> [commands]` and `apply(selection) -> ApplyResult`, plus
`snapshot()`/`restore()` for the revert flow. Subprocess backends share a single
`_run()` seam so unit tests can substitute canned command output; the GNOME backend
shares a `_call()` seam for mocked D-Bus.

---

## Support matrix

| Desktop | Session | Backend | Internal | Duplicate | Extend | External | Popup overlay | Hotkey |
|---|---|---|---|---|---|---|---|---|
| GNOME / Ubuntu | X11 | xrandr | ✅ | ✅ | ✅ | ✅ | always-on-top, centered | gsettings |
| GNOME / Ubuntu | Wayland | Mutter D-Bus | ✅ | ✅ | ✅ | ✅ | normal window¹ | gsettings |
| KDE Plasma | X11 | xrandr | ✅ | ✅ | ✅ | ✅ | always-on-top | kglobalaccel |
| KDE Plasma | Wayland | kscreen-doctor | ✅ | ✅² | ✅ | ✅ | layer-shell | kglobalaccel |
| Sway | Wayland | swaymsg | ✅ | ✅ | ✅ | ✅ | layer-shell | config snippet³ |
| Hyprland | Wayland | hyprctl | ✅ | ✅⁴ | ✅ | ✅ | layer-shell | config snippet³ |
| river / labwc / Wayfire | Wayland | wlr-randr | ✅ | ✅² | ✅ | ✅ | layer-shell | config snippet³ |
| COSMIC | Wayland | cosmic-randr | ✅ | ✅⁴ | ✅ | ✅ | layer-shell | manual |
| Cinnamon / MATE | any | xrandr / Mutter⁵ | ✅ | ✅ | ✅ | ✅ | per session | dconf⁶ |
| XFCE | X11 | xrandr | ✅ | ✅ | ✅ | ✅ | always-on-top | xfconf-query |
| Other X11 (i3, openbox, …) | X11 | xrandr | ✅ | ✅ | ✅ | ✅ | always-on-top | XGrabKey daemon / sxhkd |
| Other Wayland | Wayland | — | ❌ | ❌ | ❌ | ❌ | — | — |

¹ GNOME Wayland has no wlr-layer-shell, so the popup is a normal focused window and
   cannot be positioned or kept on top. It still works — just focus it with Super+P.
² KDE / wlr-randr "duplicate" places both outputs at the same position with the same
   mode; most compositors treat that as mirroring. On KDE, KScreen's own replication
   is used under the hood.
³ Sway/Hyprland/i3 configs are **never edited automatically**. `install.sh` prints
   the exact snippet; pass `--append-config` to append it.
⁴ Hyprland and COSMIC use their native `mirror` feature.
⁵ Cinnamon/MATE on Wayland fall back to the X11/xrandr or Mutter backend depending
   on the session; on Wayland-only setups MATE/Cinnamon are not currently supported.
⁶ Cinnamon/MATE hotkey registration is best-effort via dconf; schema names vary by
   version, so `install.sh` prints manual instructions if it fails.

### Known limitations

* **GNOME Wayland**: requires `IsExperimentalApiEnabled` (on by default in modern
  Mutter). Mode IDs are the exact strings mutter reports; if a mode isn't found the
  D-Bus call is rejected atomically.
* **Scaling**: the GNOME backend preserves each monitor's scale, but extend position
  math uses the logical (scaled) size — fractional-scaling edge cases are possible.
* **Duplicate refresh**: when two displays share a resolution but not a refresh rate,
  the lower-rate display is driven at the common resolution; a warning is shown.
* **NVIDIA on Wayland**: behaviour depends on the compositor/driver; X11/xrandr is
  the most reliable path on NVIDIA.
* **cosmic-randr** and **kscreen-doctor** CLIs are version-dependent; the backends
  parse leniently but newer releases may need small adjustments.

---

## Testing

Unit tests mock every backend's command output (or D-Bus responses), so they run on
any machine without real displays:

```bash
python3 -m unittest discover -s tests        # stdlib runner
# or, if you have pytest:
python3 -m pytest -q
```

Covered: environment detection, mode inference, duplicate-resolution selection, and
`list_outputs`/`plan`/`apply` for X11, GNOME, KDE, Sway, Hyprland, wlr-randr and
COSMIC (see `tests/`).

### Testing with a single physical monitor

* **X11 — fake a second monitor with `xrandr --setmonitor`:**
  ```bash
  xrandr --setmonitor VIRTUAL1 1920/520x1080/290+1920+0 none
  project-menu --list          # VIRTUAL1 should appear
  ```
* **X11 — headless with Xvfb:**
  ```bash
  Xvfb :99 -screen 0 1920x1080x24 &
  DISPLAY=:99 xrandr           # exercise the xrandr backend
  ```
* **Sway — create a virtual output:**
  ```bash
  swaymsg create_output
  swaymsg output HEADLESS-1 resolution 1920x1080
  ```
* **Hyprland — create a headless output:**
  ```bash
  hyprctl output create headless
  ```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `project-menu: command not found` | `~/.local/bin` is not on your `PATH`; log out/in or add it. |
| Popup doesn't appear / no overlay | GNOME Wayland has no layer-shell — the window is a normal window; press Super+P again to focus. Ensure `python3-gi` + `gir1.2-gtk-3.0` are installed. |
| "No supported display backend" | Run `project-menu --debug` to see the detected environment; see "How to add a new backend". |
| Super+P does nothing | `install.sh` couldn't register it; run `project-menu --register-hotkey` to see the manual instructions for your desktop. |
| Black screen after switching | The popup auto-reverts after 15 s unless you click "Keep". From a terminal: `project-menu --mode internal`. |
| Duplicate shows different refresh | Expected — see "Known limitations". |
| KDE: changes don't stick | kscreen-doctor is atomic; if one setting is invalid *nothing* is applied (this is intentional). |

Logs are written to `~/.local/state/project-menu/log`; run with `--debug` for
verbose output on stderr.

---

## How to add a new backend

Adding support for a new compositor/desktop is a two-file change:

1. **Create `backends/<name>.py`** subclassing `DisplayBackend`
   (`from interfaces import DisplayBackend`), or `SubprocessBackend`
   (`from backends.base import SubprocessBackend`) if it shells out to a CLI.

   ```python
   from backends.base import SubprocessBackend
   from interfaces import DisplayMode, Selection

   class MyBackend(SubprocessBackend):
       name = "mywm"                    # used by --backend and registry
       priority = 70                    # lower = preferred in auto-detect
       LIST_CMD = ["mywmctl", "outputs"]

       @classmethod
       def can_handle(cls, env):
           return env.session_type == "wayland" and env.has_desktop("mywm")

       def parse_outputs(self, text):   # -> list[Output]
           ...

       def get_current_mode(self):      # usually: return infer_mode(self.list_outputs())
           from core import infer_mode
           return infer_mode(self.list_outputs())

       def plan(self, selection: Selection):  # -> list[str] human-readable commands
           ...

       def apply(self, selection: Selection): # -> ApplyResult
           ...
   ```

   Reuse the helpers in `core.py` (`infer_mode`, `primary_output`,
   `best_duplicate_mode`, …) so mode logic stays consistent.

2. **Register it** in `backends/registry.py`: add the class to `BACKENDS` and,
   optionally, an alias in `ALIASES`.

Then add unit tests in `tests/test_<name>_backend.py` using `make_runner(...)` from
`tests/helpers.py` (see the existing backend tests).

The same pattern applies to **hotkeys** (`hotkeys/<name>.py` + `hotkeys/registry.py`)
and **UIs** (`ui/<name>.py`).

### Project layout

```
main.py  cli.py  detect.py  interfaces.py  core.py
backends/   base.py  x11.py  gnome.py  kde.py  sway.py  hyprland.py  wlroots.py  cosmic.py  registry.py
hotkeys/    gnome.py  kde.py  xfce.py  wm.py  x11_grab.py  registry.py
ui/         base.py  gtk_ui.py  qt_ui.py
tests/      test_*.py  helpers.py  conftest.py
install.sh  uninstall.sh  pyproject.toml  README.md
```
