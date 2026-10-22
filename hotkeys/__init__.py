"""Hotkey package: per-environment Super+P registration."""

from hotkeys.gnome import GnomeHotkey, CinnamonHotkey, MateHotkey
from hotkeys.kde import KdeHotkey
from hotkeys.xfce import XfceHotkey
from hotkeys.wm import SwayHotkey, HyprlandHotkey, I3Hotkey
from hotkeys.x11_grab import X11GrabHotkey

__all__ = [
    "GnomeHotkey",
    "CinnamonHotkey",
    "MateHotkey",
    "KdeHotkey",
    "XfceHotkey",
    "SwayHotkey",
    "HyprlandHotkey",
    "I3Hotkey",
    "X11GrabHotkey",
]
