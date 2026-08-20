from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class WorkerState(StrEnum):
    OFFLINE = "OFFLINE"
    IDLE = "IDLE"
    BUSY = "BUSY"
    PAUSED = "PAUSED"
    TAKEOVER = "TAKEOVER"
    ERROR = "ERROR"


class DeviceCommandType(StrEnum):
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    TAKEOVER = "TAKEOVER"
    STOP = "STOP"


class DeviceCommandStatus(StrEnum):
    PENDING = "PENDING"
    ACKNOWLEDGED = "ACKNOWLEDGED"


@dataclass(frozen=True, slots=True)
class PermissionState:
    notifications: bool
    accessibility: bool
    screen_capture: bool


@dataclass(frozen=True, slots=True)
class InstalledApp:
    package_name: str
    version_name: str


@dataclass(frozen=True, slots=True)
class PairingSession:
    code_digest: str
    expires_at: datetime
    consumed_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DeviceRecord:
    device_id: str
    display_name: str
    token_digest: str
    worker_state: WorkerState
    app_version: str
    capabilities: tuple[str, ...]
    battery_percent: int | None
    permissions: PermissionState
    installed_apps: tuple[InstalledApp, ...]
    last_sequence: int
    current_task_id: str | None
    paired_at: datetime
    last_heartbeat_at: datetime | None
    online: bool


@dataclass(frozen=True, slots=True)
class HeartbeatRecord:
    sequence: int
    worker_state: WorkerState
    current_task_id: str | None
    battery_percent: int
    permissions: PermissionState
    installed_apps: tuple[InstalledApp, ...]
    received_at: datetime


@dataclass(frozen=True, slots=True)
class DeviceCommand:
    command_id: str
    device_id: str
    type: DeviceCommandType
    reason: str
    status: DeviceCommandStatus
    created_at: datetime
    acknowledged_at: datetime | None
