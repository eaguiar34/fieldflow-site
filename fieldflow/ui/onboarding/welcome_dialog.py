from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QVBoxLayout,
    QLabel,
    QHBoxLayout,
    QPushButton,
    QMessageBox,
)

from fieldflow.ui.shell.app_context import AppContext
from fieldflow.ui.onboarding.tour import GuidedTour
from fieldflow.ui.onboarding.demo_runner import DemoRunner

from fieldflow.app.controls_store import ControlsStore
from fieldflow.app.controls_models import WorkPackage, RFI, Submittal

WALKTHROUGH_URL = "https://your-site.com/tutorials/getting-started"


class WelcomeDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.dont_show_again = True
        self.setWindowTitle("Welcome to FieldFlow")
        self.setModal(True)
        self.resize(640, 460)

        layout = QVBoxLayout(self)

        # --- Big logo ---
        logo = QLabel()
        logo.setAlignment(Qt.AlignCenter)
        pix = self._load_logo_pixmap()
        if pix is not None and not pix.isNull():
            logo.setPixmap(pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            logo.setText("FieldFlow")
            logo.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(logo)

        title = QLabel("Welcome to FieldFlow")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        msg = QLabel(
            "FieldFlow is an offline-first project-controls tool.\n\n"
            "Pick a quick start option:"
        )
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignCenter)
        layout.addWidget(msg)

        r1 = QHBoxLayout()
        self.btn_video = QPushButton("Watch walkthrough video")
        self.btn_sample = QPushButton("Load sample project")
        r1.addWidget(self.btn_video)
        r1.addWidget(self.btn_sample)
        layout.addLayout(r1)

        r2 = QHBoxLayout()
        self.btn_example = QPushButton("Load example data")
        self.btn_demo = QPushButton("Run Walkthrough Demo")
        r2.addWidget(self.btn_example)
        r2.addWidget(self.btn_demo)
        layout.addLayout(r2)

        r3 = QHBoxLayout()
        self.btn_tour = QPushButton("Start guided tour")
        r3.addWidget(self.btn_tour)
        r3.addStretch(1)
        layout.addLayout(r3)

        self.chk_dont = QCheckBox("Don’t show again")
        self.chk_dont.setChecked(True)
        self.chk_dont.stateChanged.connect(lambda _: self._sync_checkbox())
        layout.addWidget(self.chk_dont)

        r4 = QHBoxLayout()
        self.btn_close = QPushButton("Close")
        r4.addStretch(1)
        r4.addWidget(self.btn_close)
        layout.addLayout(r4)

        fine = QLabel("Tip: Reopen anytime via Help → Welcome / Walkthrough…")
        fine.setStyleSheet("color: #666;")
        fine.setWordWrap(True)
        fine.setAlignment(Qt.AlignCenter)
        layout.addWidget(fine)

        self.btn_video.clicked.connect(self._open_video)
        self.btn_sample.clicked.connect(self._load_sample)
        self.btn_example.clicked.connect(self._load_example_data)
        self.btn_demo.clicked.connect(self._run_demo)
        self.btn_tour.clicked.connect(self._start_tour)
        self.btn_close.clicked.connect(self.accept)

    def _sync_checkbox(self) -> None:
        self.dont_show_again = bool(self.chk_dont.isChecked())

    def _open_video(self) -> None:
        QDesktopServices.openUrl(QUrl(WALKTHROUGH_URL))

    def _load_sample(self) -> None:
        candidates = [
            Path(__file__).resolve().parent / "sample_project.fieldflow",
            Path(__file__).resolve().parents[2] / "example_data" / "sample_project.fieldflow",
        ]
        sample = next((p for p in candidates if p.exists()), None)
        if sample is None:
            QMessageBox.information(
                self,
                "Sample Project",
                "No bundled sample project found yet.\n\n"
                "For now you can use “Run Walkthrough Demo”.",
            )
            return

        try:
            self.ctx.open_project_file(sample)
            QMessageBox.information(self, "Sample Project", f"Loaded sample project:\n{sample}")
        except Exception as e:
            QMessageBox.warning(self, "Sample Project", f"Failed to load sample project:\n{e}")

    def _load_example_data(self) -> None:
        base = Path(__file__).resolve().parent / "sample_data"
        act_csv = base / "activities_example.csv"
        log_csv = base / "logic_example.csv"
        ctl_json = base / "controls_seed.json"

        if not (act_csv.exists() and log_csv.exists() and ctl_json.exists()):
            QMessageBox.warning(
                self,
                "Load example data",
                "Missing bundled sample_data files.\n"
                f"Expected:\n  {act_csv}\n  {log_csv}\n  {ctl_json}",
            )
            return

        try:
            self.ctx.import_activities(act_csv)
            self.ctx.import_logic(log_csv)

            data = json.loads(ctl_json.read_text(encoding="utf-8"))
            store = ControlsStore()

            def parse_date(s):
                if not s:
                    return None
                return date.fromisoformat(s)

            wps = [
                WorkPackage(
                    id=str(x.get("id", "")),
                    name=str(x.get("name", "")),
                    qty=float(x.get("qty", 0.0)),
                    unit=str(x.get("unit", "")),
                    unit_cost=float(x.get("unit_cost", 0.0)),
                    linked_activity_ids=str(x.get("linked_activity_ids", "")),
                )
                for x in data.get("work_packages", [])
            ]
            rfis = [
                RFI(
                    id=str(x.get("id", "")),
                    title=str(x.get("title", "")),
                    status=str(x.get("status", "Open")),
                    created=parse_date(x.get("created")),
                    due=parse_date(x.get("due")),
                    answered=parse_date(x.get("answered")),
                    linked_activity_ids=str(x.get("linked_activity_ids", "")),
                    impact_days=int(x.get("impact_days", 0) or 0),
                )
                for x in data.get("rfis", [])
            ]
            subs = [
                Submittal(
                    id=str(x.get("id", "")),
                    spec_section=str(x.get("spec_section", "")),
                    status=str(x.get("status", "Required")),
                    required_by_activity_id=str(x.get("required_by_activity_id", "")),
                    lead_time_days=int(x.get("lead_time_days", 0) or 0),
                    submit_date=parse_date(x.get("submit_date")),
                    approve_date=parse_date(x.get("approve_date")),
                )
                for x in data.get("submittals", [])
            ]
            store.save(self.ctx.project_key, wps, rfis, subs)

            shell = self.parent()
            if shell is not None and hasattr(shell, "_reload_pages"):
                try:
                    shell._reload_pages()  # type: ignore[attr-defined]
                except Exception:
                    pass

            QMessageBox.information(
                self,
                "Example data loaded",
                "Loaded example activities, logic, and controls.\n\nNext: Tools → Compute Both.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Load example data", f"Failed:\n{e}")

    def _run_demo(self) -> None:
        shell = self.parent()
        if shell is None:
            QMessageBox.warning(self, "Walkthrough Demo", "Demo requires main window as parent.")
            return

        self.accept()
        runner = DemoRunner(self.ctx, shell)
        runner.finished.connect(self._demo_finished)
        runner.run()

    def _demo_finished(self, ok: bool, msg: str) -> None:
        if not ok:
            QMessageBox.warning(self.parent(), "Walkthrough Demo", msg)

    def _start_tour(self) -> None:
        shell = self.parent()
        if shell is None or not hasattr(shell, "set_page"):
            QMessageBox.warning(self, "Guided Tour", "Tour requires the main window as parent.")
            return
        self.accept()
        try:
            GuidedTour(shell).start()  # type: ignore[arg-type]
        except Exception as e:
            QMessageBox.warning(self, "Guided Tour", f"Failed to start tour:\n{e}")

    def _load_logo_pixmap(self) -> QPixmap | None:
        try:
            # fieldflow/ui/onboarding/welcome_dialog.py -> fieldflow/ui/assets/fieldflow_icon.png
            icon_path = Path(__file__).resolve().parents[1] / "assets" / "fieldflow_icon.png"
            if icon_path.exists():
                return QPixmap(str(icon_path))
        except Exception:
            pass
        return None