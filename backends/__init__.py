"""Backend package: pluggable display backends, auto-detected at runtime."""

from backends.base import SubprocessBackend
from backends.x11 import X11Backend
from backends.gnome import GnomeWaylandBackend
from backends.kde import KdeBackend
from backends.sway import SwayBackend
from backends.hyprland import HyprlandBackend
from backends.wlroots import WlrootsBackend
from backends.cosmic import CosmicBackend

__all__ = [
    "SubprocessBackend",
    "X11Backend",
    "GnomeWaylandBackend",
    "KdeBackend",
    "SwayBackend",
    "HyprlandBackend",
    "WlrootsBackend",
    "CosmicBackend",
]
