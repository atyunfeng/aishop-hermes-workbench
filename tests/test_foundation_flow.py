import pytest
from aishop.runtime import (
    clear_runtime_caches,
    get_business_data_service,
    get_demo_flow_service,
    get_device_service,
    get_operator_auth,
    get_service,
    get_workflow_run_service,
)
from dashboard.plugin_api import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AISHOP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AISHOP_OPERATOR_TOKEN", "test-operator-token-0000000000000000")
    clear_runtime_caches()
    get_service.cache_clear()
    get_device_service.cache_clear()
    get_operator_auth.cache_clear()
    get_demo_flow_service.cache_clear()
    get_business_data_service.cache_clear()
    get_workflow_run_service.cache_clear()
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as test_client:
        test_client.headers["X-AIShop-Operator-Token"] = "test-operator-token-0000000000000000"
        yield test_client
    clear_runtime_caches()
    get_service.cache_clear()
    get_device_service.cache_clear()
    get_operator_auth.cache_clear()
    get_demo_flow_service.cache_clear()
    get_business_data_service.cache_clear()
    get_workflow_run_service.cache_clear()


def test_demo_reset_builds_enterprise_wechat_command_flow(client):
    first = client.post("/demo/reset").json()
    second = client.post("/demo/reset").json()
    assert first["removed_tasks"] == 0
    assert second["removed_tasks"] == 1
    assert first["task"]["task_id"] != second["task"]["task_id"]
    assert first["task"]["idempotency_key"] == second["task"]["idempotency_key"]
    task = first["task"]
    assert task["source"] == "wecom"
    assert task["title"] == "检查今天超时发货订单，并逐一通知客户"
    assert task["state"] == "EXECUTING"
    assert [event["to_state"] for event in first["events"]] == [
        "RECEIVED",
        "PLANNING",
        "QUEUED",
        "ASSIGNED",
        "EXECUTING",
    ]
