from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class TaskState(StrEnum):
    RECEIVED = "RECEIVED"
    PLANNING = "PLANNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    QUEUED = "QUEUED"
    ASSIGNED = "ASSIGNED"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    RETRY_WAIT = "RETRY_WAIT"
    HUMAN_TAKEOVER = "HUMAN_TAKEOVER"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class TaskRecord:
    task_id: str
    idempotency_key: str
    source: str
    title: str
    state: TaskState
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TaskEvent:
    event_id: str
    task_id: str
    from_state: TaskState | None
    to_state: TaskState
    reason: str
    created_at: datetime
    idempotency_key: str


def utc_now() -> datetime:
    return datetime.now(UTC)
