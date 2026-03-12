from __future__ import annotations

import os
from pathlib import Path


def get_default_db_path(app_name: str = "FieldFlow", filename: str = "fieldflow.sqlite") -> Path:
    """
    Windows-friendly default location:
      %LOCALAPPDATA%\\FieldFlow\\fieldflow.sqlite

    Falls back to:
      <project_root>\\_local_data\\fieldflow.sqlite
    """
    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
    if local_appdata:
        base = Path(local_appdata) / app_name
    else:
        # Fallback: put it near the repo (useful for dev boxes / odd envs)
        base = Path.cwd() / "_local_data"

    base.mkdir(parents=True, exist_ok=True)
    return base / filename