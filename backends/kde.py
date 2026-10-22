"""KDE Plasma Wayland backend via ``kscreen-doctor``.

Uses the atomic ``kscreen-doctor output.<name>.<setting>[.<value>]`` interface.
The KScreen D-Bus API is avoided in favour of the CLI, which is simpler and
present on every Plasma install (``libkscreen``/``plasma-workspace``).
"""

from __future__ import annotations

import json
import re
import shutil

from backends.base import SubprocessBackend
from core import best_duplicate_mode, infer_mode, is_builtin_name, primary_output, secondary_outputs
from interfaces import (
    ApplyResult,
    DisplayMode,
    ExtendPosition,
    ModeInfo,
    Output,
    Selection,
)

_TEXT_LINE = re.compile(
    r"^Output:\s+(?P<id>\d+)\s+(?P<name>\S+)\s+"
    r"(?P<enabled>enabled|disabled)\s+(?P<connected>connected|disconnected)\b.*?"
    r"Modes:\s*(?P<modes>.*?)\s+Geometry:\s*"
    r"(?P<x>-?\d+),(?P<y>-?\d+)\s+(?P<w>\d+)x(?P<h>\d+)\s*$"
)
_MODE_TOKEN = re.compile(r"(?P<id>\d+):(?P<w>\d+)x(?P<h>\d+)@(?P<r>[\d.]+)(?P<flags>[*!]?)")


class KdeBackend(SubprocessBackend):
    name = "kde"
    environments = ("wayland:kde", "wayland:plasma")
    priority = 30
    LIST_CMD = ["kscreen-doctor", "--outputs"]

    @classmethod
    def can_handle(cls, env) -> bool:
        return env.session_type == "wayland" and env.has_desktop("kde", "plasma")

    def available(self) -> bool:
        return shutil.which("kscreen-doctor") is not None

    # -- parsing -----------------------------------------------------------
    def parse_outputs(self, text: str):
        outputs: list[Output] = []
        for line in text.splitlines():
            m = _TEXT_LINE.match(line.strip())
            if not m:
                continue
            out = Output(
                name=m.group("name"),
                connected=m.group("connected") == "connected",
                enabled=m.group("enabled") == "enabled",
                builtin=is_builtin_name(m.group("name")),
            )
            out.x = int(m.group("x"))
            out.y = int(m.group("y"))
            out.width = int(m.group("w"))
            out.height = int(m.group("h"))
            for tok in m.group("modes").split():
                mt = _MODE_TOKEN.match(tok)
                if not mt:
                    continue
                mode = ModeInfo(
                    int(mt.group("w")), int(mt.group("h")), float(mt.group("r")),
                    mode_id=mt.group("id"),
                )
                out.modes.append(mode)
                if "*" in mt.group("flags"):
                    out.current_mode = mode
            outputs.append(out)
        return outputs

    # -- queries -----------------------------------------------------------
    def get_current_mode(self):
        return infer_mode(self.list_outputs())

    # -- planning ----------------------------------------------------------
    def _prim(self, outputs):
        return primary_output(outputs)

    def _second(self, outputs, target):
        if target:
            for o in outputs:
                if o.name == target:
                    return o
        secs = secondary_outputs(outputs)
        return secs[0] if secs else None

    def _mode_arg(self, out: Output, width: int | None = None, height: int | None = None) -> str | None:
        if out.current_mode and width is None:
            return out.current_mode.mode_id
        cands = [m for m in out.modes if m.width == width and m.height == height]
        if not cands:
            return None
        return max(cands, key=lambda m: m.refresh).mode_id

    def _build_argv(self, outputs, selection: Selection) -> list[str]:
        prim = self._prim(outputs)
        if prim is None:
            return []
        second = self._second(outputs, selection.target_output)
        others = [o for o in outputs if o.connected and o.name not in (prim.name, (second.name if second else None))]
        mode = selection.mode
        argv = ["kscreen-doctor"]

        def s(out, setting, value=None):
            argv.append(f"output.{out.name}.{setting}" + (f".{value}" if value is not None else ""))

        if mode == DisplayMode.INTERNAL:
            s(prim, "enable")
            s(prim, "primary")
            mid = self._mode_arg(prim)
            if mid:
                s(prim, "mode", mid)
            for o in outputs:
                if o.connected and o.name != prim.name:
                    s(o, "disable")
        elif mode == DisplayMode.EXTERNAL:
            if second is None:
                return []
            s(second, "enable")
            for o in outputs:
                if o.connected and o.name != second.name:
                    s(o, "disable")
        elif mode == DisplayMode.DUPLICATE:
            if second is None:
                return []
            ma, mb, _warn = best_duplicate_mode(prim, second)
            if ma is None:
                return []
            s(prim, "enable")
            s(second, "enable")
            s(prim, "primary")
            s(prim, "mode", self._mode_arg(prim, ma.width, ma.height))
            s(second, "mode", self._mode_arg(second, mb.width, mb.height))
            s(prim, "position", "0,0")
            s(second, "position", "0,0")
            for o in others:
                s(o, "disable")
        elif mode == DisplayMode.EXTEND:
            if second is None:
                return []
            pos = selection.position
            s(prim, "enable")
            s(second, "enable")
            s(prim, "primary")
            mid_p = self._mode_arg(prim)
            mid_s = self._mode_arg(second)
            if mid_p:
                s(prim, "mode", mid_p)
            if mid_s:
                s(second, "mode", mid_s)
            pw, ph = prim.width, prim.height
            sw, sh = second.width, second.height
            if pos == ExtendPosition.RIGHT:
                s(prim, "position", "0,0")
                s(second, "position", f"{pw},0")
            elif pos == ExtendPosition.LEFT:
                s(prim, "position", f"{sw},0")
                s(second, "position", "0,0")
            elif pos == ExtendPosition.ABOVE:
                s(prim, "position", f"0,{sh}")
                s(second, "position", "0,0")
            elif pos == ExtendPosition.BELOW:
                s(prim, "position", "0,0")
                s(second, "position", f"0,{ph}")
            for o in others:
                s(o, "disable")
        return argv

    def plan(
        self,
        mode_or_selection: DisplayMode | Selection | str,
        target_output: str | None = None,
        position: ExtendPosition | str = ExtendPosition.RIGHT,
    ) -> list[str]:
        selection = self._normalize_selection(mode_or_selection, target_output, position)
        outputs = self.list_outputs()
        if len(outputs) <= 1 and selection.mode != DisplayMode.INTERNAL:
            return ["# no second display detected"]
        argv = self._build_argv(outputs, selection)
        if not argv:
            return ["# no second display detected" if len(outputs) <= 1 else "# no valid configuration"]
        return [" ".join(argv)]

    def apply(
        self,
        mode_or_selection: DisplayMode | Selection | str,
        target_output: str | None = None,
        position: ExtendPosition | str = ExtendPosition.RIGHT,
    ) -> ApplyResult:
        selection = self._normalize_selection(mode_or_selection, target_output, position)
        outputs = self.list_outputs()
        self._snapshot = outputs
        if len(outputs) <= 1 and selection.mode != DisplayMode.INTERNAL:
            return ApplyResult(False, selection.mode, error="no second display detected")
        argv = self._build_argv(outputs, selection)
        warnings: list[str] = []
        if selection.mode == DisplayMode.DUPLICATE:
            prim = self._prim(outputs)
            second = self._second(outputs, selection.target_output)
            if prim and second:
                _, _, warn = best_duplicate_mode(prim, second)
                if warn:
                    warnings.append(warn)
        if not argv:
            err = "no second display detected" if len(outputs) <= 1 else "no valid configuration"
            return ApplyResult(False, selection.mode, error=err)
        try:
            self._run(argv, check=True)
        except Exception as exc:  # noqa: BLE001
            return ApplyResult(False, selection.mode, [" ".join(argv)], warnings, str(exc))
        return ApplyResult(True, selection.mode, [" ".join(argv)], warnings)

    def restore(self, snapshot) -> ApplyResult:
        if not snapshot:
            return ApplyResult(False, error="no snapshot to restore")
        argv = ["kscreen-doctor"]
        for o in snapshot:
            if not o.connected:
                continue
            argv.append(f"output.{o.name}.{'enable' if o.enabled else 'disable'}")
            if o.enabled:
                if o.current_mode and o.current_mode.mode_id:
                    argv.append(f"output.{o.name}.mode.{o.current_mode.mode_id}")
                argv.append(f"output.{o.name}.position.{o.x},{o.y}")
                if o.primary:
                    argv.append(f"output.{o.name}.primary")
        try:
            self._run(argv, check=True)
        except Exception as exc:  # noqa: BLE001
            return ApplyResult(False, error=str(exc), commands=[" ".join(argv)])
        return ApplyResult(True, commands=[" ".join(argv)])
