"""Tests for the KDE (kscreen-doctor) backend."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backends.kde import KdeBackend
from helpers import Result, make_runner
from interfaces import DisplayMode, ExtendPosition, Selection

KSCREEN = """\
Output: 1 eDP-1 enabled connected Panel Modes: 1:1920x1080@60*! 2:1680x1050@60 Geometry: 0,0 1920x1080
Output: 2 DP-1 enabled connected HDMI Modes: 3:1920x1080@60*! 4:1280x720@60 Geometry: 1920,0 1920x1080
"""


def backend():
    return KdeBackend(env=None, runner=make_runner({"kscreen-doctor": Result(stdout=KSCREEN)}))


class TestKdeParse(unittest.TestCase):
    def test_parse_outputs(self):
        outs = backend().parse_outputs(KSCREEN)
        self.assertEqual([o.name for o in outs], ["eDP-1", "DP-1"])
        edp = outs[0]
        self.assertTrue(edp.builtin)
        self.assertTrue(edp.enabled)
        self.assertEqual((edp.x, edp.y), (0, 0))
        self.assertEqual(edp.current_mode.mode_id, "1")
        self.assertEqual(outs[1].current_mode.mode_id, "3")

    def test_get_current_mode(self):
        self.assertEqual(backend().get_current_mode(), DisplayMode.EXTEND)


class TestKdePlan(unittest.TestCase):
    def test_internal(self):
        cmds = backend().plan(Selection(DisplayMode.INTERNAL))
        self.assertEqual(
            cmds,
            ["kscreen-doctor output.eDP-1.enable output.eDP-1.primary "
             "output.eDP-1.mode.1 output.DP-1.disable"],
        )

    def test_external(self):
        cmds = backend().plan(Selection(DisplayMode.EXTERNAL))
        self.assertIn("output.DP-1.enable", cmds[0])
        self.assertIn("output.eDP-1.disable", cmds[0])

    def test_extend_right(self):
        cmds = backend().plan(Selection(DisplayMode.EXTEND, position=ExtendPosition.RIGHT))
        self.assertIn("output.eDP-1.position.0,0", cmds[0])
        self.assertIn("output.DP-1.position.1920,0", cmds[0])

    def test_extend_above(self):
        cmds = backend().plan(Selection(DisplayMode.EXTEND, position=ExtendPosition.ABOVE))
        self.assertIn("output.eDP-1.position.0,1080", cmds[0])
        self.assertIn("output.DP-1.position.0,0", cmds[0])

    def test_duplicate(self):
        cmds = backend().plan(Selection(DisplayMode.DUPLICATE))
        self.assertIn("output.eDP-1.mode.1", cmds[0])
        self.assertIn("output.DP-1.mode.3", cmds[0])
        self.assertIn("output.DP-1.position.0,0", cmds[0])

    def test_apply_positional_arguments(self):
        b = backend()
        res = b.apply(DisplayMode.EXTEND, "DP-1", ExtendPosition.RIGHT)
        self.assertTrue(res.ok)
        self.assertEqual(res.mode, DisplayMode.EXTEND)
        self.assertIn("output.DP-1.position.1920,0", res.commands[0])

    def test_single_monitor_error(self):
        single = "Output: 1 eDP-1 enabled connected Panel Modes: 1:1920x1080@60*! Geometry: 0,0 1920x1080\n"
        b = KdeBackend(env=None, runner=make_runner({"kscreen-doctor": Result(stdout=single)}))
        res = b.apply(DisplayMode.EXTEND)
        self.assertFalse(res.ok)
        self.assertEqual(res.error, "no second display detected")


if __name__ == "__main__":
    unittest.main()
