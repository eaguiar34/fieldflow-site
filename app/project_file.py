from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectFile:
    project_key: str
    name: str = "Untitled Project"

    @staticmethod
    def new(name: str = "Untitled Project") -> "ProjectFile":
        return ProjectFile(project_key=str(uuid.uuid4()), name=name)


def load_project_file(path: Path) -> ProjectFile:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    project_key = str(data.get("project_key", "")).strip()
    if not project_key:
        raise ValueError("Invalid .fieldflow file: missing project_key")
    name = str(data.get("name", "Untitled Project"))
    return ProjectFile(project_key=project_key, name=name)


def save_project_file(path: Path, proj: ProjectFile) -> None:
    payload = {"project_key": proj.project_key, "name": proj.name}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")