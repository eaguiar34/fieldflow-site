from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from PySide6.QtCore import QDate
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
    QFileDialog,
)


@dataclass
class CPMWizardResult:
    start_date: date
    holidays: set[date]
    activities_path: str
    logic_path: str


def _qdate_to_date(qd: QDate) -> date:
    return date(qd.year(), qd.month(), qd.day())


def _date_to_qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


class StartDatePage(QWizardPage):
    def __init__(self, default_start: date):
        super().__init__()
        self.setTitle("Project Start Date")
        self.setSubTitle("Pick a start date (calendar) or type YYYY-MM-DD.")

        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel("Start date:"))

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(_date_to_qdate(default_start))
        row.addWidget(self.date_edit)

        row.addStretch(1)
        layout.addLayout(row)

        hint = QLabel("Tip: You can type directly into the box, or use the calendar popup.")
        hint.setStyleSheet("color: #666;")
        layout.addWidget(hint)

    def get_start_date(self) -> date:
        return _qdate_to_date(self.date_edit.date())


class HolidaysPage(QWizardPage):
    def __init__(self, initial_holidays: set[date]):
        super().__init__()
        self.setTitle("Holidays / Exceptions")
        self.setSubTitle("Click dates to toggle holidays (non-working days). Holidays are highlighted.")

        self.holidays: set[date] = set(initial_holidays)

        layout = QHBoxLayout(self)

        cal_box = QVBoxLayout()
        cal_label = QLabel("Calendar (click to toggle holiday)")
        cal_label.setStyleSheet("font-weight: 600;")
        cal_box.addWidget(cal_label)

        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.clicked.connect(self._toggle_holiday)
        cal_box.addWidget(self.calendar)

        layout.addLayout(cal_box, 2)

        right = QVBoxLayout()
        list_label = QLabel("Holidays (red)")
        list_label.setStyleSheet("font-weight: 600;")
        right.addWidget(list_label)

        self.list_widget = QListWidget()
        right.addWidget(self.list_widget, 1)

        btns = QHBoxLayout()
        self.btn_clear = QPushButton("Clear All")
        self.btn_clear.clicked.connect(self._clear_all)
        btns.addWidget(self.btn_clear)
        btns.addStretch(1)
        right.addLayout(btns)

        layout.addLayout(right, 1)

        self._refresh_formats()
        self._refresh_list()

    def _holiday_format(self) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(150, 0, 0))
        fmt.setBackground(QColor(255, 230, 230))
        fmt.setFontWeight(600)
        return fmt

    def _normal_format(self) -> QTextCharFormat:
        return QTextCharFormat()

    def _toggle_holiday(self, qd: QDate) -> None:
        d = _qdate_to_date(qd)
        if d in self.holidays:
            self.holidays.remove(d)
        else:
            self.holidays.add(d)
        self._refresh_formats()
        self._refresh_list()

    def _clear_all(self) -> None:
        self.holidays.clear()
        self._refresh_formats()
        self._refresh_list()

    def _refresh_formats(self) -> None:
        fmt_h = self._holiday_format()
        fmt_n = self._normal_format()

        cur = self.calendar.selectedDate()
        center = _qdate_to_date(cur)

        for year in range(center.year - 1, center.year + 2):
            for month in range(1, 13):
                for day in (1, 8, 15, 22, 28):
                    q = QDate(year, month, min(day, QDate(year, month, 1).daysInMonth()))
                    self.calendar.setDateTextFormat(q, fmt_n)

        for d in self.holidays:
            self.calendar.setDateTextFormat(_date_to_qdate(d), fmt_h)

    def _refresh_list(self) -> None:
        self.list_widget.clear()
        for d in sorted(self.holidays):
            item = QListWidgetItem(str(d))
            item.setForeground(QColor(150, 0, 0))
            self.list_widget.addItem(item)

    def get_holidays(self) -> set[date]:
        return set(self.holidays)


class ImportActivitiesPage(QWizardPage):
    def __init__(self, last_path: Optional[str]):
        super().__init__()
        self.setTitle("Import Activities")
        self.setSubTitle("Choose an Activities file (CSV or TXT).")

        self.path: str = last_path or ""

        layout = QVBoxLayout(self)
        self.label = QLabel(self.path if self.path else "No file selected.")
        layout.addWidget(self.label)

        btn = QPushButton("Choose Activities File…")
        btn.clicked.connect(self._pick_file)
        layout.addWidget(btn)

    def _pick_file(self) -> None:
        start_dir = self.path or ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Activities",
            start_dir,
            "CSV/TXT Files (*.csv *.txt);;All Files (*.*)",
        )
        if path:
            self.path = path
            self.label.setText(path)

    def get_path(self) -> str:
        return self.path


class ImportLogicPage(QWizardPage):
    def __init__(self, last_path: Optional[str]):
        super().__init__()
        self.setTitle("Import Logic")
        self.setSubTitle("Choose a Logic file (CSV or TXT).")

        self.path: str = last_path or ""

        layout = QVBoxLayout(self)
        self.label = QLabel(self.path if self.path else "No file selected.")
        layout.addWidget(self.label)

        btn = QPushButton("Choose Logic File…")
        btn.clicked.connect(self._pick_file)
        layout.addWidget(btn)

    def _pick_file(self) -> None:
        start_dir = self.path or ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Logic",
            start_dir,
            "CSV/TXT Files (*.csv *.txt);;All Files (*.*)",
        )
        if path:
            self.path = path
            self.label.setText(path)

    def get_path(self) -> str:
        return self.path


class CPMWizard(QWizard):
    def __init__(
        self,
        default_start: date,
        initial_holidays: set[date],
        last_activities_path: Optional[str] = None,
        last_logic_path: Optional[str] = None,
    ):
        super().__init__()
        self.setWindowTitle("CPM Calculator Wizard")
        self.setWizardStyle(QWizard.ModernStyle)

        self.page_start = StartDatePage(default_start)
        self.page_holidays = HolidaysPage(initial_holidays)
        self.page_acts = ImportActivitiesPage(last_activities_path)
        self.page_logic = ImportLogicPage(last_logic_path)

        self.addPage(self.page_start)
        self.addPage(self.page_holidays)
        self.addPage(self.page_acts)
        self.addPage(self.page_logic)

        self._result: Optional[CPMWizardResult] = None

    def result_value(self) -> Optional[CPMWizardResult]:
        return self._result

    def accept(self) -> None:
        start = self.page_start.get_start_date()
        holidays = self.page_holidays.get_holidays()
        acts = self.page_acts.get_path()
        logic = self.page_logic.get_path()

        self._result = CPMWizardResult(
            start_date=start,
            holidays=holidays,
            activities_path=acts,
            logic_path=logic,
        )
        super().accept()