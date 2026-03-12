from __future__ import annotations

from dataclasses import dataclass
from typing import List

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QTextEdit,
    QHBoxLayout,
    QPushButton,
    QCheckBox,
    QComboBox,
)


@dataclass(frozen=True)
class MSProjectImportDecision:
    commit: bool
    target: str
    mode: str  # "overwrite" or "merge"
    update_calendar: bool
    compute_cpm: bool


class MSProjectImportDialog(QDialog):
    """
    Import cockpit (single dialog):
      - choose target scenario
      - choose import mode (overwrite/merge)
      - toggle calendar update (start date + holidays)
      - toggle compute CPM
      - preview warnings
    """
    def __init__(
        self,
        *,
        targets: List[str],
        default_target: str,
        tasks_count: int,
        links_count: int,
        holidays_count: int,
        warnings: List[str],
    ):
        super().__init__()
        self.setWindowTitle("MS Project Import (Preview + Options)")
        self.resize(760, 560)

        self._decision = MSProjectImportDecision(
            commit=False,
            target=default_target,
            mode="overwrite",
            update_calendar=True,
            compute_cpm=False,
        )

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Import target:"))
        self.cmb_target = QComboBox()
        self.cmb_target.addItems(targets)
        if default_target in targets:
            self.cmb_target.setCurrentIndex(targets.index(default_target))
        layout.addWidget(self.cmb_target)

        layout.addWidget(QLabel("Import mode:"))
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem("Overwrite (replace activities + relationships)", "overwrite")
        self.cmb_mode.addItem("Merge by ID (update/add, keep extras)", "merge")
        layout.addWidget(self.cmb_mode)

        layout.addWidget(
            QLabel(
                f"Tasks: <b>{tasks_count}</b>    Links: <b>{links_count}</b>    Holidays: <b>{holidays_count}</b>"
            )
        )

        self.chk_calendar = QCheckBox("Update Project Start Date + Holidays from MS Project")
        self.chk_calendar.setChecked(True)
        layout.addWidget(self.chk_calendar)

        self.chk_cpm = QCheckBox("Compute CPM after import")
        layout.addWidget(self.chk_cpm)

        wlabel = QLabel("Warnings / Notes:")
        wlabel.setStyleSheet("font-weight: 600;")
        layout.addWidget(wlabel)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText("\n".join(warnings) if warnings else "No warnings.")
        layout.addWidget(self.text, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self._on_cancel)
        btn_row.addWidget(btn_cancel)

        btn_commit = QPushButton("Commit Import")
        btn_commit.clicked.connect(self._on_commit)
        btn_commit.setDefault(True)
        btn_row.addWidget(btn_commit)

        layout.addLayout(btn_row)

    def _on_cancel(self) -> None:
        self._decision = MSProjectImportDecision(
            commit=False,
            target=self.cmb_target.currentText(),
            mode=self.cmb_mode.currentData(),
            update_calendar=self.chk_calendar.isChecked(),
            compute_cpm=self.chk_cpm.isChecked(),
        )
        self.reject()

    def _on_commit(self) -> None:
        self._decision = MSProjectImportDecision(
            commit=True,
            target=self.cmb_target.currentText(),
            mode=self.cmb_mode.currentData(),
            update_calendar=self.chk_calendar.isChecked(),
            compute_cpm=self.chk_cpm.isChecked(),
        )
        self.accept()

    def decision(self) -> MSProjectImportDecision:
        return self._decision