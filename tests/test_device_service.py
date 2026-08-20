import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from aishop.device_repository import (
    DeviceAuthenticationFailed,
    DeviceRepository,
    PairingUnavailable,
)
from aishop.device_service import DeviceService, InvalidDeviceCommand

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


@pytest.fixture
def service(tmp_path):
    return DeviceService(
        DeviceRepository(tmp_path / "aishop.db"),
        code_generator=lambda: "482731",
        token_generator=lambda: "raw-device-token",
        clock=lambda: NOW,
    )


def pair(service):
    session = service.create_pairing_session()
    return service.pair_device(
        session["pairing_code"],
        "android-1",
        "9号 AI 手机员工",
        "0.1.0",
        ["heartbeat", "manual_control"],
    )


def test_pairing_is_five_minutes_single_use_and_hashes_secrets(service):
    session = service.create_pairing_session()
    assert session == {
        "pairing_code": "482731",
        "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
    }
    response = service.pair_device("482731", "android-1", "9号 AI 手机员工", "0.1.0", ["heartbeat"])
    assert response["device_token"] == "raw-device-token"
    digest = hashlib.sha256(b"raw-device-token").hexdigest()
    assert service.repository.authenticate("android-1", digest).token_digest == digest
    with pytest.raises(PairingUnavailable):
        service.pair_device("482731", "android-2", "10号 AI 手机员工", "0.1.0", ["heartbeat"])


def test_heartbeat_auth_and_online_cutoff(service):
    credentials = pair(service)
    with pytest.raises(DeviceAuthenticationFailed):
        service.heartbeat("android-1", "wrong", heartbeat_payload())
    response = service.heartbeat("android-1", credentials["device_token"], heartbeat_payload())
    assert response["next_heartbeat_seconds"] == 5
    assert response["command"] is None
    assert response["job"] is None
    assert response["acknowledged_step_id"] is None
    assert service.list_devices()[0]["online"] is True


def test_only_safe_control_commands_are_accepted(service):
    credentials = pair(service)
    service.heartbeat("android-1", credentials["device_token"], heartbeat_payload())
    command = service.queue_command("android-1", "PAUSE", "operator requested pause")
    assert command["type"] == "PAUSE"
    with pytest.raises(InvalidDeviceCommand):
        service.queue_command("android-1", "TAP", "unsafe arbitrary action")


def heartbeat_payload(acknowledged_command_id=None):
    return {
        "sequence": 1,
        "worker_state": "IDLE",
        "current_task_id": None,
        "battery_percent": 86,
        "permissions": {
            "notifications": True,
            "accessibility": False,
            "screen_capture": False,
        },
        "installed_apps": [],
        "acknowledged_command_id": acknowledged_command_id,
    }
