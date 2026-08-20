import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from aishop.device_domain import (
    DeviceCommandType,
    DeviceRecord,
    HeartbeatRecord,
    PermissionState,
    WorkerState,
)
from aishop.device_repository import (
    DeviceAuthenticationFailed,
    DeviceRepository,
    PairingUnavailable,
    PendingCommandConflict,
)

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


@pytest.fixture
def repository(tmp_path):
    return DeviceRepository(tmp_path / "aishop.db")


def device(token_digest="token-digest"):
    return DeviceRecord(
        device_id="android-1",
        display_name="9号 AI 手机员工",
        token_digest=token_digest,
        worker_state=WorkerState.IDLE,
        app_version="0.1.0",
        capabilities=("heartbeat", "manual_control"),
        battery_percent=None,
        permissions=PermissionState(False, False, False),
        installed_apps=(),
        last_sequence=0,
        current_task_id=None,
        paired_at=NOW,
        last_heartbeat_at=None,
        online=False,
    )


def heartbeat(sequence, state=WorkerState.IDLE, received_at=NOW):
    return HeartbeatRecord(
        sequence=sequence,
        worker_state=state,
        current_task_id=None,
        battery_percent=86,
        permissions=PermissionState(True, False, False),
        installed_apps=(),
        received_at=received_at,
    )


def test_pairing_code_is_single_use_and_raw_secrets_are_not_stored(repository):
    repository.create_pairing_session("code-digest", NOW + timedelta(minutes=5))
    repository.consume_pairing_session("code-digest", NOW)
    with pytest.raises(PairingUnavailable):
        repository.consume_pairing_session("code-digest", NOW)
    repository.upsert_device(device())

    connection = sqlite3.connect(repository.database_path)
    dump = "\n".join(connection.iterdump())
    connection.close()
    assert "482731" not in dump
    assert "raw-device-token" not in dump
    assert "code-digest" in dump
    assert "token-digest" in dump


def test_expired_pairing_code_is_rejected(repository):
    repository.create_pairing_session("expired", NOW - timedelta(seconds=1))
    with pytest.raises(PairingUnavailable):
        repository.consume_pairing_session("expired", NOW)


def test_old_heartbeat_does_not_overwrite_newer_device_state(repository):
    repository.upsert_device(device())
    current = repository.record_heartbeat("android-1", heartbeat(2, WorkerState.BUSY))
    stale = repository.record_heartbeat("android-1", heartbeat(1, WorkerState.ERROR))
    assert current.worker_state is WorkerState.BUSY
    assert stale.worker_state is WorkerState.BUSY
    assert stale.last_sequence == 2


def test_command_redelivers_until_acknowledged(repository):
    repository.upsert_device(device())
    command = repository.queue_command(
        "android-1", DeviceCommandType.PAUSE, "operator requested pause"
    )
    assert repository.get_pending_command("android-1") == command
    assert repository.get_pending_command("android-1") == command
    with pytest.raises(PendingCommandConflict):
        repository.queue_command("android-1", DeviceCommandType.STOP, "stop")
    repository.acknowledge_command("android-1", command.command_id)
    assert repository.get_pending_command("android-1") is None


def test_online_state_uses_supplied_cutoff(repository):
    repository.upsert_device(device())
    repository.record_heartbeat("android-1", heartbeat(1, received_at=NOW))
    online = repository.list_devices(NOW - timedelta(seconds=15))[0]
    offline = repository.list_devices(NOW + timedelta(seconds=1))[0]
    assert online.online is True
    assert offline.online is False


def test_emergency_stop_replaces_any_pending_device_command(repository):
    repository.upsert_device(device())
    pending = repository.queue_command("android-1", DeviceCommandType.PAUSE, "pause")
    stopped = repository.queue_emergency_stop("android-1", "global emergency stop")
    assert stopped.command_id == pending.command_id
    assert stopped.type is DeviceCommandType.STOP
    assert stopped.reason == "global emergency stop"


def test_token_rotation_expiry_and_revoke_are_enforced(repository):
    repository.upsert_device(device("old"))
    repository.authenticate("android-1", "old", NOW)
    repository.rotate_token("android-1", "new", NOW, timedelta(minutes=5))
    with pytest.raises(DeviceAuthenticationFailed):
        repository.authenticate("android-1", "old", NOW)
    repository.authenticate("android-1", "new", NOW + timedelta(minutes=5))
    with pytest.raises(DeviceAuthenticationFailed):
        repository.authenticate("android-1", "new", NOW + timedelta(minutes=6))
    repository.rotate_token("android-1", "newer", NOW, timedelta(minutes=5))
    repository.revoke_token("android-1", NOW)
    with pytest.raises(DeviceAuthenticationFailed):
        repository.authenticate("android-1", "newer", NOW)
