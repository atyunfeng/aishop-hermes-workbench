import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[1]


def load_schema(name: str) -> dict:
    return json.loads((ROOT / "packages" / "contracts" / name).read_text())


def test_task_contract_has_versioned_identity_and_state():
    schema = load_schema("task-envelope.schema.json")
    assert schema["$id"] == "aishop.task-envelope.v1"
    assert set(schema["required"]) == {
        "task_id",
        "idempotency_key",
        "source",
        "title",
        "state",
        "version",
        "created_at",
        "updated_at",
    }
    assert schema["properties"]["state"]["enum"] == [
        "RECEIVED",
        "PLANNING",
        "WAITING_APPROVAL",
        "QUEUED",
        "ASSIGNED",
        "EXECUTING",
        "VERIFYING",
        "SUCCEEDED",
        "RETRY_WAIT",
        "HUMAN_TAKEOVER",
        "FAILED",
        "CANCELLED",
    ]


def test_workbench_contract_exposes_tasks_devices_and_approvals():
    schema = load_schema("workbench-summary.schema.json")
    assert schema["$id"] == "aishop.workbench-summary.v1"
    assert set(schema["required"]) == {
        "generated_at",
        "task_counts",
        "devices",
        "approvals",
        "recent_tasks",
    }
    assert schema["properties"]["devices"]["items"] == {"$ref": "device-envelope.schema.json"}


def test_device_contract_has_health_and_safe_control_enums():
    schema = load_schema("device-envelope.schema.json")
    assert schema["$id"] == "aishop.device-envelope.v1"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "device_id",
        "display_name",
        "online",
        "worker_state",
        "app_version",
        "capabilities",
        "battery_percent",
        "permissions",
        "installed_apps",
        "last_heartbeat_at",
        "pending_command",
    }
    assert schema["properties"]["worker_state"]["enum"] == [
        "OFFLINE",
        "IDLE",
        "BUSY",
        "PAUSED",
        "TAKEOVER",
        "ERROR",
    ]
    command_schema = schema["$defs"]["command"]
    assert command_schema["additionalProperties"] is False
    assert command_schema["properties"]["type"]["enum"] == [
        "PAUSE",
        "RESUME",
        "TAKEOVER",
        "STOP",
    ]


def test_device_pair_request_is_sealed():
    schema = load_schema("device-pair-request.schema.json")
    assert schema["$id"] == "aishop.device-pair-request.v1"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "pairing_code",
        "device_id",
        "display_name",
        "app_version",
        "capabilities",
    }


def test_device_heartbeat_contract_bounds_sequence_and_battery():
    schema = load_schema("device-heartbeat.schema.json")
    assert schema["$id"] == "aishop.device-heartbeat.v1"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["sequence"]["minimum"] == 1
    assert schema["properties"]["battery_percent"] == {
        "type": "integer",
        "minimum": 0,
        "maximum": 100,
    }
    assert schema["properties"]["permissions"]["additionalProperties"] is False
    assert schema["$defs"]["installed_app"]["additionalProperties"] is False
    assert "completed_step" in schema["required"]


def test_device_job_contract_uses_closed_actions_and_rejects_coordinates():
    schema = load_schema("device-job.schema.json")
    assert schema["$id"] == "aishop.device-job.v1"
    actions = schema["$defs"]["step"]["properties"]["action"]["enum"]
    assert actions == [
        "LAUNCH_APP",
        "TAP_NODE",
        "SET_TEXT",
        "SCROLL",
        "BACK",
        "WAIT_FOR",
        "VERIFY_NODE",
        "CAPTURE_SCREEN",
    ]
    validator = Draft202012Validator(schema)
    job = {
        "job_id": "job-1",
        "task_id": "task-1",
        "app_skill_id": "we-chat",
        "skill_version": "1.0.0",
        "lease_id": "lease-1",
        "lease_expires_at": "2026-08-17T12:00:30Z",
        "steps": [
            {
                "step_id": "tap-send",
                "ordinal": 1,
                "action": "TAP_NODE",
                "arguments": {"text_any": ["发送"]},
                "timeout_seconds": 15,
                "evidence_required": False,
            }
        ],
    }
    assert list(validator.iter_errors(job)) == []
    job["steps"][0]["arguments"] = {"x": 10, "y": 20}
    assert list(validator.iter_errors(job))


def test_evidence_contract_requires_explicit_source_label():
    schema = load_schema("evidence-envelope.schema.json")
    assert schema["properties"]["source"]["enum"] == ["DEVICE", "SIMULATED"]
    assert "source" in schema["required"]
