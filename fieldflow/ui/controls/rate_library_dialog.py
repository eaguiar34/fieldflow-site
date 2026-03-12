from __future__ import annotations

from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QWidget,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
)

from fieldflow.app.rate_library import RateLibraryStore, CrewProfile, EquipmentProfile


def _f(s: str) -> float:
    try:
        return float((s or "").strip())
    except Exception:
        return 0.0


class _RateTable(QWidget):
    """Editable table for (id, name, cost_per_day)."""

    def __init__(self, title: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))

        btns = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_del = QPushButton("Delete")
        btns.addWidget(self.btn_add)
        btns.addWidget(self.btn_del)
        btns.addStretch(1)
        layout.addLayout(btns)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "$ / day"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table, 1)

        self.btn_add.clicked.connect(self._add_row)
        self.btn_del.clicked.connect(self._del_rows)

    def set_rows(self, rows: List[Tuple[str, str, float]], default_prefix: str) -> None:
        self._default_prefix = default_prefix
        self.table.setRowCount(len(rows))
        for r, (rid, name, cost) in enumerate(rows):
            self._set(r, 0, rid)
            self._set(r, 1, name)
            self._set(r, 2, f"{float(cost):.2f}")
        self.table.resizeColumnsToContents()

    def get_rows(self) -> List[Tuple[str, str, float]]:
        out: List[Tuple[str, str, float]] = []
        for r in range(self.table.rowCount()):
            rid = self._txt(r, 0)
            name = self._txt(r, 1)
            cost = _f(self._txt(r, 2))
            if not rid and not name:
                continue
            out.append((rid.strip(), name.strip(), float(cost)))
        return out

    def _set(self, r: int, c: int, text: str) -> None:
        it = QTableWidgetItem(text)
        it.setFlags(it.flags() | Qt.ItemIsEditable)
        self.table.setItem(r, c, it)

    def _txt(self, r: int, c: int) -> str:
        it = self.table.item(r, c)
        return "" if it is None else (it.text() or "").strip()

    def _add_row(self) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        rid = f"{getattr(self, '_default_prefix', 'R')}-{r+1:03d}"
        self._set(r, 0, rid)
        self._set(r, 1, "")
        self._set(r, 2, "0")
        self.table.selectRow(r)

    def _del_rows(self) -> None:
        sel = self.table.selectionModel()
        if sel is None:
            return
        rows = sorted({idx.row() for idx in sel.selectedRows()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)


class RateLibraryDialog(QDialog):
    """Edit the global Crew + Equipment daily-rate library.

    Current storage: local QSettings.

    Future: allow loading/saving from a shared "library pack" folder without
    breaking this dialog (we'll swap the store implementation).
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Rate Libraries")
        self.resize(720, 420)

        self.store = RateLibraryStore()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Company standards: crews & equipment daily rates (offline, local for now)."))

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self.crews = _RateTable("Crew profiles (used by Work Packages in crew/production mode)")
        self.equip = _RateTable("Equipment profiles")
        self.tabs.addTab(self.crews, "Crews")
        self.tabs.addTab(self.equip, "Equipment")

        btns = QHBoxLayout()
        self.btn_reload = QPushButton("Reload")
        self.btn_save = QPushButton("Save")
        self.btn_close = QPushButton("Close")
        btns.addWidget(self.btn_reload)
        btns.addWidget(self.btn_save)
        btns.addStretch(1)
        btns.addWidget(self.btn_close)
        layout.addLayout(btns)

        self.btn_reload.clicked.connect(self._load)
        self.btn_save.clicked.connect(self._save)
        self.btn_close.clicked.connect(self.accept)

        self._load()

    def _load(self) -> None:
        crews, equips = self.store.load()
        self.crews.set_rows(
            [(c.id, c.name, c.cost_per_day) for c in crews],
            default_prefix="CREW",
        )
        self.equip.set_rows(
            [(e.id, e.name, e.cost_per_day) for e in equips],
            default_prefix="EQ",
        )

    def _save(self) -> None:
        crews_raw = self.crews.get_rows()
        equips_raw = self.equip.get_rows()

        # Validate IDs unique per table
        crew_ids = [rid for rid, _, _ in crews_raw if rid]
        eq_ids = [rid for rid, _, _ in equips_raw if rid]
        if len(set(crew_ids)) != len(crew_ids):
            QMessageBox.warning(self, "Rate Library", "Crew IDs must be unique.")
            return
        if len(set(eq_ids)) != len(eq_ids):
            QMessageBox.warning(self, "Rate Library", "Equipment IDs must be unique.")
            return

        crews = [CrewProfile(id=rid, name=name, cost_per_day=cost) for rid, name, cost in crews_raw if rid]
        equips = [EquipmentProfile(id=rid, name=name, cost_per_day=cost) for rid, name, cost in equips_raw if rid]

        try:
            self.store.save(crews, equips)
        except Exception as e:
            QMessageBox.warning(self, "Rate Library", f"Failed to save: {e}")
            return

        QMessageBox.information(self, "Rate Library", "Saved.")