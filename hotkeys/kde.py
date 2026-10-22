"""KDE Plasma hotkey registration via kglobalshortcutsrc + kglobalaccel."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from interfaces import HotkeyRegistrar

DESKTOP_FILE = Path.home() / ".local" / "share" / "applications" / "project-menu.desktop"
SHORTCUT = "Meta+P"


def _kw() -> str:
    return "kwriteconfig6" if shutil.which("kwriteconfig6") else "kwriteconfig5"


def _qdbus() -> str:
    return "qdbus6" if shutil.which("qdbus6") else "qdbus"


def _kglobalaccel_service() -> str:
    # Plasma 6 uses org.kde.KGlobalAccel; Plasma 5 uses org.kde.kglobalaccel.
    return "org.kde.KGlobalAccel" if shutil.which("qdbus6") else "org.kde.kglobalaccel"


class KdeHotkey(HotkeyRegistrar):
    name = "kde"

    def __init__(self, append: bool = False) -> None:
        self._append = append

    @classmethod
    def can_handle(cls, env) -> bool:
        return env.has_desktop("kde", "plasma")

    def _write_desktop_file(self, command: str) -> str:
        DESKTOP_FILE.parent.mkdir(parents=True, exist_ok=True)
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Project Menu\n"
            "Comment=Switch display mode (Win+P style)\n"
            f"Exec={command}\n"
            "Icon=video-display\n"
            "NoDisplay=true\n"
            "X-KDE-GlobalAccel=true\n"
            "Actions=launch\n"
            "[Desktop Action launch]\n"
            "Name=Project Menu\n"
            f"Exec={command}\n"
        )
        DESKTOP_FILE.write_text(content)
        return str(DESKTOP_FILE)

    def register(self, command: str) -> list[str]:
        if not shutil.which(_kw()):
            return [f"{_kw()} not found. Manual: {self.instructions(command)}"]
        actions: list[str] = []
        actions.append(f"write {self._write_desktop_file(command)}")
        kw = _kw()
        self._run([kw, "--file", "kglobalshortcutsrc", "--group", "project-menu.desktop",
                   "--key", "_launch", f"{SHORTCUT},none,Project Menu"], check=True)
        actions.append(f"{kw} --file kglobalshortcutsrc --group project-menu.desktop --key _launch \"{SHORTCUT},none,Project Menu\"")
        self._reload()
        actions.append(f"{_qdbus()} {_kglobalaccel_service()} /kglobalaccel reloadConfig")
        return actions

    def unregister(self) -> list[str]:
        actions: list[str] = []
        kw = _kw()
        if shutil.which(kw):
            self._run([kw, "--file", "kglobalshortcutsrc", "--group", "project-menu.desktop", "--key", "_launch", "--delete"])
            actions.append(f"{kw} --file kglobalshortcutsrc --group project-menu.desktop --key _launch --delete")
            self._reload()
        if DESKTOP_FILE.exists():
            DESKTOP_FILE.unlink()
            actions.append(f"rm {DESKTOP_FILE}")
        return actions

    def _reload(self) -> None:
        subprocess.run([_qdbus(), _kglobalaccel_service(), "/kglobalaccel", "reloadConfig"],
                       capture_output=True)

    def _run(self, argv, check=False):
        return subprocess.run(argv, capture_output=True, text=True)

    def instructions(self, command: str) -> str:
        return (
            "Register a global shortcut in KDE Plasma:\n"
            "  1. Create ~/.local/share/applications/project-menu.desktop with:\n"
            "       Exec=" + command + "\n"
            "       X-KDE-GlobalAccel=true\n"
            "  2. Set the shortcut:\n"
            f"       {_kw()} --file kglobalshortcutsrc --group project-menu.desktop --key _launch \"{SHORTCUT},none,Project Menu\"\n"
            f"  3. Reload: {_qdbus()} {_kglobalaccel_service()} /kglobalaccel reloadConfig\n"
        )
