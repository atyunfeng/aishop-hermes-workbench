import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta
from typing import Any

from .app_skills import AppSkillRegistry
from .domain import TaskState, utc_now
from .execution_repository import ExecutionRepository
from .execution_service import ExecutionService
from .policy import PolicyDenied, PolicyEngine
from .service import TaskService


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class DispatchService:
    APPROVAL_TTL = timedelta(minutes=10)

    def __init__(
        self,
        tasks: TaskService,
        registry: AppSkillRegistry,
        execution: ExecutionService,
        repository: ExecutionRepository,
        allowed_recipients: set[str] | None = None,
    ):
        self.tasks = tasks
        self.registry = registry
        self.execution = execution
        self.repository = repository
        defaults = {
            "AIShop 测试客户",
            "AIShop 微信测试客户",
            "AIShop 企业微信测试群",
            "DEMO-DD-2001",
        }
        configured = {
            item.strip()
            for item in os.getenv("AISHOP_ALLOWED_RECIPIENTS", "").split(",")
            if item.strip()
        }
        self.policy = PolicyEngine(repository, allowed_recipients or (defaults | configured))

    def dispatch(
        self,
        task_id: str,
        app_skill_id: str,
        workflow_id: str,
        inputs: dict[str, Any],
        mode: str = "DEVICE",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = now or utc_now()
        task = self.tasks.get_task(task_id)
        if task["state"] != TaskState.PLANNING:
            raise ValueError("workflow dispatch requires a PLANNING task")
        compiled = self.registry.compile(app_skill_id, workflow_id, inputs, task_id, mode)
        action = compiled.pop("risk_action")
        context = self._policy_context(task_id, app_skill_id, workflow_id, inputs)
        risk = self.policy.classify(action, context)
        if str(risk) == "HUMAN_ONLY":
            self.tasks.transition(
                task_id,
                task["version"],
                TaskState.HUMAN_TAKEOVER,
                "workflow is outside the automatic policy boundary",
                f"dispatch:{task_id}:{workflow_id}:takeover",
            )
            raise PolicyDenied("action requires human takeover")
        if str(risk) == "APPROVAL_REQUIRED":
            scope = {
                "workflow_id": workflow_id,
                "binding": self._binding(task_id, workflow_id, inputs),
                "target": context["recipient"],
            }
            approval = self.repository.create_approval(
                task_id, action, scope, timestamp + self.APPROVAL_TTL, timestamp
            )
            self.repository.create_pending_dispatch(
                approval.approval_id, task_id, action, scope, compiled, timestamp
            )
            updated = self.tasks.transition(
                task_id,
                task["version"],
                TaskState.WAITING_APPROVAL,
                f"{action} requires scoped approval",
                f"approval:{approval.approval_id}:waiting",
            )
            return {
                "status": "WAITING_APPROVAL",
                "task": updated,
                "approval": self.execution.approval_envelope(approval),
            }
        updated = self.tasks.transition(
            task_id,
            task["version"],
            TaskState.QUEUED,
            "workflow passed server-side policy",
            f"dispatch:{task_id}:{workflow_id}:queued",
        )
        return {"status": "QUEUED", "task": updated, "job": self.execution.create_job(compiled)}

    def decide_and_resume(
        self, approval_id: str, approved: bool, now: datetime | None = None
    ) -> dict[str, Any]:
        timestamp = now or utc_now()
        pending = self.repository.get_pending_dispatch(approval_id)
        if pending["status"] != "PENDING":
            raise ValueError("approval dispatch was already resolved")
        raw_token = secrets.token_urlsafe(24) if approved else None
        approval = self.repository.decide_approval(
            approval_id,
            approved,
            hashlib.sha256(raw_token.encode()).hexdigest() if raw_token else None,
            timestamp,
        )
        task = self.tasks.get_task(str(pending["task_id"]))
        if not approved:
            self.repository.complete_pending_dispatch(approval_id, "REJECTED", timestamp)
            updated = self.tasks.transition(
                task["task_id"],
                task["version"],
                TaskState.CANCELLED,
                "operator rejected scoped action",
                f"approval:{approval_id}:rejected",
            )
            return {
                "status": "REJECTED",
                "task": updated,
                "approval": self.execution.approval_envelope(approval),
            }
        self.policy.authorize(
            str(pending["action"]), dict(pending["context"]), raw_token, timestamp
        )
        updated = self.tasks.transition(
            task["task_id"],
            task["version"],
            TaskState.QUEUED,
            "operator approved exact workflow scope",
            f"approval:{approval_id}:queued",
        )
        job = self.execution.create_job(dict(pending["payload"]))
        self.repository.complete_pending_dispatch(
            approval_id, "DISPATCHED", timestamp, job["job_id"]
        )
        return {
            "status": "QUEUED",
            "task": updated,
            "job": job,
            "approval": self.execution.approval_envelope(
                self.repository.get_approval(approval_id)
            ),
        }

    @staticmethod
    def _policy_context(
        task_id: str, app_skill_id: str, workflow_id: str, inputs: dict[str, Any]
    ) -> dict[str, object]:
        recipient = (
            inputs.get("customer_name")
            or inputs.get("conversation_name")
            or inputs.get("order_id")
            or ""
        )
        return {
            "task_id": task_id,
            "app_skill_id": app_skill_id,
            "workflow_id": workflow_id,
            "recipient": recipient,
            "binding": DispatchService._binding(task_id, workflow_id, inputs),
        }

    @staticmethod
    def _binding(task_id: str, workflow_id: str, inputs: dict[str, Any]) -> str:
        value = f"{task_id}\n{workflow_id}\n{_canonical(inputs)}"
        return hashlib.sha256(value.encode()).hexdigest()
