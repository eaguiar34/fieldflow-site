from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QAbstractItemView
)

from fieldflow.app.controls_models import WorkPackage
from fieldflow.ui.onboarding.sparkline import Sparkline


def _f(x) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def _opt_f(s: str) -> Optional[float]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _pct_to_float(s: str) -> float:
    """Parse '12.5%' or '12.5' -> 0.125"""
    s = (s or "").strip().replace("%", "")
    try:
        return float(s) / 100.0
    except Exception:
        return 0.0


def _weights(n: int, curve: str) -> List[float]:
    """Tiny curve weights for sparkline preview. Must be fast + deterministic."""
    n = max(1, int(n))
    curve = (curve or "linear").strip().lower()

    if n == 1:
        return [1.0]

    if curve == "front":
        raw = [float(n - i) for i in range(n)]
    elif curve == "back":
        raw = [float(i + 1) for i in range(n)]
    elif curve == "bell":
        mid = (n - 1) / 2.0
        raw = [max(0.1, (mid + 1.0) - abs(i - mid)) for i in range(n)]
    else:
        raw = [1.0 for _ in range(n)]

    s = sum(raw) or 1.0
    return [x / s for x in raw]


class WorkPackagesDock(QWidget):
    changed = Signal()

    COLS = [
        "ID",
        "Name",
        "Qty",
        "Unit",
        "Mode",
        "Curve",
        "Preview",
        "Unit $ (manual)",
        "Prod/day",
        "Crew $/day",
        "Equip $/day",
        "CrewRef",
        "EquipRef",
        "Mat $/unit",
        "Waste %",
        "Derived $/unit",
        "Total $",
        "Linked Activity IDs",
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)

        bar = QHBoxLayout()
        self.btn_add = QPushButton("Add WP")
        self.btn_del = QPushButton("Delete WP")
        bar.addWidget(self.btn_add)
        bar.addWidget(self.btn_del)
        bar.addStretch(1)
        root.addLayout(bar)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSortingEnabled(True)
        root.addWidget(self.table, 1)

        self.lbl_warn = QLabel("")
        self.lbl_warn.setStyleSheet("color: #b26a00; padding: 4px;")
        self.lbl_warn.setWordWrap(True)
        root.addWidget(self.lbl_warn)

        self.btn_add.clicked.connect(self._add_row)
        self.btn_del.clicked.connect(self._delete_selected)
        self.table.itemChanged.connect(self._on_item_changed)

        self._loading = False
        self._read_only = False

    def set_read_only(self, read_only: bool = True) -> None:
        """Disable edits for locked/view-only workspaces."""
        self._read_only = bool(read_only)
        try:
            self.btn_add.setEnabled(not self._read_only)
            self.btn_del.setEnabled(not self._read_only)
        except Exception:
            pass
        try:
            if self._read_only:
                self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            else:
                self.table.setEditTriggers(
                    QAbstractItemView.DoubleClicked
                    | QAbstractItemView.EditKeyPressed
                    | QAbstractItemView.AnyKeyPressed
                )
        except Exception:
            pass

    def set_items(self, items: List[WorkPackage]) -> None:
        self._loading = True
        try:
            self.table.setRowCount(len(items))
            for r, wp in enumerate(items):
                self._set(r, 0, wp.id, editable=True)
                self._set(r, 1, wp.name, editable=True)
                self._set(r, 2, str(_f(wp.qty)), editable=True)
                self._set(r, 3, wp.unit, editable=True)

                mode = (wp.pricing_mode or "unit").lower()
                if mode not in ("unit", "crew"):
                    mode = "unit"
                self._set(r, 4, mode, editable=True)

                curve = (getattr(wp, "curve_style", "linear") or "linear").lower()
                if curve not in ("linear", "front", "back", "bell"):
                    curve = "linear"
                self._set(r, 5, curve, editable=True)

                # Preview sparkline widget (cellWidget)
                self._set_preview(r, curve)

                self._set(r, 7, str(_f(wp.unit_cost)), editable=True)

                self._set(r, 8, "" if wp.production_units_per_day is None else str(_f(wp.production_units_per_day)), editable=True)
                self._set(r, 9, "" if wp.crew_cost_per_day is None else str(_f(wp.crew_cost_per_day)), editable=True)
                self._set(r, 10, "" if wp.equipment_cost_per_day is None else str(_f(wp.equipment_cost_per_day)), editable=True)

                self._set(r, 11, str(getattr(wp, "crew_profile_id", "") or ""), editable=True)
                self._set(r, 12, str(getattr(wp, "equip_profile_id", "") or ""), editable=True)

                self._set(r, 13, "" if wp.material_unit_cost is None else str(_f(wp.material_unit_cost)), editable=True)
                self._set(r, 14, f"{_f(wp.waste_factor) * 100:.1f}%", editable=True)

                self._set(r, 15, f"{wp.derived_unit_cost():,.2f}", editable=False)
                self._set(r, 16, f"{wp.total_cost():,.2f}", editable=False)

                self._set(r, 17, wp.linked_activity_ids or "", editable=True)

            self.table.resizeColumnsToContents()
            self._update_warnings()
        finally:
            self._loading = False

    def get_items(self) -> List[WorkPackage]:
        out: List[WorkPackage] = []
        for r in range(self.table.rowCount()):
            wp = self._row_to_wp(r)
            if wp is None:
                continue
            out.append(wp)
        return out

    def _set(self, r: int, c: int, text: str, *, editable: bool) -> None:
        it = QTableWidgetItem(text)
        if editable:
            it.setFlags(it.flags() | Qt.ItemIsEditable)
        else:
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(r, c, it)

    def _txt(self, r: int, c: int) -> str:
        it = self.table.item(r, c)
        return "" if it is None else it.text().strip()

    def _set_preview(self, r: int, curve: str) -> None:
        s = Sparkline()
        s.set_values(_weights(10, curve))
        self.table.setCellWidget(r, 6, s)

    def _row_to_wp(self, r: int) -> Optional[WorkPackage]:
        wp_id = self._txt(r, 0)
        name = self._txt(r, 1)
        if not wp_id and not name:
            return None

        qty = _f(self._txt(r, 2))
        unit = self._txt(r, 3)

        mode = (self._txt(r, 4) or "unit").lower()
        if mode not in ("unit", "crew"):
            mode = "unit"

        curve = (self._txt(r, 5) or "linear").lower()
        if curve not in ("linear", "front", "back", "bell"):
            curve = "linear"

        unit_cost = _f(self._txt(r, 7))
        prod = _opt_f(self._txt(r, 8))
        crew = _opt_f(self._txt(r, 9))
        equip = _opt_f(self._txt(r, 10))
        crew_ref = self._txt(r, 11)
        equip_ref = self._txt(r, 12)
        mat = _opt_f(self._txt(r, 13))
        waste = _pct_to_float(self._txt(r, 14))
        linked = self._txt(r, 17)

        return WorkPackage(
            id=wp_id,
            name=name,
            qty=qty,
            unit=unit,
            unit_cost=unit_cost,
            linked_activity_ids=linked,
            pricing_mode=mode,
            curve_style=curve,
            production_units_per_day=prod,
            crew_cost_per_day=crew,
            equipment_cost_per_day=equip,
            crew_profile_id=crew_ref,
            equip_profile_id=equip_ref,
            material_unit_cost=mat,
            waste_factor=waste,
        )

    def _recompute_row(self, r: int) -> None:
        wp = self._row_to_wp(r)
        if wp is None:
            return
        self._loading = True
        try:
            self._set(r, 15, f"{wp.derived_unit_cost():,.2f}", editable=False)
            self._set(r, 16, f"{wp.total_cost():,.2f}", editable=False)
            self._set_preview(r, (wp.curve_style or "linear"))
        finally:
            self._loading = False

    def _update_warnings(self) -> None:
        msgs = []
        for r in range(self.table.rowCount()):
            mode = (self._txt(r, 4) or "unit").lower()
            if mode != "crew":
                continue
            wp_id = self._txt(r, 0) or f"Row {r+1}"
            prod = _opt_f(self._txt(r, 8))
            crew = _opt_f(self._txt(r, 9))
            equip = _opt_f(self._txt(r, 10))
            crew_ref = self._txt(r, 11)
            equip_ref = self._txt(r, 12)

            if prod is None or prod <= 0:
                msgs.append(f"{wp_id}: missing Prod/day")
            if (crew is None and not crew_ref) and (equip is None and not equip_ref):
                msgs.append(f"{wp_id}: missing Crew/Equip $/day or refs")

        self.lbl_warn.setText(
            "" if not msgs else
            ("Crew-mode checks: " + " | ".join(msgs[:4]) + ("" if len(msgs) <= 4 else f" (+{len(msgs)-4} more)"))
        )

    def _add_row(self) -> None:
        if self._read_only:
            return
        r = self.table.rowCount()
        self.table.insertRow(r)
        self._loading = True
        try:
            self._set(r, 0, f"WP-{r+1:02d}", editable=True)
            self._set(r, 1, "New Work Package", editable=True)
            self._set(r, 2, "1", editable=True)
            self._set(r, 3, "LS", editable=True)
            self._set(r, 4, "unit", editable=True)
            self._set(r, 5, "linear", editable=True)
            self._set_preview(r, "linear")
            self._set(r, 7, "0", editable=True)
            self._set(r, 8, "", editable=True)
            self._set(r, 9, "", editable=True)
            self._set(r, 10, "", editable=True)
            self._set(r, 11, "", editable=True)
            self._set(r, 12, "", editable=True)
            self._set(r, 13, "", editable=True)
            self._set(r, 14, "0%", editable=True)
            self._set(r, 15, "0.00", editable=False)
            self._set(r, 16, "0.00", editable=False)
            self._set(r, 17, "", editable=True)
        finally:
            self._loading = False

        self.table.selectRow(r)
        self.changed.emit()
        self._update_warnings()

    def _delete_selected(self) -> None:
        if self._read_only:
            return
        sel = self.table.selectionModel()
        if sel is None:
            return
        rows = sorted({idx.row() for idx in sel.selectedRows()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
        self.changed.emit()
        self._update_warnings()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or self._read_only:
            return

        if item.column() == 4:
            v = (item.text() or "").strip().lower()
            if v not in ("unit", "crew"):
                QMessageBox.information(self, "Mode", "Mode must be 'unit' or 'crew'.")
                self._loading = True
                try:
                    item.setText("unit")
                finally:
                    self._loading = False

        if item.column() == 5:
            v = (item.text() or "").strip().lower()
            if v not in ("linear", "front", "back", "bell"):
                QMessageBox.information(self, "Curve", "Curve must be: linear, front, back, or bell.")
                self._loading = True
                try:
                    item.setText("linear")
                finally:
                    self._loading = False

        if item.column() in (2, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14):
            self._recompute_row(item.row())
            self._update_warnings()

        self.changed.emit()