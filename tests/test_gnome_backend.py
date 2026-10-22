"""Tests for the GNOME Wayland (Mutter D-Bus) backend with a mocked D-Bus."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backends.gnome import GnomeWaylandBackend
from interfaces import DisplayMode, ExtendPosition, Selection

MONITORS = [
    (
        ("eDP-1", "AUO", "Panel", "0"),
        [
            ("1920x1080@60.0", 1920, 1080, 60.0, 1.0, [1.0],
             {"is-current": True, "is-preferred": True}),
            ("1920x1080@59.9", 1920, 1080, 59.9, 1.0, [1.0], {}),
        ],
        {"is-builtin": True, "display-name": "Laptop"},
    ),
    (
        ("DP-1", "Dell", "U2415", "1"),
        [
            ("1920x1080@60.0", 1920, 1080, 60.0, 1.0, [1.0],
             {"is-current": True, "is-preferred": True}),
            ("1280x720@60.0", 1280, 720, 60.0, 1.0, [1.0], {}),
        ],
        {"display-name": "Dell U2415"},
    ),
]

LOGICAL = [
    (0, 0, 1.0, 0, True, [("eDP-1", "AUO", "Panel", "0")], {}),
    (1920, 0, 1.0, 0, False, [("DP-1", "Dell", "U2415", "1")], {}),
]


def backend():
    calls = {"apply": []}

    def fake(method, *args):
        if method == "GetCurrentState":
            return (0, MONITORS, LOGICAL, {})
        if method == "ApplyMonitorsConfig":
            calls["apply"].append(args)
            return None
        raise AssertionError(f"unexpected method {method}")

    b = GnomeWaylandBackend(env=None, dbus=fake)
    b.calls = calls
    return b


class TestGnomeParse(unittest.TestCase):
    def test_list_outputs(self):
        outs = backend().list_outputs()
        self.assertEqual([o.name for o in outs], ["eDP-1", "DP-1"])
        edp = outs[0]
        self.assertTrue(edp.builtin)
        self.assertTrue(edp.primary)
        self.assertEqual((edp.x, edp.y), (0, 0))
        self.assertEqual((edp.width, edp.height), (1920, 1080))

    def test_get_current_mode(self):
        self.assertEqual(backend().get_current_mode(), DisplayMode.EXTEND)

    def test_available(self):
        self.assertTrue(backend().available())


class TestGnomeApply(unittest.TestCase):
    def _last_apply(self, b):
        _type_str, payload = b.calls["apply"][0]
        serial, method, value, props = payload
        return serial, method, value, props

    def test_internal(self):
        b = backend()
        res = b.apply(Selection(DisplayMode.INTERNAL))
        self.assertTrue(res.ok)
        _serial, method, value, _props = self._last_apply(b)
        self.assertEqual(method, 2)
        self.assertEqual(len(value), 1)
        x, y, scale, transform, primary, monitors = value[0]
        self.assertTrue(primary)
        self.assertEqual(monitors[0][0], "eDP-1")

    def test_external(self):
        b = backend()
        b.apply(Selection(DisplayMode.EXTERNAL))
        _s, _m, value, _p = self._last_apply(b)
        self.assertEqual(len(value), 1)
        self.assertEqual(value[0][5][0][0], "DP-1")

    def test_extend_right(self):
        b = backend()
        b.apply(Selection(DisplayMode.EXTEND, position=ExtendPosition.RIGHT))
        _s, _m, value, _p = self._last_apply(b)
        self.assertEqual(len(value), 2)
        second = value[1]
        self.assertEqual((second[0], second[1]), (1920, 0))
        self.assertEqual(second[5][0][0], "DP-1")

    def test_duplicate(self):
        b = backend()
        b.apply(Selection(DisplayMode.DUPLICATE))
        _s, _m, value, _p = self._last_apply(b)
        self.assertEqual(len(value), 1)
        _x, _y, _scale, _t, primary, monitors = value[0]
        self.assertEqual(sorted(m[0] for m in monitors), ["DP-1", "eDP-1"])

    def test_apply_positional_arguments(self):
        b = backend()
        res = b.apply(DisplayMode.EXTEND, "DP-1", ExtendPosition.ABOVE)
        self.assertTrue(res.ok)
        _s, _m, value, _p = self._last_apply(b)
        self.assertEqual(len(value), 2)
        # Check that second monitor is above (y < 0)
        self.assertEqual(value[1][1], -1080)

    def test_single_monitor_error(self):
        def fake(method, *args):
            if method == "GetCurrentState":
                return (0, [MONITORS[0]], [LOGICAL[0]], {})
            return None

        b = GnomeWaylandBackend(env=None, dbus=fake)
        res = b.apply(DisplayMode.EXTEND)
        self.assertFalse(res.ok)
        self.assertEqual(res.error, "no second display detected")


class TestGnomeRestore(unittest.TestCase):
    def test_restore_reapplies_snapshot(self):
        b = backend()
        snap = b.snapshot()
        res = b.restore(snap)
        self.assertTrue(res.ok)
        self.assertGreaterEqual(len(b.calls["apply"]), 1)


class TestGnomeDisabledMonitor(unittest.TestCase):
    """A connected-but-disabled second screen must still be discoverable."""

    def _backend(self):
        logical = [(0, 0, 1.0, 0, True, [("eDP-1", "AUO", "Panel", "0")], {})]
        calls = {"apply": []}

        def fake(method, *args):
            if method == "GetCurrentState":
                return (0, MONITORS, logical, {})
            if method == "ApplyMonitorsConfig":
                calls["apply"].append(args)
                return None
            raise AssertionError(method)

        b = GnomeWaylandBackend(env=None, dbus=fake)
        b.calls = calls
        return b

    def test_disabled_monitor_is_listed(self):
        outs = self._backend().list_outputs()
        by_name = {o.name: o for o in outs}
        self.assertEqual(set(by_name), {"eDP-1", "DP-1"})
        self.assertTrue(by_name["eDP-1"].enabled)
        self.assertFalse(by_name["DP-1"].enabled)
        self.assertTrue(by_name["DP-1"].connected)
        self.assertTrue(by_name["DP-1"].modes)  # still exposes modes for duplicate math

    def test_external_enables_disabled_monitor(self):
        b = self._backend()
        res = b.apply(Selection(DisplayMode.EXTERNAL))
        self.assertTrue(res.ok)
        _type_str, payload = b.calls["apply"][0]
        _serial, _method, value, _props = payload
        self.assertEqual(len(value), 1)
        self.assertEqual(value[0][5][0][0], "DP-1")


if __name__ == "__main__":
    unittest.main()
