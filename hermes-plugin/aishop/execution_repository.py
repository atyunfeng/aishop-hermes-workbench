import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from .domain import utc_now
from .execution_domain import (
    ActionType,
    ApprovalRecord,
    DeviceJob,
    EvidenceRecord,
    EvidenceSource,
    ExecutionStep,
    JobStatus,
    StepResult,
    StepStatus,
)


class JobNotFound(LookupError):
    pass


class LeaseConflict(RuntimeError):
    pass


class EvidenceNotFound(LookupError):
    pass


class ApprovalNotFound(LookupError):
    pass


class ApprovalConflict(RuntimeError):
    pass


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ExecutionRepository:
    def __init__(self, database_path: str | Path, evidence_dir: str | Path | None = None):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.evidence_dir = Path(evidence_dir or self.database_path.parent / "evidence")
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS execution_jobs (
                  job_id TEXT PRIMARY KEY,
                  task_id TEXT NOT NULL,
                  app_skill_id TEXT NOT NULL,
                  skill_version TEXT NOT NULL,
                  status TEXT NOT NULL,
                  required_packages_json TEXT NOT NULL,
                  required_capabilities_json TEXT NOT NULL,
                  mode TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS execution_steps (
                  step_id TEXT PRIMARY KEY,
                  job_id TEXT NOT NULL REFERENCES execution_jobs(job_id) ON DELETE CASCADE,
                  ordinal INTEGER NOT NULL,
                  action TEXT NOT NULL,
                  arguments_json TEXT NOT NULL,
                  timeout_seconds INTEGER NOT NULL,
                  evidence_required INTEGER NOT NULL,
                  UNIQUE(job_id, ordinal)
                );
                CREATE TABLE IF NOT EXISTS device_leases (
                  lease_id TEXT PRIMARY KEY,
                  job_id TEXT NOT NULL REFERENCES execution_jobs(job_id),
                  device_id TEXT NOT NULL,
                  status TEXT NOT NULL,
                  expires_at TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  released_at TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_lease_per_job
                  ON device_leases(job_id) WHERE status = 'ACTIVE';
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_lease_per_device
                  ON device_leases(device_id) WHERE status = 'ACTIVE';
                CREATE TABLE IF NOT EXISTS step_results (
                  job_id TEXT NOT NULL REFERENCES execution_jobs(job_id),
                  step_id TEXT NOT NULL REFERENCES execution_steps(step_id),
                  lease_id TEXT NOT NULL REFERENCES device_leases(lease_id),
                  status TEXT NOT NULL,
                  code TEXT NOT NULL,
                  message TEXT NOT NULL,
                  observed_json TEXT NOT NULL,
                  evidence_ids_json TEXT NOT NULL,
                  completed_at TEXT NOT NULL,
                  PRIMARY KEY(job_id, step_id)
                );
                CREATE TABLE IF NOT EXISTS evidence (
                  evidence_id TEXT PRIMARY KEY,
                  task_id TEXT NOT NULL,
                  job_id TEXT NOT NULL,
                  step_id TEXT NOT NULL,
                  source TEXT NOT NULL,
                  media_type TEXT NOT NULL,
                  sha256 TEXT NOT NULL,
                  byte_size INTEGER NOT NULL,
                  storage_path TEXT NOT NULL,
                  label TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                  approval_id TEXT PRIMARY KEY,
                  task_id TEXT NOT NULL,
                  action TEXT NOT NULL,
                  scope_json TEXT NOT NULL,
                  status TEXT NOT NULL,
                  token_digest TEXT,
                  expires_at TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  decided_at TEXT,
                  used_at TEXT
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                  event_id TEXT PRIMARY KEY,
                  task_id TEXT NOT NULL,
                  job_id TEXT,
                  event_type TEXT NOT NULL,
                  actor TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pending_dispatches (
                  approval_id TEXT PRIMARY KEY REFERENCES approvals(approval_id),
                  task_id TEXT NOT NULL,
                  action TEXT NOT NULL,
                  context_json TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  status TEXT NOT NULL,
                  job_id TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                """
            )
            lease_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(device_leases)").fetchall()
            }
            if "resolved_package" not in lease_columns:
                connection.execute("ALTER TABLE device_leases ADD COLUMN resolved_package TEXT")
            result_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(step_results)").fetchall()
            }
            if "received_at" not in result_columns:
                connection.execute("ALTER TABLE step_results ADD COLUMN received_at TEXT")
            evidence_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(evidence)").fetchall()
            }
            if "device_id" not in evidence_columns:
                connection.execute("ALTER TABLE evidence ADD COLUMN device_id TEXT")
            job_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(execution_jobs)").fetchall()
            }
            if "supported_app_versions_json" not in job_columns:
                connection.execute(
                    "ALTER TABLE execution_jobs ADD COLUMN supported_app_versions_json TEXT"
                )

    def create_pending_dispatch(
        self,
        approval_id: str,
        task_id: str,
        action: str,
        context: dict[str, object],
        payload: dict[str, object],
        now: datetime,
    ) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """INSERT INTO pending_dispatches
                   (approval_id, task_id, action, context_json, payload_json, status,
                    job_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'PENDING', NULL, ?, ?)""",
                (
                    approval_id,
                    task_id,
                    action,
                    _json(context),
                    _json(payload),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )

    def get_pending_dispatch(self, approval_id: str) -> dict[str, object]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM pending_dispatches WHERE approval_id = ?", (approval_id,)
            ).fetchone()
        if row is None:
            raise ApprovalNotFound(approval_id)
        return {
            "approval_id": row["approval_id"],
            "task_id": row["task_id"],
            "action": row["action"],
            "context": json.loads(row["context_json"]),
            "payload": json.loads(row["payload_json"]),
            "status": row["status"],
            "job_id": row["job_id"],
        }

    def complete_pending_dispatch(
        self, approval_id: str, status: str, now: datetime, job_id: str | None = None
    ) -> None:
        if status not in {"DISPATCHED", "REJECTED"}:
            raise ValueError("invalid pending dispatch status")
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """UPDATE pending_dispatches SET status = ?, job_id = ?, updated_at = ?
                   WHERE approval_id = ? AND status = 'PENDING'""",
                (status, job_id, now.isoformat(), approval_id),
            )
            if cursor.rowcount != 1:
                raise ApprovalConflict("pending dispatch was already resolved")

    def create_job(
        self,
        task_id: str,
        app_skill_id: str,
        skill_version: str,
        steps: tuple[ExecutionStep, ...],
        required_packages: tuple[str, ...],
        required_capabilities: tuple[str, ...],
        supported_app_versions: dict[str, dict[str, str | None]] | None = None,
        mode: EvidenceSource = EvidenceSource.DEVICE,
        job_id: str | None = None,
        now: datetime | None = None,
    ) -> DeviceJob:
        if not steps:
            raise ValueError("job must contain at least one step")
        if len({step.step_id for step in steps}) != len(steps):
            raise ValueError("step ids must be unique")
        if sorted(step.ordinal for step in steps) != list(range(len(steps))):
            raise ValueError("step ordinals must be contiguous from zero")
        created_at = now or utc_now()
        safe_job_id = job_id or str(uuid4())
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """INSERT INTO execution_jobs
                   (job_id, task_id, app_skill_id, skill_version, status,
                    required_packages_json, required_capabilities_json, mode,
                    created_at, updated_at, supported_app_versions_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    safe_job_id,
                    task_id,
                    app_skill_id,
                    skill_version,
                    JobStatus.QUEUED,
                    _json(list(required_packages)),
                    _json(list(required_capabilities)),
                    mode,
                    created_at.isoformat(),
                    created_at.isoformat(),
                    _json(supported_app_versions or {}),
                ),
            )
            connection.executemany(
                """INSERT INTO execution_steps VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        step.step_id,
                        safe_job_id,
                        step.ordinal,
                        step.action,
                        _json(step.arguments),
                        step.timeout_seconds,
                        int(step.evidence_required),
                    )
                    for step in steps
                ],
            )
            self._audit(connection, task_id, safe_job_id, "JOB_CREATED", "AGENT", {})
        return self.get_job(safe_job_id)

    def get_job(self, job_id: str) -> DeviceJob:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM execution_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise JobNotFound(job_id)
            steps = connection.execute(
                "SELECT * FROM execution_steps WHERE job_id = ? ORDER BY ordinal", (job_id,)
            ).fetchall()
            lease = connection.execute(
                "SELECT * FROM device_leases WHERE job_id = ? AND status = 'ACTIVE'",
                (job_id,),
            ).fetchone()
        return self._job_from_rows(row, steps, lease)

    def claim_job(
        self,
        device_id: str,
        installed_packages: set[str] | dict[str, str],
        capabilities: set[str],
        now: datetime,
        ttl: timedelta = timedelta(seconds=30),
    ) -> DeviceJob | None:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._expire_leases(connection, now)
            active = connection.execute(
                "SELECT job_id FROM device_leases WHERE device_id = ? AND status = 'ACTIVE'",
                (device_id,),
            ).fetchone()
            if active:
                connection.commit()
                return self.get_job(active["job_id"])
            candidates = connection.execute(
                "SELECT * FROM execution_jobs WHERE status IN (?, ?) ORDER BY created_at, job_id",
                (JobStatus.QUEUED, JobStatus.RETRY_WAIT),
            ).fetchall()
            installed_names = set(installed_packages)
            selected = next(
                (
                    row
                    for row in candidates
                    if set(json.loads(row["required_packages_json"])).intersection(
                        installed_names
                    )
                    and self._has_supported_installed_alias(row, installed_packages)
                    and set(json.loads(row["required_capabilities_json"])).issubset(capabilities)
                ),
                None,
            )
            if selected is None:
                connection.commit()
                return None
            lease_id = str(uuid4())
            expires_at = now + ttl
            package_aliases = json.loads(selected["required_packages_json"])
            resolved_package = next(
                package_name
                for package_name in package_aliases
                if package_name in installed_names
                and self._package_version_supported(selected, package_name, installed_packages)
            )
            connection.execute(
                """INSERT INTO device_leases
                   (lease_id, job_id, device_id, status, expires_at, created_at,
                    released_at, resolved_package)
                   VALUES (?, ?, ?, 'ACTIVE', ?, ?, NULL, ?)""",
                (
                    lease_id,
                    selected["job_id"],
                    device_id,
                    expires_at.isoformat(),
                    now.isoformat(),
                    resolved_package,
                ),
            )
            connection.execute(
                "UPDATE execution_jobs SET status = ?, updated_at = ? WHERE job_id = ?",
                (JobStatus.LEASED, now.isoformat(), selected["job_id"]),
            )
            self._audit(
                connection,
                selected["task_id"],
                selected["job_id"],
                "LEASE_ACQUIRED",
                device_id,
                {
                    "lease_id": lease_id,
                    "expires_at": expires_at.isoformat(),
                    "resolved_package": resolved_package,
                },
                now,
            )
            connection.commit()
        return self.get_job(selected["job_id"])

    @classmethod
    def _has_supported_installed_alias(
        cls, row: sqlite3.Row, installed: set[str] | dict[str, str]
    ) -> bool:
        return any(
            package in installed and cls._package_version_supported(row, package, installed)
            for package in json.loads(row["required_packages_json"])
        )

    @staticmethod
    def _package_version_supported(
        row: sqlite3.Row,
        package_name: str,
        installed: set[str] | dict[str, str],
    ) -> bool:
        if not isinstance(installed, dict):
            return True
        ranges = json.loads(row["supported_app_versions_json"] or "{}")
        bounds = ranges.get(package_name)
        if not bounds:
            return True
        version_name = installed.get(package_name, "")
        if not version_name or any(not part.isdecimal() for part in version_name.split(".")):
            return False
        raw_versions = [version_name, bounds["min"]]
        if bounds.get("max"):
            raw_versions.append(bounds["max"])
        if any(
            not value or any(not part.isdecimal() for part in value.split("."))
            for value in raw_versions
        ):
            return False
        versions = [tuple(int(part) for part in value.split(".")) for value in raw_versions]
        width = max(len(version) for version in versions)
        padded = [version + (0,) * (width - len(version)) for version in versions]
        version, minimum = padded[:2]
        maximum = padded[2] if bounds.get("max") else None
        return version >= minimum and (maximum is None or version <= maximum)

    def renew_lease(self, lease_id: str, device_id: str, now: datetime, ttl: timedelta) -> None:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """UPDATE device_leases SET expires_at = ?
                   WHERE lease_id = ? AND device_id = ? AND status = 'ACTIVE' AND expires_at >= ?""",
                ((now + ttl).isoformat(), lease_id, device_id, now.isoformat()),
            )
            if cursor.rowcount != 1:
                raise LeaseConflict("lease is stale or belongs to another device")

    def record_step_result(
        self, device_id: str, result: StepResult, received_at: datetime | None = None
    ) -> DeviceJob:
        server_time = received_at or utc_now()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            lease = connection.execute(
                "SELECT * FROM device_leases WHERE lease_id = ? AND job_id = ?",
                (result.lease_id, result.job_id),
            ).fetchone()
            if (
                lease is None
                or lease["device_id"] != device_id
                or lease["status"] != "ACTIVE"
                or datetime.fromisoformat(lease["expires_at"]) < server_time
            ):
                connection.rollback()
                raise LeaseConflict("step result does not match an active lease")
            step = connection.execute(
                "SELECT 1 FROM execution_steps WHERE job_id = ? AND step_id = ?",
                (result.job_id, result.step_id),
            ).fetchone()
            if step is None:
                connection.rollback()
                raise ValueError("step does not belong to job")
            evidence_ids = tuple(result.evidence_ids)
            if bool(
                connection.execute(
                    "SELECT evidence_required FROM execution_steps WHERE step_id = ?",
                    (result.step_id,),
                ).fetchone()[0]
            ) and not evidence_ids:
                connection.rollback()
                raise ValueError("step requires evidence")
            for evidence_id in evidence_ids:
                evidence = connection.execute(
                    "SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)
                ).fetchone()
                job_mode = connection.execute(
                    "SELECT mode FROM execution_jobs WHERE job_id = ?", (result.job_id,)
                ).fetchone()[0]
                if (
                    evidence is None
                    or evidence["task_id"]
                    != connection.execute(
                        "SELECT task_id FROM execution_jobs WHERE job_id = ?", (result.job_id,)
                    ).fetchone()[0]
                    or evidence["job_id"] != result.job_id
                    or evidence["step_id"] != result.step_id
                    or evidence["source"] != job_mode
                    or (job_mode == "DEVICE" and evidence["device_id"] != device_id)
                ):
                    connection.rollback()
                    raise ValueError("evidence does not belong to this device job step")
            prior = connection.execute(
                "SELECT * FROM step_results WHERE job_id = ? AND step_id = ?",
                (result.job_id, result.step_id),
            ).fetchone()
            if prior:
                connection.commit()
                return self.get_job(result.job_id)
            connection.execute(
                """INSERT INTO step_results
                   (job_id, step_id, lease_id, status, code, message, observed_json,
                    evidence_ids_json, completed_at, received_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.job_id,
                    result.step_id,
                    result.lease_id,
                    result.status,
                    result.code,
                    result.message,
                    _json(result.observed),
                    _json(list(result.evidence_ids)),
                    result.completed_at.isoformat(),
                    server_time.isoformat(),
                ),
            )
            job_row = connection.execute(
                "SELECT * FROM execution_jobs WHERE job_id = ?", (result.job_id,)
            ).fetchone()
            total = connection.execute(
                "SELECT COUNT(*) FROM execution_steps WHERE job_id = ?", (result.job_id,)
            ).fetchone()[0]
            succeeded = connection.execute(
                "SELECT COUNT(*) FROM step_results WHERE job_id = ? AND status = ?",
                (result.job_id, StepStatus.SUCCEEDED),
            ).fetchone()[0]
            next_status = JobStatus.LEASED
            release_status = None
            if result.status is StepStatus.SUCCEEDED and succeeded == total:
                next_status, release_status = JobStatus.SUCCEEDED, "COMPLETED"
            elif result.status is StepStatus.RETRYABLE:
                next_status, release_status = JobStatus.RETRY_WAIT, "RETRY"
            elif result.status is StepStatus.HUMAN_TAKEOVER:
                next_status, release_status = JobStatus.HUMAN_TAKEOVER, "TAKEOVER"
            elif result.status is StepStatus.FAILED:
                next_status, release_status = JobStatus.FAILED, "FAILED"
            connection.execute(
                "UPDATE execution_jobs SET status = ?, updated_at = ? WHERE job_id = ?",
                (next_status, server_time.isoformat(), result.job_id),
            )
            if release_status:
                connection.execute(
                    "UPDATE device_leases SET status = ?, released_at = ? WHERE lease_id = ?",
                    (release_status, server_time.isoformat(), result.lease_id),
                )
            self._audit(
                connection,
                job_row["task_id"],
                result.job_id,
                "STEP_RESULT",
                device_id,
                {"step_id": result.step_id, "status": result.status, "code": result.code},
                server_time,
            )
            connection.commit()
        return self.get_job(result.job_id)

    def expire_leases(self, now: datetime) -> int:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            count = self._expire_leases(connection, now)
            connection.commit()
        return count

    def _expire_leases(self, connection: sqlite3.Connection, now: datetime) -> int:
        rows = connection.execute(
            "SELECT * FROM device_leases WHERE status = 'ACTIVE' AND expires_at < ?",
            (now.isoformat(),),
        ).fetchall()
        for row in rows:
            connection.execute(
                "UPDATE device_leases SET status = 'EXPIRED', released_at = ? WHERE lease_id = ?",
                (now.isoformat(), row["lease_id"]),
            )
            connection.execute(
                "UPDATE execution_jobs SET status = ?, updated_at = ? WHERE job_id = ?",
                (JobStatus.RETRY_WAIT, now.isoformat(), row["job_id"]),
            )
            task_id = connection.execute(
                "SELECT task_id FROM execution_jobs WHERE job_id = ?", (row["job_id"],)
            ).fetchone()[0]
            self._audit(
                connection,
                task_id,
                row["job_id"],
                "LEASE_EXPIRED",
                "SYSTEM",
                {"device_id": row["device_id"]},
                now,
            )
        return len(rows)

    def store_evidence(
        self,
        task_id: str,
        job_id: str,
        step_id: str,
        source: EvidenceSource,
        media_type: str,
        content: bytes,
        label: str,
        now: datetime | None = None,
        device_id: str | None = None,
    ) -> EvidenceRecord:
        if media_type not in {"image/png", "image/jpeg", "text/plain"}:
            raise ValueError("unsupported evidence media type")
        if len(content) > 716_800:
            raise ValueError("evidence exceeds 700 KiB")
        if not label or len(label) > 120:
            raise ValueError("evidence label must contain 1 to 120 characters")
        created_at = now or utc_now()
        digest = hashlib.sha256(content).hexdigest()
        suffix = {"image/png": ".png", "image/jpeg": ".jpg", "text/plain": ".txt"}[media_type]
        storage = self.evidence_dir / f"{digest}{suffix}"
        if not storage.exists():
            storage.write_bytes(content)
        record = EvidenceRecord(
            evidence_id=str(uuid4()),
            task_id=task_id,
            job_id=job_id,
            step_id=step_id,
            source=source,
            media_type=media_type,
            sha256=digest,
            byte_size=len(content),
            storage_path=str(storage),
            label=label,
            created_at=created_at,
        )
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """INSERT INTO evidence
                   (evidence_id, task_id, job_id, step_id, source, media_type, sha256,
                    byte_size, storage_path, label, created_at, device_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.evidence_id,
                    task_id,
                    job_id,
                    step_id,
                    source,
                    media_type,
                    digest,
                    len(content),
                    str(storage),
                    label,
                    created_at.isoformat(),
                    device_id,
                ),
            )
            self._audit(
                connection,
                task_id,
                job_id,
                "EVIDENCE_STORED",
                source,
                {
                    "evidence_id": record.evidence_id,
                    "sha256": digest,
                    "media_type": media_type,
                    "source": str(source),
                    "label": label,
                },
                created_at,
            )
        return record

    def validate_evidence_upload(
        self,
        device_id: str,
        task_id: str,
        job_id: str,
        step_id: str,
        now: datetime,
    ) -> None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT 1 FROM execution_jobs j
                   JOIN execution_steps s ON s.job_id = j.job_id
                   JOIN device_leases l ON l.job_id = j.job_id
                   WHERE j.job_id = ? AND j.task_id = ? AND s.step_id = ?
                     AND j.mode = 'DEVICE' AND l.device_id = ?
                     AND l.status = 'ACTIVE' AND l.expires_at >= ?""",
                (job_id, task_id, step_id, device_id, now.isoformat()),
            ).fetchone()
        if row is None:
            raise LeaseConflict("evidence upload does not match an active device lease")

    def prune_evidence(
        self,
        now: datetime,
        retention: timedelta = timedelta(days=7),
        max_bytes: int = 512 * 1024 * 1024,
    ) -> dict[str, int]:
        cutoff = now - retention
        removed_rows: list[sqlite3.Row] = []
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT * FROM evidence ORDER BY created_at, evidence_id"
            ).fetchall()
            total = sum(row["byte_size"] for row in rows)
            for row in rows:
                if datetime.fromisoformat(row["created_at"]) < cutoff or total > max_bytes:
                    connection.execute(
                        "DELETE FROM evidence WHERE evidence_id = ?", (row["evidence_id"],)
                    )
                    removed_rows.append(row)
                    total -= row["byte_size"]
            connection.commit()
        with closing(self._connect()) as connection:
            remaining_paths = {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT storage_path FROM evidence"
                ).fetchall()
            }
        for row in removed_rows:
            path = Path(row["storage_path"])
            if str(path) not in remaining_paths:
                path.unlink(missing_ok=True)
        return {"removed": len(removed_rows), "remaining_bytes": total}

    def get_evidence(self, evidence_id: str) -> tuple[EvidenceRecord, bytes]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)
            ).fetchone()
        if row is None:
            raise EvidenceNotFound(evidence_id)
        record = self._evidence_from_row(row)
        return record, Path(record.storage_path).read_bytes()

    def list_timeline(self, task_id: str) -> list[dict[str, object]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM audit_events WHERE task_id = ? ORDER BY created_at, rowid",
                (task_id,),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "task_id": row["task_id"],
                "job_id": row["job_id"],
                "event_type": row["event_type"],
                "actor": row["actor"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def create_approval(
        self,
        task_id: str,
        action: str,
        scope: dict[str, object],
        expires_at: datetime,
        now: datetime | None = None,
    ) -> ApprovalRecord:
        created_at = now or utc_now()
        approval_id = str(uuid4())
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO approvals VALUES (?, ?, ?, ?, 'PENDING', NULL, ?, ?, NULL, NULL)",
                (
                    approval_id,
                    task_id,
                    action,
                    _json(scope),
                    expires_at.isoformat(),
                    created_at.isoformat(),
                ),
            )
        return self.get_approval(approval_id)

    def decide_approval(
        self,
        approval_id: str,
        approved: bool,
        token_digest: str | None,
        now: datetime,
    ) -> ApprovalRecord:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
            ).fetchone()
            if row is None:
                connection.rollback()
                raise ApprovalNotFound(approval_id)
            if row["status"] != "PENDING" or datetime.fromisoformat(row["expires_at"]) < now:
                connection.rollback()
                raise ApprovalConflict("approval is not pending or has expired")
            if approved and not token_digest:
                connection.rollback()
                raise ValueError("approved decision requires token digest")
            connection.execute(
                "UPDATE approvals SET status = ?, token_digest = ?, decided_at = ? WHERE approval_id = ?",
                (
                    "APPROVED" if approved else "REJECTED",
                    token_digest,
                    now.isoformat(),
                    approval_id,
                ),
            )
            connection.commit()
        return self.get_approval(approval_id)

    def consume_approval(
        self, token_digest: str, action: str, scope: dict[str, object], now: datetime
    ) -> ApprovalRecord:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT * FROM approvals WHERE token_digest = ? AND action = ?
                   AND status = 'APPROVED' AND used_at IS NULL AND expires_at >= ?""",
                (token_digest, action, now.isoformat()),
            ).fetchone()
            if row is None or json.loads(row["scope_json"]) != scope:
                connection.rollback()
                raise ApprovalConflict("approval token is invalid, expired, used, or out of scope")
            connection.execute(
                "UPDATE approvals SET used_at = ? WHERE approval_id = ?",
                (now.isoformat(), row["approval_id"]),
            )
            connection.commit()
        return self.get_approval(row["approval_id"])

    def get_approval(self, approval_id: str) -> ApprovalRecord:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
            ).fetchone()
        if row is None:
            raise ApprovalNotFound(approval_id)
        return self._approval_from_row(row)

    def list_approvals(self, status: str = "PENDING") -> list[ApprovalRecord]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM approvals WHERE status = ? ORDER BY created_at, approval_id",
                (status,),
            ).fetchall()
        return [self._approval_from_row(row) for row in rows]

    def cancel_all(self, now: datetime) -> int:
        terminal = (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            placeholders = ",".join("?" for _ in terminal)
            rows = connection.execute(
                f"SELECT * FROM execution_jobs WHERE status NOT IN ({placeholders})", terminal
            ).fetchall()
            for row in rows:
                connection.execute(
                    "UPDATE execution_jobs SET status = ?, updated_at = ? WHERE job_id = ?",
                    (JobStatus.CANCELLED, now.isoformat(), row["job_id"]),
                )
                connection.execute(
                    """UPDATE device_leases SET status = 'CANCELLED', released_at = ?
                       WHERE job_id = ? AND status = 'ACTIVE'""",
                    (now.isoformat(), row["job_id"]),
                )
                self._audit(
                    connection,
                    row["task_id"],
                    row["job_id"],
                    "JOB_CANCELLED",
                    "OPERATOR",
                    {"reason": "global emergency stop"},
                    now,
                )
            connection.commit()
        return len(rows)

    def retry_task_jobs(self, task_id: str, now: datetime) -> int:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """SELECT * FROM execution_jobs WHERE task_id = ?
                   AND status IN (?, ?)""",
                (task_id, JobStatus.RETRY_WAIT, JobStatus.HUMAN_TAKEOVER),
            ).fetchall()
            for row in rows:
                connection.execute(
                    "UPDATE execution_jobs SET status=?, updated_at=? WHERE job_id=?",
                    (JobStatus.QUEUED, now.isoformat(), row["job_id"]),
                )
                connection.execute(
                    """UPDATE device_leases SET status='RETRY', released_at=?
                       WHERE job_id=? AND status='ACTIVE'""",
                    (now.isoformat(), row["job_id"]),
                )
                self._audit(
                    connection,
                    task_id,
                    row["job_id"],
                    "JOB_REQUEUED",
                    "OPERATOR",
                    {},
                    now,
                )
            connection.commit()
        return len(rows)

    @staticmethod
    def _approval_from_row(row: sqlite3.Row) -> ApprovalRecord:
        return ApprovalRecord(
            approval_id=row["approval_id"],
            task_id=row["task_id"],
            action=row["action"],
            scope=json.loads(row["scope_json"]),
            status=row["status"],
            token_digest=row["token_digest"],
            expires_at=datetime.fromisoformat(row["expires_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            decided_at=datetime.fromisoformat(row["decided_at"]) if row["decided_at"] else None,
            used_at=datetime.fromisoformat(row["used_at"]) if row["used_at"] else None,
        )

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        task_id: str,
        job_id: str | None,
        event_type: str,
        actor: str,
        payload: dict[str, object],
        now: datetime | None = None,
    ) -> None:
        connection.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid4()),
                task_id,
                job_id,
                event_type,
                actor,
                _json(payload),
                (now or utc_now()).isoformat(),
            ),
        )

    @staticmethod
    def _job_from_rows(
        row: sqlite3.Row, steps: list[sqlite3.Row], lease: sqlite3.Row | None
    ) -> DeviceJob:
        resolved_package = lease["resolved_package"] if lease else None
        compiled_steps = []
        for step in steps:
            arguments = json.loads(step["arguments_json"])
            if resolved_package and step["action"] == ActionType.LAUNCH_APP:
                arguments = {**arguments, "package_name": resolved_package}
            compiled_steps.append(
                ExecutionStep(
                    step_id=step["step_id"],
                    ordinal=step["ordinal"],
                    action=ActionType(step["action"]),
                    arguments=arguments,
                    timeout_seconds=step["timeout_seconds"],
                    evidence_required=bool(step["evidence_required"]),
                )
            )
        return DeviceJob(
            job_id=row["job_id"],
            task_id=row["task_id"],
            app_skill_id=row["app_skill_id"],
            skill_version=row["skill_version"],
            status=JobStatus(row["status"]),
            required_packages=(resolved_package,)
            if resolved_package
            else tuple(json.loads(row["required_packages_json"])),
            required_capabilities=tuple(json.loads(row["required_capabilities_json"])),
            steps=tuple(compiled_steps),
            lease_id=lease["lease_id"] if lease else None,
            device_id=lease["device_id"] if lease else None,
            lease_expires_at=datetime.fromisoformat(lease["expires_at"]) if lease else None,
            mode=EvidenceSource(row["mode"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _evidence_from_row(row: sqlite3.Row) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=row["evidence_id"],
            task_id=row["task_id"],
            job_id=row["job_id"],
            step_id=row["step_id"],
            source=EvidenceSource(row["source"]),
            media_type=row["media_type"],
            sha256=row["sha256"],
            byte_size=row["byte_size"],
            storage_path=row["storage_path"],
            label=row["label"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
