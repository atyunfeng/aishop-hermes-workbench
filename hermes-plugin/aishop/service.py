from dataclasses import asdict
from typing import Any

from .domain import TaskEvent, TaskRecord, TaskState
from .repository import TaskRepository


class TaskService:
    def __init__(self, repository: TaskRepository):
        self.repository = repository

    def create_task(self, idempotency_key: str, source: str, title: str) -> dict[str, Any]:
        return self._task_envelope(
            self.repository.create_task(idempotency_key, source, title)
        )

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._task_envelope(self.repository.get_task(task_id))

    def transition(
        self,
        task_id: str,
        expected_version: int,
        target_state: str | TaskState,
        reason: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        target = target_state if isinstance(target_state, TaskState) else TaskState(target_state)
        task = self.repository.transition(
            task_id,
            expected_version=expected_version,
            target=target,
            reason=reason,
            idempotency_key=idempotency_key,
        )
        return self._task_envelope(task)

    def stop_all(self, reason: str) -> list[dict[str, Any]]:
        cancelled = []
        for task in self.repository.list_non_terminal():
            updated = self.repository.transition(
                task.task_id,
                expected_version=task.version,
                target=TaskState.CANCELLED,
                reason=reason,
                idempotency_key=f"stop:{task.task_id}:{task.version}",
            )
            cancelled.append(self._task_envelope(updated))
        return cancelled

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        return [self._task_envelope(task) for task in self.repository.list_recent(limit)]

    def count_by_state(self) -> dict[str, int]:
        return self.repository.count_by_state()

    def list_events(self, task_id: str) -> list[dict[str, Any]]:
        return [self._event_envelope(event) for event in self.repository.list_events(task_id)]

    def retry(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(task_id)
        if task["state"] not in {TaskState.RETRY_WAIT, TaskState.HUMAN_TAKEOVER}:
            raise ValueError("only retry-wait or takeover tasks can be retried")
        return self.transition(
            task_id,
            task["version"],
            TaskState.QUEUED,
            "operator requested safe retry",
            f"retry:{task_id}:{task['version']}",
        )

    def seed_demo(self) -> dict[str, Any]:
        task = self.create_task(
            "demo:wecom:delayed-orders:v1",
            "wecom",
            "检查今天超时发货订单，并逐一通知客户",
        )
        transitions = (
            (1, TaskState.PLANNING, "Hermes 已解析企业微信指令", "demo:wecom:planning:v1"),
            (2, TaskState.QUEUED, "执行计划已生成", "demo:wecom:queued:v1"),
            (3, TaskState.ASSIGNED, "已分配给 9 号 AI 手机员工", "demo:wecom:assigned:v1"),
            (4, TaskState.EXECUTING, "手机员工开始检查订单", "demo:wecom:executing:v1"),
        )
        for expected_version, state, reason, idempotency_key in transitions:
            task = self.transition(
                task["task_id"],
                expected_version,
                state,
                reason,
                idempotency_key,
            )
        return {"task": task, "events": self.list_events(task["task_id"])}

    @staticmethod
    def _task_envelope(task: TaskRecord) -> dict[str, Any]:
        result = asdict(task)
        result["state"] = task.state.value
        result["created_at"] = task.created_at.isoformat()
        result["updated_at"] = task.updated_at.isoformat()
        return result

    @staticmethod
    def _event_envelope(event: TaskEvent) -> dict[str, Any]:
        result = asdict(event)
        result["from_state"] = event.from_state.value if event.from_state else None
        result["to_state"] = event.to_state.value
        result["created_at"] = event.created_at.isoformat()
        return result
