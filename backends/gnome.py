"""GNOME Wayland backend via ``org.gnome.Mutter.DisplayConfig`` D-Bus.

We deliberately do **not** use ``gdctl`` (missing on many GNOME versions).
Instead we talk to Mutter directly:

* ``GetCurrentState()`` -> ``(serial, monitors, logical_monitors, properties)``
* ``ApplyMonitorsConfig(serial, method, logical_monitors, properties)``
  where ``method`` is ``0=verify, 1=temporary, 2=persistent``.

The exact D-Bus signatures are taken from mutter's
``data/dbus-interfaces/org.gnome.Mutter.DisplayConfig.xml``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core import is_builtin_name
from interfaces import (
    ApplyResult,
    DisplayBackend,
    DisplayMode,
    ExtendPosition,
    ModeInfo,
    Output,
    Selection,
)

SERVICE = "org.gnome.Mutter.DisplayConfig"
OBJECT = "/org/gnome/Mutter/DisplayConfig"
IFACE = "org.gnome.Mutter.DisplayConfig"

# ApplyMonitorsConfig method: 2 = persistent (0 = verify, 1 = temporary).
APPLY_METHOD = 2

APPLY_TYPE = "(uua(iiduba(ssa{sv}))a{sv})"


@dataclass
class _ConnectorInfo:
    connector: str
    builtin: bool = False
    display_name: str = ""
    modes: list[ModeInfo] = field(default_factory=list)
    current_mode_id: str | None = None
    preferred_mode_id: str | None = None


class GnomeWaylandBackend(DisplayBackend):
    name = "gnome-wayland"
    environments = ("wayland:gnome", "wayland:ubuntu")
    priority = 20

    def __init__(self, env=None, dbus=None) -> None:
        super().__init__(env)
        self._dbus = dbus or self._real_dbus_call
        self._snapshot = None

    @classmethod
    def can_handle(cls, env) -> bool:
        return env.session_type == "wayland" and env.has_desktop("gnome", "ubuntu")

    # -- D-Bus plumbing ----------------------------------------------------
    def _real_dbus_call(self, method: str, *args):
        from gi.repository import Gio, GLib  # noqa: WPS433 (lazy import)

        conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        proxy = Gio.DBusProxy.new_sync(
            conn, Gio.DBusProxyFlags.NONE, None, SERVICE, OBJECT, IFACE, None,
        )
        params = None
        if args:
            type_str, value = args
            params = GLib.Variant(type_str, value)
        result = proxy.call_sync(method, params, Gio.DBusCallFlags.NONE, -1, None)
        return result.unpack()

    def _call(self, method: str, *args):
        return self._dbus(method, *args)

    def available(self) -> bool:
        try:
            self._get_current_state()
            return True
        except Exception:
            return False

    # -- state -------------------------------------------------------------
    def _get_current_state(self):
        return self._call("GetCurrentState")

    def _connector_map(self, monitors):
        """connector -> _ConnectorInfo, from the GetCurrentState monitors array."""
        result: dict[str, _ConnectorInfo] = {}
        for (connector, vendor, product, serial), modes, props in monitors:
            info = _ConnectorInfo(
                connector=connector,
                builtin=bool(props.get("is-builtin", False)),
                display_name=props.get("display-name", "") or "",
            )
            for (mode_id, w, h, refresh, pref_scale, scales, mprops) in modes:
                info.modes.append(ModeInfo(w, h, refresh, mode_id=mode_id))
                if mprops.get("is-current"):
                    info.current_mode_id = mode_id
                if mprops.get("is-preferred"):
                    info.preferred_mode_id = mode_id
            result[connector] = info
        return result

    def list_outputs(self) -> list[Output]:
        _serial, monitors, logical_monitors, _props = self._get_current_state()
        cmap = self._connector_map(monitors)
        outputs: dict[str, Output] = {}

        # Seed with every *connected* monitor, including disabled ones, so that
        # a plugged-in second screen is discoverable even when it is currently off.
        for connector, info in cmap.items():
            out = Output(
                name=connector,
                description=info.display_name,
                connected=True,
                enabled=False,
                builtin=info.builtin,
                modes=list(info.modes),
            )
            # Use the preferred (or current) mode for sizing so position math and
            # duplicate-resolution selection work even while the monitor is off.
            mid = info.preferred_mode_id or info.current_mode_id
            mode = next((m for m in info.modes if m.mode_id == mid), None)
            if mode:
                out.width, out.height = mode.width, mode.height
                if info.current_mode_id:
                    cmode = next((m for m in info.modes if m.mode_id == info.current_mode_id), mode)
                    out.current_mode = cmode
            outputs[connector] = out

        # Overlay logical-monitor info for the monitors that are actually enabled.
        for (x, y, scale, transform, primary, lm_monitors, _lm_props) in logical_monitors:
            for (connector, vendor, product, serial) in lm_monitors:
                out = outputs.get(connector)
                if out is None:
                    continue
                out.x, out.y = x, y
                out.primary = bool(primary)
                out.enabled = True
                out.scale = float(scale or 1.0)
                if out.current_mode:
                    out.width = int(round(out.current_mode.width / out.scale))
                    out.height = int(round(out.current_mode.height / out.scale))
        return list(outputs.values())

    def get_current_mode(self):
        from core import infer_mode
        return infer_mode(self.list_outputs())

    # -- planning ----------------------------------------------------------
    def _logical_width(self, out: Output) -> int:
        return out.width or (out.current_mode.width if out.current_mode else 0)

    def _logical_height(self, out: Output) -> int:
        return out.height or (out.current_mode.height if out.current_mode else 0)

    def _best_mode_id(self, info: _ConnectorInfo, width: int | None = None,
                      height: int | None = None) -> str:
        if info is None:
            return ""
        if width is not None and height is not None:
            cands = [m for m in info.modes if m.width == width and m.height == height]
            if cands:
                best = max(cands, key=lambda m: m.refresh)
                if best.mode_id:
                    return best.mode_id
        mid = info.preferred_mode_id or info.current_mode_id
        if mid:
            return mid
        if info.modes and info.modes[0].mode_id:
            return info.modes[0].mode_id
        return ""

    def _scale(self, outputs: dict[str, Output], connector: str) -> float:
        out = outputs.get(connector)
        return out.scale if out else 1.0

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
        cmap = self._connector_map(self._get_current_state()[1])
        config = self._build_config(outputs, cmap, selection)
        if not config:
            return ["# no second display detected" if len(outputs) <= 1 else "# no valid configuration"]
        return [f"ApplyMonitorsConfig(serial, method={APPLY_METHOD}, logical_monitors={config})"]

    def _build_config(self, outputs, cmap, selection: Selection):
        from core import primary_output, secondary_outputs, best_duplicate_mode

        prim = primary_output(outputs)
        if prim is None:
            return []
        second = None
        if selection.target_output:
            second = next((o for o in outputs if o.name == selection.target_output), None)
        if second is None:
            secs = secondary_outputs(outputs)
            second = secs[0] if secs else None

        prim_info = cmap.get(prim.name)
        sec_info = cmap.get(second.name) if second else None

        def lm(x, y, primary, monitors):
            scale = self._scale(dict((o.name, o) for o in outputs), monitors[0][0])
            return (x, y, scale, 0, primary, [(c, mid or "") for c, mid in monitors])

        mode = selection.mode
        if mode == DisplayMode.INTERNAL:
            return [lm(0, 0, True, [(prim.name, self._best_mode_id(prim_info))])]
        if second is None:
            return []
        if mode == DisplayMode.EXTERNAL:
            return [lm(0, 0, True, [(second.name, self._best_mode_id(sec_info))])]
        if mode == DisplayMode.DUPLICATE:
            ma, mb, _warn = best_duplicate_mode(prim, second)
            if ma is None:
                return []
            pa = self._best_mode_id(prim_info, ma.width, ma.height)
            pb = self._best_mode_id(sec_info, mb.width, mb.height)
            return [lm(0, 0, True, [(prim.name, pa), (second.name, pb)])]
        if mode == DisplayMode.EXTEND:
            pos = selection.position
            pw = self._logical_width(prim)
            ph = self._logical_height(prim)
            sw = self._logical_width(second)
            sh = self._logical_height(second)
            sx, sy = prim.x, prim.y
            if pos == ExtendPosition.RIGHT:
                sx, sy = prim.x + pw, prim.y
            elif pos == ExtendPosition.LEFT:
                sx, sy = prim.x - sw, prim.y
            elif pos == ExtendPosition.ABOVE:
                sx, sy = prim.x, prim.y - sh
            elif pos == ExtendPosition.BELOW:
                sx, sy = prim.x, prim.y + ph
            return [
                lm(prim.x, prim.y, True, [(prim.name, self._best_mode_id(prim_info))]),
                lm(sx, sy, False, [(second.name, self._best_mode_id(sec_info))]),
            ]
        return []

    def apply(
        self,
        mode_or_selection: DisplayMode | Selection | str,
        target_output: str | None = None,
        position: ExtendPosition | str = ExtendPosition.RIGHT,
    ) -> ApplyResult:
        selection = self._normalize_selection(mode_or_selection, target_output, position)
        serial, monitors, logical_monitors, props = self._get_current_state()
        self._snapshot = (monitors, logical_monitors, props)
        outputs = self.list_outputs()
        cmap = self._connector_map(monitors)
        config = self._build_config(outputs, cmap, selection)
        warnings: list[str] = []
        if selection.mode == DisplayMode.DUPLICATE:
            from core import primary_output, secondary_outputs, best_duplicate_mode
            prim = primary_output(outputs)
            secs = secondary_outputs(outputs)
            if prim and secs:
                _, _, warn = best_duplicate_mode(prim, secs[0])
                if warn:
                    warnings.append(warn)
        if not config:
            err = "no second display detected" if len(outputs) <= 1 else "no valid configuration"
            return ApplyResult(False, selection.mode, error=err)
        value = self._to_apply_value(config)
        try:
            self._call("ApplyMonitorsConfig", APPLY_TYPE, (serial, APPLY_METHOD, value, {}))
        except Exception as exc:  # noqa: BLE001
            return ApplyResult(False, selection.mode, error=str(exc), warnings=warnings)
        return ApplyResult(True, selection.mode, warnings=warnings,
                           commands=[f"ApplyMonitorsConfig(method={APPLY_METHOD}, logical_monitors={config})"])

    def _to_apply_value(self, config):
        return [
            (x, y, scale, transform, primary, [(c, mid, {}) for c, mid in monitors])
            for (x, y, scale, transform, primary, monitors) in config
        ]

    def snapshot(self):
        return self._get_current_state()

    def restore(self, snapshot) -> ApplyResult:
        if not snapshot:
            return ApplyResult(False, error="no snapshot to restore")
        _serial, monitors, logical_monitors, _props = snapshot
        cmap = self._connector_map(monitors)
        config = []
        for (x, y, scale, transform, primary, lm_monitors, _lp) in logical_monitors:
            specs = []
            for (connector, vendor, product, serial) in lm_monitors:
                info = cmap.get(connector)
                mid = ""
                if info:
                    mid = info.current_mode_id or info.preferred_mode_id or (info.modes[0].mode_id if info.modes else "")
                specs.append((connector, mid or ""))
            config.append((x, y, scale, transform, primary, specs))
        try:
            serial, _m, _l, _p = self._get_current_state()
            value = self._to_apply_value(config)
            self._call("ApplyMonitorsConfig", APPLY_TYPE, (serial, APPLY_METHOD, value, {}))
        except Exception as exc:  # noqa: BLE001
            return ApplyResult(False, error=str(exc))
        return ApplyResult(True)
