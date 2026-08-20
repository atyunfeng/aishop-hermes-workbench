import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from .repository import IdempotencyConflict
from .service import TaskService


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class InboundEventService:
    SOURCES = frozenset({"qian-niu", "dou-dian", "we-chat", "we-com", "qq"})

    def __init__(self, database_path: str | Path, tasks: TaskService):
        self.database_path = Path(database_path)
        self.tasks = tasks
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS inbound_events (
                  identity_key TEXT PRIMARY KEY,
                  event_id TEXT NOT NULL,
                  source TEXT NOT NULL,
                  account_id TEXT NOT NULL,
                  conversation_id TEXT NOT NULL,
                  sender TEXT NOT NULL,
                  event_type TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  payload_sha256 TEXT NOT NULL,
                  device_id TEXT NOT NULL,
                  status TEXT NOT NULL,
                  task_id TEXT,
                  occurred_at TEXT NOT NULL,
                  received_at TEXT NOT NULL
                )"""
            )

    def ingest(
        self, device_id: str, payload: dict[str, Any], received_at: datetime
    ) -> dict[str, Any]:
        identity = f"{payload['source']}/{payload['account_id']}/{payload['event_id']}"
        canonical = _json(payload)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM inbound_events WHERE identity_key = ?", (identity,)
            ).fetchone()
            if existing:
                if existing["payload_sha256"] != digest:
                    connection.rollback()
                    raise IdempotencyConflict("inbound event identity reused with different payload")
                connection.commit()
                task = (
                    self.tasks.get_task(existing["task_id"])
                    if existing["task_id"]
                    else None
                )
                return {"event": self._envelope(existing), "task": task, "duplicate": True}
            known = payload["source"] in self.SOURCES
            status = "ROUTED" if known else "QUARANTINED"
            connection.execute(
                """INSERT INTO inbound_events VALUES
                   (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
                (
                    identity,
                    payload["event_id"],
                    payload["source"],
                    payload["account_id"],
                    payload["conversation_id"],
                    payload["sender"],
                    payload["event_type"],
                    canonical,
                    digest,
                    device_id,
                    status,
                    payload["occurred_at"],
                    received_at.isoformat(),
                ),
            )
            connection.commit()
        task = None
        if known:
            title_text = payload.get("text", "").strip().replace("\n", " ")[:80]
            title = f"{payload['sender']}: {title_text or payload['event_type']}"
            task = self.tasks.create_task(f"event:{identity}", payload["source"], title)
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    "UPDATE inbound_events SET task_id = ? WHERE identity_key = ?",
                    (task["task_id"], identity),
                )
        return {
            "event": self.get(identity),
            "task": task,
            "duplicate": False,
        }

    def get(self, identity_key: str) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM inbound_events WHERE identity_key = ?", (identity_key,)
            ).fetchone()
        if row is None:
            raise LookupError(identity_key)
        return self._envelope(row)

    def list_pending(self, limit: int = 50) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT * FROM inbound_events WHERE status IN ('ROUTED', 'QUARANTINED')
                   ORDER BY received_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [self._envelope(row) for row in rows]

    @staticmethod
    def _envelope(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "identity_key": row["identity_key"],
            "event_id": row["event_id"],
            "source": row["source"],
            "account_id": row["account_id"],
            "conversation_id": row["conversation_id"],
            "sender": row["sender"],
            "event_type": row["event_type"],
            "payload": json.loads(row["payload_json"]),
            "device_id": row["device_id"],
            "status": row["status"],
            "task_id": row["task_id"],
            "occurred_at": row["occurred_at"],
            "received_at": row["received_at"],
        }
