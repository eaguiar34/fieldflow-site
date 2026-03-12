from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, List, Set, Tuple

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem


@dataclass(frozen=True)
class ActivityDiff:
    activity_id: str
    field: str
    baseline: str
    scenario: str


def _fmt_date(d: Optional[date]) -> str:
    return "" if d is None else d.isoformat()


class CompareDockWidget(QWidget):
    """
    Baseline vs Active Scenario INPUT diffs:
      - Activity fields: duration_days, snet, fnet
      - Relationship set: added/removed
    """

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        self.title = QLabel("Compare")
        self.title.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.title)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Activity", "Field", "Baseline", "Scenario"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

        self.footer = QLabel("")
        self.footer.setStyleSheet("color: #666;")
        layout.addWidget(self.footer)

    def set_title(self, baseline_name: str, scenario_name: str) -> None:
        self.title.setText(f"Compare: {baseline_name} vs {scenario_name} (inputs)")

    def show_diffs(self, diffs: List[ActivityDiff], rel_added: int, rel_removed: int) -> None:
        self.table.setRowCount(len(diffs))
        for r, d in enumerate(diffs):
            self.table.setItem(r, 0, QTableWidgetItem(d.activity_id))
            self.table.setItem(r, 1, QTableWidgetItem(d.field))
            self.table.setItem(r, 2, QTableWidgetItem(d.baseline))
            self.table.setItem(r, 3, QTableWidgetItem(d.scenario))
        self.table.resizeColumnsToContents()
        self.footer.setText(f"Relationships: +{rel_added} added, -{rel_removed} removed")