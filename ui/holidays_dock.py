from __future__ import annotations

from datetime import date
from typing import Callable, Set

from PySide6.QtCore import QDate
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QCalendarWidget,
)


def _qdate_to_date(qd: QDate) -> date:
    return date(qd.year(), qd.month(), qd.day())


def _date_to_qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


class HolidaysDockWidget(QWidget):
    def __init__(
        self,
        get_holidays: Callable[[], Set[date]],
        set_holidays: Callable[[Set[date]], None],
        on_changed: Callable[[], None],
    ):
        super().__init__()
        self._get_holidays = get_holidays
        self._set_holidays = set_holidays
        self._on_changed = on_changed

        layout = QHBoxLayout(self)

        left = QVBoxLayout()
        title = QLabel("Calendar (click to toggle holiday)")
        title.setStyleSheet("font-weight: 600;")
        left.addWidget(title)

        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.clicked.connect(self._toggle)
        left.addWidget(self.calendar)

        layout.addLayout(left, 2)

        right = QVBoxLayout()
        lab = QLabel("Holidays (red)")
        lab.setStyleSheet("font-weight: 600;")
        right.addWidget(lab)

        self.list_widget = QListWidget()
        right.addWidget(self.list_widget, 1)

        btns = QHBoxLayout()
        self.btn_clear = QPushButton("Clear All")
        self.btn_clear.clicked.connect(self._clear)
        btns.addWidget(self.btn_clear)
        btns.addStretch(1)
        right.addLayout(btns)

        layout.addLayout(right, 1)

        self.refresh()

    def _holiday_format(self) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(150, 0, 0))
        fmt.setBackground(QColor(255, 230, 230))
        fmt.setFontWeight(600)
        return fmt

    def _normal_format(self) -> QTextCharFormat:
        return QTextCharFormat()

    def _toggle(self, qd: QDate) -> None:
        d = _qdate_to_date(qd)
        holidays = set(self._get_holidays())
        if d in holidays:
            holidays.remove(d)
        else:
            holidays.add(d)
        self._set_holidays(holidays)
        self.refresh()
        self._on_changed()

    def _clear(self) -> None:
        self._set_holidays(set())
        self.refresh()
        self._on_changed()

    def refresh(self) -> None:
        holidays = set(self._get_holidays())

        fmt_h = self._holiday_format()
        fmt_n = self._normal_format()

        # Cheap “reset nearby formats” to avoid tracking all formatted dates.
        cur = self.calendar.selectedDate()
        center = _qdate_to_date(cur)
        for year in range(center.year - 1, center.year + 2):
            for month in range(1, 13):
                for day in (1, 8, 15, 22, 28):
                    q = QDate(year, month, min(day, QDate(year, month, 1).daysInMonth()))
                    self.calendar.setDateTextFormat(q, fmt_n)

        for d in holidays:
            self.calendar.setDateTextFormat(_date_to_qdate(d), fmt_h)

        self.list_widget.clear()
        for d in sorted(holidays):
            item = QListWidgetItem(str(d))
            item.setForeground(QColor(150, 0, 0))
            self.list_widget.addItem(item)