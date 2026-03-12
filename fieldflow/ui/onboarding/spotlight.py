from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, QTimer, QRect, QPoint, Qt
from PySide6.QtWidgets import QWidget, QFrame


class Spotlight(QObject):
    """
    Simple "spotlight" overlay that draws a rectangle around a target widget.

    - No QtWebEngine
    - No external libs
    - Works across different pages by anchoring to the main window (host)

    Usage:
        s = Spotlight(host_window)
        s.flash(target_widget)
    """

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.host = host
        self._frame: Optional[QFrame] = None

    def flash(self, target: QWidget, *, ms: int = 1200, pad: int = 6) -> None:
        if target is None or not isinstance(target, QWidget):
            return
        if not target.isVisible():
            # Try to show anyway after a short delay (page switch/layout)
            QTimer.singleShot(120, lambda: self.flash(target, ms=ms, pad=pad))
            return

        frame = self._ensure_frame()
        rect = self._target_rect_in_host(target, pad=pad)
        if rect is None:
            return

        frame.setGeometry(rect)
        frame.show()
        frame.raise_()

        # Hide after a bit
        QTimer.singleShot(ms, self.hide)

    def hide(self) -> None:
        if self._frame is not None:
            self._frame.hide()

    def _ensure_frame(self) -> QFrame:
        if self._frame is not None:
            return self._frame

        f = QFrame(self.host)
        f.setObjectName("fieldflow_spotlight")
        f.setFrameShape(QFrame.Box)
        f.setFrameShadow(QFrame.Plain)
        # bright border + slight translucent fill
        f.setStyleSheet(
            "QFrame#fieldflow_spotlight {"
            "  border: 3px solid #ffcc00;"
            "  border-radius: 8px;"
            "  background: rgba(255, 204, 0, 35);"
            "}"
        )
        f.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        f.hide()
        self._frame = f
        return f

    def _target_rect_in_host(self, target: QWidget, *, pad: int) -> Optional[QRect]:
        try:
            top_left_global = target.mapToGlobal(QPoint(0, 0))
            top_left_host = self.host.mapFromGlobal(top_left_global)
            r = QRect(top_left_host, target.size())
            r.adjust(-pad, -pad, pad, pad)
            # clamp to host rect (avoid negative/huge)
            hr = self.host.rect()
            return r.intersected(hr)
        except Exception:
            return None