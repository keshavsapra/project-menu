"""GTK popup UI (GTK3 or GTK4).

Single instance is provided by :class:`Gtk.Application` (a subclass of
Gio.Application): a second ``project-menu`` launch signals the running instance,
which then cycles to the next option.

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
from interfaces import DisplayMode, ExtendPosition, MODE_LABELS, PopupUI, Selection, UIContext  # noqa: E402
from ui.base import ICON_NAMES, has_layer_shell  # noqa: E402

POSITION_LABELS = {
    ExtendPosition.RIGHT: "Right",
    ExtendPosition.LEFT: "Left",
    ExtendPosition.ABOVE: "Above",
    ExtendPosition.BELOW: "Below",
}


MODE_CONFIG = {
    DisplayMode.INTERNAL: {
        "title": "PC Screen Only",
        "subtitle": "Use built-in display only",
        "icon": "computer",
        "gradient_class": "icon-internal",
    },
    DisplayMode.DUPLICATE: {
        "title": "Duplicate",
        "subtitle": "Mirror content on both displays",
        "icon": "video-display",
        "gradient_class": "icon-duplicate",
    },
    DisplayMode.EXTEND: {
        "title": "Extend",
        "subtitle": "Expand desktop to the side",
        "icon": "video-x-generic",
        "gradient_class": "icon-extend",
    },
    DisplayMode.EXTERNAL: {
        "title": "Second Screen Only",
        "subtitle": "Use external display only",
        "icon": "video-display",
        "gradient_class": "icon-external",
    },
}


def _icon(name: str, size: int = 24):
    if GTK_MAJOR == 3:
        img = Gtk.Image.new_from_icon_name(name, Gtk.IconSize.DND)
        img.set_pixel_size(size)
        return img
    img = Gtk.Image.new_from_icon_name(name)
    img.set_pixel_size(size)
    return img


def _apply_css():
    css_data = b"""
    window.project-window {
        background-color: transparent;
    }
    .apple-card {
        background-color: alpha(@theme_bg_color, 0.94);
        color: @theme_fg_color;
        border: 1px solid alpha(@theme_fg_color, 0.16);
        border-radius: 18px;
        box-shadow: 0 20px 48px rgba(0, 0, 0, 0.4), 0 2px 8px rgba(0, 0, 0, 0.15);
    }
    .apple-header {
        padding-bottom: 8px;
        border-bottom: 1px solid alpha(@theme_fg_color, 0.08);
        margin-bottom: 4px;
    }
    .apple-title {
        font-size: 13px;
        font-weight: 700;
        letter-spacing: -0.2px;
    }
    .apple-subtitle {
        font-size: 11px;
        opacity: 0.6;
    }
    .apple-footer {
        font-size: 10px;
        opacity: 0.45;
        margin-top: 6px;
    }
    .mode-row {
        background-color: alpha(@theme_fg_color, 0.04);
        border: 1px solid alpha(@theme_fg_color, 0.07);
        border-radius: 12px;
        padding: 6px 10px;
        margin: 2px 0;
        transition: all 140ms ease-in-out;
    }
    .mode-row:hover {
        background-color: alpha(@theme_fg_color, 0.09);
        border-color: alpha(@theme_fg_color, 0.14);
    }
    .mode-row:focus, .mode-row.suggested-action {
        background-color: alpha(#007aff, 0.18);
        border: 1.5px solid #007aff;
        box-shadow: 0 0 0 2px alpha(#007aff, 0.3);
    }
    .mode-row.active-mode {
        border-color: alpha(#007aff, 0.55);
    }
    .mode-title {
        font-size: 13px;
        font-weight: 600;
        letter-spacing: -0.15px;
    }
    .mode-subtitle {
        font-size: 11px;
        opacity: 0.58;
    }
    .icon-squircle {
        min-width: 40px;
        min-height: 40px;
        border-radius: 10px;
        color: #ffffff;
    }
    .icon-internal {
        background-image: linear-gradient(135deg, #788494, #4e5866);
    }
    .icon-duplicate {
        background-image: linear-gradient(135deg, #0a84ff, #0062cc);
    }
    .icon-extend {
        background-image: linear-gradient(135deg, #5e5ce6, #3634a3);
    }
    .icon-external {
        background-image: linear-gradient(135deg, #30b0c7, #007a99);
    }
    .keycap {
        font-family: ui-monospace, "SF Mono", "Ubuntu Mono", monospace;
        font-size: 11px;
        font-weight: 700;
        padding: 3px 7px;
        border-radius: 6px;
        background-color: alpha(@theme_fg_color, 0.08);
        border: 1px solid alpha(@theme_fg_color, 0.18);
        color: alpha(@theme_fg_color, 0.75);
    }
    .active-pill {
        font-size: 11px;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 10px;
        background-color: alpha(#007aff, 0.18);
        color: #007aff;
        border: 1px solid alpha(#007aff, 0.4);
    }
    .confirm-card {
        background-color: alpha(@theme_bg_color, 0.95);
        color: @theme_fg_color;
        border-radius: 18px;
        border: 1px solid alpha(@theme_fg_color, 0.16);
    }
    .btn-keep {
        background-image: linear-gradient(180deg, #0a84ff, #007aff);
        color: #ffffff;
        font-weight: 600;
        border-radius: 8px;
        padding: 8px 22px;
        border: none;
    }
    .btn-revert {
        background-color: alpha(@theme_fg_color, 0.08);
        color: @theme_fg_color;
        border-radius: 8px;
        padding: 8px 18px;
        border: 1px solid alpha(@theme_fg_color, 0.14);
    }
    .btn-choice {
        background-color: alpha(@theme_fg_color, 0.05);
        border: 1px solid alpha(@theme_fg_color, 0.1);
        border-radius: 10px;
        padding: 10px 16px;
        font-weight: 500;
    }
    .btn-choice:hover, .btn-choice:focus {
        background-color: alpha(#007aff, 0.18);
        border-color: #007aff;
    }
    """
    try:
        provider = Gtk.CssProvider()
        if GTK_MAJOR == 3:
            provider.load_from_data(css_data)
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(),
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
        else:
            provider.load_from_data(css_data.decode("utf-8"))
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
        # Set initial focus to active mode if available
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
        win.set_default_size(360, -1)
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
            # GNOME Wayland / unknown: normal focused window, no positioning/always-on-top.
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
        w = 360
        h = 320
        win.move(
            int(geo.x + (geo.width - w) / 2),
            int(geo.y + (geo.height - h) / 2),
        )

    def _build_buttons(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.get_style_context().add_class("apple-card")
        card.set_margin_top(8)
        card.set_margin_bottom(8)
        card.set_margin_start(8)
        card.set_margin_end(8)

        # Apple Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.get_style_context().add_class("apple-header")
        header.set_margin_start(6)
        header.set_margin_end(6)
        header.set_margin_top(4)

        hdr_icon = _icon("video-display", 16)
        header.pack_start(hdr_icon, False, False, 0)

        hdr_title = Gtk.Label(label="Displays")
        hdr_title.get_style_context().add_class("apple-title")
        hdr_title.set_xalign(0.0)
        header.pack_start(hdr_title, False, False, 0)

        connected_count = len([o for o in self.outputs if o.connected])
        sub_text = self.ctx.note or (f"{connected_count} Displays" if connected_count > 1 else "1 Display")
        hdr_sub = Gtk.Label(label=sub_text)
        hdr_sub.get_style_context().add_class("apple-subtitle")
        header.pack_end(hdr_sub, False, False, 0)

        card.pack_start(header, False, False, 4)

        self.buttons = []
        for i, (mode, enabled) in enumerate(self.ctx.options):
            btn = self._make_button(mode, enabled, i + 1)
            btn.connect("clicked", self._on_click, mode)
            card.pack_start(btn, True, True, 2)
            self.buttons.append((btn, mode, enabled))

        footer = Gtk.Label(label="↑ / ↓ to navigate  •  Enter to apply  •  Esc to close")
        footer.get_style_context().add_class("apple-footer")
        card.pack_start(footer, False, False, 4)

        self.window.add(card)

    def _make_button(self, mode: DisplayMode, enabled: bool, shortcut_num: int) -> Gtk.Button:
        cfg = MODE_CONFIG.get(mode, {
            "title": MODE_LABELS.get(mode, str(mode)),
            "subtitle": "",
            "icon": "video-display",
            "gradient_class": "icon-duplicate",
        })

        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hb.set_margin_top(4)
        hb.set_margin_bottom(4)
        hb.set_margin_start(4)
        hb.set_margin_end(4)

        # Icon squircle tile
        squircle = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        squircle.get_style_context().add_class("icon-squircle")
        squircle.get_style_context().add_class(cfg["gradient_class"])
        squircle.set_valign(Gtk.Align.CENTER)
        icon_img = _icon(cfg["icon"], 20)
        squircle.pack_start(icon_img, True, True, 0)
        hb.pack_start(squircle, False, False, 0)

        # Text stack: Title & Subtitle
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vb.set_valign(Gtk.Align.CENTER)
        title_lbl = Gtk.Label(label=cfg["title"])
        title_lbl.set_xalign(0.0)
        title_lbl.get_style_context().add_class("mode-title")
        vb.pack_start(title_lbl, False, False, 0)

        sub_lbl = Gtk.Label(label=cfg["subtitle"])
        sub_lbl.set_xalign(0.0)
        sub_lbl.get_style_context().add_class("mode-subtitle")
        vb.pack_start(sub_lbl, False, False, 0)

        hb.pack_start(vb, True, True, 0)

        # Right accessories
        right_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        right_box.set_valign(Gtk.Align.CENTER)

        if self.ctx.active_mode == mode:
            active_pill = Gtk.Label(label="✓ Active")
            active_pill.get_style_context().add_class("active-pill")
            right_box.pack_start(active_pill, False, False, 0)

        keycap = Gtk.Label(label=str(shortcut_num))
        keycap.get_style_context().add_class("keycap")
        right_box.pack_start(keycap, False, False, 0)

        hb.pack_end(right_box, False, False, 0)

        btn = Gtk.Button()
        btn.add(hb)
        btn.set_sensitive(enabled)
        btn.get_style_context().add_class("mode-row")
        if self.ctx.active_mode == mode:
            btn.get_style_context().add_class("active-mode")
        return btn

    # -- keyboard ----------------------------------------------------------
    def _on_key_press(self, _widget, event):
        from gi.repository import Gdk
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
        from gi.repository import Gdk
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
        self._simple_choice("Choose the second display", [(n, n) for n in candidates], callback)

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
        content.set_spacing(8)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.get_style_context().add_class("confirm-card")

        hdr = Gtk.Label(label=title)
        hdr.get_style_context().add_class("apple-title")
        content.pack_start(hdr, False, False, 4)

        for value, label in options:
            btn = Gtk.Button(label=str(label))
            btn.get_style_context().add_class("btn-choice")
            btn.connect("clicked", lambda _w, v=value: (dialog.destroy(), callback(v)))
            content.pack_start(btn, True, True, 2)

        cancel = Gtk.Button(label="Cancel")
        cancel.get_style_context().add_class("btn-revert")
        cancel.connect("clicked", lambda _w: (dialog.destroy(), callback(None)))
        content.pack_start(cancel, True, True, 6)
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
        msg = "Keep this display configuration?"
        dialog = Gtk.Dialog(title="Keep Changes?")
        dialog.set_modal(True)
        if self.window:
            dialog.set_transient_for(self.window)
        _block_close(dialog)
        content = dialog.get_content_area()
        content.set_spacing(10)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(18)
        content.set_margin_end(18)
        content.get_style_context().add_class("confirm-card")

        # Top alert icon
        icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        icon_box.set_halign(Gtk.Align.CENTER)
        squircle = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        squircle.get_style_context().add_class("icon-squircle")
        squircle.get_style_context().add_class("icon-duplicate")
        alert_icon = _icon("video-display", 24)
        squircle.pack_start(alert_icon, True, True, 0)
        icon_box.pack_start(squircle, False, False, 0)
        content.pack_start(icon_box, False, False, 2)

        # Alert title
        title_lbl = Gtk.Label(label=msg)
        title_lbl.get_style_context().add_class("apple-title")
        content.pack_start(title_lbl, False, False, 2)

        if warnings:
            warn_lbl = Gtk.Label(label="⚠ " + "\n⚠ ".join(warnings))
            warn_lbl.set_line_wrap(True)
            content.pack_start(warn_lbl, False, False, 2)

        state = {"seconds": 15, "done": False}
        counter = Gtk.Label()
        counter.get_style_context().add_class("apple-subtitle")
        content.pack_start(counter, False, False, 4)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)
        revert_btn = Gtk.Button(label="Revert")
        revert_btn.get_style_context().add_class("btn-revert")
        keep_btn = Gtk.Button(label="Keep Changes")
        keep_btn.get_style_context().add_class("btn-keep")

        box.pack_start(revert_btn, True, True, 0)
        box.pack_start(keep_btn, True, True, 0)
        content.pack_start(box, True, True, 6)

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
            counter.set_text(f"Reverting automatically in {state['seconds']}s…")
            return True

        counter.set_text(f"Reverting automatically in {state['seconds']}s…")
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
