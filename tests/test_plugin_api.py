import json
from pathlib import Path

import pytest
from aishop.runtime import clear_runtime_caches, get_device_service, get_operator_auth, get_service
from dashboard.plugin_api import router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

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


def validate_workbench(summary):
    contract_dir = ROOT / "packages" / "contracts"
    task_schema = json.loads((contract_dir / "task-envelope.schema.json").read_text())
    summary_schema = json.loads((contract_dir / "workbench-summary.schema.json").read_text())
    registry = Registry().with_resource(
        "task-envelope.schema.json", Resource.from_contents(task_schema)
    )
    Draft202012Validator(summary_schema, registry=registry).validate(summary)


def test_create_task_then_workbench_summary(client):
    created = client.post(
        "/tasks",
        json={
            "idempotency_key": "demo:1",
            "source": "wecom",
            "title": "Check delayed orders",
        },
    )
    assert created.status_code == 201
    summary = client.get("/workbench").json()
    assert summary["task_counts"] == {"RECEIVED": 1}
    assert summary["devices"] == []
    assert summary["approvals"] == []
    validate_workbench(summary)


def test_stale_transition_returns_version_conflict(client):
    task = client.post(
        "/tasks",
        json={"idempotency_key": "demo:2", "source": "wecom", "title": "demo"},
    ).json()
    response = client.post(
        f"/tasks/{task['task_id']}/transitions",
        json={
            "expected_version": 2,
            "target_state": "PLANNING",
            "reason": "planning",
            "idempotency_key": "demo:2:planning",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "VERSION_CONFLICT"


def test_operator_routes_reject_missing_token_but_health_remains_public(client):
    token = client.headers.pop("X-AIShop-Operator-Token")
    try:
        assert client.get("/health").status_code == 200
        response = client.get("/workbench")
        assert response.status_code == 401
        assert response.json()["detail"]["error"]["code"] == "OPERATOR_AUTHENTICATION_FAILED"
    finally:
        client.headers["X-AIShop-Operator-Token"] = token


def test_raw_execution_steps_are_not_an_accepted_api_contract(client):
    response = client.post(
        "/execution/jobs",
        json={
            "task_id": "task",
            "app_skill_id": "we-chat",
            "steps": [{"action": "TAP_NODE", "arguments": {"text_any": ["发送"]}}],
        },
    )
    assert response.status_code == 422
