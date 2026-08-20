import csv
import hashlib
import io
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


class BusinessDataService:
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
                CREATE TABLE IF NOT EXISTS order_snapshots (
                  order_id TEXT PRIMARY KEY,
                  source TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_versions (
                  knowledge_id TEXT NOT NULL,
                  version TEXT NOT NULL,
                  title TEXT NOT NULL,
                  content TEXT NOT NULL,
                  media_type TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  PRIMARY KEY(knowledge_id, version)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                  knowledge_id UNINDEXED, version UNINDEXED, title, content,
                  tokenize='trigram'
                );
                CREATE TABLE IF NOT EXISTS image_analysis_requests (
                  request_id TEXT PRIMARY KEY,
                  artifact_id TEXT NOT NULL,
                  provider TEXT,
                  status TEXT NOT NULL,
                  result_json TEXT,
                  reason TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                """
            )

    def import_orders(
        self, rows: list[dict[str, Any]], source: str, now: datetime | None = None
    ) -> dict[str, int]:
        timestamp = (now or utc_now()).isoformat()
        imported = 0
        unchanged = 0
        with closing(self._connect()) as connection, connection:
            for row in rows:
                order_id = str(row.get("order_id", "")).strip()
                if not order_id:
                    raise ValueError("every order snapshot requires order_id")
                canonical = _json(row)
                digest = hashlib.sha256(canonical.encode()).hexdigest()
                existing = connection.execute(
                    "SELECT content_sha256 FROM order_snapshots WHERE order_id = ?",
                    (order_id,),
                ).fetchone()
                if existing and existing["content_sha256"] == digest:
                    unchanged += 1
                    continue
                connection.execute(
                    """INSERT INTO order_snapshots VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(order_id) DO UPDATE SET source=excluded.source,
                       payload_json=excluded.payload_json,
                       content_sha256=excluded.content_sha256,
                       updated_at=excluded.updated_at""",
                    (order_id, source, canonical, digest, timestamp),
                )
                imported += 1
        return {"imported": imported, "unchanged": unchanged}

    def import_orders_csv(self, content: str, source: str) -> dict[str, int]:
        return self.import_orders(list(csv.DictReader(io.StringIO(content))), source)

    def get_order(self, order_id: str) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM order_snapshots WHERE order_id = ?", (order_id,)
            ).fetchone()
        if row is None:
            raise LookupError(order_id)
        return {
            **json.loads(row["payload_json"]),
            "snapshot_source": row["source"],
            "snapshot_updated_at": row["updated_at"],
        }

    def put_knowledge(
        self,
        knowledge_id: str,
        version: str,
        title: str,
        content: str,
        media_type: str = "text/markdown",
        now: datetime | None = None,
    ) -> dict[str, str]:
        if media_type not in {"text/markdown", "application/json"}:
            raise ValueError("unsupported knowledge media type")
        digest = hashlib.sha256(content.encode()).hexdigest()
        created_at = (now or utc_now()).isoformat()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT OR IGNORE INTO knowledge_versions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (knowledge_id, version, title, content, media_type, digest, created_at),
            )
            connection.execute(
                """INSERT INTO knowledge_fts(knowledge_id, version, title, content)
                   SELECT ?, ?, ?, ? WHERE NOT EXISTS (
                     SELECT 1 FROM knowledge_fts WHERE knowledge_id = ? AND version = ?
                   )""",
                (knowledge_id, version, title, content, knowledge_id, version),
            )
        return {
            "knowledge_id": knowledge_id,
            "version": version,
            "content_sha256": digest,
            "created_at": created_at,
        }

    def search_knowledge(self, query: str, limit: int = 10) -> list[dict[str, str]]:
        if not query.strip():
            return []
        with closing(self._connect()) as connection:
            if len(query.strip()) < 3:
                rows = connection.execute(
                    """SELECT knowledge_id, version, title, substr(content, 1, 120) AS excerpt
                       FROM knowledge_versions WHERE title LIKE ? OR content LIKE ? LIMIT ?""",
                    (f"%{query}%", f"%{query}%", limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT knowledge_id, version, title,
                       snippet(knowledge_fts, 3, '', '', '…', 24) AS excerpt
                       FROM knowledge_fts WHERE knowledge_fts MATCH ? LIMIT ?""",
                    (query, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def create_image_analysis(
        self, artifact_id: str, provider: str | None = None, now: datetime | None = None
    ) -> dict[str, Any]:
        timestamp = (now or utc_now()).isoformat()
        request_id = str(uuid4())
        status = "QUEUED" if provider else "UNAVAILABLE"
        reason = None if provider else "VISION_PROVIDER_NOT_CONFIGURED"
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO image_analysis_requests VALUES (?, ?, ?, ?, NULL, ?, ?, ?)",
                (request_id, artifact_id, provider, status, reason, timestamp, timestamp),
            )
        return self.get_image_analysis(request_id)

    def complete_image_analysis(
        self, request_id: str, result: dict[str, Any], now: datetime | None = None
    ) -> dict[str, Any]:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """UPDATE image_analysis_requests SET status='SUCCEEDED', result_json=?,
                   reason=NULL, updated_at=? WHERE request_id=? AND status='QUEUED'""",
                (_json(result), (now or utc_now()).isoformat(), request_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("image analysis request is not queued")
        return self.get_image_analysis(request_id)

    def get_image_analysis(self, request_id: str) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM image_analysis_requests WHERE request_id = ?", (request_id,)
            ).fetchone()
        if row is None:
            raise LookupError(request_id)
        return {
            "request_id": row["request_id"],
            "artifact_id": row["artifact_id"],
            "provider": row["provider"],
            "status": row["status"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "reason": row["reason"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
