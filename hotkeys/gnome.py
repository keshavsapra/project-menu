"""GNOME / Cinnamon / MATE hotkey registration via gsettings/dconf."""

from __future__ import annotations

import re
import shutil
import subprocess

from interfaces import HotkeyRegistrar

_PATH_RE = re.compile(r"'([^']+)'")


class GsettingsHotkey(HotkeyRegistrar):
    """Register a custom Super+P binding through a gsettings media-keys schema.

    Subclasses supply the desktop-specific schema names.
    """

    MEDIA_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
    SWITCH_SCHEMA = "org.gnome.mutter.keybindings"
    SWITCH_KEY = "switch-monitor"
    BINDING = "<Super>p"
    LABEL = "Project Menu"

    def __init__(self, append: bool = False) -> None:
        self._append = append

    def _run(self, argv, check=False):
        return subprocess.run(argv, capture_output=True, text=True)

    def _get_paths(self) -> list[str]:
        p = self._run(["gsettings", "get", self.MEDIA_SCHEMA, "custom-keybindings"])
        return _PATH_RE.findall(p.stdout)

    def _set_paths(self, paths: list[str]) -> None:
        val = "[" + ", ".join(f"'{p}'" for p in paths) + "]" if paths else "[]"
        self._run(["gsettings", "set", self.MEDIA_SCHEMA, "custom-keybindings", val], check=True)

    def _slot_path(self, paths: list[str], index: int) -> str:
        prefix = f"/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom{index}/"
        # derive prefix from schema for cinnamon/mate
        if "cinnamon" in self.MEDIA_SCHEMA:
            prefix = f"/org/cinnamon/settings-daemon/plugins/media-keys/custom-keybindings/custom{index}/"
        elif "mate" in self.MEDIA_SCHEMA:
            prefix = f"/org/mate/settings-daemon/plugins/media-keys/custom-keybindings/custom{index}/"
        return prefix

    def register(self, command: str) -> list[str]:
        if not shutil.which("gsettings"):
            return [f"gsettings not found. Manual: {self.instructions(command)}"]
        actions: list[str] = []
        paths = self._get_paths()
        # Find a free slot index.
        used = set()
        for p in paths:
            m = re.search(r"custom(\d+)/", p)
            if m:
                used.add(int(m.group(1)))
        index = 0
        while index in used:
            index += 1
        slot = self._slot_path(paths, index)
        paths = paths + [slot]
        self._set_paths(paths)
        actions.append(f"gsettings set {self.MEDIA_SCHEMA} custom-keybindings (added {slot})")

        schema = f"{self.MEDIA_SCHEMA}.custom-keybinding:{slot}"
        for key, value in (("name", self.LABEL), ("command", command), ("binding", self.BINDING)):
            self._run(["gsettings", "set", schema, key, value], check=True)
            actions.append(f"gsettings set {schema} {key} '{value}'")

        # Disable the built-in switch-monitor Super+P binding.
        if self.SWITCH_SCHEMA:
            self._run(["gsettings", "set", self.SWITCH_SCHEMA, self.SWITCH_KEY, "[]"], check=True)
            actions.append(f"gsettings set {self.SWITCH_SCHEMA} {self.SWITCH_KEY} '[]' (disabled built-in Super+P)")
        return actions

    def unregister(self) -> list[str]:
        if not shutil.which("gsettings"):
            return ["gsettings not found; nothing to unregister"]
        actions: list[str] = []
        paths = self._get_paths()
        kept = [p for p in paths if self.LABEL not in p and not self._is_ours(p)]
        # Identify our slot by checking the command value.
        ours = [p for p in paths if self._slot_is_ours(p)]
        for slot in ours:
            schema = f"{self.MEDIA_SCHEMA}.custom-keybinding:{slot}"
            for key in ("name", "command", "binding"):
                self._run(["gsettings", "reset", schema, key])
            actions.append(f"gsettings reset {schema} *")
        kept = [p for p in paths if p not in ours]
        self._set_paths(kept)
        if self.SWITCH_SCHEMA:
            self._run(["gsettings", "reset", self.SWITCH_SCHEMA, self.SWITCH_KEY])
            actions.append(f"gsettings reset {self.SWITCH_SCHEMA} {self.SWITCH_KEY} (restored built-in Super+P)")
        return actions

    def _slot_is_ours(self, slot: str) -> bool:
        schema = f"{self.MEDIA_SCHEMA}.custom-keybinding:{slot}"
        p = self._run(["gsettings", "get", schema, "name"])
        return self.LABEL in p.stdout

    def _is_ours(self, slot: str) -> bool:
        return "custom-keybindings/custom" in slot

    def instructions(self, command: str) -> str:
        return (
            "Create a custom keybinding manually:\n"
            f"  gsettings set {self.MEDIA_SCHEMA} custom-keybindings \"['/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/']\"\n"
            f"  gsettings set {self.MEDIA_SCHEMA}.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/ name '{self.LABEL}'\n"
            f"  gsettings set {self.MEDIA_SCHEMA}.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/ command '{command}'\n"
            f"  gsettings set {self.MEDIA_SCHEMA}.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/ binding '<Super>p'\n"
            f"  gsettings set {self.SWITCH_SCHEMA} {self.SWITCH_KEY} \"[]\"\n"
        )


class GnomeHotkey(GsettingsHotkey):
    name = "gnome"
    MEDIA_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
    SWITCH_SCHEMA = "org.gnome.mutter.keybindings"

    @classmethod
    def can_handle(cls, env) -> bool:
        return env.has_desktop("gnome", "ubuntu")


class CinnamonHotkey(GsettingsHotkey):
    name = "cinnamon"
    MEDIA_SCHEMA = "org.cinnamon.settings-daemon.plugins.media-keys"
    SWITCH_SCHEMA = "org.cinnamon.desktop.keybindings.wm"

    @classmethod
    def can_handle(cls, env) -> bool:
        return env.has_desktop("cinnamon")


class MateHotkey(GsettingsHotkey):
    name = "mate"
    MEDIA_SCHEMA = "org.mate.settings-daemon.plugins.media-keys"
    SWITCH_SCHEMA = "org.mate.Marco.global-keybindings"

    @classmethod
    def can_handle(cls, env) -> bool:
        return env.has_desktop("mate")
