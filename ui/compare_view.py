from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem


class CompareView(QWidget):
    """
    Simple, readable compare table:
      - duration changes
      - relationships added/removed
    """
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        title = QLabel("Compare (Baseline → Active Scenario)")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Change Type", "Item", "From", "To"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        layout.addWidget(self.table)

    def set_rows(self, rows: list[tuple[str, str, str, str]]) -> None:
        self.table.setRowCount(len(rows))
        for r, (ctype, item, frm, to) in enumerate(rows):
            items = [
                QTableWidgetItem(ctype),
                QTableWidgetItem(item),
                QTableWidgetItem(frm),
                QTableWidgetItem(to),
            ]
            for c, it in enumerate(items):
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, it)
        self.table.resizeColumnsToContents()