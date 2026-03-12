from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
)


class RelationshipsView(QWidget):
    """Relationships (logic) table with Add/Delete controls.

    This widget is used by LogicPage. LogicPage expects:
      - self.table (QTableWidget)
      - self.btn_add (QPushButton)
      - self.btn_delete (QPushButton)

    Rows are shaped like:
        (pred_id: str, succ_id: str, rel_type: str, lag_days: int)
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)

        # Toolbar
        bar = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_delete = QPushButton("Delete")
        bar.addWidget(self.btn_add)
        bar.addWidget(self.btn_delete)
        bar.addStretch(1)
        root.addLayout(bar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Pred", "Succ", "Type", "Lag (wd)"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        root.addWidget(self.table, 1)

    def set_rows(self, rows) -> None:
        """Populate the table (non-destructive)."""
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(len(rows))
            for r, (pred, succ, rtype, lag) in enumerate(rows):
                self._set_item(r, 0, str(pred), editable=True)
                self._set_item(r, 1, str(succ), editable=True)
                self._set_item(r, 2, str(rtype), editable=True)
                self._set_item(r, 3, str(lag), editable=True)
            self.table.resizeColumnsToContents()
        finally:
            self.table.blockSignals(False)

    def rows(self):
        """Return current rows from the UI."""
        out = []
        for r in range(self.table.rowCount()):
            pred = self._text(r, 0)
            succ = self._text(r, 1)
            rtype = self._text(r, 2)
            lag_s = self._text(r, 3)
            try:
                lag = int(float(lag_s)) if lag_s else 0
            except Exception:
                lag = 0
            if pred or succ or rtype or lag:
                out.append((pred, succ, rtype, lag))
        return out

    def add_blank_row(self) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self._set_item(r, 0, "", editable=True)
        self._set_item(r, 1, "", editable=True)
        self._set_item(r, 2, "FS", editable=True)
        self._set_item(r, 3, "0", editable=True)
        self.table.setCurrentCell(r, 0)

    def delete_selected_rows(self) -> None:
        sel = self.table.selectionModel()
        if sel is None:
            return
        rows = sorted({idx.row() for idx in sel.selectedRows()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)

    # -------------------- helpers --------------------
    def _set_item(self, r: int, c: int, text: str, editable: bool) -> None:
        it = QTableWidgetItem(text)
        if editable:
            it.setFlags(it.flags() | Qt.ItemIsEditable)
        else:
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(r, c, it)

    def _text(self, r: int, c: int) -> str:
        it = self.table.item(r, c)
        return "" if it is None else it.text().strip()