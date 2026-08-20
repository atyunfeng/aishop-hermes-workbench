from datetime import UTC, datetime

import pytest
from aishop.workflow_runs import WorkflowRunService

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def nodes():
    return [
        {"node_id": "a", "name": "A", "target": "qian", "dependencies": []},
        {"node_id": "b", "name": "B", "target": "dou", "dependencies": []},
        {
            "node_id": "summary",
            "name": "Summary",
            "target": "wecom",
            "dependencies": ["a", "b"],
        },
    ]


def test_ready_nodes_follow_dependencies_and_aggregate_success(tmp_path):
    service = WorkflowRunService(tmp_path / "aishop.db")
    service.create("parent", nodes(), "run-1", NOW)
    assert {node["node_id"] for node in service.ready_nodes("run-1")} == {"a", "b"}
    service.complete_node("a", "SUCCEEDED", {"count": 1}, NOW)
    service.complete_node("b", "SUCCEEDED", {"count": 2}, NOW)
    assert [node["node_id"] for node in service.ready_nodes("run-1")] == ["summary"]
    service.complete_node("summary", "SUCCEEDED", {"count": 3}, NOW)
    assert service.get("run-1")["status"] == "SUCCEEDED"


def test_partial_success_and_idempotent_completion(tmp_path):
    service = WorkflowRunService(tmp_path / "aishop.db")
    service.create("parent", nodes()[:2], "run-2", NOW)
    service.complete_node("a", "SUCCEEDED", {"ok": True}, NOW)
    service.complete_node("a", "SUCCEEDED", {"ok": True}, NOW)
    service.complete_node("b", "FAILED", {"code": "OFFLINE"}, NOW)
    assert service.get("run-2")["status"] == "PARTIAL_SUCCESS"
    with pytest.raises(ValueError):
        service.complete_node("a", "FAILED", {"ok": False}, NOW)


def test_cycle_is_rejected(tmp_path):
    service = WorkflowRunService(tmp_path / "aishop.db")
    with pytest.raises(ValueError, match="cycle"):
        service.create(
            "parent",
            [
                {"node_id": "a", "name": "A", "target": "x", "dependencies": ["b"]},
                {"node_id": "b", "name": "B", "target": "x", "dependencies": ["a"]},
            ],
        )
