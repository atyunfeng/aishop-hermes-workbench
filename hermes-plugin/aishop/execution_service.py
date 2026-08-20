import base64
import hashlib
import secrets
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from .domain import TaskState
from .execution_domain import (
    ActionType,
    EvidenceSource,
    ExecutionStep,
    StepResult,
    StepStatus,
)
from .execution_repository import ExecutionRepository
from .service import TaskService


class InvalidEvidence(ValueError):
    pass


class ExecutionService:
    LEASE_TTL = timedelta(seconds=30)

    def __init__(self, repository: ExecutionRepository, tasks: TaskService | None = None):
        self.repository = repository
        self.tasks = tasks
        self._last_evidence_cleanup_at: datetime | None = None

    def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        steps = tuple(
            ExecutionStep(
                step_id=item["step_id"],
                ordinal=item["ordinal"],
                action=ActionType(item["action"]),
                arguments=item["arguments"],
                timeout_seconds=item.get("timeout_seconds", 15),
                evidence_required=item.get("evidence_required", False),
            )
            for item in payload["steps"]
        )
        job = self.repository.create_job(
            task_id=payload["task_id"],
            app_skill_id=payload["app_skill_id"],
            skill_version=payload["skill_version"],
            steps=steps,
            required_packages=tuple(payload["required_packages"]),
            supported_app_versions=payload.get("supported_app_versions", {}),
            required_capabilities=tuple(payload["required_capabilities"]),
            mode=EvidenceSource(payload.get("mode", EvidenceSource.DEVICE)),
            job_id=payload.get("job_id"),
        )
        return self.job_envelope(job)

    def heartbeat_job(
        self,
        device_id: str,
        worker_state: str,
        installed_packages: set[str] | dict[str, str],
        capabilities: set[str],
        completed_step: dict[str, Any] | None,
        now: datetime,
    ) -> tuple[dict[str, Any] | None, str | None]:
        if (
            self._last_evidence_cleanup_at is None
            or now - self._last_evidence_cleanup_at >= timedelta(days=1)
        ):
            self.repository.prune_evidence(now)
            self._last_evidence_cleanup_at = now
        acknowledged_step_id = None
        if completed_step:
            result = StepResult(
                job_id=completed_step["job_id"],
                lease_id=completed_step["lease_id"],
                step_id=completed_step["step_id"],
                status=StepStatus(completed_step["status"]),
                code=completed_step["code"],
                message=completed_step["message"],
                observed=completed_step["observed"],
                evidence_ids=tuple(completed_step["evidence_ids"]),
                completed_at=datetime.fromisoformat(completed_step["completed_at"]),
            )
            updated = self.repository.record_step_result(device_id, result, now)
            self._sync_task_after_result(updated)
            acknowledged_step_id = result.step_id
        if worker_state in {"PAUSED", "TAKEOVER", "OFFLINE", "ERROR"}:
            return None, acknowledged_step_id
        job = self.repository.claim_job(
            device_id, installed_packages, capabilities, now, self.LEASE_TTL
        )
        if job is None:
            return None, acknowledged_step_id
        self._sync_task_after_claim(job)
        self.repository.renew_lease(job.lease_id, device_id, now, self.LEASE_TTL)
        return self.job_envelope(self.repository.get_job(job.job_id)), acknowledged_step_id

    def upload_evidence(
        self,
        payload: dict[str, Any],
        source: EvidenceSource = EvidenceSource.DEVICE,
        device_id: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        try:
            content = base64.b64decode(payload["content_base64"], validate=True)
        except Exception as error:
            raise InvalidEvidence("evidence content is not valid base64") from error
        if source is EvidenceSource.DEVICE and payload.get("source", "DEVICE") != "DEVICE":
            raise InvalidEvidence("device upload must use DEVICE source")
        timestamp = now or datetime.now().astimezone()
        if source is EvidenceSource.DEVICE:
            if device_id is None:
                raise InvalidEvidence("device identity is required for device evidence")
            self.repository.validate_evidence_upload(
                device_id,
                payload["task_id"],
                payload["job_id"],
                payload["step_id"],
                timestamp,
            )
        record = self.repository.store_evidence(
            task_id=payload["task_id"],
            job_id=payload["job_id"],
            step_id=payload["step_id"],
            source=source,
            media_type=payload["media_type"],
            content=content,
            label=payload["label"],
            now=timestamp,
            device_id=device_id,
        )
        return self.evidence_envelope(record)

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self.job_envelope(self.repository.get_job(job_id), include_all_steps=True)

    def timeline(self, task_id: str) -> list[dict[str, object]]:
        return self.repository.list_timeline(task_id)

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        return [self.approval_envelope(item) for item in self.repository.list_approvals()]

    def decide_approval(self, approval_id: str, approved: bool, now: datetime) -> dict[str, Any]:
        raw_token = secrets.token_urlsafe(24) if approved else None
        record = self.repository.decide_approval(
            approval_id,
            approved,
            hashlib.sha256(raw_token.encode()).hexdigest() if raw_token else None,
            now,
        )
        envelope = self.approval_envelope(record)
        envelope["approval_token"] = raw_token
        return envelope

    def cancel_all(self, now: datetime) -> int:
        return self.repository.cancel_all(now)

    def _sync_task_after_claim(self, job) -> None:
        if self.tasks is None:
            return
        task = self.tasks.get_task(job.task_id)
        if task["state"] == TaskState.QUEUED:
            task = self.tasks.transition(
                job.task_id,
                task["version"],
                TaskState.ASSIGNED,
                f"leased to {job.device_id}",
                f"job:{job.job_id}:assigned",
            )
        if task["state"] == TaskState.ASSIGNED:
            self.tasks.transition(
                job.task_id,
                task["version"],
                TaskState.EXECUTING,
                "Android Worker accepted leased job",
                f"job:{job.job_id}:executing",
            )

    def _sync_task_after_result(self, job) -> None:
        if self.tasks is None:
            return
        task = self.tasks.get_task(job.task_id)
        target_by_job = {
            "RETRY_WAIT": TaskState.RETRY_WAIT,
            "HUMAN_TAKEOVER": TaskState.HUMAN_TAKEOVER,
            "FAILED": TaskState.FAILED,
        }
        if str(job.status) == "SUCCEEDED" and task["state"] == TaskState.EXECUTING:
            task = self.tasks.transition(
                job.task_id,
                task["version"],
                TaskState.VERIFYING,
                "all device steps completed; verifying evidence",
                f"job:{job.job_id}:verifying",
            )
            self.tasks.transition(
                job.task_id,
                task["version"],
                TaskState.SUCCEEDED,
                "device result and evidence verified",
                f"job:{job.job_id}:succeeded",
            )
        elif str(job.status) in target_by_job and task["state"] == TaskState.EXECUTING:
            self.tasks.transition(
                job.task_id,
                task["version"],
                target_by_job[str(job.status)],
                f"device job entered {job.status}",
                f"job:{job.job_id}:{job.status}",
            )

    @staticmethod
    def job_envelope(job, include_all_steps: bool = False) -> dict[str, Any]:
        steps = job.steps
        if not include_all_steps:
            steps = job.steps
        return {
            "job_id": job.job_id,
            "task_id": job.task_id,
            "app_skill_id": job.app_skill_id,
            "skill_version": job.skill_version,
            "status": job.status,
            "required_packages": list(job.required_packages),
            "required_capabilities": list(job.required_capabilities),
            "lease_id": job.lease_id,
            "device_id": job.device_id,
            "lease_expires_at": job.lease_expires_at.isoformat() if job.lease_expires_at else None,
            "mode": job.mode,
            "steps": [
                {
                    "step_id": step.step_id,
                    "ordinal": step.ordinal,
                    "action": step.action,
                    "arguments": step.arguments,
                    "timeout_seconds": step.timeout_seconds,
                    "evidence_required": step.evidence_required,
                }
                for step in steps
            ],
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
        }

    @staticmethod
    def evidence_envelope(record) -> dict[str, Any]:
        envelope = asdict(record)
        envelope.pop("storage_path")
        envelope["created_at"] = record.created_at.isoformat()
        return envelope

    @staticmethod
    def approval_envelope(record) -> dict[str, Any]:
        return {
            "approval_id": record.approval_id,
            "task_id": record.task_id,
            "action": record.action,
            "scope": record.scope,
            "status": record.status,
            "expires_at": record.expires_at.isoformat(),
            "created_at": record.created_at.isoformat(),
            "decided_at": record.decided_at.isoformat() if record.decided_at else None,
            "used_at": record.used_at.isoformat() if record.used_at else None,
        }
