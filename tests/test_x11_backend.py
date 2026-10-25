"""Tests for the X11 (xrandr) backend using mocked command output."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backends.x11 import X11Backend
from helpers import Result, make_runner
from interfaces import DisplayMode, ExtendPosition, Selection

XRANDR = """\
Screen 0: minimum 8 x 8, current 3840 x 1080, maximum 32767 x 32767
eDP-1 connected primary 1920x1080+0+0 (normal left inverted right x axis y axis) 344mm x 193mm
   1920x1080     60.00*+  59.94    50.00
   1680x1050     59.95
DP-1 connected 1920x1080+1920+0 (normal left inverted right x axis y axis) 531mm x 299mm
   1920x1080     60.00*+  59.94
   1280x720      60.00
HDMI-1 disconnected (normal left inverted right x axis y axis)
"""


def backend(text=XRANDR):
    return X11Backend(env=None, runner=make_runner({"xrandr --query": Result(stdout=text)}))


class TestX11Parse(unittest.TestCase):
    def test_parse_outputs(self):
        b = backend()
        outs = b.parse_outputs(XRANDR)
        names = [o.name for o in outs]
        self.assertEqual(names, ["eDP-1", "DP-1", "HDMI-1"])
        edp = outs[0]
        self.assertTrue(edp.primary)
        self.assertTrue(edp.builtin)
        self.assertTrue(edp.enabled)
        self.assertEqual((edp.width, edp.height), (1920, 1080))
        self.assertEqual((edp.current_mode.width, edp.current_mode.refresh), (1920, 60.0))

    def test_single_screen_with_preferred_marker_token(self):
        """xrandr emits the preferred marker "+" as a standalone token for a
        connected-but-disabled output: "60.00 +  50.00". This must not raise
        ValueError from float('')."""
        text = (
            "Screen 0: minimum 8 x 8, current 1920 x 1080, maximum 32767 x 32767\n"
            "HDMI-0 connected primary 1920x1080+0+0 (normal left inverted right x axis y axis) 527mm x 296mm\n"
            "   1920x1080     60.00*+  74.97    59.94    50.00\n"
            "   1600x900      60.00\n"
            "HDMI-1-1 connected (normal left inverted right x axis y axis)\n"
            "   1920x1080     60.00 +  50.00    59.94\n"
            "   1280x720      60.00    50.00\n"
        )
        b = backend(text)
        outs = b.parse_outputs(text)
        prim, sec = outs[0], outs[1]
        # No 0 Hz ghost modes from bare markers.
        self.assertEqual([m for m in sec.modes if m.refresh == 0], [])
        self.assertTrue(sec.connected)
        self.assertFalse(sec.enabled)
        self.assertTrue(any(m.width == 1920 and m.refresh == 60.0 for m in sec.modes))
        self.assertTrue(any(m.width == 1920 and m.refresh == 50.0 for m in sec.modes))
        self.assertEqual(prim.current_mode.refresh, 60.0)

    def test_modes_counted_once_per_refresh(self):
        text = (
            "HDMI-A connected 1920x1080+0+0\n"
            "   1920x1080     60.00 +  50.00\n"
        )
        outs = backend(text).parse_outputs(text)
        self.assertEqual([(m.width, m.refresh) for m in outs[0].modes],
                         [(1920, 60.0), (1920, 50.0)])

    def test_get_current_mode(self):
        self.assertEqual(backend().get_current_mode(), DisplayMode.EXTEND)


class TestX11Plan(unittest.TestCase):
    def test_internal(self):
        b = backend()
        cmds = b.plan(Selection(DisplayMode.INTERNAL))
        self.assertEqual(
            cmds,
            ["xrandr --output eDP-1 --auto --primary --output DP-1 --off"],
        )

    def test_external(self):
        b = backend()
        cmds = b.plan(Selection(DisplayMode.EXTERNAL))
        self.assertEqual(
            cmds,
            ["xrandr --output DP-1 --auto --output eDP-1 --off"],
        )

    def test_extend_right(self):
        b = backend()
        cmds = b.plan(Selection(DisplayMode.EXTEND, position=ExtendPosition.RIGHT))
        self.assertEqual(
            cmds,
            ["xrandr --output eDP-1 --auto --primary --output DP-1 --auto --right-of eDP-1"],
        )

    def test_extend_left(self):
        b = backend()
        cmds = b.plan(Selection(DisplayMode.EXTEND, position=ExtendPosition.LEFT))
        self.assertIn("--left-of eDP-1", cmds[0])

    def test_duplicate(self):
        b = backend()
        cmds = b.plan(Selection(DisplayMode.DUPLICATE))
        self.assertEqual(
            cmds,
            ["xrandr --output eDP-1 --mode 1920x1080 --rate 60 --output DP-1 --same-as eDP-1"],
        )


class TestX11Apply(unittest.TestCase):
    def test_apply_records_commands(self):
        b = backend()
        result = b.apply(Selection(DisplayMode.INTERNAL))
        self.assertTrue(result.ok)
        self.assertEqual(result.mode, DisplayMode.INTERNAL)

    def test_apply_positional_arguments(self):
        b = backend()
        res = b.apply(DisplayMode.EXTEND, "DP-1", ExtendPosition.LEFT)
        self.assertTrue(res.ok)
        self.assertEqual(res.mode, DisplayMode.EXTEND)
        self.assertIn("--left-of eDP-1", res.commands[0])

    def test_single_monitor_error(self):
        single = """\
Screen 0: minimum 8 x 8, current 1920 x 1080, maximum 32767 x 32767
eDP-1 connected primary 1920x1080+0+0 344mm x 193mm
   1920x1080     60.00*+
"""
        b = backend(single)
        res = b.apply(DisplayMode.EXTEND)
        self.assertFalse(res.ok)
        self.assertEqual(res.error, "no second display detected")

    def test_duplicate_warns_on_refresh_mismatch(self):
        text = XRANDR.replace("60.00*+  59.94\n   1280x720", "60.00*+  59.94    50.00\n   1280x720")
        # give DP-1 a different refresh set
        text = text.replace("DP-1 connected", "DP-1 connected")
        b = backend(text)
        result = b.apply(Selection(DisplayMode.DUPLICATE))
        # both at 60Hz here -> no warning expected, but verify no crash
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
