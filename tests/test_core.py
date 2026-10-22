"""Tests for shared mode-inference helpers in core."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import best_duplicate_mode, build_options, infer_mode, primary_output
from interfaces import DisplayMode, ExtendPosition, ModeInfo, Output


def out(name, **kw):
    o = Output(name=name, connected=True, enabled=True, builtin=name.startswith("eDP"))
    o.__dict__.update(kw)
    return o


class TestInferMode(unittest.TestCase):
    def test_internal_single_builtin(self):
        o = out("eDP-1", x=0, y=0, width=1920, height=1080)
        self.assertEqual(infer_mode([o]), DisplayMode.INTERNAL)

    def test_external_single_non_builtin(self):
        o = out("HDMI-1", x=0, y=0, width=1920, height=1080)
        self.assertEqual(infer_mode([o]), DisplayMode.EXTERNAL)

    def test_duplicate_same_position(self):
        a = out("eDP-1", x=0, y=0, width=1920, height=1080)
        b = out("HDMI-1", x=0, y=0, width=1920, height=1080)
        self.assertEqual(infer_mode([a, b]), DisplayMode.DUPLICATE)

    def test_extend_different_position(self):
        a = out("eDP-1", x=0, y=0, width=1920, height=1080)
        b = out("HDMI-1", x=1920, y=0, width=1920, height=1080)
        self.assertEqual(infer_mode([a, b]), DisplayMode.EXTEND)

    def test_none_when_no_active(self):
        a = out("eDP-1", enabled=False)
        self.assertIsNone(infer_mode([a]))


class TestDuplicateMode(unittest.TestCase):
    def _mk(self, modes):
        o = Output(name="x", connected=True, enabled=True)
        o.modes = [ModeInfo(w, h, r) for w, h, r in modes]
        return o

    def test_highest_common_resolution(self):
        a = self._mk([(1920, 1080, 60.0), (1280, 720, 60.0)])
        b = self._mk([(1920, 1080, 60.0), (1024, 768, 60.0)])
        ma, mb, warn = best_duplicate_mode(a, b)
        self.assertEqual((ma.width, ma.height), (1920, 1080))
        self.assertEqual((mb.width, mb.height), (1920, 1080))
        self.assertEqual(warn, "")

    def test_refresh_mismatch_warns(self):
        a = self._mk([(1920, 1080, 60.0)])
        b = self._mk([(1920, 1080, 59.94)])
        _ma, _mb, warn = best_duplicate_mode(a, b)
        self.assertIn("refresh", warn)

    def test_no_common(self):
        a = self._mk([(1920, 1080, 60.0)])
        b = self._mk([(1280, 720, 60.0)])
        ma, mb, warn = best_duplicate_mode(a, b)
        self.assertIsNone(ma)
        self.assertIsNone(mb)
        self.assertIn("no common", warn)


class TestBuildOptions(unittest.TestCase):
    def test_single_monitor(self):
        options, note = build_options([out("eDP-1")])
        enabled = {m: e for m, e in options}
        self.assertTrue(enabled[DisplayMode.INTERNAL])
        self.assertFalse(enabled[DisplayMode.DUPLICATE])
        self.assertFalse(enabled[DisplayMode.EXTEND])
        self.assertFalse(enabled[DisplayMode.EXTERNAL])
        self.assertIn("No second display", note)

    def test_two_monitors(self):
        options, note = build_options([out("eDP-1"), out("HDMI-1")])
        enabled = {m: e for m, e in options}
        self.assertTrue(all(enabled.values()))


class TestPrimaryOutput(unittest.TestCase):
    def test_primary_priority(self):
        a = out("HDMI-1", primary=True)
        b = out("eDP-1")
        self.assertEqual(primary_output([b, a]).name, "HDMI-1")

    def test_builtin_fallback(self):
        a = out("HDMI-1")
        b = out("eDP-1")
        self.assertEqual(primary_output([a, b]).name, "eDP-1")


if __name__ == "__main__":
    unittest.main()
