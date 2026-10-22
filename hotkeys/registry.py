"""Hotkey registry: pick a registrar for the detected environment."""

from __future__ import annotations

from interfaces import HotkeyRegistrar

from hotkeys.gnome import CinnamonHotkey, GnomeHotkey, MateHotkey
from hotkeys.kde import KdeHotkey
from hotkeys.wm import HyprlandHotkey, I3Hotkey, SwayHotkey
from hotkeys.x11_grab import X11GrabHotkey
from hotkeys.xfce import XfceHotkey

REGISTRARS: list[type[HotkeyRegistrar]] = [
    GnomeHotkey,
    CinnamonHotkey,
    MateHotkey,
    KdeHotkey,
    XfceHotkey,
    SwayHotkey,
    HyprlandHotkey,
    I3Hotkey,
    X11GrabHotkey,
]

BY_NAME: dict[str, type[HotkeyRegistrar]] = {r.name: r for r in REGISTRARS}


def select(env, append_config: bool = False) -> HotkeyRegistrar | None:
    """Return the appropriate registrar, or None if none matches."""
    for cls in REGISTRARS:
        if cls.can_handle(env):
            return cls(append=append_config)
    return None


def select_by_name(name: str, append_config: bool = False) -> HotkeyRegistrar | None:
    cls = BY_NAME.get(name)
    if cls is None:
        return None
    return cls(append=append_config)
