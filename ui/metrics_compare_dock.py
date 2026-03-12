from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHBoxLayout,
    QCheckBox,
    QComboBox,
    QSpinBox,
    QPushButton,
)


@dataclass(frozen=True)
class MetricDeltaRow:
    activity_id: str
    name: str

    base_es: str
    scen_es: str
    d_es: str

    base_ef: str
    scen_ef: str
    d_ef: str

    base_ls: str
    scen_ls: str
    d_ls: str

    base_lf: str
    scen_lf: str
    d_lf: str

    base_tf: str
    scen_tf: str
    d_tf: str

    base_crit: str
    scen_crit: str
    crit_flip: str

    risk: str


class MetricsCompareDock(QWidget):
    """Results compare dock: baseline vs scenario CPM metric deltas.

    The dock only renders rows and provides UI controls. The caller (MainWindow)
    owns the computation and persistence of settings.
    """

    settings_changed = Signal()
    export_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        self.title = QLabel("Metrics Compare (compute CPM to populate)")
        self.title.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.title)

        # Controls row
        controls = QHBoxLayout()

        self.chk_changed = QCheckBox("Changed only")
        self.chk_changed.setChecked(True)
        self.chk_changed.stateChanged.connect(lambda _=None: self.settings_changed.emit())
        controls.addWidget(self.chk_changed)

        self.chk_critical = QCheckBox("Critical only")
        self.chk_critical.setChecked(False)
        self.chk_critical.stateChanged.connect(lambda _=None: self.settings_changed.emit())
        controls.addWidget(self.chk_critical)

        controls.addWidget(QLabel("Sort:"))
        self.cmb_sort = QComboBox()
        self.cmb_sort.addItem("Δ Finish (proxy ΔEF)", "delta_finish")
        self.cmb_sort.addItem("Δ ES", "delta_es")
        self.cmb_sort.addItem("Δ EF", "delta_ef")
        self.cmb_sort.addItem("Δ LS", "delta_ls")
        self.cmb_sort.addItem("Δ LF", "delta_lf")
        self.cmb_sort.addItem("Δ TF", "delta_tf")
        self.cmb_sort.addItem("Activity ID", "activity_id")
        self.cmb_sort.currentIndexChanged.connect(lambda _=None: self.settings_changed.emit())
        controls.addWidget(self.cmb_sort)

        controls.addWidget(QLabel("Top:"))
        self.spin_top = QSpinBox()
        self.spin_top.setRange(10, 5000)
        self.spin_top.setSingleStep(10)
        self.spin_top.setValue(200)
        self.spin_top.valueChanged.connect(lambda _=None: self.settings_changed.emit())
        controls.addWidget(self.spin_top)

        self.btn_export = QPushButton("Export Results Δ CSV")
        self.btn_export.clicked.connect(lambda: self.export_requested.emit())
        controls.addWidget(self.btn_export)

        controls.addStretch(1)
        layout.addLayout(controls)

        self.table = QTableWidget()
        self.table.setColumnCount(18)
        self.table.setHorizontalHeaderLabels([
            "ID",
            "Name",
            "B.ES",
            "S.ES",
            "ΔES",
            "B.EF",
            "S.EF",
            "ΔEF",
            "B.LS",
            "S.LS",
            "ΔLS",
            "B.LF",
            "S.LF",
            "ΔLF",
            "B.TF",
            "S.TF",
            "ΔTF",
            "Risk",
        ])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table, 1)

        self.footer = QLabel("")
        self.footer.setStyleSheet("color: #666;")
        layout.addWidget(self.footer)

    def set_title(self, baseline_name: str, scenario_name: str) -> None:
        self.title.setText(f"Metrics Compare: {baseline_name} vs {scenario_name}")

    def set_footer(self, text: str) -> None:
        self.footer.setText(text)

    def get_settings(self) -> dict:
        return {
            "show_changed_only": self.chk_changed.isChecked(),
            "critical_only": self.chk_critical.isChecked(),
            "sort_key": self.cmb_sort.currentData(),
            "top_n": int(self.spin_top.value()),
        }

    def set_settings(self, *, show_changed_only: bool, critical_only: bool, sort_key: str, top_n: int) -> None:
        self.chk_changed.blockSignals(True)
        self.chk_critical.blockSignals(True)
        self.cmb_sort.blockSignals(True)
        self.spin_top.blockSignals(True)
        try:
            self.chk_changed.setChecked(bool(show_changed_only))
            self.chk_critical.setChecked(bool(critical_only))

            # set sort index
            idx = 0
            for i in range(self.cmb_sort.count()):
                if self.cmb_sort.itemData(i) == sort_key:
                    idx = i
                    break
            self.cmb_sort.setCurrentIndex(idx)

            self.spin_top.setValue(max(10, int(top_n)))
        finally:
            self.chk_changed.blockSignals(False)
            self.chk_critical.blockSignals(False)
            self.cmb_sort.blockSignals(False)
            self.spin_top.blockSignals(False)

    def set_rows(self, rows: List[MetricDeltaRow]) -> None:
        self.table.setRowCount(len(rows))
        for r, d in enumerate(rows):
            vals = [
                d.activity_id,
                d.name,
                d.base_es,
                d.scen_es,
                d.d_es,
                d.base_ef,
                d.scen_ef,
                d.d_ef,
                d.base_ls,
                d.scen_ls,
                d.d_ls,
                d.base_lf,
                d.scen_lf,
                d.d_lf,
                d.base_tf,
                d.scen_tf,
                d.d_tf,
                d.risk,
            ]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, it)

        self.table.resizeColumnsToContents()
