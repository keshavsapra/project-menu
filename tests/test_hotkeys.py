"""Unit tests for hotkey registrars across desktop environments."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detect import Environment
from hotkeys import registry as hotkey_registry
from hotkeys.gnome import CinnamonHotkey, GnomeHotkey, MateHotkey
from hotkeys.kde import KdeHotkey
from hotkeys.wm import HyprlandHotkey, I3Hotkey, SwayHotkey
from hotkeys.x11_grab import X11GrabHotkey
from hotkeys.xfce import XfceHotkey


class TestHotkeyRegistry(unittest.TestCase):
    def test_select_gnome(self):
        env = Environment(session_type="wayland", desktop="gnome", desktops=["gnome"])
        r = hotkey_registry.select(env)
        self.assertIsInstance(r, GnomeHotkey)

    def test_select_kde(self):
        env = Environment(session_type="wayland", desktop="kde", desktops=["kde"])
        r = hotkey_registry.select(env)
        self.assertIsInstance(r, KdeHotkey)

    def test_select_sway(self):
        env = Environment(session_type="wayland", desktop="sway", sway_sock="/tmp/sway.sock")
        r = hotkey_registry.select(env)
        self.assertIsInstance(r, SwayHotkey)

    def test_select_hyprland(self):
        env = Environment(session_type="wayland", desktop="hyprland", hyprland_instance="abc")
        r = hotkey_registry.select(env)
        self.assertIsInstance(r, HyprlandHotkey)

    def test_select_xfce(self):
        env = Environment(session_type="x11", desktop="xfce", desktops=["xfce"])
        r = hotkey_registry.select(env)
        self.assertIsInstance(r, XfceHotkey)

    def test_select_x11_fallback(self):
        env = Environment(session_type="x11", desktop="openbox", display=":0")
        r = hotkey_registry.select(env)
        self.assertIsInstance(r, X11GrabHotkey)


class TestGnomeHotkey(unittest.TestCase):
    def setUp(self):
        self.hotkey = GnomeHotkey()
        self.commands = []

        def fake_run(argv, check=False):
            self.commands.append(argv)
            mock_proc = MagicMock()
            if "custom-keybindings" in argv and "get" in argv:
                mock_proc.stdout = "['/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/']"
            elif "name" in argv and "get" in argv:
                mock_proc.stdout = "'Project Menu'"
            else:
                mock_proc.stdout = ""
            mock_proc.returncode = 0
            return mock_proc

        self.hotkey._run = fake_run

    @patch("shutil.which", return_value="/usr/bin/gsettings")
    def test_register(self, _which):
        actions = self.hotkey.register("project-menu")
        self.assertTrue(any("custom-keybindings" in a for a in actions))
        self.assertTrue(any("switch-monitor" in a for a in actions))

    @patch("shutil.which", return_value="/usr/bin/gsettings")
    def test_unregister(self, _which):
        actions = self.hotkey.unregister()
        self.assertTrue(any("restored" in a for a in actions))


class TestWmHotkey(unittest.TestCase):
    def test_sway_snippet_only_without_append(self):
        hk = SwayHotkey(append=False)
        actions = hk.register("project-menu")
        self.assertTrue(any("bindsym $mod+p exec project-menu" in a for a in actions))

    def test_sway_append(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Path(tmpdir) / "config"
            hk = SwayHotkey(append=True)
            hk.config_path = cfg
            actions = hk.register("project-menu")
            self.assertTrue(cfg.exists())
            content = cfg.read_text()
            self.assertIn("bindsym $mod+p exec project-menu", content)
            self.assertTrue(any("appended" in a for a in actions))

            # Test unregister removes it
            un_actions = hk.unregister()
            self.assertTrue(any("removed" in a for a in un_actions))
            self.assertNotIn("bindsym $mod+p", cfg.read_text())

    def test_hyprland_append(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Path(tmpdir) / "hyprland.conf"
            hk = HyprlandHotkey(append=True)
            hk.config_path = cfg
            actions = hk.register("project-menu")
            self.assertTrue(cfg.exists())
            self.assertIn("bind = SUPER, P, exec, project-menu", cfg.read_text())


class TestKdeHotkey(unittest.TestCase):
    def test_instructions(self):
        hk = KdeHotkey()
        inst = hk.instructions("project-menu")
        self.assertIn("project-menu.desktop", inst)
        self.assertIn("Meta+P", inst)


class TestCinnamonHotkey(unittest.TestCase):
    """Cinnamon stores custom shortcuts in org.cinnamon.desktop.keybindings,
    NOT in settings-daemon media-keys like GNOME/MATE."""

    def setUp(self):
        self.hotkey = CinnamonHotkey()
        self.commands = []

        def fake_run(argv, check=False):
            self.commands.append(argv)
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = ""
            if argv[1] == "get" and argv[-1] == "custom-list":
                mock_proc.stdout = "@as ['custom0']"
            elif argv[1] == "get" and argv[-1] == "name":
                mock_proc.stdout = "'Project Menu'" if "custom0" in argv[2] else "''"
            return mock_proc

        self.hotkey._run = fake_run

    @patch("shutil.which", return_value="/usr/bin/gsettings")
    def test_register_uses_cinnamon_list_schema(self, _which):
        actions = self.hotkey.register("project-menu")
        flat = str(self.commands)
        # Must not touch the GNOME-style media-keys schema at all.
        self.assertNotIn("org.cinnamon.settings-daemon.plugins.media-keys", flat)
        self.assertNotIn("org.gnome", flat)
        # Must use custom-list and the relocatable custom-keybinding schema.
        self.assertIn("org.cinnamon.desktop.keybindings", flat)
        self.assertIn("custom-keybinding", flat)
        # name/command are plain strings, binding is an array of strings.
        self.assertTrue(any("name" in c and "Project Menu" in c and "['Project Menu']" not in c for c in self.commands))
        self.assertTrue(any("command" in c and "project-menu" in c and "['project-menu']" not in c
                            for c in self.commands))
        self.assertTrue(any("binding" in c and "['<Super>p']" in c for c in self.commands))
        self.assertTrue(actions)

    @patch("shutil.which", return_value="/usr/bin/gsettings")
    def test_register_takes_free_slot(self, _which):
        self.hotkey.register("project-menu")
        # custom0 is in use -> new slot must be custom1.
        flat = str(self.commands)
        self.assertIn("/custom1/", flat)
        self.assertNotIn("/custom0/", flat)

    @patch("shutil.which", return_value="/usr/bin/gsettings")
    def test_unregister_removes_our_slot(self, _which):
        actions = self.hotkey.unregister()
        # Our slot (custom0, named 'Project Menu') must be reset and dropped from the list.
        self.assertTrue(any(c[1] == "reset" and "/custom0/" in c[2] for c in self.commands))
        list_writes = [c for c in self.commands if c[1] == "set" and c[-2] == "custom-list"]
        self.assertEqual(list_writes, [["gsettings", "set", "org.cinnamon.desktop.keybindings", "custom-list", "[]"]])
        self.assertTrue(any("restored" in a for a in actions))


if __name__ == "__main__":
    unittest.main()
