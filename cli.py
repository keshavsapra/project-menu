"""Command-line interface and dispatch logic."""

from __future__ import annotations

import argparse
import os
import sys

import core
import detect
from backends import registry as backend_registry
from core import notify
from hotkeys import registry as hotkey_registry
from interfaces import (
    DisplayMode,
    ExtendPosition,
    MODE_ALIASES,
    MODE_LABELS,
    POSITION_ALIASES,
    Selection,
    UIContext,
)

HOTKEY_COMMAND = "project-menu"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="project-menu",
        description="Cross-desktop Win+P style display-mode switcher.",
    )
    p.add_argument("--list", "-l", action="store_true", help="list detected outputs and exit")
    p.add_argument("--mode", "-m", choices=sorted(set(MODE_ALIASES)), help="apply a mode without the popup")
    p.add_argument("--output", "--target-output", "-o", metavar="NAME", dest="output",
                   help="which output is the 'second screen' (for 3+ monitors)")
    p.add_argument("--position", "-p", choices=sorted(set(POSITION_ALIASES)), default="right",
                   help="extend position: right/left/above/below (default right)")
    p.add_argument("--confirm", action="store_true",
                   help="prompt with 15-second auto-revert confirmation when applying via CLI")
    p.add_argument("--timeout", type=int, default=15, metavar="SEC",
                   help="confirmation timeout in seconds (default: 15)")
    p.add_argument("--dry-run", "-n", action="store_true", help="print commands without running them")
    p.add_argument("--debug", "-d", action="store_true", help="enable debug logging (and print environment/backend); also implies foreground")
    p.add_argument("--foreground", "-F", action="store_true",
                   help="run the popup in the foreground (a plain launch backgrounds itself so no console window stays open)")
    p.add_argument("--backend", "-b", metavar="NAME", help="override the auto-detected backend")
    p.add_argument("--register-hotkey", action="store_true", help="register the Super+P hotkey")
    p.add_argument("--unregister-hotkey", action="store_true", help="remove the Super+P hotkey")
    p.add_argument("--append-config", action="store_true",
                   help="(Sway/Hyprland/i3) append the hotkey snippet to the WM config")
    p.add_argument("--hotkey-command", metavar="CMD", default=HOTKEY_COMMAND,
                   help="command bound to Super+P (default: project-menu)")
    p.add_argument("--hotkey-daemon", action="store_true",
                   help="run the python-xlib XGrabKey daemon (generic X11 fallback)")
    return p


def _print_outputs(outputs) -> None:
    for o in outputs:
        status = "connected" if o.connected else "disconnected"
        on = "on" if o.enabled else "off"
        primary = " primary" if o.primary else ""
        builtin = " builtin" if o.builtin else ""
        mode = o.current_mode or ""
        print(f"{o.name:<14} {status:<12} {on:<3}{primary:<8}{builtin:<8} "
              f"{o.width}x{o.height}+{o.x}+{o.y}  {mode}")


def _selection_from_args(args) -> Selection:
    mode = MODE_ALIASES[args.mode]
    position = POSITION_ALIASES[args.position]
    return Selection(mode=mode, target_output=args.output, position=position)


def _print_plan(cmds) -> None:
    for c in cmds:
        print(c)


def run(args: argparse.Namespace) -> int:
    core.setup_logging(args.debug)
    env = detect.detect()
    core.log().info("environment: %s", env.summary())

    # -- environment-only actions -----------------------------------------
    if args.hotkey_daemon:
        from hotkeys.x11_grab import run_grab_daemon
        return run_grab_daemon(args.hotkey_command)

    if args.register_hotkey or args.unregister_hotkey:
        return _run_hotkey(env, args)

    # -- backend-dependent actions ----------------------------------------
    try:
        backend = backend_registry.select(env, args.backend)
    except Exception as exc:  # noqa: BLE001
        print(exc, file=sys.stderr)
        notify("Project Menu", "No display backend available", urgent=True)
        return 1

    if args.debug:
        print(f"session: {env.summary()}")
        print(f"backend: {backend.name}")

    if args.list:
        _print_outputs(backend.list_outputs())
        return 0

    if args.dry_run and not args.mode:
        outputs = backend.list_outputs()
        active = backend.get_current_mode()
        print(f"current mode: {active.value if active else 'unknown'}")
        for m in DisplayMode:
            try:
                plan = backend.plan(Selection(m, args.output, POSITION_ALIASES[args.position]))
            except Exception as exc:  # noqa: BLE001
                plan = [f"# {m.value}: {exc}"]
            print(f"\n[{MODE_LABELS[m]} ({m.value})]")
            _print_plan(plan)
        return 0

    if args.mode:
        selection = _selection_from_args(args)
        if args.dry_run:
            _print_plan(backend.plan(selection))
            return 0
        snapshot = None
        if args.confirm:
            try:
                snapshot = backend.snapshot()
            except Exception:
                pass
        result = backend.apply(selection)
        for w in result.warnings:
            print(f"warning: {w}")
        if not result.ok:
            print(f"error: {result.error}", file=sys.stderr)
            notify("Project Menu", f"Failed to apply: {result.error}", urgent=True)
            return 1
        print(f"applied mode '{selection.mode.value}'")
        for c in result.commands:
            print(f"  {c}")
        if args.confirm and snapshot is not None:
            import select
            print(f"Keep changes? (Y/n) [auto-reverting in {args.timeout}s]: ", end="", flush=True)
            r, _, _ = select.select([sys.stdin], [], [], args.timeout)
            if r:
                ans = sys.stdin.readline().strip().lower()
                if ans.startswith("n"):
                    print("Reverting changes...")
                    backend.restore(snapshot)
                    print("Reverted.")
                    return 0
                print("Changes kept.")
            else:
                print(f"\nTimed out after {args.timeout}s. Reverting changes...")
                backend.restore(snapshot)
                print("Reverted.")
                return 0
        return 0

    # -- interactive popup -------------------------------------------------
    from ui import get_ui
    ui_cls = get_ui()
    if ui_cls is None:
        print("No GUI toolkit available. Install python3-gi (GTK) or PyQt/PySide, "
              "or use `project-menu --mode ...` / `--list`.", file=sys.stderr)
        return 1

    outputs = backend.list_outputs()
    options, note = core.build_options(outputs)
    active = backend.get_current_mode()
    context = UIContext(
        backend=backend,
        options=options,
        active_mode=active,
        targets=[o for o in outputs if o.connected],
        note=note,
        env=env,
    )
    ui_cls().run(context)
    return 0


def _run_hotkey(env, args) -> int:
    registrar = hotkey_registry.select(env, append_config=args.append_config)
    if registrar is None:
        print("No automatic hotkey registration for this environment.")
        print("Register Super+P manually to run:", args.hotkey_command)
        return 1
    if args.unregister_hotkey:
        actions = registrar.unregister()
    else:
        actions = registrar.register(args.hotkey_command)
    for a in actions:
        print(a)
    return 0


def _detach() -> None:
    """Re-launch in a background session so no console window stays attached.

    Double-fork + detach from the controlling terminal, then point the std
    streams at /dev/null. The parent returns to the shell immediately while
    the popup keeps running as an orphan owned by init.
    """
    try:
        if os.fork() > 0:
            os._exit(0)  # parent: hand control back to the shell right away
        os.setsid()
        if os.fork() > 0:
            os._exit(0)  # intermediate: not a session leader anymore
    except OSError:
        return  # forking failed; just keep running in the foreground
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(devnull, fd)
    if devnull > 2:
        os.close(devnull)


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    popup_launch = not (args.list or args.mode or args.dry_run or args.register_hotkey
                        or args.unregister_hotkey or args.hotkey_daemon)
    if popup_launch and not args.foreground and not args.debug:
        _detach()
    try:
        return run(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        core.setup_logging()
        core.log().exception("unhandled error")
        print(f"error: {exc}", file=sys.stderr)
        notify("Project Menu", f"Error: {exc}", urgent=True)
        return 1
