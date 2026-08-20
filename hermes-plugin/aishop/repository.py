import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .domain import TaskEvent, TaskRecord, TaskState, utc_now
from .state_machine import require_transition


class TaskNotFound(LookupError):
    pass


class VersionConflict(RuntimeError):
    pass


class IdempotencyConflict(RuntimeError):
    pass


TERMINAL_STATES = (TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED)


class TaskRepository:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                  task_id TEXT PRIMARY KEY,
                  idempotency_key TEXT NOT NULL UNIQUE,
                  source TEXT NOT NULL,
                  title TEXT NOT NULL,
                  state TEXT NOT NULL,
                  version INTEGER NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS task_events (
                  event_id TEXT PRIMARY KEY,
                  task_id TEXT NOT NULL REFERENCES tasks(task_id),
                  from_state TEXT,
                  to_state TEXT NOT NULL,
                  reason TEXT NOT NULL,
                  idempotency_key TEXT NOT NULL UNIQUE,
                  created_at TEXT NOT NULL
                );
                """
            )

    def create_task(self, idempotency_key: str, source: str, title: str) -> TaskRecord:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM tasks WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing is not None:
                connection.commit()
                return self._task_from_row(existing)

            task_id = str(uuid4())
            now = utc_now().isoformat()
            connection.execute(
                """
                INSERT INTO tasks (
                  task_id, idempotency_key, source, title, state, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (task_id, idempotency_key, source, title, TaskState.RECEIVED, now, now),
            )
            connection.execute(
                """
                INSERT INTO task_events (
                  event_id, task_id, from_state, to_state, reason, idempotency_key, created_at
                ) VALUES (?, ?, NULL, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    task_id,
                    TaskState.RECEIVED,
                    "task created",
                    f"{idempotency_key}:received",
                    now,
                ),
            )
            row = connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            connection.commit()
        return self._task_from_row(row)

    def get_task(self, task_id: str) -> TaskRecord:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise TaskNotFound(task_id)
        return self._task_from_row(row)

    def transition(
        self,
        task_id: str,
        expected_version: int,
        target: TaskState,
        reason: str,
        idempotency_key: str,
    ) -> TaskRecord:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior_event = connection.execute(
                "SELECT task_id FROM task_events WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if prior_event is not None:
                if prior_event["task_id"] != task_id:
                    connection.rollback()
                    raise IdempotencyConflict(idempotency_key)
                row = connection.execute(
                    "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
                ).fetchone()
                connection.commit()
                if row is None:
                    raise TaskNotFound(task_id)
                return self._task_from_row(row)

            row = connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if row is None:
                connection.rollback()
                raise TaskNotFound(task_id)
            current = self._task_from_row(row)
            if current.version != expected_version:
                connection.rollback()
                raise VersionConflict(
                    f"task {task_id} expected version {expected_version}, found {current.version}"
                )
            require_transition(current.state, target)

            now = utc_now().isoformat()
            cursor = connection.execute(
                """
                UPDATE tasks
                SET state = ?, version = version + 1, updated_at = ?
                WHERE task_id = ? AND version = ?
                """,
                (target, now, task_id, expected_version),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise VersionConflict(f"task {task_id} changed during transition")
            connection.execute(
                """
                INSERT INTO task_events (
                  event_id, task_id, from_state, to_state, reason, idempotency_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid4()), task_id, current.state, target, reason, idempotency_key, now),
            )
            updated_row = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            connection.commit()
        return self._task_from_row(updated_row)

    def list_recent(self, limit: int = 20) -> list[TaskRecord]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM tasks ORDER BY updated_at DESC, task_id ASC LIMIT ?", (limit,)
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def list_non_terminal(self) -> list[TaskRecord]:
        placeholders = ", ".join("?" for _ in TERMINAL_STATES)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"SELECT * FROM tasks WHERE state NOT IN ({placeholders}) "
                "ORDER BY created_at ASC, task_id ASC",
                tuple(TERMINAL_STATES),
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def list_events(self, task_id: str) -> list[TaskEvent]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM task_events
                WHERE task_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (task_id,),
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    def count_by_state(self) -> dict[str, int]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT state, COUNT(*) AS task_count FROM tasks GROUP BY state"
            ).fetchall()
        return {row["state"]: row["task_count"] for row in rows}

    @staticmethod
    def _task_from_row(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            task_id=row["task_id"],
            idempotency_key=row["idempotency_key"],
            source=row["source"],
            title=row["title"],
            state=TaskState(row["state"]),
            version=row["version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> TaskEvent:
        return TaskEvent(
            event_id=row["event_id"],
            task_id=row["task_id"],
            from_state=TaskState(row["from_state"]) if row["from_state"] else None,
            to_state=TaskState(row["to_state"]),
            reason=row["reason"],
            created_at=datetime.fromisoformat(row["created_at"]),
            idempotency_key=row["idempotency_key"],
        )
