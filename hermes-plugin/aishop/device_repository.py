import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from .device_domain import (
    DeviceCommand,
    DeviceCommandStatus,
    DeviceCommandType,
    DeviceRecord,
    HeartbeatRecord,
    InstalledApp,
    PairingSession,
    PermissionState,
    WorkerState,
)
from .domain import utc_now


class PairingUnavailable(RuntimeError):
    pass


class DeviceNotFound(LookupError):
    pass


class DeviceAuthenticationFailed(PermissionError):
    pass


class PendingCommandConflict(RuntimeError):
    pass


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class DeviceRepository:
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
                CREATE TABLE IF NOT EXISTS pairing_sessions (
                  code_digest TEXT PRIMARY KEY,
                  expires_at TEXT NOT NULL,
                  consumed_at TEXT,
                  created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS devices (
                  device_id TEXT PRIMARY KEY,
                  display_name TEXT NOT NULL,
                  token_digest TEXT NOT NULL,
                  worker_state TEXT NOT NULL,
                  app_version TEXT NOT NULL,
                  capabilities_json TEXT NOT NULL,
                  battery_percent INTEGER,
                  permissions_json TEXT NOT NULL,
                  installed_apps_json TEXT NOT NULL,
                  last_sequence INTEGER NOT NULL DEFAULT 0,
                  current_task_id TEXT,
                  paired_at TEXT NOT NULL,
                  last_heartbeat_at TEXT
                );

                CREATE TABLE IF NOT EXISTS device_heartbeats (
                  device_id TEXT NOT NULL REFERENCES devices(device_id),
                  sequence INTEGER NOT NULL,
                  worker_state TEXT NOT NULL,
                  current_task_id TEXT,
                  battery_percent INTEGER NOT NULL,
                  permissions_json TEXT NOT NULL,
                  installed_apps_json TEXT NOT NULL,
                  received_at TEXT NOT NULL,
                  PRIMARY KEY (device_id, sequence)
                );

                CREATE TABLE IF NOT EXISTS device_commands (
                  command_id TEXT PRIMARY KEY,
                  device_id TEXT NOT NULL REFERENCES devices(device_id),
                  command_type TEXT NOT NULL,
                  reason TEXT NOT NULL,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  acknowledged_at TEXT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS one_pending_command_per_device
                ON device_commands(device_id)
                WHERE status = 'PENDING';
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(devices)").fetchall()
            }
            if "token_issued_at" not in columns:
                connection.execute("ALTER TABLE devices ADD COLUMN token_issued_at TEXT")
            if "token_expires_at" not in columns:
                connection.execute("ALTER TABLE devices ADD COLUMN token_expires_at TEXT")
            if "token_revoked_at" not in columns:
                connection.execute("ALTER TABLE devices ADD COLUMN token_revoked_at TEXT")

    def create_pairing_session(
        self, code_digest: str, expires_at: datetime
    ) -> PairingSession:
        created_at = utc_now()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO pairing_sessions (code_digest, expires_at, consumed_at, created_at)
                VALUES (?, ?, NULL, ?)
                """,
                (code_digest, expires_at.isoformat(), created_at.isoformat()),
            )
        return PairingSession(code_digest, expires_at, None, created_at)

    def consume_pairing_session(self, code_digest: str, now: datetime) -> None:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM pairing_sessions WHERE code_digest = ?", (code_digest,)
            ).fetchone()
            if (
                row is None
                or row["consumed_at"] is not None
                or datetime.fromisoformat(row["expires_at"]) < now
            ):
                connection.rollback()
                raise PairingUnavailable("pairing code is invalid, expired, or already used")
            connection.execute(
                "UPDATE pairing_sessions SET consumed_at = ? WHERE code_digest = ?",
                (now.isoformat(), code_digest),
            )
            connection.commit()

    def upsert_device(self, device: DeviceRecord) -> DeviceRecord:
        capabilities = _canonical_json(list(device.capabilities))
        permissions = _canonical_json(asdict(device.permissions))
        installed_apps = _canonical_json([asdict(app) for app in device.installed_apps])
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO devices (
                  device_id, display_name, token_digest, worker_state, app_version,
                  capabilities_json, battery_percent, permissions_json, installed_apps_json, last_sequence,
                  current_task_id, paired_at, last_heartbeat_at,
                  token_issued_at, token_expires_at, token_revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(device_id) DO UPDATE SET
                  display_name = excluded.display_name,
                  token_digest = excluded.token_digest,
                  worker_state = excluded.worker_state,
                  app_version = excluded.app_version,
                  capabilities_json = excluded.capabilities_json,
                  battery_percent = excluded.battery_percent,
                  permissions_json = excluded.permissions_json,
                  installed_apps_json = excluded.installed_apps_json,
                  paired_at = excluded.paired_at,
                  token_issued_at = excluded.token_issued_at,
                  token_expires_at = excluded.token_expires_at,
                  token_revoked_at = NULL
                """,
                (
                    device.device_id,
                    device.display_name,
                    device.token_digest,
                    device.worker_state,
                    device.app_version,
                    capabilities,
                    device.battery_percent,
                    permissions,
                    installed_apps,
                    device.last_sequence,
                    device.current_task_id,
                    device.paired_at.isoformat(),
                    device.last_heartbeat_at.isoformat() if device.last_heartbeat_at else None,
                    device.paired_at.isoformat(),
                    (device.paired_at + timedelta(days=90)).isoformat(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM devices WHERE device_id = ?", (device.device_id,)
            ).fetchone()
        return self._device_from_row(row, online=False)

    def authenticate(
        self, device_id: str, token_digest: str, now: datetime | None = None
    ) -> DeviceRecord:
        timestamp = now or utc_now()
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM devices WHERE device_id = ?", (device_id,)
            ).fetchone()
        if (
            row is None
            or row["token_digest"] != token_digest
            or row["token_revoked_at"] is not None
            or (
                row["token_expires_at"] is not None
                and datetime.fromisoformat(row["token_expires_at"]) < timestamp
            )
        ):
            raise DeviceAuthenticationFailed("device authentication failed")
        return self._device_from_row(row, online=False)

    def rotate_token(
        self, device_id: str, token_digest: str, now: datetime, ttl: timedelta
    ) -> None:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """UPDATE devices SET token_digest = ?, token_issued_at = ?,
                   token_expires_at = ?, token_revoked_at = NULL WHERE device_id = ?""",
                (token_digest, now.isoformat(), (now + ttl).isoformat(), device_id),
            )
            if cursor.rowcount != 1:
                raise DeviceNotFound(device_id)

    def revoke_token(self, device_id: str, now: datetime) -> None:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "UPDATE devices SET token_revoked_at = ? WHERE device_id = ?",
                (now.isoformat(), device_id),
            )
            if cursor.rowcount != 1:
                raise DeviceNotFound(device_id)

    def record_heartbeat(self, device_id: str, heartbeat: HeartbeatRecord) -> DeviceRecord:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM devices WHERE device_id = ?", (device_id,)
            ).fetchone()
            if row is None:
                connection.rollback()
                raise DeviceNotFound(device_id)
            if heartbeat.sequence <= row["last_sequence"]:
                connection.commit()
                return self._device_from_row(row, online=True)

            permissions = _canonical_json(asdict(heartbeat.permissions))
            installed_apps = _canonical_json([asdict(app) for app in heartbeat.installed_apps])
            connection.execute(
                """
                INSERT INTO device_heartbeats (
                  device_id, sequence, worker_state, current_task_id, battery_percent,
                  permissions_json, installed_apps_json, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    heartbeat.sequence,
                    heartbeat.worker_state,
                    heartbeat.current_task_id,
                    heartbeat.battery_percent,
                    permissions,
                    installed_apps,
                    heartbeat.received_at.isoformat(),
                ),
            )
            connection.execute(
                """
                UPDATE devices SET
                  worker_state = ?, permissions_json = ?, installed_apps_json = ?,
                  battery_percent = ?, last_sequence = ?, current_task_id = ?, last_heartbeat_at = ?
                WHERE device_id = ?
                """,
                (
                    heartbeat.worker_state,
                    permissions,
                    installed_apps,
                    heartbeat.battery_percent,
                    heartbeat.sequence,
                    heartbeat.current_task_id,
                    heartbeat.received_at.isoformat(),
                    device_id,
                ),
            )
            updated = connection.execute(
                "SELECT * FROM devices WHERE device_id = ?", (device_id,)
            ).fetchone()
            connection.commit()
        return self._device_from_row(updated, online=True)

    def queue_command(
        self, device_id: str, command_type: DeviceCommandType, reason: str
    ) -> DeviceCommand:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute(
                "SELECT 1 FROM devices WHERE device_id = ?", (device_id,)
            ).fetchone() is None:
                connection.rollback()
                raise DeviceNotFound(device_id)
            if connection.execute(
                "SELECT 1 FROM device_commands WHERE device_id = ? AND status = 'PENDING'",
                (device_id,),
            ).fetchone():
                connection.rollback()
                raise PendingCommandConflict(f"device {device_id} already has a pending command")
            command = DeviceCommand(
                command_id=str(uuid4()),
                device_id=device_id,
                type=command_type,
                reason=reason,
                status=DeviceCommandStatus.PENDING,
                created_at=utc_now(),
                acknowledged_at=None,
            )
            connection.execute(
                """
                INSERT INTO device_commands (
                  command_id, device_id, command_type, reason, status,
                  created_at, acknowledged_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    command.command_id,
                    command.device_id,
                    command.type,
                    command.reason,
                    command.status,
                    command.created_at.isoformat(),
                ),
            )
            connection.commit()
        return command

    def acknowledge_command(self, device_id: str, command_id: str) -> None:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE device_commands
                SET status = ?, acknowledged_at = ?
                WHERE command_id = ? AND device_id = ? AND status = ?
                """,
                (
                    DeviceCommandStatus.ACKNOWLEDGED,
                    utc_now().isoformat(),
                    command_id,
                    device_id,
                    DeviceCommandStatus.PENDING,
                ),
            )
            connection.commit()

    def get_pending_command(self, device_id: str) -> DeviceCommand | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT * FROM device_commands
                WHERE device_id = ? AND status = ?
                ORDER BY created_at ASC LIMIT 1
                """,
                (device_id, DeviceCommandStatus.PENDING),
            ).fetchone()
        return self._command_from_row(row) if row else None

    def queue_emergency_stop(self, device_id: str, reason: str) -> DeviceCommand:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM device_commands WHERE device_id = ? AND status = 'PENDING'",
                (device_id,),
            ).fetchone()
            now = utc_now()
            if existing:
                connection.execute(
                    """UPDATE device_commands SET command_type = ?, reason = ?, created_at = ?
                       WHERE command_id = ?""",
                    (DeviceCommandType.STOP, reason, now.isoformat(), existing["command_id"]),
                )
                command_id = existing["command_id"]
            else:
                command_id = str(uuid4())
                connection.execute(
                    "INSERT INTO device_commands VALUES (?, ?, ?, ?, ?, ?, NULL)",
                    (
                        command_id,
                        device_id,
                        DeviceCommandType.STOP,
                        reason,
                        DeviceCommandStatus.PENDING,
                        now.isoformat(),
                    ),
                )
            row = connection.execute(
                "SELECT * FROM device_commands WHERE command_id = ?", (command_id,)
            ).fetchone()
            connection.commit()
        return self._command_from_row(row)

    def list_devices(self, online_after: datetime) -> list[DeviceRecord]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM devices ORDER BY display_name ASC, device_id ASC"
            ).fetchall()
        return [
            self._device_from_row(
                row,
                online=(
                    row["last_heartbeat_at"] is not None
                    and datetime.fromisoformat(row["last_heartbeat_at"]) >= online_after
                ),
            )
            for row in rows
        ]

    @staticmethod
    def _device_from_row(row: sqlite3.Row, online: bool) -> DeviceRecord:
        permissions = json.loads(row["permissions_json"])
        installed_apps = json.loads(row["installed_apps_json"])
        return DeviceRecord(
            device_id=row["device_id"],
            display_name=row["display_name"],
            token_digest=row["token_digest"],
            worker_state=WorkerState(row["worker_state"]),
            app_version=row["app_version"],
            capabilities=tuple(json.loads(row["capabilities_json"])),
            battery_percent=row["battery_percent"],
            permissions=PermissionState(**permissions),
            installed_apps=tuple(InstalledApp(**app) for app in installed_apps),
            last_sequence=row["last_sequence"],
            current_task_id=row["current_task_id"],
            paired_at=datetime.fromisoformat(row["paired_at"]),
            last_heartbeat_at=(
                datetime.fromisoformat(row["last_heartbeat_at"])
                if row["last_heartbeat_at"]
                else None
            ),
            online=online,
        )

    @staticmethod
    def _command_from_row(row: sqlite3.Row) -> DeviceCommand:
        return DeviceCommand(
            command_id=row["command_id"],
            device_id=row["device_id"],
            type=DeviceCommandType(row["command_type"]),
            reason=row["reason"],
            status=DeviceCommandStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            acknowledged_at=(
                datetime.fromisoformat(row["acknowledged_at"])
                if row["acknowledged_at"]
                else None
            ),
        )
