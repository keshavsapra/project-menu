"""Backend registry: ordered list + runtime selection."""

from __future__ import annotations

from interfaces import DisplayBackend, UnsupportedBackendError

from backends.cosmic import CosmicBackend
from backends.gnome import GnomeWaylandBackend
from backends.hyprland import HyprlandBackend
from backends.kde import KdeBackend
from backends.sway import SwayBackend
from backends.wlroots import WlrootsBackend
from backends.x11 import X11Backend

# Priority order: more specific / preferred backends first.
BACKENDS: list[type[DisplayBackend]] = [
    X11Backend,           # X11 (any desktop/WM)
    GnomeWaylandBackend,  # GNOME Wayland (Mutter D-Bus)
    KdeBackend,           # KDE Plasma Wayland
    SwayBackend,          # Sway
    HyprlandBackend,      # Hyprland
    WlrootsBackend,       # generic wlroots (river/labwc/wayfire)
    CosmicBackend,        # COSMIC
]

ALIASES = {
    "x11": "x11",
    "gnome": "gnome-wayland",
    "gnome-wayland": "gnome-wayland",
    "mutter": "gnome-wayland",
    "kde": "kde",
    "plasma": "kde",
    "sway": "sway",
    "hyprland": "hyprland",
    "wlroots": "wlr-randr",
    "wlr-randr": "wlr-randr",
    "river": "wlr-randr",
    "labwc": "wlr-randr",
    "wayfire": "wlr-randr",
    "cosmic": "cosmic",
}

BY_NAME: dict[str, type[DisplayBackend]] = {b.name: b for b in BACKENDS}


def select(env, override: str | None = None) -> DisplayBackend:
    """Choose and instantiate a backend for *env*, honouring *override*."""
    if override:
        name = ALIASES.get(override.strip().lower(), override.strip().lower())
        cls = BY_NAME.get(name)
        if cls is None:
            raise UnsupportedBackendError(
                f"Unknown backend '{override}'. Available: {', '.join(sorted(BY_NAME))}"
            )
        inst = cls(env)
        if hasattr(inst, "available") and not inst.available():
            raise UnsupportedBackendError(
                f"Backend '{override}' selected, but its required tool/API is not available."
            )
        return inst

    for cls in sorted(BACKENDS, key=lambda c: c.priority):
        if not cls.can_handle(env):
            continue
        inst = cls(env)
        if hasattr(inst, "available") and not inst.available():
            continue
        return inst

    raise UnsupportedBackendError(fallback_message(env))


def fallback_message(env) -> str:
    """Explain why nothing matched and how to add a backend."""
    parts = [
        f"No supported display backend for this environment ({env.summary()}).",
        "",
        "To add a backend:",
        "  1. Create a module in backends/ that subclasses DisplayBackend",
        "     (implement list_outputs, get_current_mode, plan, apply).",
        "  2. Register it in backends/registry.py (add to BACKENDS).",
        "  3. Implement can_handle() to match this environment, or select it",
        "     manually with `project-menu --backend <name>`.",
        "",
        "See README.md, section 'How to add a new backend'.",
    ]
    return "\n".join(parts)
