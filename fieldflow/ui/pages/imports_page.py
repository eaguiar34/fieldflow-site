from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QFileDialog, QCheckBox, QMessageBox

from fieldflow.ui.shell.app_context import AppContext


class ImportsPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        layout = QVBoxLayout(self)

        title = QLabel("Imports")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title)

        row = QHBoxLayout()
        self.btn_act = QPushButton("Import Activities (CSV/TXT)…")
        self.btn_logic = QPushButton("Import Logic (CSV/TXT)…")
        self.btn_msp = QPushButton("Import MS Project XML…")
        row.addWidget(self.btn_act)
        row.addWidget(self.btn_logic)
        row.addWidget(self.btn_msp)
        row.addStretch(1)
        layout.addLayout(row)

        self.chk_update_calendar = QCheckBox("Update start date + holidays from MS Project XML")
        self.chk_update_calendar.setChecked(True)
        layout.addWidget(self.chk_update_calendar)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #666; padding: 6px;")
        layout.addWidget(self.status)

        self.btn_act.clicked.connect(self._import_activities)
        self.btn_logic.clicked.connect(self._import_logic)
        self.btn_msp.clicked.connect(self._import_msp)

    def _import_activities(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Activities CSV/TXT",
            str(Path.home()),
            "CSV/TXT Files (*.csv *.txt);;All Files (*.*)",
        )
        if not path:
            return
        try:
            n, p = self.ctx.import_activities(Path(path))
            self.status.setText(f"Imported {n} activities from {p}")
        except Exception as e:
            QMessageBox.critical(self, "Import failed", str(e))

    def _import_logic(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Logic CSV/TXT",
            str(Path.home()),
            "CSV/TXT Files (*.csv *.txt);;All Files (*.*)",
        )
        if not path:
            return
        try:
            n, p = self.ctx.import_logic(Path(path))
            self.status.setText(f"Imported {n} relationships from {p}")
        except Exception as e:
            QMessageBox.critical(self, "Import failed", str(e))

    def _import_msp(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import MS Project XML (MSPDI)",
            str(Path.home()),
            "XML Files (*.xml);;All Files (*.*)",
        )
        if not path:
            return
        try:
            a, r, h = self.ctx.import_msproject_xml_into_active(Path(path), update_calendar=self.chk_update_calendar.isChecked())
            self.status.setText(f"Imported MSP XML: {a} activities, {r} links, {h} holidays")
        except Exception as e:
            QMessageBox.critical(self, "MS Project import failed", str(e))
