"""Generic wlroots backend via ``wlr-randr``.

Targets wlroots compositors without their own CLI: river, labwc, Wayfire, etc.
"""

from __future__ import annotations

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

_HEADER = re.compile(r'^(?P<name>\S+)\s+"(?P<desc>.*)"$')
_MODE = re.compile(r"(?P<w>\d+)x(?P<h>\d+)@(?P<r>[\d.]+)Hz")


class WlrootsBackend(SubprocessBackend):
    name = "wlr-randr"
    environments = ("wayland:river", "wayland:labwc", "wayland:wayfire", "wayland:wlroots")
    priority = 50
    LIST_CMD = ["wlr-randr"]

    @classmethod
    def can_handle(cls, env) -> bool:
        return env.session_type == "wayland" and env.has_desktop("river", "labwc", "wayfire", "sway")

    def available(self) -> bool:
        return shutil.which("wlr-randr") is not None

    def parse_outputs(self, text: str):
        outputs: list[Output] = []
        current: Output | None = None
        in_modes = False
        for raw in text.splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue
            if not line.startswith((" ", "\t")):
                m = _HEADER.match(line)
                if m:
                    current = Output(
                        name=m.group("name"), description=m.group("desc"),
                        connected=True, builtin=is_builtin_name(m.group("name")),
                    )
                    outputs.append(current)
                    in_modes = False
                continue
            if current is None:
                continue
            stripped = line.strip()
            key, _, val = stripped.partition(":")
            val = val.strip()
            if key == "Enabled":
                current.enabled = val.lower() == "yes"
                in_modes = False
            elif key == "Position":
                x, _, y = val.partition(",")
                current.x, current.y = int(x), int(y)
                in_modes = False
            elif key == "Scale":
                try:
                    current.scale = float(val)
                except ValueError:
                    pass
                in_modes = False
            elif key == "Mode":
                m = _MODE.match(val)
                if m:
                    current.current_mode = ModeInfo(int(m.group("w")), int(m.group("h")), float(m.group("r")))
                    current.width, current.height = current.current_mode.width, current.current_mode.height
                in_modes = False
            elif key == "Modes":
                in_modes = True
            elif in_modes:
                m = _MODE.match(stripped)
                if m:
                    current.modes.append(ModeInfo(int(m.group("w")), int(m.group("h")), float(m.group("r"))))
        return outputs

    def get_current_mode(self):
        return infer_mode(self.list_outputs())

    def _prim(self, outputs):
        return primary_output(outputs)

    def _second(self, outputs, target):
        if target:
            for o in outputs:
                if o.name == target:
                    return o
        secs = secondary_outputs(outputs)
        return secs[0] if secs else None

    def _build_argv(self, outputs, selection: Selection) -> list[str]:
        prim = self._prim(outputs)
        if prim is None:
            return []
        second = self._second(outputs, selection.target_output)
        others = [o for o in outputs if o.name not in (prim.name, (second.name if second else None))]
        mode = selection.mode
        argv = ["wlr-randr"]

        def on(o: Output, res=None, pos=None):
            argv.append("--output")
            argv.append(o.name)
            argv.append("--on")
            if res:
                argv.extend(["--mode", res])
            if pos:
                argv.extend(["--pos", f"{pos[0]},{pos[1]}"])

        def off(o: Output):
            argv.append("--output")
            argv.append(o.name)
            argv.append("--off")

        if mode == DisplayMode.INTERNAL:
            on(prim)
            for o in outputs:
                if o.name != prim.name:
                    off(o)
        elif mode == DisplayMode.EXTERNAL:
            if second is None:
                return []
            on(second)
            for o in outputs:
                if o.name != second.name:
                    off(o)
        elif mode == DisplayMode.DUPLICATE:
            if second is None:
                return []
            ma, mb, _warn = best_duplicate_mode(prim, second)
            if ma is None:
                return []
            res = f"{ma.width}x{ma.height}@{ma.refresh:g}"
            on(prim, res=res, pos=(0, 0))
            on(second, res=res, pos=(0, 0))
            for o in others:
                off(o)
        elif mode == DisplayMode.EXTEND:
            if second is None:
                return []
            pos = selection.position
            pw, ph = prim.width, prim.height
            sw, sh = second.width, second.height
            prim_pos = (0, 0)
            sec_pos = (pw, 0)
            if pos == ExtendPosition.LEFT:
                prim_pos, sec_pos = (sw, 0), (0, 0)
            elif pos == ExtendPosition.ABOVE:
                prim_pos, sec_pos = (0, sh), (0, 0)
            elif pos == ExtendPosition.BELOW:
                prim_pos, sec_pos = (0, 0), (0, ph)
            on(prim, pos=prim_pos)
            on(second, pos=sec_pos)
            for o in others:
                off(o)
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
        if len(argv) <= 1:
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
        if len(argv) <= 1:
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
        argv = ["wlr-randr"]
        for o in snapshot:
            argv.append("--output")
            argv.append(o.name)
            if not o.enabled:
                argv.append("--off")
            else:
                argv.append("--on")
                if o.current_mode:
                    argv += ["--mode", f"{o.current_mode.width}x{o.current_mode.height}@{o.current_mode.refresh:g}"]
                argv += ["--pos", f"{o.x},{o.y}"]
                if o.scale and o.scale != 1.0:
                    argv += ["--scale", f"{o.scale:g}"]
        try:
            self._run(argv, check=True)
        except Exception as exc:  # noqa: BLE001
            return ApplyResult(False, error=str(exc), commands=[" ".join(argv)])
        return ApplyResult(True, commands=[" ".join(argv)])
