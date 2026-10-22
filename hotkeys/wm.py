"""Sway / Hyprland / i3 hotkey registration.

We never edit user configs automatically. ``register`` prints the exact snippet;
with ``--append-config`` (``append=True``) it appends to the user's config file.
"""

from __future__ import annotations

from pathlib import Path

from interfaces import HotkeyRegistrar


class WmHotkey(HotkeyRegistrar):
    config_path: Path | None = None
    snippet_template: str = "bindsym $mod+p exec {command}"

    def __init__(self, append: bool = False) -> None:
        self._append = append

    def _snippet(self, command: str) -> str:
        return self.snippet_template.format(command=command)

    def register(self, command: str) -> list[str]:
        snippet = self._snippet(command)
        if self._append and self.config_path is not None:
            path = self.config_path.expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as f:
                f.write("\n# project-menu\n" + snippet + "\n")
            return [f"appended to {path}: {snippet}"]
        where = f" {self.config_path}" if self.config_path else ""
        return [f"add this line to{where}:\n    {snippet}"]

    def unregister(self) -> list[str]:
        if not self._append or self.config_path is None:
            return ["remove the project-menu line from your WM config manually"]
        path = self.config_path.expanduser()
        if not path.exists():
            return [f"{path} not found; nothing to remove"]
        lines = path.read_text().splitlines()
        kept = [ln for ln in lines if "project-menu" not in ln and "bindsym $mod+p exec" not in ln and "bind = SUPER, P" not in ln]
        path.write_text("\n".join(kept) + "\n")
        return [f"removed project-menu lines from {path}"]

    def instructions(self, command: str) -> str:
        where = f" in {self.config_path}" if self.config_path else ""
        return f"Add this line to your config{where}:\n    {self._snippet(command)}\n"


class SwayHotkey(WmHotkey):
    name = "sway"
    config_path = Path.home() / ".config" / "sway" / "config"
    snippet_template = "bindsym $mod+p exec {command}"

    @classmethod
    def can_handle(cls, env) -> bool:
        return env.sway_sock or env.has_desktop("sway")


class HyprlandHotkey(WmHotkey):
    name = "hyprland"
    config_path = Path.home() / ".config" / "hypr" / "hyprland.conf"
    snippet_template = "bind = SUPER, P, exec, {command}"

    @classmethod
    def can_handle(cls, env) -> bool:
        return bool(env.hyprland_instance) or env.has_desktop("hyprland")


class I3Hotkey(WmHotkey):
    name = "i3"
    config_path = Path.home() / ".config" / "i3" / "config"
    snippet_template = "bindsym $mod+p exec {command}"

    @classmethod
    def can_handle(cls, env) -> bool:
        return env.session_type == "x11" and env.has_desktop("i3")
