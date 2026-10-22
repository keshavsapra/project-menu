"""Tests for the Sway backend."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backends.sway import SwayBackend
from helpers import Result, make_runner
from interfaces import DisplayMode, ExtendPosition, Selection

SWAY = json.dumps([
    {"name": "eDP-1", "make": "AUO", "model": "0x0000", "active": True, "primary": False,
     "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080},
     "current_mode": {"width": 1920, "height": 1080, "refresh": 60000},
     "modes": [{"width": 1920, "height": 1080, "refresh": 60000},
               {"width": 1920, "height": 1080, "refresh": 59940}],
     "scale": 1.0},
    {"name": "HDMI-A-1", "make": "Dell", "model": "U2415", "active": True, "primary": False,
     "rect": {"x": 1920, "y": 0, "width": 1920, "height": 1080},
     "current_mode": {"width": 1920, "height": 1080, "refresh": 60000},
     "modes": [{"width": 1920, "height": 1080, "refresh": 60000}],
     "scale": 1.0},
])


def backend():
    return SwayBackend(env=None, runner=make_runner({"swaymsg": Result(stdout=SWAY)}))


class TestSwayParse(unittest.TestCase):
    def test_parse_outputs(self):
        outs = backend().parse_outputs(SWAY)
        self.assertEqual([o.name for o in outs], ["eDP-1", "HDMI-A-1"])
        self.assertTrue(outs[0].builtin)
        self.assertEqual(outs[0].current_mode.refresh, 60.0)
        self.assertEqual((outs[1].x, outs[1].y), (1920, 0))

    def test_get_current_mode(self):
        self.assertEqual(backend().get_current_mode(), DisplayMode.EXTEND)


class TestSwayPlan(unittest.TestCase):
    def test_internal(self):
        cmds = backend().plan(Selection(DisplayMode.INTERNAL))
        self.assertEqual(
            cmds,
            ["swaymsg output eDP-1 enable output HDMI-A-1 disable"],
        )

    def test_external(self):
        cmds = backend().plan(Selection(DisplayMode.EXTERNAL))
        self.assertIn("output HDMI-A-1 enable", cmds[0])
        self.assertIn("output eDP-1 disable", cmds[0])

    def test_extend_right(self):
        cmds = backend().plan(Selection(DisplayMode.EXTEND, position=ExtendPosition.RIGHT))
        self.assertIn("output HDMI-A-1 position 1920 0", cmds[0])

    def test_duplicate(self):
        cmds = backend().plan(Selection(DisplayMode.DUPLICATE))
        self.assertIn("output eDP-1 mode 1920x1080@60", cmds[0])
        self.assertIn("output HDMI-A-1 position 0 0", cmds[0])

    def test_apply_positional_arguments(self):
        b = backend()
        res = b.apply(DisplayMode.EXTEND, "HDMI-A-1", ExtendPosition.RIGHT)
        self.assertTrue(res.ok)
        self.assertEqual(res.mode, DisplayMode.EXTEND)
        self.assertIn("output HDMI-A-1 position 1920 0", res.commands[0])

    def test_single_monitor_error(self):
        single = json.dumps([
            {"name": "eDP-1", "make": "AUO", "model": "0x0000", "active": True, "primary": False,
             "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080},
             "current_mode": {"width": 1920, "height": 1080, "refresh": 60000},
             "modes": [{"width": 1920, "height": 1080, "refresh": 60000}],
             "scale": 1.0},
        ])
        b = SwayBackend(env=None, runner=make_runner({"swaymsg": Result(stdout=single)}))
        res = b.apply(DisplayMode.EXTEND)
        self.assertFalse(res.ok)
        self.assertEqual(res.error, "no second display detected")


if __name__ == "__main__":
    unittest.main()
