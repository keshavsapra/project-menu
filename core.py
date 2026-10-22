"""Shared helpers: logging, notifications, mode inference and output selection."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from interfaces import DisplayMode, ExtendPosition, ModeInfo, Output

APP_NAME = "project-menu"
APP_ID = "org.projectmenu.ProjectMenu"
APP_TITLE = "Project Menu"

_HOME = Path.home()
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", _HOME / ".local" / "state")) / APP_NAME
LOG_PATH = STATE_DIR / "log"

_log_configured = False


def setup_logging(debug: bool = False) -> None:
    """Configure file + (optionally) console logging. Idempotent."""
    global _log_configured
    if _log_configured:
        return
    logger = logging.getLogger("projectmenu")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        file_handler = None
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        except OSError:
            try:
                import tempfile
                tmp_dir = Path(tempfile.gettempdir()) / f"project-menu-{os.getuid() if hasattr(os, 'getuid') else 'user'}"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                file_handler = logging.FileHandler(tmp_dir / "log", encoding="utf-8")
            except OSError:
                file_handler = None
        if file_handler is not None:
            file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
            logger.addHandler(file_handler)
        if debug:
            sh = logging.StreamHandler()
            sh.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
            logger.addHandler(sh)
    _log_configured = True


def log() -> logging.Logger:
    return logging.getLogger("projectmenu")


def notify(title: str, message: str, urgent: bool = False) -> None:
    """Best-effort desktop notification via notify-send."""
    if not shutil.which("notify-send"):
        return
    argv = ["notify-send", "-a", APP_NAME]
    if urgent:
        argv.append("-u")
        argv.append("critical")
    argv += [title, message]
    try:
        subprocess.run(argv, capture_output=True, timeout=5)
    except Exception:
        pass


def which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


_BUILTIN_RE = re.compile(r"^(eDP|LVDS|DSI)", re.IGNORECASE)


def is_builtin_name(name: str) -> bool:
    return bool(_BUILTIN_RE.match(name or ""))


def active_outputs(outputs) -> list[Output]:
    return [o for o in outputs if o.is_active]


def infer_mode(outputs) -> DisplayMode | None:
    """Infer the current project mode from a set of :class:`Output` objects."""
    active = active_outputs(outputs)
    if not active:
        return None
    if len(active) == 1:
        return DisplayMode.EXTERNAL if not active[0].builtin else DisplayMode.INTERNAL
    positions = {(o.x, o.y) for o in active}
    if len(positions) == 1:
        return DisplayMode.DUPLICATE
    return DisplayMode.EXTEND


def primary_output(outputs) -> Output | None:
    outs = list(outputs)
    for o in outs:
        if o.primary and o.connected:
            return o
    for o in outs:
        if o.builtin and o.connected:
            return o
    for o in outs:
        if o.connected:
            return o
    return None


def secondary_outputs(outputs) -> list[Output]:
    prim = primary_output(outputs)
    prim_name = prim.name if prim else None
    return [o for o in outputs if o.connected and o.name != prim_name]


def find_mode(output: Output, width: int, height: int, refresh: float | None = None) -> ModeInfo | None:
    """Find the closest matching mode on *output*."""
    candidates = [m for m in output.modes if m.width == width and m.height == height]
    if not candidates:
        return None
    if refresh is not None:
        exact = min(candidates, key=lambda m: abs(m.refresh - refresh), default=None)
        if exact is not None:
            return exact
    # Prefer the currently active or preferred mode.
    for m in candidates:
        if output.current_mode and m.width == output.current_mode.width and m.height == output.current_mode.height \
                and abs(m.refresh - output.current_mode.refresh) < 0.01:
            return m
    return max(candidates, key=lambda m: m.refresh)


def best_duplicate_mode(a: Output, b: Output) -> tuple[ModeInfo | None, ModeInfo | None, str]:
    """Choose the highest common resolution between two outputs.

    Returns ``(mode_a, mode_b, warning)``. ``mode_a``/``mode_b`` are the per-output
    :class:`ModeInfo` at the chosen resolution (they may differ in refresh rate,
    in which case a warning is produced).
    """
    a_modes: dict[str, ModeInfo] = {}
    modes_a = list(a.modes)
    if not modes_a and a.current_mode:
        modes_a = [a.current_mode]
    elif not modes_a and a.width and a.height:
        modes_a = [ModeInfo(a.width, a.height, 60.0)]
    for m in modes_a:
        a_modes.setdefault(f"{m.width}x{m.height}", m)

    b_modes: dict[str, ModeInfo] = {}
    modes_b = list(b.modes)
    if not modes_b and b.current_mode:
        modes_b = [b.current_mode]
    elif not modes_b and b.width and b.height:
        modes_b = [ModeInfo(b.width, b.height, 60.0)]
    for m in modes_b:
        b_modes.setdefault(f"{m.width}x{m.height}", m)

    common = [k for k in a_modes if k in b_modes]
    if not common:
        return None, None, "no common resolution between the displays"
    common.sort(key=lambda k: a_modes[k].pixels, reverse=True)
    ma, mb = a_modes[common[0]], b_modes[common[0]]
    warning = ""
    if abs(ma.refresh - mb.refresh) > 0.01:
        warning = (
            f"displays run at different refresh rates at {common[0]} "
            f"({ma.refresh:g}Hz vs {mb.refresh:g}Hz)"
        )
    return ma, mb, warning


def build_options(outputs) -> tuple[list[tuple[DisplayMode, bool]], str]:
    """Build the popup's (mode, enabled) options plus a note string."""
    connected = [o for o in outputs if o.connected]
    n = len(connected)
    multi = n >= 2
    options = [
        (DisplayMode.INTERNAL, True),
        (DisplayMode.DUPLICATE, multi),
        (DisplayMode.EXTEND, multi),
        (DisplayMode.EXTERNAL, multi),
    ]
    note = ""
    if n == 0:
        note = "No displays detected."
    elif n == 1:
        note = "No second display detected."
    elif n > 2:
        note = f"{n} displays detected — the second screen can be chosen."
    return options, note
