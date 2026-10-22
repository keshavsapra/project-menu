"""Tests for the Hyprland backend."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backends.hyprland import HyprlandBackend
from helpers import Result, make_runner
from interfaces import DisplayMode, ExtendPosition, Selection

HYPR = json.dumps([
    {"id": 0, "name": "eDP-1", "description": "AUO 0x0000", "width": 1920, "height": 1080,
     "refreshRate": 60.0, "x": 0, "y": 0, "scale": 1.0,
     "availableModes": ["1920x1080@60.00Hz", "1920x1080@59.94Hz"]},
    {"id": 1, "name": "DP-1", "description": "Dell U2415", "width": 1920, "height": 1080,
     "refreshRate": 60.0, "x": 1920, "y": 0, "scale": 1.0,
     "availableModes": ["1920x1080@60.00Hz"]},
])


def backend():
    return HyprlandBackend(env=None, runner=make_runner({"hyprctl": Result(stdout=HYPR)}))


class TestHyprlandParse(unittest.TestCase):
    def test_parse_outputs(self):
        outs = backend().parse_outputs(HYPR)
        self.assertEqual([o.name for o in outs], ["eDP-1", "DP-1"])
        self.assertTrue(outs[0].builtin)
        self.assertEqual(len(outs[0].modes), 2)

    def test_get_current_mode(self):
        self.assertEqual(backend().get_current_mode(), DisplayMode.EXTEND)


class TestHyprlandPlan(unittest.TestCase):
    def test_internal(self):
        cmds = backend().plan(Selection(DisplayMode.INTERNAL))
        self.assertEqual(
            cmds,
            ["hyprctl keyword monitor eDP-1,preferred,auto,1",
             "hyprctl keyword monitor DP-1,disable"],
        )

    def test_extend_right(self):
        cmds = backend().plan(Selection(DisplayMode.EXTEND, position=ExtendPosition.RIGHT))
        self.assertIn("hyprctl keyword monitor DP-1,preferred,1920x0,1", cmds)

    def test_duplicate_uses_mirror(self):
        cmds = backend().plan(Selection(DisplayMode.DUPLICATE))
        self.assertTrue(any("mirror,eDP-1" in c for c in cmds))


class TestHyprlandDisabledMonitor(unittest.TestCase):
    """`hyprctl -j monitors all` includes disabled outputs, which must be listed."""

    DISABLED = json.dumps([
        {"id": 0, "name": "eDP-1", "description": "AUO 0x0000", "width": 1920, "height": 1080,
         "refreshRate": 60.0, "x": 0, "y": 0, "scale": 1.0,
         "availableModes": ["1920x1080@60.00Hz"]},
        {"id": 1, "name": "DP-1", "description": "Dell U2415", "disabled": True},
    ])

    def test_disabled_monitor_is_listed(self):
        b = HyprlandBackend(env=None, runner=make_runner({"hyprctl": Result(stdout=self.DISABLED)}))
        outs = b.parse_outputs(self.DISABLED)
        by_name = {o.name: o for o in outs}
        self.assertEqual(set(by_name), {"eDP-1", "DP-1"})
        self.assertTrue(by_name["eDP-1"].enabled)
        self.assertFalse(by_name["DP-1"].enabled)
        self.assertTrue(by_name["DP-1"].connected)

    def test_external_plan_enables_disabled_monitor(self):
        b = HyprlandBackend(env=None, runner=make_runner({"hyprctl": Result(stdout=self.DISABLED)}))
        cmds = b.plan(Selection(DisplayMode.EXTERNAL))
        self.assertTrue(any("monitor DP-1,preferred,auto,1" in c for c in cmds))
        self.assertTrue(any("monitor eDP-1,disable" in c for c in cmds))

    def test_apply_positional_arguments(self):
        b = backend()
        res = b.apply(DisplayMode.EXTEND, "DP-1", ExtendPosition.RIGHT)
        self.assertTrue(res.ok)
        self.assertEqual(res.mode, DisplayMode.EXTEND)
        self.assertTrue(any("monitor DP-1,preferred,1920x0,1" in c for c in res.commands))

    def test_single_monitor_error(self):
        single = json.dumps([
            {"id": 0, "name": "eDP-1", "description": "AUO", "width": 1920, "height": 1080,
             "refreshRate": 60.0, "x": 0, "y": 0, "scale": 1.0,
             "availableModes": ["1920x1080@60.00Hz"]},
        ])
        b = HyprlandBackend(env=None, runner=make_runner({"hyprctl": Result(stdout=single)}))
        res = b.apply(DisplayMode.EXTEND)
        self.assertFalse(res.ok)
        self.assertEqual(res.error, "no second display detected")


if __name__ == "__main__":
    unittest.main()
