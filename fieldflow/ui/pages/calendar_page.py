from __future__ import annotations

from datetime import date
from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QInputDialog, QMessageBox

from fieldflow.ui.shell.app_context import AppContext
from fieldflow.ui.holidays_dock import HolidaysDockWidget


def _parse_date(s: str) -> Optional[date]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


class CalendarPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        layout = QVBoxLayout(self)

        title = QLabel("Calendar")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title)

        btns = QHBoxLayout()
        self.btn_set_start = QPushButton("Set Start Date…")
        self.btn_clear = QPushButton("Clear Holidays")
        btns.addWidget(self.btn_set_start)
        btns.addWidget(self.btn_clear)
        btns.addStretch(1)
        layout.addLayout(btns)

        self.holidays = HolidaysDockWidget(
            get_holidays=lambda: set(self.ctx.calendar.holidays),
            set_holidays=self._set_holidays,
            on_changed=self._on_changed,
        )
        layout.addWidget(self.holidays, 1)

        self.btn_set_start.clicked.connect(self._set_start_date)
        self.btn_clear.clicked.connect(lambda: self.ctx.update_calendar(holidays=set()))
        ctx.signals.calendar_changed.connect(self.refresh)

        self.refresh()

    def refresh(self) -> None:
        self.holidays.refresh()

    def _set_holidays(self, holidays: set[date]) -> None:
        self.ctx.calendar.holidays = set(holidays)

    def _on_changed(self) -> None:
        self.ctx.autosave()
        self.ctx.signals.calendar_changed.emit()

    def _set_start_date(self) -> None:
        s, ok = QInputDialog.getText(self, "Project Start Date", "Enter date (YYYY-MM-DD):", text=str(self.ctx.project_start))
        if not ok:
            return
        d = _parse_date(s)
        if d is None:
            QMessageBox.warning(self, "Invalid date", "Use YYYY-MM-DD.")
            return
        self.ctx.update_calendar(start=d)
