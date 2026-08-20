import hashlib
import secrets
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from .device_domain import (
    DeviceCommand,
    DeviceCommandType,
    DeviceRecord,
    HeartbeatRecord,
    InstalledApp,
    PermissionState,
    WorkerState,
)
from .device_repository import DeviceRepository
from .domain import utc_now


class InvalidDeviceCommand(ValueError):
    pass


class DeviceService:
    PAIRING_TTL = timedelta(minutes=5)
    ONLINE_TTL = timedelta(seconds=15)
    HEARTBEAT_INTERVAL_SECONDS = 5
    TOKEN_TTL = timedelta(days=90)

    def __init__(
        self,
        repository: DeviceRepository,
        code_generator: Callable[[], str] | None = None,
        token_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] = utc_now,
        execution_service: Any | None = None,
    ):
        self.repository = repository
        self.code_generator = code_generator or self._random_code
        self.token_generator = token_generator or (lambda: secrets.token_urlsafe(32))
        self.clock = clock
        self.execution_service = execution_service

    def create_pairing_session(self) -> dict[str, Any]:
        code = self.code_generator()
        if len(code) != 6 or not code.isdecimal():
            raise ValueError("pairing code generator must return six digits")
        expires_at = self.clock() + self.PAIRING_TTL
        self.repository.create_pairing_session(self._digest(code), expires_at)
        return {"pairing_code": code, "expires_at": expires_at.isoformat()}

    def pair_device(
        self,
        pairing_code: str,
        device_id: str,
        display_name: str,
        app_version: str,
        capabilities: list[str],
    ) -> dict[str, Any]:
        now = self.clock()
        self.repository.consume_pairing_session(self._digest(pairing_code), now)
        raw_token = self.token_generator()
        self.repository.upsert_device(
            DeviceRecord(
                device_id=device_id,
                display_name=display_name,
                token_digest=self._digest(raw_token),
                worker_state=WorkerState.IDLE,
                app_version=app_version,
                capabilities=tuple(sorted(set(capabilities))),
                battery_percent=None,
                permissions=PermissionState(False, False, False),
                installed_apps=(),
                last_sequence=0,
                current_task_id=None,
                paired_at=now,
                last_heartbeat_at=None,
                online=False,
            )
        )
        return {
            "device_id": device_id,
            "device_token": raw_token,
            "heartbeat_interval_seconds": self.HEARTBEAT_INTERVAL_SECONDS,
        }

    def heartbeat(self, device_id: str, raw_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = self.clock()
        self.repository.authenticate(device_id, self._digest(raw_token), now)
        acknowledged_command_id = payload.get("acknowledged_command_id")
        if acknowledged_command_id:
            self.repository.acknowledge_command(device_id, acknowledged_command_id)
        permissions = PermissionState(**payload["permissions"])
        installed_apps = tuple(InstalledApp(**item) for item in payload["installed_apps"])
        device = self.repository.record_heartbeat(
            device_id,
            HeartbeatRecord(
                sequence=payload["sequence"],
                worker_state=WorkerState(payload["worker_state"]),
                current_task_id=payload["current_task_id"],
                battery_percent=payload["battery_percent"],
                permissions=permissions,
                installed_apps=installed_apps,
                received_at=now,
            ),
        )
        job = None
        acknowledged_step_id = None
        if self.execution_service is not None:
            job, acknowledged_step_id = self.execution_service.heartbeat_job(
                device_id=device_id,
                worker_state=payload["worker_state"],
                installed_packages={app.package_name: app.version_name for app in installed_apps},
                capabilities=set(device.capabilities),
                completed_step=payload.get("completed_step"),
                now=now,
            )
        command = self.repository.get_pending_command(device_id)
        return {
            "server_time": now.isoformat(),
            "next_heartbeat_seconds": self.HEARTBEAT_INTERVAL_SECONDS,
            "command": self._command_envelope(command) if command else None,
            "job": job,
            "acknowledged_step_id": acknowledged_step_id,
        }

    def authenticate_token(self, device_id: str, raw_token: str) -> DeviceRecord:
        return self.repository.authenticate(device_id, self._digest(raw_token), self.clock())

    def rotate_token(self, device_id: str) -> dict[str, str]:
        now = self.clock()
        raw_token = self.token_generator()
        self.repository.rotate_token(device_id, self._digest(raw_token), now, self.TOKEN_TTL)
        return {
            "device_id": device_id,
            "device_token": raw_token,
            "expires_at": (now + self.TOKEN_TTL).isoformat(),
        }

    def revoke_token(self, device_id: str) -> dict[str, str]:
        now = self.clock()
        self.repository.revoke_token(device_id, now)
        return {"device_id": device_id, "revoked_at": now.isoformat()}

    def queue_command(self, device_id: str, command_type: str, reason: str) -> dict[str, Any]:
        try:
            safe_type = DeviceCommandType(command_type)
        except ValueError as error:
            raise InvalidDeviceCommand(command_type) from error
        return self._command_envelope(self.repository.queue_command(device_id, safe_type, reason))

    def list_devices(self) -> list[dict[str, Any]]:
        cutoff = self.clock() - self.ONLINE_TTL
        return [self._device_envelope(device) for device in self.repository.list_devices(cutoff)]

    def emergency_stop_all(self, reason: str) -> list[dict[str, Any]]:
        devices = self.repository.list_devices(self.clock() - self.ONLINE_TTL)
        return [
            self._command_envelope(self.repository.queue_emergency_stop(device.device_id, reason))
            for device in devices
        ]

    def _device_envelope(self, device: DeviceRecord) -> dict[str, Any]:
        pending = self.repository.get_pending_command(device.device_id)
        return {
            "device_id": device.device_id,
            "display_name": device.display_name,
            "online": device.online,
            "worker_state": device.worker_state.value,
            "app_version": device.app_version,
            "capabilities": list(device.capabilities),
            "battery_percent": device.battery_percent,
            "permissions": asdict(device.permissions),
            "installed_apps": [asdict(app) for app in device.installed_apps],
            "last_heartbeat_at": (
                device.last_heartbeat_at.isoformat() if device.last_heartbeat_at else None
            ),
            "pending_command": self._command_envelope(pending) if pending else None,
        }

    @staticmethod
    def _command_envelope(command: DeviceCommand) -> dict[str, Any]:
        return {
            "command_id": command.command_id,
            "type": command.type.value,
            "reason": command.reason,
            "created_at": command.created_at.isoformat(),
        }

    @staticmethod
    def _digest(secret: str) -> str:
        return hashlib.sha256(secret.encode()).hexdigest()

    @staticmethod
    def _random_code() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"
