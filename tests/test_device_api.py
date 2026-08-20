import json
from pathlib import Path

import pytest
from aishop.runtime import clear_runtime_caches, get_device_service, get_operator_auth, get_service
from dashboard.plugin_api import router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[1]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AISHOP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AISHOP_OPERATOR_TOKEN", "test-operator-token-0000000000000000")
    clear_runtime_caches()
    get_service.cache_clear()
    get_device_service.cache_clear()
    get_operator_auth.cache_clear()
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as test_client:
        test_client.headers["X-AIShop-Operator-Token"] = "test-operator-token-0000000000000000"
        yield test_client
    clear_runtime_caches()
    get_service.cache_clear()
    get_device_service.cache_clear()
    get_operator_auth.cache_clear()


def pair_device(client):
    session = client.post("/devices/pairing-sessions").json()
    response = client.post(
        "/devices/pair",
        json={
            "pairing_code": session["pairing_code"],
            "device_id": "android-1",
            "display_name": "9号 AI 手机员工",
            "app_version": "0.1.0",
            "capabilities": ["heartbeat", "manual_control"],
        },
    )
    assert response.status_code == 201
    return response.json()


def heartbeat(sequence=1, acknowledged_command_id=None):
    return {
        "sequence": sequence,
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


def test_authenticated_heartbeat_and_command_acknowledgement(client):
    credentials = pair_device(client)
    endpoint = "/devices/android-1/heartbeat"
    assert client.post(endpoint, json=heartbeat()).status_code == 401
    headers = {"Authorization": f"Bearer {credentials['device_token']}"}
    assert client.post(endpoint, headers=headers, json=heartbeat()).status_code == 200

    queued = client.post(
        "/devices/android-1/commands",
        json={"type": "PAUSE", "reason": "operator requested pause"},
    )
    assert queued.status_code == 201
    command = client.post(endpoint, headers=headers, json=heartbeat(sequence=2)).json()["command"]
    assert command["type"] == "PAUSE"
    response = client.post(
        endpoint,
        headers=headers,
        json=heartbeat(sequence=3, acknowledged_command_id=command["command_id"]),
    ).json()
    assert response["command"] is None


def test_workbench_exposes_schema_valid_device(client):
    credentials = pair_device(client)
    client.post(
        "/devices/android-1/heartbeat",
        headers={"Authorization": f"Bearer {credentials['device_token']}"},
        json=heartbeat(),
    )
    device = client.get("/workbench").json()["devices"][0]
    schema = json.loads(
        (ROOT / "packages/contracts/device-envelope.schema.json").read_text()
    )
    Draft202012Validator(schema).validate(device)
    assert device["online"] is True


def test_heartbeat_rejects_wrong_token(client):
    pair_device(client)
    response = client.post(
        "/devices/android-1/heartbeat",
        headers={"Authorization": "Bearer wrong"},
        json=heartbeat(),
    )
    assert response.status_code == 401
