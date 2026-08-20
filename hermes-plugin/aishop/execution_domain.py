from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class ActionType(StrEnum):
    LAUNCH_APP = "LAUNCH_APP"
    TAP_NODE = "TAP_NODE"
    SET_TEXT = "SET_TEXT"
    SCROLL = "SCROLL"
    BACK = "BACK"
    WAIT_FOR = "WAIT_FOR"
    VERIFY_NODE = "VERIFY_NODE"
    CAPTURE_SCREEN = "CAPTURE_SCREEN"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    LEASED = "LEASED"
    SUCCEEDED = "SUCCEEDED"
    RETRY_WAIT = "RETRY_WAIT"
    HUMAN_TAKEOVER = "HUMAN_TAKEOVER"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    RETRYABLE = "RETRYABLE"
    HUMAN_TAKEOVER = "HUMAN_TAKEOVER"
    FAILED = "FAILED"


class EvidenceSource(StrEnum):
    DEVICE = "DEVICE"
    SIMULATED = "SIMULATED"


class RiskLevel(StrEnum):
    LOW = "LOW"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    HUMAN_ONLY = "HUMAN_ONLY"


SELECTOR_KEYS = frozenset({"text_any", "description_any", "view_id_any"})
FORBIDDEN_ARGUMENT_KEYS = frozenset({"x", "y", "coordinates", "shell", "script"})


def validate_action_arguments(action: ActionType, arguments: dict[str, Any]) -> None:
    if FORBIDDEN_ARGUMENT_KEYS.intersection(arguments):
        raise ValueError("raw coordinates, shell, and script arguments are forbidden")
    allowed: dict[ActionType, set[str]] = {
        ActionType.LAUNCH_APP: {"package_name"},
        ActionType.TAP_NODE: set(SELECTOR_KEYS) | {"require_enabled", "require_clickable"},
        ActionType.SET_TEXT: set(SELECTOR_KEYS) | {"text"},
        ActionType.SCROLL: set(SELECTOR_KEYS) | {"direction"},
        ActionType.BACK: set(),
        ActionType.WAIT_FOR: set(SELECTOR_KEYS),
        ActionType.VERIFY_NODE: set(SELECTOR_KEYS),
        ActionType.CAPTURE_SCREEN: {"label"},
    }
    unknown = set(arguments) - allowed[action]
    if unknown:
        raise ValueError(f"unsupported {action} arguments: {sorted(unknown)}")
    selector_count = sum(key in arguments for key in SELECTOR_KEYS)
    if (
        action
        in {
            ActionType.TAP_NODE,
            ActionType.SET_TEXT,
            ActionType.SCROLL,
            ActionType.WAIT_FOR,
            ActionType.VERIFY_NODE,
        }
        and selector_count != 1
    ):
        raise ValueError(f"{action} requires exactly one semantic selector family")
    for key in SELECTOR_KEYS:
        if key in arguments:
            values = arguments[key]
            if not isinstance(values, list) or not 1 <= len(values) <= 10:
                raise ValueError(f"{key} must contain 1 to 10 strings")
            if any(not isinstance(value, str) or not 1 <= len(value) <= 120 for value in values):
                raise ValueError(f"{key} contains an invalid value")
    if action is ActionType.LAUNCH_APP and not arguments.get("package_name"):
        raise ValueError("LAUNCH_APP requires package_name")
    if action is ActionType.SET_TEXT:
        text = arguments.get("text")
        if not isinstance(text, str) or not 1 <= len(text) <= 2000:
            raise ValueError("SET_TEXT text must contain 1 to 2000 characters")
    if action is ActionType.SCROLL and arguments.get("direction") not in {"FORWARD", "BACKWARD"}:
        raise ValueError("SCROLL direction must be FORWARD or BACKWARD")


@dataclass(frozen=True, slots=True)
class ExecutionStep:
    step_id: str
    ordinal: int
    action: ActionType
    arguments: dict[str, Any]
    timeout_seconds: int = 15
    evidence_required: bool = False

    def __post_init__(self) -> None:
        if not self.step_id or self.ordinal < 0:
            raise ValueError("step_id must be non-empty and ordinal must be non-negative")
        if not 1 <= self.timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be between 1 and 60")
        validate_action_arguments(self.action, self.arguments)


@dataclass(frozen=True, slots=True)
class DeviceJob:
    job_id: str
    task_id: str
    app_skill_id: str
    skill_version: str
    status: JobStatus
    required_packages: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    steps: tuple[ExecutionStep, ...]
    lease_id: str | None
    device_id: str | None
    lease_expires_at: datetime | None
    mode: EvidenceSource
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class StepResult:
    job_id: str
    lease_id: str
    step_id: str
    status: StepStatus
    code: str
    message: str
    observed: dict[str, Any]
    evidence_ids: tuple[str, ...]
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    task_id: str
    job_id: str
    step_id: str
    source: EvidenceSource
    media_type: str
    sha256: str
    byte_size: int
    storage_path: str
    label: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    approval_id: str
    task_id: str
    action: str
    scope: dict[str, Any]
    status: str
    token_digest: str | None
    expires_at: datetime
    created_at: datetime
    decided_at: datetime | None
    used_at: datetime | None
