"""Unit tests for backend registry selection and fallback logic."""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backends import registry as backend_registry
from backends.gnome import GnomeWaylandBackend
from backends.hyprland import HyprlandBackend
from backends.kde import KdeBackend
from backends.sway import SwayBackend
from backends.x11 import X11Backend
from detect import Environment
from interfaces import UnsupportedBackendError


class TestBackendRegistry(unittest.TestCase):
    @patch("shutil.which", return_value="/usr/bin/xrandr")
    def test_select_x11(self, _which):
        env = Environment(session_type="x11", display=":0")
        backend = backend_registry.select(env)
        self.assertIsInstance(backend, X11Backend)

    @patch("backends.gnome.GnomeWaylandBackend.available", return_value=True)
    def test_select_gnome_wayland(self, _avail):
        env = Environment(session_type="wayland", desktop="ubuntu:gnome", desktops=["ubuntu", "gnome"])
        backend = backend_registry.select(env)
        self.assertIsInstance(backend, GnomeWaylandBackend)

    @patch("shutil.which", return_value="/usr/bin/kscreen-doctor")
    def test_select_kde_wayland(self, _which):
        env = Environment(session_type="wayland", desktop="kde", desktops=["kde"])
        backend = backend_registry.select(env)
        self.assertIsInstance(backend, KdeBackend)

    @patch("shutil.which", return_value="/usr/bin/swaymsg")
    def test_select_sway(self, _which):
        env = Environment(session_type="wayland", desktop="sway", sway_sock="/tmp/sway.sock")
        backend = backend_registry.select(env)
        self.assertIsInstance(backend, SwayBackend)

    @patch("shutil.which", return_value="/usr/bin/hyprctl")
    def test_select_hyprland(self, _which):
        env = Environment(session_type="wayland", desktop="hyprland", hyprland_instance="sig123")
        backend = backend_registry.select(env)
        self.assertIsInstance(backend, HyprlandBackend)

    @patch("shutil.which", return_value="/usr/bin/swaymsg")
    def test_override_backend(self, _which):
        env = Environment(session_type="x11", display=":0")
        backend = backend_registry.select(env, override="sway")
        self.assertIsInstance(backend, SwayBackend)

    def test_unknown_override(self):
        env = Environment(session_type="x11", display=":0")
        with self.assertRaises(UnsupportedBackendError):
            backend_registry.select(env, override="nonexistent-backend")

    def test_unsupported_environment_fallback(self):
        env = Environment(session_type="unknown-wm", desktop="exotic")
        with self.assertRaises(UnsupportedBackendError) as ctx:
            backend_registry.select(env)
        msg = str(ctx.exception)
        self.assertIn("No supported display backend", msg)
        self.assertIn("How to add a new backend", msg)


if __name__ == "__main__":
    unittest.main()
