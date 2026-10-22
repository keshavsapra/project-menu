"""UI package: GTK popup with a Qt fallback."""

from __future__ import annotations

from interfaces import DisplayMode

ICON_NAMES = {
    DisplayMode.INTERNAL: "computer",
    DisplayMode.DUPLICATE: "video-display",
    DisplayMode.EXTEND: "video-x-generic",
    DisplayMode.EXTERNAL: "video-display",
}

__all__ = ["get_ui", "gtk_version", "ICON_NAMES"]


def gtk_version() -> int | None:
    """Return 3 or 4 if GTK is importable, else None."""
    for major in (3, 4):
        try:
            import gi  # noqa: WPS433

            gi.require_version("Gtk", f"{major}.0")
            from gi.repository import Gtk  # noqa: F401

            return major
        except Exception:
            continue
    return None


def qt_available() -> bool:
    try:
        import PyQt6  # noqa: F401
        return True
    except Exception:
        pass
    try:
        import PyQt5  # noqa: F401
        return True
    except Exception:
        pass
    try:
        import PySide6  # noqa: F401
        return True
    except Exception:
        pass
    try:
        import PySide2  # noqa: F401
        return True
    except Exception:
        pass
    return False


def get_ui():
    """Return a PopupUI subclass, preferring GTK then Qt."""
    if gtk_version() is not None:
        from ui.gtk_ui import GtkPopupUI
        return GtkPopupUI
    if qt_available():
        from ui.qt_ui import QtPopupUI
        return QtPopupUI
    return None


def has_layer_shell() -> bool:
    try:
        import gi  # noqa: WPS433
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell  # noqa: F401
        return True
    except Exception:
        return False
