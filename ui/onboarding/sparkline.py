from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QWidget


class Sparkline(QWidget):
    """
    Tiny sparkline for previewing distribution weights.
    No seaborn, offline, pure Qt paint.

    set_values([0..1]) and it draws a line.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._values: List[float] = []
        self.setMinimumHeight(18)
        self.setMinimumWidth(70)

    def sizeHint(self) -> QSize:
        return QSize(90, 18)

    def set_values(self, values: List[float]) -> None:
        self._values = [float(x) for x in (values or [])]
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._values:
            return

        vals = self._values
        n = len(vals)
        if n < 2:
            return

        vmin = min(vals)
        vmax = max(vals)
        span = (vmax - vmin) if vmax != vmin else 1.0

        w = max(1, self.width() - 4)
        h = max(1, self.height() - 4)

        def x(i: int) -> int:
            return 2 + int((i / (n - 1)) * w)

        def y(v: float) -> int:
            # invert: higher value -> higher on screen
            return 2 + int((1.0 - ((v - vmin) / span)) * h)

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        # faint baseline box
        p.setPen(QPen(QColor(180, 180, 180), 1))
        p.drawRect(1, 1, self.width() - 2, self.height() - 2)

        # sparkline
        p.setPen(QPen(QColor(60, 120, 200), 2))
        for i in range(n - 1):
            p.drawLine(x(i), y(vals[i]), x(i + 1), y(vals[i + 1]))