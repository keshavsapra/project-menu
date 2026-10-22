"""Generic X11 fallback hotkey: python-xlib XGrabKey daemon or sxhkd instructions."""

from __future__ import annotations

import shutil
import subprocess

from interfaces import HotkeyRegistrar

SXHKD_SNIPPET = "super + p\n    project-menu\n"


class X11GrabHotkey(HotkeyRegistrar):
    name = "x11-grab"

    def __init__(self, append: bool = False) -> None:
        self._append = append

    @classmethod
    def can_handle(cls, env) -> bool:
        return env.session_type == "x11"

    def _has_xlib(self) -> bool:
        try:
            import Xlib  # noqa: F401
            return True
        except Exception:
            return False

    def register(self, command: str) -> list[str]:
        if self._has_xlib():
            return [
                "python-xlib available; start the grab daemon with:",
                f"    project-menu --hotkey-daemon &   # or add to autostart",
            ]
        if shutil.which("sxhkd"):
            return [f"add to ~/.config/sxhkd/sxhkdrc:\n{SXHKD_SNIPPET}"]
        return [self.instructions(command)]

    def unregister(self) -> list[str]:
        return ["kill the project-menu --hotkey-daemon process, or remove the sxhkd rule"]

    def instructions(self, command: str) -> str:
        return (
            "No automatic hotkey registration is available for this X11 desktop.\n"
            "Options:\n"
            "  1. Install python-xlib and run `project-menu --hotkey-daemon &`\n"
            "  2. Or install sxhkd and add to ~/.config/sxhkd/sxhkdrc:\n"
            + SXHKD_SNIPPET
        )


def run_grab_daemon(command: str) -> int:
    """Grab Super+P with python-xlib and exec *command* on press (blocking)."""
    try:
        from Xlib import X, XK, display
        from Xlib.ext import record
        from Xlib.protocol import rq
    except Exception as exc:  # noqa: BLE001
        print(f"python-xlib not available: {exc}")
        return 1

    local_dpy = display.Display()
    keysym = XK.string_to_keysym("P")

    root = local_dpy.screen().root
    # Grab Super+P on the root window, including NumLock/CapsLock combinations
    modmask = 0x40  # Mod4 (Super); best-effort, may vary by X server
    keycode = root.keysym_to_keycode(keysym)
    for extra in (0, 0x02, 0x10, 0x12):
        try:
            root.grab_key(keycode, modmask | extra, True, X.GrabModeAsync, X.GrabModeAsync)
        except Exception:
            pass
    print("project-menu hotkey daemon running (Super+P).")

    while True:
        event = local_dpy.next_event()
        if event.type == X.KeyPress:
            subprocess.Popen(command.split())
    return 0
