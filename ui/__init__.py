"""UI dispatch (GTK preferred, Qt fallback)."""

from ui.base import get_ui, gtk_version, has_layer_shell, qt_available

__all__ = ["get_ui", "gtk_version", "qt_available", "has_layer_shell"]
