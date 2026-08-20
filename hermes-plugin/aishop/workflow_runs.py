import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .domain import utc_now


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class WorkflowRunService:
    TERMINAL = frozenset({"SUCCEEDED", "FAILED", "HUMAN_TAKEOVER"})

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflow_runs (
                  run_id TEXT PRIMARY KEY,
                  parent_task_id TEXT NOT NULL,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_nodes (
                  node_id TEXT PRIMARY KEY,
                  run_id TEXT NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
                  name TEXT NOT NULL,
                  target TEXT NOT NULL,
                  dependencies_json TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  status TEXT NOT NULL,
                  task_id TEXT,
                  job_id TEXT,
                  result_json TEXT,
                  updated_at TEXT NOT NULL
                );
                """
            )

    def create(
        self,
        parent_task_id: str,
        nodes: list[dict[str, Any]],
        run_id: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = now or utc_now()
        safe_run_id = run_id or str(uuid4())
        ids = [str(node["node_id"]) for node in nodes]
        if len(ids) != len(set(ids)) or not ids:
            raise ValueError("workflow node ids must be unique and non-empty")
        known = set(ids)
        for node in nodes:
            dependencies = set(node.get("dependencies", []))
            if str(node["node_id"]) in dependencies or not dependencies.issubset(known):
                raise ValueError("workflow dependencies must reference other nodes")
        self._assert_acyclic(nodes)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO workflow_runs VALUES (?, ?, 'RUNNING', ?, ?)",
                (safe_run_id, parent_task_id, timestamp.isoformat(), timestamp.isoformat()),
            )
            connection.executemany(
                """INSERT INTO workflow_nodes
                   (node_id, run_id, name, target, dependencies_json, payload_json,
                    status, task_id, job_id, result_json, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'PENDING', NULL, NULL, NULL, ?)""",
                [
                    (
                        str(node["node_id"]),
                        safe_run_id,
                        str(node["name"]),
                        str(node["target"]),
                        _json(node.get("dependencies", [])),
                        _json(node.get("payload", {})),
                        timestamp.isoformat(),
                    )
                    for node in nodes
                ],
            )
            connection.commit()
        return self.get(safe_run_id)

    def ready_nodes(self, run_id: str) -> list[dict[str, Any]]:
        run = self.get(run_id)
        statuses = {node["node_id"]: node["status"] for node in run["nodes"]}
        return [
            node
            for node in run["nodes"]
            if node["status"] == "PENDING"
            and all(statuses[item] == "SUCCEEDED" for item in node["dependencies"])
        ]

    def start_node(
        self,
        node_id: str,
        task_id: str,
        job_id: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = now or utc_now()
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """UPDATE workflow_nodes SET status='RUNNING', task_id=?, job_id=?, updated_at=?
                   WHERE node_id=? AND status='PENDING'""",
                (task_id, job_id, timestamp.isoformat(), node_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("workflow node is not pending")
        return self.get_node(node_id)

    def complete_node(
        self,
        node_id: str,
        status: str,
        result: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if status not in self.TERMINAL:
            raise ValueError("invalid terminal workflow node status")
        timestamp = now or utc_now()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM workflow_nodes WHERE node_id = ?", (node_id,)
            ).fetchone()
            if row is None:
                connection.rollback()
                raise LookupError(node_id)
            if row["status"] in self.TERMINAL:
                if row["status"] != status or json.loads(row["result_json"]) != result:
                    connection.rollback()
                    raise ValueError("workflow node result conflicts with prior completion")
                connection.commit()
                return self.get_node(node_id)
            connection.execute(
                """UPDATE workflow_nodes SET status=?, result_json=?, updated_at=?
                   WHERE node_id=?""",
                (status, _json(result), timestamp.isoformat(), node_id),
            )
            run_id = row["run_id"]
            connection.commit()
        self.aggregate(run_id, timestamp)
        return self.get_node(node_id)

    def aggregate(
        self, run_id: str, now: datetime | None = None
    ) -> dict[str, Any]:
        timestamp = now or utc_now()
        run = self.get(run_id)
        statuses_by_id = {node["node_id"]: node["status"] for node in run["nodes"]}
        blocked = [
            node
            for node in run["nodes"]
            if node["status"] == "PENDING"
            and any(
                statuses_by_id[dependency] in {"FAILED", "HUMAN_TAKEOVER"}
                for dependency in node["dependencies"]
            )
        ]
        if blocked:
            with closing(self._connect()) as connection, connection:
                for node in blocked:
                    connection.execute(
                        """UPDATE workflow_nodes SET status='FAILED', result_json=?, updated_at=?
                           WHERE node_id=? AND status='PENDING'""",
                        (
                            _json({"code": "DEPENDENCY_FAILED"}),
                            timestamp.isoformat(),
                            node["node_id"],
                        ),
                    )
            run = self.get(run_id)
        statuses = [node["status"] for node in run["nodes"]]
        if any(status == "HUMAN_TAKEOVER" for status in statuses):
            status = "HUMAN_TAKEOVER"
        elif all(status == "SUCCEEDED" for status in statuses):
            status = "SUCCEEDED"
        elif all(status in self.TERMINAL for status in statuses):
            status = "PARTIAL_SUCCESS" if "SUCCEEDED" in statuses else "FAILED"
        else:
            status = "RUNNING"
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE workflow_runs SET status=?, updated_at=? WHERE run_id=?",
                (status, timestamp.isoformat(), run_id),
            )
        return self.get(run_id)

    def get(self, run_id: str) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            run = connection.execute(
                "SELECT * FROM workflow_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            nodes = connection.execute(
                "SELECT * FROM workflow_nodes WHERE run_id = ? ORDER BY rowid", (run_id,)
            ).fetchall()
        if run is None:
            raise LookupError(run_id)
        return {
            "run_id": run["run_id"],
            "parent_task_id": run["parent_task_id"],
            "status": run["status"],
            "created_at": run["created_at"],
            "updated_at": run["updated_at"],
            "nodes": [self._node(row) for row in nodes],
        }

    def get_node(self, node_id: str) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM workflow_nodes WHERE node_id = ?", (node_id,)
            ).fetchone()
        if row is None:
            raise LookupError(node_id)
        return self._node(row)

    @staticmethod
    def _node(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "node_id": row["node_id"],
            "name": row["name"],
            "target": row["target"],
            "dependencies": json.loads(row["dependencies_json"]),
            "payload": json.loads(row["payload_json"]),
            "status": row["status"],
            "task_id": row["task_id"],
            "job_id": row["job_id"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
        }

    @staticmethod
    def _assert_acyclic(nodes: list[dict[str, Any]]) -> None:
        graph = {
            str(node["node_id"]): set(node.get("dependencies", [])) for node in nodes
        }
        remaining = set(graph)
        resolved: set[str] = set()
        while remaining:
            ready = {node for node in remaining if graph[node].issubset(resolved)}
            if not ready:
                raise ValueError("workflow graph contains a cycle")
            resolved.update(ready)
            remaining -= ready
