from __future__ import annotations

from datetime import date
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QLabel

from fieldflow.app.controls_models import RFI


def _d(d: date | None) -> str:
    return "" if d is None else d.isoformat()


def _p(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


class RFIDock(QWidget):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("RFIs (simple tracker; link to activities)") )

        btns = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_del = QPushButton("Delete")
        btns.addWidget(self.btn_add)
        btns.addWidget(self.btn_del)
        btns.addStretch(1)
        layout.addLayout(btns)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "ID", "Title", "Status", "Created", "Due", "Answered", "Linked Activity IDs", "Impact Days"
        ])
        self.table.itemChanged.connect(lambda _: self.changed.emit())
        layout.addWidget(self.table, 1)

        self.btn_add.clicked.connect(self._add)
        self.btn_del.clicked.connect(self._delete)

    def set_items(self, items: List[RFI]) -> None:
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(len(items))
            for r, x in enumerate(items):
                vals = [
                    x.id,
                    x.title,
                    x.status,
                    _d(x.created),
                    _d(x.due),
                    _d(x.answered),
                    x.linked_activity_ids,
                    str(int(x.impact_days)),
                ]
                for c, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    it.setFlags(it.flags() | Qt.ItemIsEditable)
                    self.table.setItem(r, c, it)
            self.table.resizeColumnsToContents()
        finally:
            self.table.blockSignals(False)

    def get_items(self) -> List[RFI]:
        out: List[RFI] = []
        for r in range(self.table.rowCount()):
            def txt(c: int) -> str:
                it = self.table.item(r, c)
                return "" if it is None else it.text().strip()

            def numi(c: int) -> int:
                try:
                    return int(float(txt(c) or 0))
                except Exception:
                    return 0

            out.append(
                RFI(
                    id=txt(0) or f"RFI{r+1}",
                    title=txt(1),
                    status=txt(2) or "Open",
                    created=_p(txt(3)),
                    due=_p(txt(4)),
                    answered=_p(txt(5)),
                    linked_activity_ids=txt(6),
                    impact_days=numi(7),
                )
            )
        return out

    def _add(self) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        defaults = [f"RFI{r+1}", "", "Open", "", "", "", "", "0"]
        for c, v in enumerate(defaults):
            it = QTableWidgetItem(v)
            it.setFlags(it.flags() | Qt.ItemIsEditable)
            self.table.setItem(r, c, it)
        self.changed.emit()

    def _delete(self) -> None:
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)
            self.changed.emit()
