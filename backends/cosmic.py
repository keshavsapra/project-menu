"""COSMIC backend via ``cosmic-randr``.

COSMIC (System76) ships ``cosmic-randr`` with subcommands: ``list``, ``enable``,
``disable``, ``mode``, ``position``, ``scale`` and ``mirror``. The CLI is
version-dependent; parsing is deliberately tolerant.
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

_HEADER = re.compile(r"^(?P<name>\S+)\s+\((?P<state>enabled|disabled)\)")
_MODE = re.compile(r"(?P<w>\d+)x(?P<h>\d+)\s+@\s+(?P<r>[\d.]+)\s*Hz")


class CosmicBackend(SubprocessBackend):
    name = "cosmic"
    environments = ("wayland:cosmic",)
    priority = 60
    LIST_CMD = ["cosmic-randr", "list"]

    @classmethod
    def can_handle(cls, env) -> bool:
        return env.session_type == "wayland" and env.has_desktop("cosmic")

    def available(self) -> bool:
        return shutil.which("cosmic-randr") is not None

    def parse_outputs(self, text: str):
        outputs: list[Output] = []
        current: Output | None = None
        for raw in text.splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue
            hm = _HEADER.match(line)
            if hm:
                current = Output(
                    name=hm.group("name"),
                    connected=True,
                    enabled=hm.group("state") == "enabled",
                    builtin=is_builtin_name(hm.group("name")),
                )
                outputs.append(current)
                continue
            if current is None:
                continue
            stripped = line.strip()
            mm = _MODE.search(stripped)
            if mm:
                w, h, r = int(mm.group("w")), int(mm.group("h")), float(mm.group("r"))
                mode = ModeInfo(w, h, r, mode_id=f"{w}x{h}@{r:.3f}")
                current.modes.append(mode)
                if "(current)" in stripped:
                    current.current_mode = mode
                    current.width, current.height = w, h
                continue
            key, _, val = stripped.partition(":")
            val = val.strip()
            if key == "Position":
                x, _, y = val.partition(",")
                current.x, current.y = int(x), int(y)
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

    def _mode_str(self, out: Output, width=None, height=None) -> str | None:
        if width is None and out.current_mode:
            return out.current_mode.mode_id
        cands = [m for m in out.modes if m.width == width and m.height == height]
        if not cands:
            return None
        return max(cands, key=lambda m: m.refresh).mode_id

    def _build_commands(self, outputs, selection: Selection) -> list[str]:
        prim = self._prim(outputs)
        if prim is None:
            return []
        second = self._second(outputs, selection.target_output)
        others = [o for o in outputs if o.name not in (prim.name, (second.name if second else None))]
        mode = selection.mode
        cmds: list[str] = []

        if mode == DisplayMode.INTERNAL:
            cmds.append(f"cosmic-randr enable {prim.name}")
            ms = self._mode_str(prim)
            if ms:
                cmds.append(f"cosmic-randr mode {prim.name} {ms}")
            for o in outputs:
                if o.connected and o.name != prim.name:
                    cmds.append(f"cosmic-randr disable {o.name}")
        elif mode == DisplayMode.EXTERNAL:
            if second is None:
                return []
            cmds.append(f"cosmic-randr enable {second.name}")
            for o in outputs:
                if o.name != second.name:
                    cmds.append(f"cosmic-randr disable {o.name}")
        elif mode == DisplayMode.DUPLICATE:
            if second is None:
                return []
            ma, mb, _warn = best_duplicate_mode(prim, second)
            if ma is None:
                return []
            cmds.append(f"cosmic-randr enable {prim.name}")
            cmds.append(f"cosmic-randr enable {second.name}")
            ms = self._mode_str(prim, ma.width, ma.height)
            if ms:
                cmds.append(f"cosmic-randr mode {prim.name} {ms}")
            cmds.append(f"cosmic-randr mirror {second.name} {prim.name}")
            for o in others:
                cmds.append(f"cosmic-randr disable {o.name}")
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
            cmds.append(f"cosmic-randr enable {prim.name}")
            cmds.append(f"cosmic-randr enable {second.name}")
            cmds.append(f"cosmic-randr position {prim.name} {prim_pos[0]} {prim_pos[1]}")
            cmds.append(f"cosmic-randr position {second.name} {sec_pos[0]} {sec_pos[1]}")
            for o in others:
                cmds.append(f"cosmic-randr disable {o.name}")
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
                cmds.append(f"cosmic-randr disable {o.name}")
            else:
                cmds.append(f"cosmic-randr enable {o.name}")
                ms = self._mode_str(o)
                if ms:
                    cmds.append(f"cosmic-randr mode {o.name} {ms}")
                cmds.append(f"cosmic-randr position {o.name} {o.x} {o.y}")
        for c in cmds:
            try:
                self._run(c.split(), check=True)
            except Exception as exc:  # noqa: BLE001
                return ApplyResult(False, error=str(exc), commands=cmds)
        return ApplyResult(True, commands=cmds)
