"""Shared helpers for backend tests (mocked command runners)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Result:
    """Minimal stand-in for subprocess.CompletedProcess."""

    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def make_runner(outputs, default=None):
    """Return a runner callable matching SubprocessBackend._run's signature.

    ``outputs`` maps a command-line prefix string to a ``Result``.
    """
    def runner(argv, check=False, timeout=10, input=None):
        key = " ".join(argv)
        for prefix, result in outputs.items():
            if key.startswith(prefix):
                return result
        return default or Result()
    return runner
