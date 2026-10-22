"""Hyprland backend via ``hyprctl``.

Reads state from ``hyprctl -j monitors`` and applies changes with
``hyprctl keyword monitor <name>,<mode>[,<pos>][,<scale>][,mirror,<src>]``.
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

_MODE_RE = re.compile(r"(?P<w>\d+)x(?P<h>\d+)@(?P<r>[\d.]+)")


class HyprlandBackend(SubprocessBackend):
    name = "hyprland"
    environments = ("wayland:hyprland",)
    priority = 45
    LIST_CMD = ["hyprctl", "-j", "monitors", "all"]

    @classmethod
    def can_handle(cls, env) -> bool:
        return env.session_type == "wayland" and (env.hyprland_instance or env.has_desktop("hyprland"))

    def available(self) -> bool:
        return shutil.which("hyprctl") is not None

    def parse_outputs(self, text: str):
        data = json.loads(text)
        outputs: list[Output] = []
        for item in data:
            name = item.get("name", "")
            disabled = bool(item.get("disabled", False))
            w = int(item.get("width", 0) or 0)
            h = int(item.get("height", 0) or 0)
            rr = float(item.get("refreshRate", 0) or 0)
            out = Output(
                name=name,
                description=item.get("description", ""),
                connected=True,
                enabled=not disabled,  # `monitors all` includes disabled outputs
                builtin=is_builtin_name(name),
                x=int(item.get("x", 0)),
                y=int(item.get("y", 0)),
                width=w,
                height=h,
                scale=float(item.get("scale", 1.0)),
                current_mode=ModeInfo(w, h, rr) if not disabled and w and h else None,
            )
            for mstr in item.get("availableModes", []) or []:
                m = _MODE_RE.match(mstr)
                if m:
                    out.modes.append(ModeInfo(int(m.group("w")), int(m.group("h")), float(m.group("r"))))
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
        mode = selection.mode
        cmds: list[str] = []

        def set_monitor(o: Output, spec: str):
            cmds.append(f"hyprctl keyword monitor {o.name},{spec}")

        def off(o: Output):
            cmds.append(f"hyprctl keyword monitor {o.name},disable")

        if mode == DisplayMode.INTERNAL:
            set_monitor(prim, "preferred,auto,1")
            for o in outputs:
                if o.name != prim.name:
                    off(o)
        elif mode == DisplayMode.EXTERNAL:
            if second is None:
                return []
            set_monitor(second, "preferred,auto,1")
            for o in outputs:
                if o.name != second.name:
                    off(o)
        elif mode == DisplayMode.DUPLICATE:
            if second is None:
                return []
            ma, mb, _warn = best_duplicate_mode(prim, second)
            if ma is None:
                # Unknown modes (e.g. the second display is currently disabled):
                # fall back to each display's preferred mode + native mirroring.
                set_monitor(prim, "preferred,auto,1")
                set_monitor(second, f"preferred,auto,1,mirror,{prim.name}")
                for o in others:
                    off(o)
                return cmds
            res = f"{ma.width}x{ma.height}@{ma.refresh:g}"
            set_monitor(prim, f"{res},auto,1")
            set_monitor(second, f"{res},auto,1,mirror,{prim.name}")
            for o in others:
                off(o)
        elif mode == DisplayMode.EXTEND:
            if second is None:
                return []
            pos = selection.position
            pw, ph = prim.width, prim.height
            sw, sh = second.width, second.height
            prim_pos = "0x0"
            sec_pos = f"{pw}x0"
            if pos == ExtendPosition.LEFT:
                prim_pos, sec_pos = f"{sw}x0", "0x0"
            elif pos == ExtendPosition.ABOVE:
                prim_pos, sec_pos = f"0x{sh}", "0x0"
            elif pos == ExtendPosition.BELOW:
                prim_pos, sec_pos = "0x0", f"0x{ph}"
            set_monitor(prim, f"preferred,{prim_pos},1")
            set_monitor(second, f"preferred,{sec_pos},1")
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
        return cmds

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
        for c in cmds:
            try:
                self._run(c.split(), check=True)
            except Exception as exc:  # noqa: BLE001
                return ApplyResult(False, selection.mode, cmds, warnings, str(exc))
        return ApplyResult(True, selection.mode, cmds, warnings)

    def restore(self, snapshot) -> ApplyResult:
        if not snapshot:
            return ApplyResult(False, error="no snapshot to restore")
        cmds: list[str] = []
        for o in snapshot:
            if not o.enabled:
                cmds.append(f"hyprctl keyword monitor {o.name},disable")
            elif o.current_mode:
                cmds.append(f"hyprctl keyword monitor {o.name},{o.current_mode.width}x{o.current_mode.height}@{o.current_mode.refresh:g},{o.x}x{o.y},{o.scale:g}")
        for c in cmds:
            try:
                self._run(c.split(), check=True)
            except Exception as exc:  # noqa: BLE001
                return ApplyResult(False, error=str(exc), commands=cmds)
        return ApplyResult(True, commands=cmds)
