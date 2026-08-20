import pytest
from aishop.domain import TaskState
from aishop.repository import TaskRepository
from aishop.service import TaskService


@pytest.fixture
def service(tmp_path):
    return TaskService(TaskRepository(tmp_path / "aishop.db"))


def test_create_task_returns_json_ready_envelope(service):
    result = service.create_task("wecom:42", "wecom", "Check delayed orders")
    assert result["state"] == "RECEIVED"
    assert result["version"] == 1
    assert result["created_at"].endswith("+00:00")


def test_stop_all_cancels_only_non_terminal_tasks(service):
    first = service.create_task("one", "demo", "one")
    second = service.create_task("two", "demo", "two")
    service.transition(
        first["task_id"], 1, TaskState.PLANNING, "plan", "one:plan"
    )
    cancelled = service.stop_all("operator emergency stop")
    assert {task["state"] for task in cancelled} == {"CANCELLED"}
    assert service.get_task(second["task_id"])["state"] == "CANCELLED"


def test_transition_accepts_state_name(service):
    task = service.create_task("three", "demo", "three")
    updated = service.transition(
        task["task_id"], 1, "PLANNING", "plan", "three:plan"
    )
    assert updated["state"] == "PLANNING"
