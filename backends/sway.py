"""Sway backend via ``swaymsg``.

Reads state from the ``get_outputs`` IPC and applies changes with ``swaymsg
output <name> ...`` commands (Sway mirrors outputs that share a mode/position).
"""

from __future__ import annotations

import json
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


class SwayBackend(SubprocessBackend):
    name = "sway"
    environments = ("wayland:sway",)
    priority = 40
    LIST_CMD = ["swaymsg", "-t", "get_outputs"]

    @classmethod
    def can_handle(cls, env) -> bool:
        return env.session_type == "wayland" and (env.sway_sock or env.has_desktop("sway"))

    def available(self) -> bool:
        return shutil.which("swaymsg") is not None

    def parse_outputs(self, text: str):
        data = json.loads(text)
        outputs: list[Output] = []
        for item in data:
            name = item.get("name", "")
            rect = item.get("rect", {})
            cm = item.get("current_mode") or {}
            modes = item.get("modes") or []
            out = Output(
                name=name,
                description=f"{item.get('make', '')} {item.get('model', '')}".strip(),
                connected=True,
                enabled=bool(item.get("active", False)),
                primary=bool(item.get("primary", False)),
                builtin=is_builtin_name(name),
                x=int(rect.get("x", 0)),
                y=int(rect.get("y", 0)),
                width=int(rect.get("width", 0)),
                height=int(rect.get("height", 0)),
                scale=float(item.get("scale", 1.0)),
            )
            for m in modes:
                out.modes.append(ModeInfo(
                    int(m["width"]), int(m["height"]), m.get("refresh", 0) / 1000.0,
                ))
            if cm:
                out.current_mode = ModeInfo(
                    int(cm["width"]), int(cm["height"]), cm.get("refresh", 0) / 1000.0,
                )
            outputs.append(out)
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

    def _build_commands(self, outputs, selection: Selection) -> list[str]:
        prim = self._prim(outputs)
        if prim is None:
            return []
        second = self._second(outputs, selection.target_output)
        others = [o for o in outputs if o.name not in (prim.name, (second.name if second else None))]
        cmds: list[str] = []
        mode = selection.mode

        def on(o: Output, pos=None, mode=None):
            cmds.append(f"output {o.name} enable")
            if mode:
                cmds.append(f"output {o.name} mode {mode}")
            if pos:
                cmds.append(f"output {o.name} position {pos[0]} {pos[1]}")

        def off(o: Output):
            cmds.append(f"output {o.name} disable")

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
            on(prim, mode=res, pos=(0, 0))
            on(second, mode=res, pos=(0, 0))
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
        return cmds

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
        cmds = self._build_commands(outputs, selection)
        if not cmds:
            return ["# no second display detected" if len(outputs) <= 1 else "# no valid configuration"]
        return ["swaymsg " + " ".join(cmds)]

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
        cmds = self._build_commands(outputs, selection)
        warnings: list[str] = []
        if selection.mode == DisplayMode.DUPLICATE:
            prim = self._prim(outputs)
            second = self._second(outputs, selection.target_output)
            if prim and second:
                _, _, warn = best_duplicate_mode(prim, second)
                if warn:
                    warnings.append(warn)
        if not cmds:
            err = "no second display detected" if len(outputs) <= 1 else "no valid configuration"
            return ApplyResult(False, selection.mode, error=err)
        argv = ["swaymsg"] + cmds
        try:
            self._run(argv, check=True)
        except Exception as exc:  # noqa: BLE001
            return ApplyResult(False, selection.mode, [" ".join(argv)], warnings, str(exc))
        return ApplyResult(True, selection.mode, [" ".join(argv)], warnings)

    def restore(self, snapshot) -> ApplyResult:
        if not snapshot:
            return ApplyResult(False, error="no snapshot to restore")
        cmds: list[str] = []
        for o in snapshot:
            if not o.enabled:
                cmds.append(f"output {o.name} disable")
            else:
                cmds.append(f"output {o.name} enable")
                if o.current_mode:
                    cmds.append(f"output {o.name} mode {o.current_mode.width}x{o.current_mode.height}@{o.current_mode.refresh:g}")
                cmds.append(f"output {o.name} position {o.x} {o.y}")
                if o.scale and o.scale != 1.0:
                    cmds.append(f"output {o.name} scale {o.scale:g}")
        argv = ["swaymsg"] + cmds
        try:
            self._run(argv, check=True)
        except Exception as exc:  # noqa: BLE001
            return ApplyResult(False, error=str(exc), commands=[" ".join(argv)])
        return ApplyResult(True, commands=[" ".join(argv)])
