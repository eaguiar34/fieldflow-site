from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

# ---- Spyder / import robustness: pin project root on sys.path ----
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[2]  # .../FieldFlow
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fieldflow.ui.shell.app_context import AppContext
from fieldflow.ui.shell.main_window import ShellMainWindow


def _load_app_icon() -> QIcon:
    icon_path = Path(__file__).resolve().parent / "assets" / "fieldflow_icon.png"
    if icon_path.exists():
        return QIcon(str(icon_path))
    return QIcon()  # fallback: empty icon


def run() -> None:
    app = QApplication.instance()
    created_app = False
    if app is None:
        app = QApplication(sys.argv)
        created_app = True

    # App icon (taskbar + dialogs) + window icon
    icon = _load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    app.setQuitOnLastWindowClosed(False)

    ctx = AppContext()
    win = ShellMainWindow(ctx)
    if not icon.isNull():
        win.setWindowIcon(icon)

    ctx.signals.project_loaded.connect(lambda: win.log("Project loaded."))
    ctx.signals.active_scenario_changed.connect(lambda name: win.log(f"Active scenario: {name}"))
    ctx.signals.schedule_computed.connect(lambda: win.log("Schedule computed."))
    ctx.signals.schedule_compared.connect(lambda: win.log("Schedule compared."))

    win.show()

    # IMPORTANT: Only exec if we created the QApplication in this run.
    if created_app:
        app.exec()


if __name__ == "__main__":
    run()