"""Common base class for subprocess-driven backends.

Most backends shell out to a CLI tool (``xrandr``, ``swaymsg``, ``hyprctl``,
``kscreen-doctor``, ``wlr-randr``, ``cosmic-randr``). This base class provides a
single ``_run`` seam so unit tests can substitute canned output.
"""

from __future__ import annotations

import subprocess
from typing import Any

from interfaces import BackendApplyError, DisplayBackend


class SubprocessBackend(DisplayBackend):
    """A :class:`DisplayBackend` implemented via command-line tools."""

    #: command used by ``list_outputs`` (parsed by ``parse_outputs``).
    LIST_CMD: list[str] = []

    def __init__(self, env=None, runner=None) -> None:
        super().__init__(env)
        self._runner = runner or self._default_run
        self._snapshot: Any = None

    # -- command execution -------------------------------------------------
    def _default_run(self, argv: list[str], check: bool = False, timeout: int = 10,
                     input: str | None = None) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, input=input,
        )
        if check and proc.returncode != 0:
            raise BackendApplyError(
                f"`{' '.join(argv)}` failed ({proc.returncode}): {proc.stderr.strip()}"
            )
        return proc

    def _run(self, argv: list[str], check: bool = False, timeout: int = 10,
             input: str | None = None) -> subprocess.CompletedProcess:
        return self._runner(argv, check=check, timeout=timeout, input=input)

    def available(self) -> bool:
        import shutil
        return bool(self.LIST_CMD) and shutil.which(self.LIST_CMD[0]) is not None

    # -- shared helpers ----------------------------------------------------
    def list_outputs(self):
        proc = self._run(self.LIST_CMD, check=True)
        return self.parse_outputs(proc.stdout)

    def parse_outputs(self, text: str):
        raise NotImplementedError

    def snapshot(self):
        return self.list_outputs()

    def _display_error(self, msg: str):
        raise BackendApplyError(msg)
