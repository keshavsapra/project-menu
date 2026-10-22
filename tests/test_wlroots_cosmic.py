"""Tests for the generic wlroots (wlr-randr) and COSMIC backends."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backends.cosmic import CosmicBackend
from backends.wlroots import WlrootsBackend
from helpers import Result, make_runner
from interfaces import DisplayMode, ExtendPosition, Selection

WLR = """\
eDP-1 "AU Optronics 0x1234 (eDP-1)"
  Enabled: yes
  Position: 0,0
  Scale: 1.000000
  Mode: 1920x1080@60.000000Hz
  Modes:
    1920x1080@60.000000Hz
    1920x1080@59.940000Hz
HDMI-A-1 "Dell U2415 (HDMI-A-1)"
  Enabled: yes
  Position: 1920,0
  Scale: 1.000000
  Mode: 1920x1080@60.000000Hz
  Modes:
    1920x1080@60.000000Hz
"""

COSMIC = """\
eDP-1 (enabled)
Model: AUO
Physical Size: 344 x 193 mm
Position: 0,0
Scale: 100%
Modes:
  1920x1080 @ 60.000 Hz (current) (preferred)
  1920x1080 @ 59.940 Hz
DP-1 (enabled)
Model: Dell
Position: 1920,0
Scale: 100%
Modes:
  1920x1080 @ 60.000 Hz (current) (preferred)
"""


class TestWlroots(unittest.TestCase):
    def _b(self):
        return WlrootsBackend(env=None, runner=make_runner({"wlr-randr": Result(stdout=WLR)}))

    def test_parse(self):
        outs = self._b().parse_outputs(WLR)
        self.assertEqual([o.name for o in outs], ["eDP-1", "HDMI-A-1"])
        self.assertTrue(outs[0].builtin)
        self.assertEqual(outs[0].current_mode.refresh, 60.0)
        self.assertEqual((outs[1].x, outs[1].y), (1920, 0))

    def test_current_mode(self):
        self.assertEqual(self._b().get_current_mode(), DisplayMode.EXTEND)

    def test_internal_plan(self):
        cmds = self._b().plan(Selection(DisplayMode.INTERNAL))
        self.assertEqual(
            cmds,
            ["wlr-randr --output eDP-1 --on --output HDMI-A-1 --off"],
        )

    def test_extend_left(self):
        cmds = self._b().plan(Selection(DisplayMode.EXTEND, position=ExtendPosition.LEFT))
        self.assertIn("--output eDP-1 --on --pos 1920,0", cmds[0])
        self.assertIn("--output HDMI-A-1 --on --pos 0,0", cmds[0])

    def test_apply_positional_arguments(self):
        b = self._b()
        res = b.apply(DisplayMode.EXTEND, "HDMI-A-1", ExtendPosition.RIGHT)
        self.assertTrue(res.ok)
        self.assertEqual(res.mode, DisplayMode.EXTEND)
        self.assertIn("--pos 1920,0", res.commands[0])

    def test_single_monitor_error(self):
        single = """\
eDP-1 "AU Optronics"
  Enabled: yes
  Position: 0,0
  Mode: 1920x1080@60.0Hz
"""
        b = WlrootsBackend(env=None, runner=make_runner({"wlr-randr": Result(stdout=single)}))
        res = b.apply(DisplayMode.EXTEND)
        self.assertFalse(res.ok)
        self.assertEqual(res.error, "no second display detected")


class TestCosmic(unittest.TestCase):
    def _b(self):
        return CosmicBackend(env=None, runner=make_runner({"cosmic-randr": Result(stdout=COSMIC)}))

    def test_parse(self):
        outs = self._b().parse_outputs(COSMIC)
        self.assertEqual([o.name for o in outs], ["eDP-1", "DP-1"])
        self.assertTrue(outs[0].builtin)
        self.assertEqual(outs[0].current_mode.mode_id, "1920x1080@60.000")

    def test_current_mode(self):
        self.assertEqual(self._b().get_current_mode(), DisplayMode.EXTEND)

    def test_internal_plan(self):
        cmds = self._b().plan(Selection(DisplayMode.INTERNAL))
        self.assertIn("cosmic-randr enable eDP-1", cmds)
        self.assertIn("cosmic-randr disable DP-1", cmds)

    def test_duplicate_uses_mirror(self):
        cmds = self._b().plan(Selection(DisplayMode.DUPLICATE))
        self.assertTrue(any("cosmic-randr mirror" in c for c in cmds))

    def test_apply_positional_arguments(self):
        b = self._b()
        res = b.apply(DisplayMode.EXTEND, "DP-1", ExtendPosition.RIGHT)
        self.assertTrue(res.ok)
        self.assertEqual(res.mode, DisplayMode.EXTEND)
        self.assertTrue(any("cosmic-randr position DP-1 1920 0" in c for c in res.commands))

    def test_single_monitor_error(self):
        single = """\
eDP-1 (enabled)
Modes:
  1920x1080 @ 60.000 Hz (current) (preferred)
"""
        b = CosmicBackend(env=None, runner=make_runner({"cosmic-randr": Result(stdout=single)}))
        res = b.apply(DisplayMode.EXTEND)
        self.assertFalse(res.ok)
        self.assertEqual(res.error, "no second display detected")


if __name__ == "__main__":
    unittest.main()
