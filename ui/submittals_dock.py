from __future__ import annotations

from datetime import date
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QLabel,
    QListWidget,
    QListWidgetItem,
)

from fieldflow.app.controls_models import Submittal
from fieldflow.app.submittal_checker import SubmittalFinding


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


class SubmittalsDock(QWidget):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Submittals (required-by + lead time + checker)") )

        btns = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_del = QPushButton("Delete")
        btns.addWidget(self.btn_add)
        btns.addWidget(self.btn_del)
        btns.addStretch(1)
        layout.addLayout(btns)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Spec", "Status", "Required-by Activity", "Lead (wd)", "Submitted", "Approved"
        ])
        self.table.itemChanged.connect(lambda _: self.changed.emit())
        layout.addWidget(self.table, 1)

        self.findings_label = QLabel("Checker findings:")
        self.findings_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.findings_label)

        self.findings = QListWidget()
        layout.addWidget(self.findings, 1)

        self.btn_add.clicked.connect(self._add)
        self.btn_del.clicked.connect(self._delete)

    def set_items(self, items: List[Submittal]) -> None:
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(len(items))
            for r, s in enumerate(items):
                vals = [
                    s.id,
                    s.spec_section,
                    s.status,
                    s.required_by_activity_id,
                    str(int(s.lead_time_days)),
                    _d(s.submit_date),
                    _d(s.approve_date),
                ]
                for c, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    it.setFlags(it.flags() | Qt.ItemIsEditable)
                    self.table.setItem(r, c, it)
            self.table.resizeColumnsToContents()
        finally:
            self.table.blockSignals(False)

    def get_items(self) -> List[Submittal]:
        out: List[Submittal] = []
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
                Submittal(
                    id=txt(0) or f"SUB{r+1}",
                    spec_section=txt(1),
                    status=txt(2) or "Required",
                    required_by_activity_id=txt(3),
                    lead_time_days=numi(4),
                    submit_date=_p(txt(5)),
                    approve_date=_p(txt(6)),
                )
            )
        return out

    def set_findings(self, findings: List[SubmittalFinding]) -> None:
        self.findings.clear()
        for f in findings:
            prefix = f"[{f.severity}] "
            msg = prefix + (f"{f.submittal_id}: " if f.submittal_id else "") + f.message
            self.findings.addItem(QListWidgetItem(msg))

    def _add(self) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        defaults = [f"SUB{r+1}", "", "Required", "", "0", "", ""]
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
