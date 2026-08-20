import pytest
from aishop.domain import TaskState
from aishop.repository import TaskRepository, VersionConflict


@pytest.fixture
def repository(tmp_path):
    return TaskRepository(tmp_path / "aishop.db")


def test_duplicate_create_returns_same_task(repository):
    first = repository.create_task("msg:1", "qianniu", "Reply to buyer")
    second = repository.create_task("msg:1", "qianniu", "Reply to buyer")
    assert second.task_id == first.task_id
    assert repository.count_by_state() == {"RECEIVED": 1}


def test_transition_increments_version_and_appends_event(repository):
    task = repository.create_task("cmd:1", "wecom", "Check delayed orders")
    updated = repository.transition(
        task.task_id,
        expected_version=1,
        target=TaskState.PLANNING,
        reason="accepted by Hermes",
        idempotency_key="cmd:1:planning",
    )
    assert updated.version == 2
    assert updated.state is TaskState.PLANNING
    assert len(repository.list_events(task.task_id)) == 2


def test_stale_transition_does_not_append_event(repository):
    task = repository.create_task("cmd:2", "wecom", "Check delayed orders")
    repository.transition(
        task.task_id, 1, TaskState.PLANNING, "planned", "cmd:2:planning"
    )
    with pytest.raises(VersionConflict):
        repository.transition(task.task_id, 1, TaskState.QUEUED, "queue", "cmd:2:queue")
    assert len(repository.list_events(task.task_id)) == 2


def test_list_non_terminal_excludes_terminal_tasks(repository):
    active = repository.create_task("active", "demo", "active")
    terminal = repository.create_task("terminal", "demo", "terminal")
    repository.transition(
        terminal.task_id,
        expected_version=1,
        target=TaskState.CANCELLED,
        reason="cancelled",
        idempotency_key="terminal:cancelled",
    )
    assert [task.task_id for task in repository.list_non_terminal()] == [active.task_id]
