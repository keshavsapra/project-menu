"""Runtime environment detection.

We inspect the standard Freedesktop / compositor environment variables to
figure out (a) the session type (X11 vs Wayland) and (b) the desktop /
compositor, then hand that to the backend and hotkey registries.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Environment:
    session_type: str = ""            # "x11", "wayland", "tty", "mir", or ""
    desktop: str = ""                 # $XDG_CURRENT_DESKTOP (lower-cased)
    desktops: list[str] = field(default_factory=list)
    wayland_display: str = ""         # $WAYLAND_DISPLAY
    hyprland_instance: str = ""       # $HYPRLAND_INSTANCE_SIGNATURE
    sway_sock: str = ""               # $SWAYSOCK
    display: str = ""                 # $DISPLAY
    xdg_session_desktop: str = ""     # $XDG_SESSION_DESKTOP (lower-cased)

    def has_desktop(self, *names: str) -> bool:
        haystack = " ".join(self.desktops + [self.desktop, self.xdg_session_desktop]).lower()
        for n in names:
            n_low = n.lower()
            if n_low in haystack:
                return True
            if n_low == "hyprland" and self.hyprland_instance:
                return True
            if n_low == "sway" and self.sway_sock:
                return True
        return False

    def summary(self) -> str:
        parts = [
            f"session_type={self.session_type or 'unknown'}",
            f"desktop={self.desktop or 'unknown'}",
        ]
        if self.wayland_display:
            parts.append(f"wayland_display={self.wayland_display}")
        if self.hyprland_instance:
            parts.append("hyprland=yes")
        if self.sway_sock:
            parts.append("sway=yes")
        if self.display:
            parts.append(f"display={self.display}")
        return ", ".join(parts)


def detect() -> Environment:
    """Read the process environment and return a normalized :class:`Environment`."""
    env = os.environ
    desktop = (env.get("XDG_CURRENT_DESKTOP") or "").strip()
    xdg_session = (env.get("XDG_SESSION_DESKTOP") or "").strip()
    session_type = (env.get("XDG_SESSION_TYPE") or "").strip().lower()
    wayland_display = env.get("WAYLAND_DISPLAY", "").strip()
    hyprland_instance = env.get("HYPRLAND_INSTANCE_SIGNATURE", "").strip()
    sway_sock = env.get("SWAYSOCK", "").strip()
    display = env.get("DISPLAY", "").strip()

    # Fall back if XDG_SESSION_TYPE is unset
    if not session_type:
        if wayland_display or hyprland_instance or sway_sock:
            session_type = "wayland"
        elif display:
            session_type = "x11"

    return Environment(
        session_type=session_type,
        desktop=desktop.lower(),
        desktops=[d.strip().lower() for d in desktop.split(":") if d.strip()],
        wayland_display=wayland_display,
        hyprland_instance=hyprland_instance,
        sway_sock=sway_sock,
        display=display,
        xdg_session_desktop=xdg_session.lower(),
    )
