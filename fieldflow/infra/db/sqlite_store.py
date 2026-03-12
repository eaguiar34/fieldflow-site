from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


SCHEMA_VERSION = 5
# v1: calendar + constraints
# v2: last-used paths columns
# v3: baseline_activities + baseline_relationships
# v4: scenarios + scenario_activities + scenario_relationships
# v5: project_settings.active_scenario_name


@dataclass(frozen=True)
class PersistedProjectSettings:
    project_key: str
    start_date_iso: Optional[str]
    holidays_iso: Set[str]
    last_activities_path: Optional[str]
    last_logic_path: Optional[str]
    active_scenario_name: Optional[str]


@dataclass(frozen=True)
class PersistedActivityRow:
    id: str
    name: str
    duration_days: int
    snet_iso: Optional[str]
    fnet_iso: Optional[str]
    sort_order: int


@dataclass(frozen=True)
class PersistedRelationshipRow:
    pred_id: str
    succ_id: str
    rel_type: str
    lag_days: int
    sort_order: int


@dataclass(frozen=True)
class PersistedScenario:
    scenario_id: int
    name: str


class SQLiteStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(self.db_path))
        con.execute("PRAGMA foreign_keys = ON;")
        con.execute("PRAGMA journal_mode = WAL;")
        return con

    def initialize(self) -> None:
        with self.connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            row = con.execute("SELECT value FROM meta WHERE key='schema_version';").fetchone()
            current = int(row[0]) if row else 0

            if current == 0:
                self._create_v1(con)
                con.execute("INSERT INTO meta(key, value) VALUES('schema_version', '1');")
                current = 1

            if current < 2:
                self._ensure_v2_cols(con)
                con.execute("UPDATE meta SET value='2' WHERE key='schema_version';")
                current = 2

            if current < 3:
                self._ensure_v3_tables(con)
                con.execute("UPDATE meta SET value='3' WHERE key='schema_version';")
                current = 3

            if current < 4:
                self._ensure_v4_tables(con)
                con.execute("UPDATE meta SET value='4' WHERE key='schema_version';")
                current = 4

            if current < 5:
                self._ensure_v5_cols(con)
                con.execute("UPDATE meta SET value='5' WHERE key='schema_version';")
                current = 5

            # Safety net: always ensure everything exists
            self._ensure_v2_cols(con)
            self._ensure_v3_tables(con)
            self._ensure_v4_tables(con)
            self._ensure_v5_cols(con)

    def _create_v1(self, con: sqlite3.Connection) -> None:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                project_key TEXT PRIMARY KEY,
                created_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS project_settings (
                project_key TEXT PRIMARY KEY,
                start_date_iso TEXT NULL,
                FOREIGN KEY(project_key) REFERENCES projects(project_key) ON DELETE CASCADE
            );
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS project_holidays (
                project_key TEXT NOT NULL,
                holiday_iso TEXT NOT NULL,
                PRIMARY KEY(project_key, holiday_iso),
                FOREIGN KEY(project_key) REFERENCES projects(project_key) ON DELETE CASCADE
            );
            """
        )

    def _ensure_v2_cols(self, con: sqlite3.Connection) -> None:
        cols = {r[1] for r in con.execute("PRAGMA table_info(project_settings);").fetchall()}
        if "last_activities_path" not in cols:
            con.execute("ALTER TABLE project_settings ADD COLUMN last_activities_path TEXT NULL;")
        if "last_logic_path" not in cols:
            con.execute("ALTER TABLE project_settings ADD COLUMN last_logic_path TEXT NULL;")

    def _ensure_v3_tables(self, con: sqlite3.Connection) -> None:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS baseline_activities (
                project_key TEXT NOT NULL,
                activity_id TEXT NOT NULL,
                name TEXT NOT NULL,
                duration_days INTEGER NOT NULL,
                snet_iso TEXT NULL,
                fnet_iso TEXT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(project_key, activity_id),
                FOREIGN KEY(project_key) REFERENCES projects(project_key) ON DELETE CASCADE
            );
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS baseline_relationships (
                project_key TEXT NOT NULL,
                pred_id TEXT NOT NULL,
                succ_id TEXT NOT NULL,
                rel_type TEXT NOT NULL,
                lag_days INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(project_key, pred_id, succ_id, sort_order),
                FOREIGN KEY(project_key) REFERENCES projects(project_key) ON DELETE CASCADE
            );
            """
        )

    def _ensure_v4_tables(self, con: sqlite3.Connection) -> None:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS scenarios (
                project_key TEXT NOT NULL,
                scenario_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                FOREIGN KEY(project_key) REFERENCES projects(project_key) ON DELETE CASCADE
            );
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS scenario_activities (
                project_key TEXT NOT NULL,
                scenario_id INTEGER NOT NULL,
                activity_id TEXT NOT NULL,
                name TEXT NOT NULL,
                duration_days INTEGER NOT NULL,
                snet_iso TEXT NULL,
                fnet_iso TEXT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(project_key, scenario_id, activity_id),
                FOREIGN KEY(project_key) REFERENCES projects(project_key) ON DELETE CASCADE,
                FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id) ON DELETE CASCADE
            );
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS scenario_relationships (
                project_key TEXT NOT NULL,
                scenario_id INTEGER NOT NULL,
                pred_id TEXT NOT NULL,
                succ_id TEXT NOT NULL,
                rel_type TEXT NOT NULL,
                lag_days INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(project_key, scenario_id, pred_id, succ_id, sort_order),
                FOREIGN KEY(project_key) REFERENCES projects(project_key) ON DELETE CASCADE,
                FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id) ON DELETE CASCADE
            );
            """
        )

    def _ensure_v5_cols(self, con: sqlite3.Connection) -> None:
        cols = {r[1] for r in con.execute("PRAGMA table_info(project_settings);").fetchall()}
        if "active_scenario_name" not in cols:
            con.execute("ALTER TABLE project_settings ADD COLUMN active_scenario_name TEXT NULL;")

    # -------------------------
    # Projects + settings
    # -------------------------
    def ensure_project(self, project_key: str) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO projects(project_key) VALUES(?)
                ON CONFLICT(project_key) DO UPDATE SET
                    updated_utc = (strftime('%Y-%m-%dT%H:%M:%fZ','now'));
                """,
                (project_key,),
            )
            con.execute(
                """
                INSERT INTO project_settings(project_key, start_date_iso, last_activities_path, last_logic_path, active_scenario_name)
                VALUES(?, NULL, NULL, NULL, NULL)
                ON CONFLICT(project_key) DO NOTHING;
                """,
                (project_key,),
            )

    def _touch(self, con: sqlite3.Connection, project_key: str) -> None:
        con.execute(
            "UPDATE projects SET updated_utc=(strftime('%Y-%m-%dT%H:%M:%fZ','now')) WHERE project_key=?;",
            (project_key,),
        )

    def load_project_settings(self, project_key: str) -> PersistedProjectSettings:
        self.ensure_project(project_key)
        with self.connect() as con:
            row = con.execute(
                """
                SELECT start_date_iso, last_activities_path, last_logic_path, active_scenario_name
                FROM project_settings
                WHERE project_key=?;
                """,
                (project_key,),
            ).fetchone()

            start_date_iso = row[0] if row else None
            last_acts = row[1] if row else None
            last_logic = row[2] if row else None
            active_name = row[3] if row else None

            holidays = con.execute(
                "SELECT holiday_iso FROM project_holidays WHERE project_key=? ORDER BY holiday_iso;",
                (project_key,),
            ).fetchall()
            holiday_set = {r[0] for r in holidays}

        return PersistedProjectSettings(
            project_key=project_key,
            start_date_iso=start_date_iso,
            holidays_iso=holiday_set,
            last_activities_path=last_acts,
            last_logic_path=last_logic,
            active_scenario_name=active_name,
        )

    def save_project_calendar(self, project_key: str, start_date_iso: Optional[str], holidays_iso: Iterable[str]) -> None:
        self.ensure_project(project_key)
        holidays_list = sorted(set(holidays_iso))
        with self.connect() as con:
            con.execute(
                "UPDATE project_settings SET start_date_iso=? WHERE project_key=?;",
                (start_date_iso, project_key),
            )
            con.execute("DELETE FROM project_holidays WHERE project_key=?;", (project_key,))
            con.executemany(
                "INSERT INTO project_holidays(project_key, holiday_iso) VALUES(?, ?);",
                [(project_key, h) for h in holidays_list],
            )
            self._touch(con, project_key)

    def save_last_used_paths(self, project_key: str, activities_path: Optional[str], logic_path: Optional[str]) -> None:
        self.ensure_project(project_key)
        with self.connect() as con:
            con.execute(
                """
                UPDATE project_settings
                SET last_activities_path=?, last_logic_path=?
                WHERE project_key=?;
                """,
                (activities_path, logic_path, project_key),
            )
            self._touch(con, project_key)

    def save_active_scenario_name(self, project_key: str, active_name: Optional[str]) -> None:
        self.ensure_project(project_key)
        with self.connect() as con:
            con.execute(
                "UPDATE project_settings SET active_scenario_name=? WHERE project_key=?;",
                (active_name, project_key),
            )
            self._touch(con, project_key)

    # -------------------------
    # Baseline load/save
    # -------------------------
    def load_baseline_activities(self, project_key: str) -> List[PersistedActivityRow]:
        self.ensure_project(project_key)
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT activity_id, name, duration_days, snet_iso, fnet_iso, sort_order
                FROM baseline_activities
                WHERE project_key=?
                ORDER BY sort_order, activity_id;
                """,
                (project_key,),
            ).fetchall()
        return [PersistedActivityRow(str(r[0]), str(r[1]), int(r[2]), r[3], r[4], int(r[5])) for r in rows]

    def save_baseline_activities(self, project_key: str, rows: List[PersistedActivityRow]) -> None:
        self.ensure_project(project_key)
        with self.connect() as con:
            con.execute("DELETE FROM baseline_activities WHERE project_key=?;", (project_key,))
            con.executemany(
                """
                INSERT INTO baseline_activities(project_key, activity_id, name, duration_days, snet_iso, fnet_iso, sort_order)
                VALUES(?, ?, ?, ?, ?, ?, ?);
                """,
                [(project_key, r.id, r.name, r.duration_days, r.snet_iso, r.fnet_iso, r.sort_order) for r in rows],
            )
            self._touch(con, project_key)

    def load_baseline_relationships(self, project_key: str) -> List[PersistedRelationshipRow]:
        self.ensure_project(project_key)
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT pred_id, succ_id, rel_type, lag_days, sort_order
                FROM baseline_relationships
                WHERE project_key=?
                ORDER BY sort_order, pred_id, succ_id;
                """,
                (project_key,),
            ).fetchall()
        return [PersistedRelationshipRow(str(r[0]), str(r[1]), str(r[2]), int(r[3]), int(r[4])) for r in rows]

    def save_baseline_relationships(self, project_key: str, rows: List[PersistedRelationshipRow]) -> None:
        self.ensure_project(project_key)
        with self.connect() as con:
            con.execute("DELETE FROM baseline_relationships WHERE project_key=?;", (project_key,))
            con.executemany(
                """
                INSERT INTO baseline_relationships(project_key, pred_id, succ_id, rel_type, lag_days, sort_order)
                VALUES(?, ?, ?, ?, ?, ?);
                """,
                [(project_key, r.pred_id, r.succ_id, r.rel_type, r.lag_days, r.sort_order) for r in rows],
            )
            self._touch(con, project_key)

    # -------------------------
    # Scenarios CRUD
    # -------------------------
    def list_scenarios(self, project_key: str) -> List[PersistedScenario]:
        self.ensure_project(project_key)
        with self.connect() as con:
            rows = con.execute(
                "SELECT scenario_id, name FROM scenarios WHERE project_key=? ORDER BY scenario_id;",
                (project_key,),
            ).fetchall()
        return [PersistedScenario(int(r[0]), str(r[1])) for r in rows]

    def create_scenario(self, project_key: str, name: str) -> int:
        self.ensure_project(project_key)
        with self.connect() as con:
            cur = con.execute("INSERT INTO scenarios(project_key, name) VALUES(?, ?);", (project_key, name))
            scenario_id = int(cur.lastrowid)
            self._touch(con, project_key)
        return scenario_id

    def delete_scenario(self, project_key: str, scenario_id: int) -> None:
        self.ensure_project(project_key)
        with self.connect() as con:
            con.execute("DELETE FROM scenarios WHERE project_key=? AND scenario_id=?;", (project_key, scenario_id))
            self._touch(con, project_key)

    def load_scenario_activities(self, project_key: str, scenario_id: int) -> List[PersistedActivityRow]:
        self.ensure_project(project_key)
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT activity_id, name, duration_days, snet_iso, fnet_iso, sort_order
                FROM scenario_activities
                WHERE project_key=? AND scenario_id=?
                ORDER BY sort_order, activity_id;
                """,
                (project_key, scenario_id),
            ).fetchall()
        return [PersistedActivityRow(str(r[0]), str(r[1]), int(r[2]), r[3], r[4], int(r[5])) for r in rows]

    def save_scenario_activities(self, project_key: str, scenario_id: int, rows: List[PersistedActivityRow]) -> None:
        self.ensure_project(project_key)
        with self.connect() as con:
            con.execute("DELETE FROM scenario_activities WHERE project_key=? AND scenario_id=?;", (project_key, scenario_id))
            con.executemany(
                """
                INSERT INTO scenario_activities(project_key, scenario_id, activity_id, name, duration_days, snet_iso, fnet_iso, sort_order)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?);
                """,
                [(project_key, scenario_id, r.id, r.name, r.duration_days, r.snet_iso, r.fnet_iso, r.sort_order) for r in rows],
            )
            self._touch(con, project_key)

    def load_scenario_relationships(self, project_key: str, scenario_id: int) -> List[PersistedRelationshipRow]:
        self.ensure_project(project_key)
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT pred_id, succ_id, rel_type, lag_days, sort_order
                FROM scenario_relationships
                WHERE project_key=? AND scenario_id=?
                ORDER BY sort_order, pred_id, succ_id;
                """,
                (project_key, scenario_id),
            ).fetchall()
        return [PersistedRelationshipRow(str(r[0]), str(r[1]), str(r[2]), int(r[3]), int(r[4])) for r in rows]

    def save_scenario_relationships(self, project_key: str, scenario_id: int, rows: List[PersistedRelationshipRow]) -> None:
        self.ensure_project(project_key)
        with self.connect() as con:
            con.execute("DELETE FROM scenario_relationships WHERE project_key=? AND scenario_id=?;", (project_key, scenario_id))
            con.executemany(
                """
                INSERT INTO scenario_relationships(project_key, scenario_id, pred_id, succ_id, rel_type, lag_days, sort_order)
                VALUES(?, ?, ?, ?, ?, ?, ?);
                """,
                [(project_key, scenario_id, r.pred_id, r.succ_id, r.rel_type, r.lag_days, r.sort_order) for r in rows],
            )
            self._touch(con, project_key)