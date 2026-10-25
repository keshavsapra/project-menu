"""X11 backend via ``xrandr``.

Works on any X11 desktop/WM. Falls back to python-xlib RandR if ``xrandr`` is
missing (best-effort; ``xrandr`` is the primary path).
"""

from __future__ import annotations

import re
import shutil

from backends.base import SubprocessBackend
from core import best_duplicate_mode, find_mode, infer_mode, is_builtin_name, primary_output, secondary_outputs
from interfaces import (
    ApplyResult,
    DisplayMode,
    ExtendPosition,
    ModeInfo,
    Output,
    Selection,
)

_MODE_LINE = re.compile(
    r"^\s*(?P<w>\d+)x(?P<h>\d+)\s+(?P<rates>[0-9.+* ]+)$"
)
_HEADER = re.compile(
    r"^(?P<name>\S+)\s+(?P<status>connected|disconnected|unknown)"
    r"(?:\s+(?P<primary>primary))?"
    r"(?:\s+(?P<geom>\d+x\d+\+\d+\+\d+))?"
    r"(?:\s+\([^)]*\))?"
    r"(?:\s+\d+mm\s+x\s+\d+mm)?\s*$"
)


def _parse_rate(token: str) -> float | None:
    cleaned = token.strip("+*")
    if not cleaned:
        # xrandr can emit the preferred/current markers as separate tokens
        # (e.g. "60.00 +  50.00" for a connected-but-disabled output); a bare
        # "+" or "*" is not a refresh rate of its own — skip it.
        return None
    return float(cleaned)


def _has_xlib_randr() -> bool:
    try:
        from Xlib.ext import randr  # noqa: F401
        return True
    except Exception:
        return False


def _list_outputs_xlib() -> list[Output]:
    try:
        import Xlib.display
        from Xlib.ext import randr

        d = Xlib.display.Display()
        s = d.screen()
        root = s.root
        res = randr.get_screen_resources(root)
        try:
            prim_obj = randr.get_output_primary(root)
            primary_id = prim_obj.output
        except Exception:
            primary_id = None

        mode_map: dict[int, ModeInfo] = {}
        for m in getattr(res, "modes", []):
            dot_clock = getattr(m, "dot_clock", 0)
            htot = getattr(m, "h_total", 0) or 1
            vtot = getattr(m, "v_total", 0) or 1
            refresh = round(dot_clock / (htot * vtot), 2) if dot_clock else 60.0
            mode_map[m.id] = ModeInfo(m.width, m.height, refresh, mode_id=str(m.id))

        outputs: list[Output] = []
        for out_id in res.outputs:
            info = randr.get_output_info(root, out_id, res.config_timestamp)
            connected = (info.connection == randr.Connected)
            name = info.name
            out = Output(
                name=name,
                connected=connected,
                primary=(out_id == primary_id),
                builtin=is_builtin_name(name),
            )
            for mid in info.modes:
                if mid in mode_map:
                    out.modes.append(mode_map[mid])
            if info.crtc:
                try:
                    cinfo = randr.get_crtc_info(root, info.crtc, res.config_timestamp)
                    out.x = cinfo.x
                    out.y = cinfo.y
                    out.width = cinfo.width
                    out.height = cinfo.height
                    out.enabled = connected and (cinfo.width > 0 and cinfo.height > 0)
                    if cinfo.mode in mode_map:
                        out.current_mode = mode_map[cinfo.mode]
                except Exception:
                    pass
            outputs.append(out)
        return outputs
    except Exception:
        return []


class X11Backend(SubprocessBackend):
    name = "x11"
    environments = ("x11",)
    priority = 10
    LIST_CMD = ["xrandr", "--query"]

    @classmethod
    def can_handle(cls, env) -> bool:
        return env.session_type == "x11" and (shutil.which("xrandr") is not None or _has_xlib_randr())

    def available(self) -> bool:
        return shutil.which("xrandr") is not None or _has_xlib_randr()

    def list_outputs(self) -> list[Output]:
        if shutil.which("xrandr") is not None:
            return super().list_outputs()
        if _has_xlib_randr():
            outs = _list_outputs_xlib()
            if outs:
                return outs
        return super().list_outputs()

    # -- parsing -----------------------------------------------------------
    def parse_outputs(self, text: str):
        outputs: list[Output] = []
        current: Output | None = None
        for raw in text.splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue
            if line.startswith((" ", "\t")):
                # Mode line, belongs to the current output.
                m = _MODE_LINE.match(line)
                if m and current is not None:
                    w, h = int(m.group("w")), int(m.group("h"))
                    for tok in m.group("rates").split():
                        refresh = _parse_rate(tok)
                        if refresh is None:  # bare preferred/current marker
                            continue
                        is_current = "*" in tok
                        mode = ModeInfo(w, h, refresh, mode_id=f"{w}x{h}")
                        current.modes.append(mode)
                        if is_current:
                            current.current_mode = mode
                continue
            m = _HEADER.match(line)
            if not m:
                continue
            name = m.group("name")
            connected = m.group("status") == "connected"
            out = Output(
                name=name,
                connected=connected,
                primary=m.group("primary") is not None,
                builtin=is_builtin_name(name),
            )
            if m.group("geom"):
                geom = m.group("geom").split("+")
                w, h = int(geom[0].split("x")[0]), int(geom[0].split("x")[1])
                out.width, out.height = w, h
                out.x, out.y = int(geom[1]), int(geom[2])
            out.enabled = connected and m.group("geom") is not None
            outputs.append(out)
            current = out
        # Link current_mode geometry where the header did not carry it.
        for o in outputs:
            if o.current_mode and (o.width == 0 or o.height == 0):
                o.width, o.height = o.current_mode.width, o.current_mode.height
        return outputs

    # -- queries -----------------------------------------------------------
    def get_current_mode(self):
        return infer_mode(self.list_outputs())

    # -- planning ----------------------------------------------------------
    def _primary(self, outputs):
        return primary_output(outputs)

    def _second(self, outputs, target):
        if target:
            for o in outputs:
                if o.name == target:
                    return o
        second = secondary_outputs(outputs)
        return second[0] if second else None

    def plan(
        self,
        mode_or_selection: DisplayMode | Selection | str,
        target_output: str | None = None,
        position: ExtendPosition | str = ExtendPosition.RIGHT,
    ) -> list[str]:
        selection = self._normalize_selection(mode_or_selection, target_output, position)
        outputs = self.list_outputs()
        return self._build_commands(outputs, selection)

    def _build_commands(self, outputs, selection: Selection) -> list[str]:
        mode = selection.mode
        prim = self._primary(outputs)
        if prim is None:
            return ["# no connected displays"]
        second = self._second(outputs, selection.target_output)
        others = [o for o in outputs if o.connected and o.name not in (prim.name, (second.name if second else None))]

        parts = ["xrandr"]
        if mode == DisplayMode.INTERNAL:
            parts += [f"--output {prim.name} --auto --primary"]
            for o in outputs:
                if o.connected and o.name != prim.name:
                    parts.append(f"--output {o.name} --off")
        elif mode == DisplayMode.EXTERNAL:
            if second is None:
                return ["# no second display detected"]
            parts += [f"--output {second.name} --auto"]
            for o in outputs:
                if o.connected and o.name != second.name:
                    parts.append(f"--output {o.name} --off")
        elif mode == DisplayMode.DUPLICATE:
            if second is None:
                return ["# no second display detected"]
            ma, mb, _warn = best_duplicate_mode(prim, second)
            if ma is None:
                return ["# no common resolution; cannot duplicate"]
            rate = f" --rate {ma.refresh:g}" if ma.refresh else ""
            parts += [f"--output {prim.name} --mode {ma.width}x{ma.height}{rate}"]
            parts.append(f"--output {second.name} --same-as {prim.name}")
            for o in others:
                parts.append(f"--output {o.name} --off")
        elif mode == DisplayMode.EXTEND:
            if second is None:
                return ["# no second display detected"]
            pos = selection.position
            flag = {
                ExtendPosition.RIGHT: "--right-of",
                ExtendPosition.LEFT: "--left-of",
                ExtendPosition.ABOVE: "--above",
                ExtendPosition.BELOW: "--below",
            }[pos]
            parts += [f"--output {prim.name} --auto --primary"]
            parts.append(f"--output {second.name} --auto {flag} {prim.name}")
            for o in others:
                parts.append(f"--output {o.name} --off")
        else:
            return ["# unknown mode"]
        return [" ".join(parts)]

    def apply(
        self,
        mode_or_selection: DisplayMode | Selection | str,
        target_output: str | None = None,
        position: ExtendPosition | str = ExtendPosition.RIGHT,
    ) -> ApplyResult:
        selection = self._normalize_selection(mode_or_selection, target_output, position)
        outputs = self.list_outputs()
        self._snapshot = outputs
        cmds = self._build_commands(outputs, selection)
        warnings: list[str] = []
        if selection.mode == DisplayMode.DUPLICATE:
            prim = self._primary(outputs)
            second = self._second(outputs, selection.target_output)
            if prim and second:
                _, _, warn = best_duplicate_mode(prim, second)
                if warn:
                    warnings.append(warn)
        if not cmds or cmds[0].startswith("#"):
            return ApplyResult(False, selection.mode, cmds, warnings, error=cmds[0].lstrip("# ") if cmds else "unknown error")
        argv = cmds[0].split()
        try:
            self._run(argv, check=True)
        except Exception as exc:  # noqa: BLE001
            return ApplyResult(False, selection.mode, cmds, warnings, error=str(exc))
        return ApplyResult(True, selection.mode, cmds, warnings)

    def restore(self, snapshot) -> ApplyResult:
        if not snapshot:
            return ApplyResult(False, error="no snapshot to restore")
        parts = ["xrandr"]
        for o in snapshot:
            if not o.connected:
                continue
            if not o.enabled:
                parts.append(f"--output {o.name} --off")
                continue
            cmd = f"--output {o.name}"
            if o.current_mode:
                cmd += f" --mode {o.current_mode.width}x{o.current_mode.height}"
                if o.current_mode.refresh:
                    cmd += f" --rate {o.current_mode.refresh:g}"
            cmd += f" --pos {o.x}x{o.y}"
            if o.primary:
                cmd += " --primary"
            parts.append(cmd)
        argv = " ".join(parts).split()
        try:
            self._run(argv, check=True)
        except Exception as exc:  # noqa: BLE001
            return ApplyResult(False, error=str(exc), commands=[" ".join(parts)])
        return ApplyResult(True, commands=[" ".join(parts)])
