"""XFCE hotkey registration via xfconf-query."""

from __future__ import annotations

import shutil
import subprocess

from interfaces import HotkeyRegistrar

PROPERTY = "/commands/custom/<Super>p"
CHANNEL = "xfce4-keyboard-shortcuts"


class XfceHotkey(HotkeyRegistrar):
    name = "xfce"

    def __init__(self, append: bool = False) -> None:
        self._append = append

    @classmethod
    def can_handle(cls, env) -> bool:
        return env.has_desktop("xfce")

    def register(self, command: str) -> list[str]:
        if not shutil.which("xfconf-query"):
            return [f"xfconf-query not found. Manual: {self.instructions(command)}"]
        argv = ["xfconf-query", "--channel", CHANNEL, "--property", PROPERTY,
                "--create", "--type", "string", "--set", command]
        subprocess.run(argv, capture_output=True)
        return [" ".join(argv)]

    def unregister(self) -> list[str]:
        if not shutil.which("xfconf-query"):
            return ["xfconf-query not found"]
        argv = ["xfconf-query", "--channel", CHANNEL, "--property", PROPERTY, "--reset"]
        subprocess.run(argv, capture_output=True)
        return [" ".join(argv)]

    def instructions(self, command: str) -> str:
        return (
            "Register the shortcut in XFCE:\n"
            f"  xfconf-query --channel {CHANNEL} --property \"{PROPERTY}\" "
            f"--create --type string --set \"{command}\"\n"
        )
