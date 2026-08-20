import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from .domain import utc_now
from .execution_repository import ExecutionRepository


class MaintenanceService:
    def __init__(self, database_path: str | Path, execution: ExecutionRepository):
        self.database_path = Path(database_path)
        self.execution = execution

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def run(self, now: datetime | None = None) -> dict[str, Any]:
        timestamp = now or utc_now()
        expired = self.execution.expire_leases(timestamp)
        evidence = self.execution.prune_evidence(timestamp)
        return {"expired_leases": expired, "evidence": evidence, "ran_at": timestamp.isoformat()}

    def diagnostics(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            counts = {}
            for table, key in (
                ("tasks", "tasks"),
                ("execution_jobs", "jobs"),
                ("inbound_events", "inbound_events"),
                ("knowledge_versions", "knowledge_versions"),
            ):
                if self._table_exists(connection, table):
                    counts[key] = connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
            counts["pending_approvals"] = self._count_where(
                connection, "approvals", "status = 'PENDING'"
            )
            counts["active_leases"] = self._count_where(
                connection, "device_leases", "status = 'ACTIVE'"
            )
            counts["revoked_devices"] = self._count_where(
                connection, "devices", "token_revoked_at IS NOT NULL"
            )
        evidence_bytes = sum(
            item.stat().st_size for item in self.execution.evidence_dir.glob("*") if item.is_file()
        )
        return {
            "database_bytes": self.database_path.stat().st_size
            if self.database_path.exists()
            else 0,
            "evidence_bytes": evidence_bytes,
            "counts": counts,
            "generated_at": utc_now().isoformat(),
        }

    def export_redacted(self) -> dict[str, Any]:
        tables = (
            "tasks",
            "task_events",
            "execution_jobs",
            "audit_events",
            "approvals",
            "inbound_events",
            "order_snapshots",
            "knowledge_versions",
            "workflow_runs",
            "workflow_nodes",
        )
        excluded = {
            "token_digest",
            "code_digest",
            "payload_json",
            "content",
            "storage_path",
        }
        result: dict[str, Any] = {"exported_at": utc_now().isoformat(), "tables": {}}
        with closing(self._connect()) as connection:
            for table in tables:
                if not self._table_exists(connection, table):
                    continue
                rows = connection.execute(
                    f"SELECT * FROM {table}"
                ).fetchall()
                result["tables"][table] = [
                    {
                        key: self._redact_value(key, value)
                        for key, value in dict(row).items()
                        if key not in excluded
                    }
                    for row in rows
                ]
        return result

    @staticmethod
    def _redact_value(key: str, value: Any) -> Any:
        if value is None:
            return None
        if "token" in key.lower() or "authorization" in key.lower():
            return "[REDACTED]"
        if key in {"scope_json", "result_json", "context_json"}:
            parsed = json.loads(value)
            return MaintenanceService._redact_mapping(parsed)
        return value

    @staticmethod
    def _redact_mapping(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "[REDACTED]"
                if any(word in key.lower() for word in ("token", "password", "secret"))
                else MaintenanceService._redact_mapping(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [MaintenanceService._redact_mapping(item) for item in value]
        return value

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone() is not None

    @classmethod
    def _count_where(cls, connection: sqlite3.Connection, table: str, where: str) -> int:
        if not cls._table_exists(connection, table):
            return 0
        return connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {where}"
        ).fetchone()[0]
