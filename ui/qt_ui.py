"""Qt popup UI — fallback used only when GTK is unavailable.

Implements the same four-button selector and 15-second "Keep changes?"
confirmation, with single-instance via ``QLocalServer``/``QLocalSocket``.
"""

from __future__ import annotations

import sys

from interfaces import DisplayMode, ExtendPosition, MODE_LABELS, PopupUI, Selection, UIContext

try:
    from PyQt6 import QtCore, QtGui, QtNetwork, QtWidgets
except ImportError:
    try:
        from PySide6 import QtCore, QtGui, QtNetwork, QtWidgets
    except ImportError:
        try:
            from PyQt5 import QtCore, QtGui, QtNetwork, QtWidgets
        except ImportError:
            from PySide2 import QtCore, QtGui, QtNetwork, QtWidgets

from core import notify

SOCKET_NAME = "projectmenu-single-instance"
POSITION_LABELS = {
    ExtendPosition.RIGHT: "Right",
    ExtendPosition.LEFT: "Left",
    ExtendPosition.ABOVE: "Above",
    ExtendPosition.BELOW: "Below",
}


class QtPopupUI(PopupUI):
    def run(self, context: UIContext):
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        app.setApplicationName("project-menu")

        # Single instance: if a primary exists, ask it to cycle and exit.
        probe = QtNetwork.QLocalSocket()
        probe.connectToServer(SOCKET_NAME)
        if probe.waitForConnected(200):
            probe.write(b"cycle")
            probe.flush()
            probe.waitForBytesWritten(200)
            probe.disconnectFromServer()
            return None

        server = QtNetwork.QLocalServer()
        server.listen(SOCKET_NAME)
        win = _QtPopup(context)
        server.newConnection.connect(lambda: win._read_cycle(server))
        app.exec_()
        return win.result


QT_APPLE_QSS = """
QWidget#AppleCard {
    background-color: rgba(30, 30, 34, 0.94);
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 18px;
}
QLabel#AppleTitle {
    color: #ffffff;
    font-size: 13px;
    font-weight: bold;
    letter-spacing: -0.2px;
}
QLabel#AppleSubtitle {
    color: rgba(255, 255, 255, 0.6);
    font-size: 11px;
}
QLabel#AppleFooter {
    color: rgba(255, 255, 255, 0.45);
    font-size: 10px;
}
QPushButton.mode-btn {
    background-color: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 8px 12px;
    text-align: left;
    color: #ffffff;
    font-size: 13px;
    font-weight: 500;
}
QPushButton.mode-btn:hover {
    background-color: rgba(255, 255, 255, 0.1);
    border-color: rgba(255, 255, 255, 0.16);
}
QPushButton.mode-btn:focus {
    background-color: rgba(0, 122, 255, 0.22);
    border: 1.5px solid #007aff;
}
QPushButton.mode-btn:disabled {
    color: rgba(255, 255, 255, 0.25);
    background-color: rgba(255, 255, 255, 0.02);
    border-color: rgba(255, 255, 255, 0.03);
}
QPushButton#KeepBtn {
    background-color: #007aff;
    color: #ffffff;
    font-weight: bold;
    border-radius: 8px;
    padding: 8px 20px;
    border: none;
}
QPushButton#RevertBtn {
    background-color: rgba(255, 255, 255, 0.08);
    color: #ffffff;
    border-radius: 8px;
    padding: 8px 16px;
    border: 1px solid rgba(255, 255, 255, 0.15);
}
"""

MODE_SUBTITLES = {
    DisplayMode.INTERNAL: "Use built-in display only",
    DisplayMode.DUPLICATE: "Mirror content on both displays",
    DisplayMode.EXTEND: "Expand desktop to the side",
    DisplayMode.EXTERNAL: "Use external display only",
}


class _QtPopup(QtWidgets.QWidget):
    def __init__(self, context: UIContext):
        super().__init__()
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet(QT_APPLE_QSS)
        self.ctx = context
        self.result: Selection | None = None
        self.outputs = context.backend.list_outputs()
        self.index = 0
        self._busy = False
        self._build()
        self._center()
        self.show()

    def focusOutEvent(self, event):
        if not self._busy and self.isVisible():
            self._cancel()
        super().focusOutEvent(event)

    def _build(self):
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)

        card = QtWidgets.QFrame()
        card.setObjectName("AppleCard")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(6)

        # Header
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Displays")
        title.setObjectName("AppleTitle")
        header.addWidget(title)
        header.addStretch()

        connected_count = len([o for o in self.outputs if o.connected])
        sub_text = self.ctx.note or (f"{connected_count} Displays" if connected_count > 1 else "1 Display")
        subtitle = QtWidgets.QLabel(sub_text)
        subtitle.setObjectName("AppleSubtitle")
        header.addWidget(subtitle)
        card_layout.addLayout(header)

        # Mode buttons
        self.buttons = []
        for i, (mode, enabled) in enumerate(self.ctx.options):
            mode_name = MODE_LABELS[mode]
            desc = MODE_SUBTITLES.get(mode, "")
            is_active = (self.ctx.active_mode == mode)
            active_mark = "  ✓ Active" if is_active else ""
            btn_text = f"[{i + 1}]  {mode_name}{active_mark}\n      {desc}"
            btn = QtWidgets.QPushButton(btn_text)
            btn.setProperty("class", "mode-btn")
            btn.setEnabled(enabled)
            btn.clicked.connect(lambda _checked, m=mode: self._select_mode(m))
            card_layout.addWidget(btn)
            self.buttons.append(btn)

        # Footer
        footer = QtWidgets.QLabel("↑ / ↓ to move  •  Enter to apply  •  Esc to close")
        footer.setObjectName("AppleFooter")
        footer.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(footer)

        root_layout.addWidget(card)
        self.setLayout(root_layout)
        self._install_shortcuts()

    def _install_shortcuts(self):
        def sc(key, fn):
            s = QtWidgets.QShortcut(QtGui.QKeySequence(key), self)
            s.activated.connect(fn)

        sc(QtCore.Qt.Key_Up, lambda: self._move(-1))
        sc(QtCore.Qt.Key_Down, lambda: self._move(1))
        sc(QtCore.Qt.Key_Tab, lambda: self._move(1))
        sc(QtCore.Qt.Key_Return, self._select)
        sc(QtCore.Qt.Key_Enter, self._select)
        sc(QtCore.Qt.Key_Escape, self._cancel)
        for n in range(1, 5):
            sc(str(n), lambda n=n: self._select_index(n - 1))

    def _center(self):
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.geometry()
        self.adjustSize()
        self.move(geo.x() + (geo.width() - self.width()) // 2,
                  geo.y() + (geo.height() - self.height()) // 2)

    def _read_cycle(self, server):
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.readAll()
        if self.isVisible():
            self._move(1)
        else:
            self.show()

    def _move(self, delta):
        n = len(self.buttons)
        self.index = (self.index + delta) % n
        steps = 0
        while not self.buttons[self.index].isEnabled() and steps < n:
            self.index = (self.index + delta) % n
            steps += 1
        self.buttons[self.index].setFocus()

    def _select_index(self, idx):
        if 0 <= idx < len(self.buttons) and self.buttons[idx].isEnabled():
            self.index = idx
            self._select()

    def _select(self):
        if self.buttons and self.buttons[self.index].isEnabled():
            self._select_mode(list(self.ctx.options)[self.index][0])

    def _select_mode(self, mode: DisplayMode):
        if self._busy:
            return
        self._busy = True
        self.hide()
        self._resolve_selection(mode)

    def _resolve_selection(self, mode: DisplayMode):
        connected = [o for o in self.outputs if o.connected]
        n = len(connected)
        needs_target = mode in (DisplayMode.DUPLICATE, DisplayMode.EXTEND, DisplayMode.EXTERNAL) and n > 2
        needs_pos = mode == DisplayMode.EXTEND
        target = None
        position = ExtendPosition.RIGHT
        if needs_target:
            target = self._choose_target()
            if target is None:
                self._cancel()
                return
        if needs_pos:
            position = self._choose_position()
            if position is None:
                self._cancel()
                return
        self._apply_and_confirm(Selection(mode, target, position))

    def _choose_target(self):
        from core import primary_output
        prim = primary_output(self.outputs)
        prim_name = prim.name if prim else None
        candidates = [o.name for o in self.outputs if o.connected and o.name != prim_name]
        if not candidates:
            candidates = [o.name for o in self.outputs if o.connected]
        return self._simple_choice("Choose the second display", candidates)

    def _choose_position(self):
        value = self._simple_choice("Extend position", [p.value for p in ExtendPosition])
        return ExtendPosition(value) if value else None

    def _simple_choice(self, title, options):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(title)
        layout = QtWidgets.QVBoxLayout(dialog)
        holder = {"value": None}
        for value in options:
            btn = QtWidgets.QPushButton(str(value))
            btn.clicked.connect(lambda _c, v=value: self._choose_value(dialog, holder, v))
            layout.addWidget(btn)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(dialog.reject)
        layout.addWidget(cancel)
        dialog.exec_()
        return holder["value"]

    @staticmethod
    def _choose_value(dialog, holder, value):
        holder["value"] = value
        dialog.accept()

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
        keep = self._confirm(result.warnings)
        if not keep and snapshot is not None:
            backend.restore(snapshot)
        self.result = selection
        self._quit()

    def _confirm(self, warnings) -> bool:
        msg = "Keep this display configuration?"
        if warnings:
            msg += "\n\n⚠ " + "\n⚠ ".join(warnings)
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Keep Changes?")
        dialog.setStyleSheet(QT_APPLE_QSS)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        lbl = QtWidgets.QLabel(msg)
        lbl.setObjectName("AppleTitle")
        lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)

        state = {"seconds": 15, "keep": False}
        counter = QtWidgets.QLabel()
        counter.setObjectName("AppleSubtitle")
        counter.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(counter)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(12)
        revert_btn = QtWidgets.QPushButton("Revert")
        revert_btn.setObjectName("RevertBtn")
        keep_btn = QtWidgets.QPushButton("Keep Changes")
        keep_btn.setObjectName("KeepBtn")
        row.addWidget(revert_btn)
        row.addWidget(keep_btn)
        layout.addLayout(row)

        def finish(keep):
            state["keep"] = keep
            dialog.accept()

        keep_btn.clicked.connect(lambda: finish(True))
        revert_btn.clicked.connect(lambda: finish(False))

        def tick():
            state["seconds"] -= 1
            if state["seconds"] <= 0:
                finish(False)
            else:
                counter.setText(f"Reverting automatically in {state['seconds']}s…")

        timer = QtCore.QTimer(dialog)
        timer.timeout.connect(tick)
        timer.start(1000)
        counter.setText(f"Reverting automatically in {state['seconds']}s…")
        dialog.exec_()
        timer.stop()
        return state["keep"]

    def _cancel(self):
        self.result = None
        self._quit()

    def _quit(self):
        QtWidgets.QApplication.instance().quit()
