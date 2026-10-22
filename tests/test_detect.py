"""Tests for environment detection."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detect import Environment, detect


class TestEnvironment(unittest.TestCase):
    def test_has_desktop_case_insensitive(self):
        env = Environment(desktop="ubuntu:GNOME", desktops=["ubuntu", "gnome"])
        self.assertTrue(env.has_desktop("gnome"))
        self.assertTrue(env.has_desktop("GNOME"))

    def test_summary(self):
        env = Environment(session_type="wayland", desktop="sway", sway_sock="/x")
        self.assertIn("session_type=wayland", env.summary())
        self.assertIn("sway=yes", env.summary())


class TestDetect(unittest.TestCase):
    def test_detect_reads_vars(self):
        old = dict(os.environ)
        try:
            os.environ["XDG_SESSION_TYPE"] = "wayland"
            os.environ["XDG_CURRENT_DESKTOP"] = "KDE"
            os.environ["WAYLAND_DISPLAY"] = "wayland-1"
            os.environ.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
            os.environ.pop("SWAYSOCK", None)
            env = detect()
            self.assertEqual(env.session_type, "wayland")
            self.assertEqual(env.desktop, "kde")
            self.assertEqual(env.wayland_display, "wayland-1")
        finally:
            os.environ.clear()
            os.environ.update(old)


if __name__ == "__main__":
    unittest.main()
