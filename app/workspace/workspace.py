from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_MANIFEST_NAME = "project.ffproj.json"


@dataclass
class ProjectRoles:
    admins: List[str]
    editors: List[str]
    viewers: List[str]

    def can_edit(self, user: str) -> bool:
        u = (user or "").lower()
        return u in [x.lower() for x in (self.admins + self.editors)]

    def can_view(self, user: str) -> bool:
        u = (user or "").lower()
        return u in [x.lower() for x in (self.admins + self.editors + self.viewers)]


class ProjectWorkspace:
    """
    Project folder packaging layer.

    This does NOT change CPM logic or core scheduling data structures.
    It provides:
      - folder layout
      - manifest (project identity, roles, shared library root)
      - standard subfolders (locks/events/snapshots/attachments)
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.manifest_path = self.root / DEFAULT_MANIFEST_NAME
        self.locks_dir = self.root / "locks"
        self.events_dir = self.root / "events"
        self.snapshots_dir = self.root / "snapshots"
        self.attachments_dir = self.root / "attachments"

        # Project identity (used as DB key and for sharing).
        self.project_key: str = ""
        self.project_name: str = "Untitled Project"

        self.shared_library_root: str = ""
        self.roles = ProjectRoles(admins=[], editors=[], viewers=[])

    @staticmethod
    def current_user() -> str:
        # Best-effort identity for Windows domain environments
        return os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"

    def ensure_layout(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.locks_dir.mkdir(exist_ok=True)
        self.events_dir.mkdir(exist_ok=True)
        self.snapshots_dir.mkdir(exist_ok=True)
        self.attachments_dir.mkdir(exist_ok=True)

        if not self.manifest_path.exists():
            self._write_default_manifest()

        self.load_manifest()

    def _write_default_manifest(self) -> None:
        payload = {
            "format": "fieldflow_project_folder_v2",
            "created_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "project_key": "",
            "project_name": "Untitled Project",
            "shared_library_root": "",
            "roles": {
                "admins": [self.current_user()],
                "editors": [self.current_user()],
                "viewers": [],
            },
        }
        self.manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_manifest(self) -> None:
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}

        # v2 fields (v1 projects simply won't have these).
        self.project_key = str(data.get("project_key", "") or "").strip()
        self.project_name = str(data.get("project_name", "Untitled Project") or "Untitled Project")

        self.shared_library_root = str(data.get("shared_library_root", "") or "")

        roles = data.get("roles", {}) or {}
        self.roles = ProjectRoles(
            admins=[str(x) for x in (roles.get("admins", []) or [])],
            editors=[str(x) for x in (roles.get("editors", []) or [])],
            viewers=[str(x) for x in (roles.get("viewers", []) or [])],
        )

    def save_manifest(self) -> None:
        payload = {
            "format": "fieldflow_project_folder_v2",
            "project_key": self.project_key,
            "project_name": self.project_name,
            "shared_library_root": self.shared_library_root,
            "roles": {
                "admins": list(self.roles.admins),
                "editors": list(self.roles.editors),
                "viewers": list(self.roles.viewers),
            },
        }
        self.manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def user_can_edit(self) -> bool:
        user = self.current_user()
        # If roles are empty (legacy), allow edit; otherwise enforce.
        if not (self.roles.admins or self.roles.editors or self.roles.viewers):
            return True
        return self.roles.can_edit(user)

    def user_can_view(self) -> bool:
        user = self.current_user()
        if not (self.roles.admins or self.roles.editors or self.roles.viewers):
            return True
        return self.roles.can_view(user)