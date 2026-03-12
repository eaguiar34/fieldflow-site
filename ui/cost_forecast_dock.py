from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem

from fieldflow.app.cost_forecast import WeeklyBucket


class CostForecastDock(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        self.title = QLabel("Cost Forecast (weekly, schedule-driven)")
        self.title.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.title)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Week Start", "Cost", "Cumulative"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table, 1)

        self.footer = QLabel("")
        self.footer.setStyleSheet("color: #666;")
        layout.addWidget(self.footer)

    def set_buckets(self, buckets: List[WeeklyBucket], warnings: List[str]) -> None:
        self.table.setRowCount(len(buckets))
        cum = 0.0
        for r, b in enumerate(buckets):
            cum += float(b.cost)
            vals = [b.week_start.isoformat(), f"{b.cost:,.2f}", f"{cum:,.2f}"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, it)
        self.table.resizeColumnsToContents()

        if warnings:
            self.footer.setText("Warnings: " + " | ".join(warnings[:5]))
        else:
            self.footer.setText("")
