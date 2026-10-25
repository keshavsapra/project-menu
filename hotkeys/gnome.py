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
    """Cinnamon does NOT use media-keys custom-keybindings (that's GNOME/MATE).

    Cinnamon keeps user shortcuts in ``org.cinnamon.desktop.keybindings
    custom-list`` with one relocatable schema per slot:
    ``org.cinnamon.desktop.keybindings.custom-keybinding`` at
    ``/org/cinnamon/desktop/keybindings/custom-keybindings/customN/`` whose
    name/command/binding keys are arrays of strings.
    """

    name = "cinnamon"
    MEDIA_SCHEMA = ""  # not used; overridden hooks below bypass it
    SWITCH_SCHEMA = "org.cinnamon.desktop.keybindings.wm"
    LIST_SCHEMA = "org.cinnamon.desktop.keybindings"
    LIST_KEY = "custom-list"
    SLOT_SCHEMA = "org.cinnamon.desktop.keybindings.custom-keybinding"
    SLOT_PREFIX = "/org/cinnamon/desktop/keybindings/custom-keybindings/"

    @classmethod
    def can_handle(cls, env) -> bool:
        return env.has_desktop("cinnamon")

    def _list(self) -> list[str]:
        p = self._run(["gsettings", "get", self.LIST_SCHEMA, self.LIST_KEY])
        return _PATH_RE.findall(p.stdout)

    def _set_list(self, names: list[str]) -> None:
        val = "[" + ", ".join(f"'{n}'" for n in names) + "]" if names else "[]"
        self._run(["gsettings", "set", self.LIST_SCHEMA, self.LIST_KEY, val], check=True)

    def _slot_path(self, name: str) -> str:
        return f"{self.SLOT_PREFIX}{name}/"

    def register(self, command: str) -> list[str]:
        if not shutil.which("gsettings"):
            return [f"gsettings not found. Manual: {self.instructions(command)}"]
        actions: list[str] = []
        existing = self._list()
        used = {n for n in existing if re.fullmatch(r"custom\d+", n)}
        index = 0
        while f"custom{index}" in used:
            index += 1
        name = f"custom{index}"
        slot = self._slot_path(name)

        self._set_list(existing + [name])
        actions.append(f"gsettings set {self.LIST_SCHEMA} {self.LIST_KEY} (added {slot})")

        schema = f"{self.SLOT_SCHEMA}:{slot}"
        # Cinnamon's schema types: name/command are plain STRINGS, binding is an
        # ARRAY of strings. Writing bracket syntax into name/command makes Cinnamon
        # try to execute a file literally named "['project-menu']".
        self._run(["gsettings", "set", schema, "name", self.LABEL], check=True)
        self._run(["gsettings", "set", schema, "command", command], check=True)
        self._run(["gsettings", "set", schema, "binding", f"['{self.BINDING}']"], check=True)
        actions.append(f"gsettings set {schema} name '{self.LABEL}'")
        actions.append(f"gsettings set {schema} command '{command}'")
        actions.append(f"gsettings set {schema} binding ['{self.BINDING}']")

        # Cinnamon's built-in monitor-switch combo would conflict with Super+P.
        if self.SWITCH_SCHEMA:
            self._run(["gsettings", "set", self.SWITCH_SCHEMA, self.SWITCH_KEY, "[]"], check=True)
            actions.append(f"gsettings set {self.SWITCH_SCHEMA} {self.SWITCH_KEY} '[]' (disabled built-in Super+P)")
        return actions

    def unregister(self) -> list[str]:
        if not shutil.which("gsettings"):
            return ["gsettings not found; nothing to unregister"]
        actions: list[str] = []
        existing = self._list()
        ours: list[str] = []
        for name in existing:
            slot = self._slot_path(name)
            schema = f"{self.SLOT_SCHEMA}:{slot}"
            p = self._run(["gsettings", "get", schema, "name"])
            if self.LABEL in p.stdout:
                ours.append(name)
                for key in ("name", "command", "binding"):
                    self._run(["gsettings", "reset", schema, key])
                actions.append(f"gsettings reset {schema} *")
        if ours:
            self._set_list([n for n in existing if n not in ours])
        if self.SWITCH_SCHEMA:
            self._run(["gsettings", "reset", self.SWITCH_SCHEMA, self.SWITCH_KEY])
            actions.append(f"gsettings reset {self.SWITCH_SCHEMA} {self.SWITCH_KEY} (restored built-in Super+P)")
        return actions

    def instructions(self, command: str) -> str:
        return (
            "Cinnamon: System Settings > Hardware > Keyboard > Shortcuts > Custom > Add custom.\n"
            f"  Name: {self.LABEL}\n"
            f"  Command: {command}\n"
            "  Shortcut: press Super+P\n"
            "or via terminal:\n"
            f"  gsettings set {self.LIST_SCHEMA} {self.LIST_KEY} \"['custom0']\"\n"
            f"  gsettings set {self.SLOT_SCHEMA}:{self.SLOT_PREFIX}custom0/ name '{self.LABEL}'\n"
            f"  gsettings set {self.SLOT_SCHEMA}:{self.SLOT_PREFIX}custom0/ command '{command}'\n"
            f"  gsettings set {self.SLOT_SCHEMA}:{self.SLOT_PREFIX}custom0/ binding \"['{self.BINDING}']\"\n"
            f"  gsettings set {self.SWITCH_SCHEMA} {self.SWITCH_KEY} \"[]\"\n"
        )


class MateHotkey(GsettingsHotkey):
    name = "mate"
    MEDIA_SCHEMA = "org.mate.settings-daemon.plugins.media-keys"
    SWITCH_SCHEMA = "org.mate.Marco.global-keybindings"

    @classmethod
    def can_handle(cls, env) -> bool:
        return env.has_desktop("mate")
