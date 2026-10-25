"""GTK popup UI (GTK3 or GTK4), deliberately minimal.

A flat, borderless list of four text rows — no icons, no header, no footer.
The active mode is marked with a small dot; the row under the cursor is
highlighted.

Single instance is provided by :class:`Gtk.Application` (a subclass of
Gio.Application): a second ``project-menu`` launch signals the running
instance, which then cycles to the next option.

Overlay behaviour:

* X11 -> borderless, always-on-top, centered on the active monitor.
* Wayland + layer-shell (KDE, Sway, Hyprland, wlroots, COSMIC) -> true overlay.
* GNOME Wayland (no layer-shell) -> normal focused window, no positioning.
"""

from __future__ import annotations

import gi  # noqa: WPS433

try:
    gi.require_version("Gtk", "3.0")
    GTK_MAJOR = 3
except ValueError:
    gi.require_version("Gtk", "4.0")
    GTK_MAJOR = 4

from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from core import APP_ID, notify  # noqa: E402
from interfaces import ExtendPosition, MODE_LABELS, PopupUI, Selection, UIContext  # noqa: E402
from interfaces import DisplayMode  # noqa: E402
from ui.base import has_layer_shell  # noqa: E402

POSITION_LABELS = {
    ExtendPosition.RIGHT: "Right",
    ExtendPosition.LEFT: "Left",
    ExtendPosition.ABOVE: "Above",
    ExtendPosition.BELOW: "Below",
}

_WINDOW_W = 280
_WINDOW_H = 220


def _apply_css():
    css = b"""
    window.project-window { background-color: transparent; }
    .card {
        background-color: alpha(@theme_bg_color, 0.9);
        color: @theme_fg_color;
        border: 1px solid alpha(@theme_fg_color, 0.14);
        border-radius: 10px;
        padding: 4px;
    }
    .row {
        background-color: alpha(@theme_fg_color, 0.03);
        background-image: none;
        color: @theme_fg_color;
        border: none;
        border-radius: 7px;
        padding: 9px 12px;
        font-weight: 500;
    }
    .row:hover, .row:focus, .row.selected {
        background-color: alpha(@theme_fg_color, 0.11);
        background-image: none;
    }
    .row:disabled { color: alpha(@theme_fg_color, 0.35); }
    .row.suggested-action {
        background-color: alpha(@theme_fg_color, 0.11);
        background-image: none;
        border: none;
        box-shadow: none;
        outline: none;
    }
    .quiet { font-size: 10px; opacity: 0.5; }
    """
    try:
        provider = Gtk.CssProvider()
        if GTK_MAJOR == 3:
            provider.load_from_data(css)
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(),
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
        else:
            provider.load_from_data(css.decode("utf-8"))
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
    except Exception:
        pass


def _show(widget):
    if GTK_MAJOR == 3:
        widget.show_all()
    else:
        widget.present()


def _block_close(window):
    if GTK_MAJOR == 3:
        window.connect("delete-event", lambda *_: True)
    else:
        window.connect("close-request", lambda *_: True)


class GtkPopupUI(PopupUI):
    def run(self, context: UIContext):
        app = _ProjectApp(context)
        return app.run_ui()


class _ProjectApp(Gtk.Application):
    def __init__(self, context: UIContext):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.ctx = context
        self.window: Gtk.Window | None = None
        self.buttons: list[tuple[Gtk.Button, DisplayMode, bool]] = []
        self.index = 0
        self.result: Selection | None = None
        self._busy = False

    # -- lifecycle ---------------------------------------------------------
    def do_command_line(self, command_line):
        command_line.get_arguments()
        self._launch()
        return 0

    def do_activate(self):
        self._launch()

    def _launch(self):
        if self.window is not None and self.window.get_visible():
            self._cycle()
        else:
            self._present()

    def run_ui(self):
        import sys
        self.run([sys.argv[0]])
        return self.result

    # -- window construction ----------------------------------------------
    def _present(self):
        _apply_css()
        self.outputs = self.ctx.backend.list_outputs()
        self.window = self._build_window()
        self.add_window(self.window)  # keeps the Gio.Application alive while shown
        self._build_buttons()
        if self.ctx.active_mode is not None:
            for i, (_btn, mode, en) in enumerate(self.buttons):
                if mode == self.ctx.active_mode and en:
                    self.index = i
                    break
        self._highlight()
        _show(self.window)
        self.window.present()

    def _build_window(self) -> Gtk.Window:
        env = self.ctx.env
        win = Gtk.Window(title="Project Menu")
        win.set_default_size(_WINDOW_W, -1)
        win.set_decorated(False)
        win.set_resizable(False)
        win.get_style_context().add_class("project-window")

        if GTK_MAJOR == 3:
            screen = win.get_screen()
            visual = screen.get_rgba_visual()
            if visual is not None:
                win.set_visual(visual)
            win.set_app_paintable(True)
            win.set_position(Gtk.WindowPosition.CENTER)

        use_layer_shell = (
            env is not None
            and env.session_type == "wayland"
            and not env.has_desktop("gnome", "ubuntu")
            and has_layer_shell()
        )

        if use_layer_shell:
            gi.require_version("GtkLayerShell", "0.1")
            from gi.repository import GtkLayerShell

            GtkLayerShell.init_for_window(win)
            GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
            # Unanchored layer-shell surface is automatically centered
            GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.EXCLUSIVE)
            self._connect_keys(win)
        elif env is not None and env.session_type == "x11":
            if GTK_MAJOR == 3:
                win.set_keep_above(True)
                win.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
                self._center_on_active_monitor(win)
            self._connect_keys(win)
        else:
            # GNOME Wayland / unknown: normal focused window, no positioning.
            self._connect_keys(win)

        if GTK_MAJOR == 3:
            win.connect("focus-out-event", self._on_focus_out)
        else:
            win.connect("notify::is-active", self._on_is_active)
        return win

    def _connect_keys(self, win):
        if GTK_MAJOR == 3:
            win.connect("key-press-event", self._on_key_press)
        else:
            controller = Gtk.EventControllerKey.new()
            controller.connect("key-pressed", self._on_key_pressed)
            win.add_controller(controller)

    def _center_on_active_monitor(self, win):
        display = win.get_display()
        monitor = None
        if hasattr(display, "get_default_seat"):
            seat = display.get_default_seat()
            if seat:
                pointer = seat.get_pointer()
                if pointer:
                    try:
                        _s, px, py = pointer.get_position()
                        monitor = display.get_monitor_at_point(px, py)
                    except Exception:
                        pass
        if monitor is None and hasattr(display, "get_primary_monitor"):
            monitor = display.get_primary_monitor()
        if monitor is None:
            return
        geo = monitor.get_geometry()
        scale = monitor.get_scale_factor() or 1
        win.move(
            int(geo.x + (geo.width / scale - _WINDOW_W) / 2),
            int(geo.y + (geo.height / scale - _WINDOW_H) / 2),
        )

    def _build_buttons(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        card.get_style_context().add_class("card")

        self.buttons = []
        for mode, enabled in self.ctx.options:
            label = MODE_LABELS.get(mode, str(mode))
            if self.ctx.active_mode == mode:
                label = "● " + label
            btn = Gtk.Button(label=label)
            btn.set_sensitive(enabled)
            btn.get_style_context().add_class("row")
            btn.set_halign(Gtk.Align.FILL)
            if GTK_MAJOR == 3:
                child = btn.get_child()
                if isinstance(child, Gtk.Label):
                    child.set_xalign(0.0)
            btn.connect("clicked", self._on_click, mode)
            card.pack_start(btn, True, True, 0)
            self.buttons.append((btn, mode, enabled))

        self.window.add(card)

    # -- keyboard ----------------------------------------------------------
    def _on_key_press(self, _widget, event):
        key = event.keyval
        if key in (Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Tab):
            delta = -1 if key == Gdk.KEY_Up else 1
            if key == Gdk.KEY_Tab and (event.state & Gdk.ModifierType.SHIFT_MASK):
                delta = -1
            self._move(delta)
            return True
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._select()
            return True
        if key == Gdk.KEY_Escape:
            self._cancel()
            return True
        for n in (1, 2, 3, 4):
            if key in (getattr(Gdk, f"KEY_{n}", None), getattr(Gdk, f"KEY_KP_{n}", None)):
                self._select_index(n - 1)
                return True
        return False

    def _on_key_pressed(self, _controller, keyval, _keycode, state):
        if keyval in (Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Tab):
            delta = -1 if keyval == Gdk.KEY_Up else 1
            if keyval == Gdk.KEY_Tab and (state & Gdk.ModifierType.SHIFT_MASK):
                delta = -1
            self._move(delta)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._select()
            return True
        if keyval == Gdk.KEY_Escape:
            self._cancel()
            return True
        for n in (1, 2, 3, 4):
            if keyval in (getattr(Gdk, f"KEY_{n}", None), getattr(Gdk, f"KEY_KP_{n}", None)):
                self._select_index(n - 1)
                return True
        return False

    def _on_focus_out(self, _widget, _event):
        if not self._busy and self.window is not None and self.window.get_visible():
            self._cancel()
        return False

    def _on_is_active(self, widget, _param):
        if not self._busy and self.window is not None and self.window.get_visible() and not widget.get_property("is-active"):
            self._cancel()

    def _move(self, delta):
        if not self.buttons:
            return
        n = len(self.buttons)
        self.index = (self.index + delta) % n
        steps = 0
        while not self.buttons[self.index][2] and steps < n:
            self.index = (self.index + delta) % n
            steps += 1
        self._highlight()

    def _highlight(self):
        for i, (btn, _mode, _en) in enumerate(self.buttons):
            style = btn.get_style_context()
            if i == self.index:
                style.add_class("suggested-action")
                btn.grab_focus()
            else:
                style.remove_class("suggested-action")

    def _cycle(self):
        self._move(1)

    # -- selection ---------------------------------------------------------
    def _on_click(self, _btn, mode: DisplayMode):
        self._select_mode(mode)

    def _select_index(self, idx):
        if 0 <= idx < len(self.buttons) and self.buttons[idx][2]:
            self.index = idx
            self._select()

    def _select(self):
        if self.buttons and self.buttons[self.index][2]:
            self._select_mode(self.buttons[self.index][1])

    def _select_mode(self, mode: DisplayMode):
        if self._busy:
            return
        self._busy = True
        self._hide()

        def done(selection):
            if selection is None:
                self._cancel()
                return
            self._apply_and_confirm(selection)

        self._resolve_selection(mode, done)

    def _resolve_selection(self, mode: DisplayMode, callback):
        connected = [o for o in self.outputs if o.connected]
        n = len(connected)
        needs_target = mode in (DisplayMode.DUPLICATE, DisplayMode.EXTEND, DisplayMode.EXTERNAL) and n > 2
        needs_pos = mode == DisplayMode.EXTEND

        def finish(target):
            if needs_pos:
                self._choose_position(lambda p: callback(Selection(mode, target, p) if p else None))
            else:
                callback(Selection(mode, target, ExtendPosition.RIGHT))

        if needs_target:
            self._choose_target(finish)
        elif needs_pos:
            self._choose_position(lambda p: callback(Selection(mode, None, p) if p else None))
        else:
            callback(Selection(mode, None, ExtendPosition.RIGHT))

    def _choose_target(self, callback):
        from core import primary_output
        prim = primary_output(self.outputs)
        prim_name = prim.name if prim else None
        candidates = [o.name for o in self.outputs if o.connected and o.name != prim_name]
        if not candidates:
            candidates = [o.name for o in self.outputs if o.connected]
        self._simple_choice("Second display", [(nm, nm) for nm in candidates], callback)

    def _choose_position(self, callback):
        self._simple_choice(
            "Extend position",
            [(p, POSITION_LABELS[p]) for p in ExtendPosition],
            callback,
        )

    def _simple_choice(self, title: str, options, callback):
        dialog = Gtk.Dialog(title=title)
        dialog.set_modal(True)
        if self.window:
            dialog.set_transient_for(self.window)
        _block_close(dialog)
        content = dialog.get_content_area()
        content.set_spacing(2)
        content.get_style_context().add_class("card")
        lbl = Gtk.Label(label=title)
        lbl.get_style_context().add_class("quiet")
        content.pack_start(lbl, False, False, 4)

        for value, label in options:
            btn = Gtk.Button(label=str(label))
            btn.get_style_context().add_class("row")
            if GTK_MAJOR == 3:
                child = btn.get_child()
                if isinstance(child, Gtk.Label):
                    child.set_xalign(0.0)
            btn.connect("clicked", lambda _w, v=value: (dialog.destroy(), callback(v)))
            content.pack_start(btn, True, True, 0)

        cancel = Gtk.Button(label="Cancel")
        cancel.get_style_context().add_class("row")
        cancel.connect("clicked", lambda _w: (dialog.destroy(), callback(None)))
        content.pack_start(cancel, True, True, 2)
        _show(dialog)

    # -- apply + confirm ---------------------------------------------------
    def _apply_and_confirm(self, selection: Selection):
        backend = self.ctx.backend
        try:
            snapshot = backend.snapshot()
        except Exception:
            snapshot = None
        result = backend.apply(selection)
        if not result.ok:
            notify("Project Menu", f"Failed to apply: {result.error or 'unknown error'}", urgent=True)
            self._cancel()
            return

        def confirmed(keep):
            if not keep and snapshot is not None:
                backend.restore(snapshot)
            self.result = selection
            self._quit()

        self._confirm(result.warnings, confirmed)

    def _confirm(self, warnings, callback):
        dialog = Gtk.Dialog(title="Keep Changes?")
        dialog.set_modal(True)
        if self.window:
            dialog.set_transient_for(self.window)
        _block_close(dialog)
        content = dialog.get_content_area()
        content.set_spacing(2)
        content.get_style_context().add_class("card")

        lbl = Gtk.Label(label="Keep this display configuration?")
        content.pack_start(lbl, False, False, 6)
        for w in warnings:
            warn = Gtk.Label(label=w)
            warn.get_style_context().add_class("quiet")
            warn.set_line_wrap(True)
            content.pack_start(warn, False, False, 2)

        state = {"seconds": 15, "done": False}
        counter = Gtk.Label()
        counter.get_style_context().add_class("quiet")
        content.pack_start(counter, False, False, 4)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        revert_btn = Gtk.Button(label="Revert")
        keep_btn = Gtk.Button(label="Keep")
        revert_btn.get_style_context().add_class("row")
        keep_btn.get_style_context().add_class("row")
        box.pack_start(revert_btn, True, True, 0)
        box.pack_start(keep_btn, True, True, 0)
        content.pack_start(box, True, True, 2)

        def finish(keep):
            if state["done"]:
                return
            state["done"] = True
            dialog.destroy()
            callback(keep)

        keep_btn.connect("clicked", lambda _w: finish(True))
        revert_btn.connect("clicked", lambda _w: finish(False))

        def tick():
            if state["done"]:
                return False
            state["seconds"] -= 1
            if state["seconds"] <= 0:
                finish(False)
                return False
            counter.set_text(f"Reverting in {state['seconds']}s")
            return True

        counter.set_text(f"Reverting in {state['seconds']}s")
        GLib.timeout_add_seconds(1, tick)
        _show(dialog)

    # -- teardown ----------------------------------------------------------
    def _hide(self):
        if self.window:
            self.window.hide()

    def _cancel(self):
        self.result = None
        self._quit()

    def _quit(self):
        if self.window:
            self.window.destroy()
        self.quit()
