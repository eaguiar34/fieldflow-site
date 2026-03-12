from __future__ import annotations

from PySide6.QtGui import QAction
from fieldflow.ui.shell.app_context import AppContext


class Actions:
    def __init__(self, ctx: AppContext, parent) -> None:
        self.ctx = ctx
        self.parent = parent

        self.open_project = QAction("Open Project…", parent)
        self.open_workspace = QAction("Open Workspace Folder…", parent)
        self.save_project_as = QAction("Save Project As…", parent)
        self.publish_snapshot = QAction("Publish Snapshot…", parent)
        self.changes_since = QAction("Changes Since…", parent)
        self.sync_now = QAction("Sync Now", parent)
        self.exit_app = QAction("Exit", parent)

        self.import_activities = QAction("Import Activities…", parent)
        self.import_logic = QAction("Import Logic…", parent)
        self.set_start_date = QAction("Set Start Date…", parent)
        self.clear_holidays = QAction("Clear Holidays", parent)

        self.compute_cpm = QAction("Compute CPM", parent)
        self.compute_both = QAction("Compute Both", parent)

        self.reset_layout = QAction("Reset Layout", parent)

        # Help
        self.welcome_walkthrough = QAction("Welcome / Walkthrough…", parent)
        self.reset_onboarding = QAction("Reset Onboarding", parent)
        self.about = QAction("About", parent)
        self.tutorials = QAction("Tutorials", parent)