"""Unit tests for CLI parsing and dispatch."""

import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cli
from interfaces import ApplyResult, DisplayMode, ExtendPosition, ModeInfo, Output


class TestCliParser(unittest.TestCase):
    def setUp(self):
        self.parser = cli.build_parser()

    def test_flags(self):
        args = self.parser.parse_args(["--list", "--dry-run", "--debug"])
        self.assertTrue(args.list)
        self.assertTrue(args.dry_run)
        self.assertTrue(args.debug)

    def test_mode_and_target_output(self):
        args = self.parser.parse_args(["--mode", "extend", "--target-output", "DP-1", "--position", "above"])
        self.assertEqual(args.mode, "extend")
        self.assertEqual(args.output, "DP-1")
        self.assertEqual(args.position, "above")

    def test_output_alias(self):
        args = self.parser.parse_args(["--mode", "clone", "-o", "HDMI-1"])
        self.assertEqual(args.mode, "clone")
        self.assertEqual(args.output, "HDMI-1")


class TestCliRun(unittest.TestCase):
    def setUp(self):
        self.fake_output = Output(
            name="eDP-1", connected=True, enabled=True, builtin=True,
            width=1920, height=1080, x=0, y=0,
            current_mode=ModeInfo(1920, 1080, 60.0),
        )
        self.fake_backend = MagicMock()
        self.fake_backend.name = "mock"
        self.fake_backend.list_outputs.return_value = [self.fake_output]
        self.fake_backend.get_current_mode.return_value = DisplayMode.INTERNAL
        self.fake_backend.plan.return_value = ["mock-cmd --plan"]
        self.fake_backend.apply.return_value = ApplyResult(True, DisplayMode.INTERNAL, ["mock-cmd --apply"])

    @patch("backends.registry.select")
    def test_run_list(self, mock_select):
        mock_select.return_value = self.fake_backend
        parser = cli.build_parser()
        args = parser.parse_args(["--list"])

        f = io.StringIO()
        with redirect_stdout(f):
            ret = cli.run(args)
        self.assertEqual(ret, 0)
        self.assertIn("eDP-1", f.getvalue())
        self.assertIn("1920x1080", f.getvalue())

    @patch("backends.registry.select")
    def test_run_dry_run_mode(self, mock_select):
        mock_select.return_value = self.fake_backend
        parser = cli.build_parser()
        args = parser.parse_args(["--mode", "internal", "--dry-run"])

        f = io.StringIO()
        with redirect_stdout(f):
            ret = cli.run(args)
        self.assertEqual(ret, 0)
        self.assertIn("mock-cmd --plan", f.getvalue())

    @patch("backends.registry.select")
    def test_run_apply_mode(self, mock_select):
        mock_select.return_value = self.fake_backend
        parser = cli.build_parser()
        args = parser.parse_args(["--mode", "internal"])

        f = io.StringIO()
        with redirect_stdout(f):
            ret = cli.run(args)
        self.assertEqual(ret, 0)
        self.assertIn("applied mode 'internal'", f.getvalue())
        self.assertIn("mock-cmd --apply", f.getvalue())


if __name__ == "__main__":
    unittest.main()
