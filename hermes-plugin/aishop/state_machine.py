from .domain import TaskState


class InvalidTransition(ValueError):
    """Raised when a task transition is not present in the explicit graph."""


TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.RECEIVED: frozenset({TaskState.PLANNING, TaskState.CANCELLED}),
    TaskState.PLANNING: frozenset(
        {
            TaskState.WAITING_APPROVAL,
            TaskState.QUEUED,
            TaskState.HUMAN_TAKEOVER,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.WAITING_APPROVAL: frozenset({TaskState.QUEUED, TaskState.CANCELLED}),
    TaskState.QUEUED: frozenset({TaskState.ASSIGNED, TaskState.CANCELLED}),
    TaskState.ASSIGNED: frozenset(
        {TaskState.EXECUTING, TaskState.QUEUED, TaskState.CANCELLED}
    ),
    TaskState.EXECUTING: frozenset(
        {
            TaskState.VERIFYING,
            TaskState.RETRY_WAIT,
            TaskState.HUMAN_TAKEOVER,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.VERIFYING: frozenset(
        {
            TaskState.SUCCEEDED,
            TaskState.RETRY_WAIT,
            TaskState.HUMAN_TAKEOVER,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.RETRY_WAIT: frozenset(
        {TaskState.QUEUED, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.HUMAN_TAKEOVER: frozenset(
        {TaskState.QUEUED, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.SUCCEEDED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}


def require_transition(source: TaskState, target: TaskState) -> None:
    if target not in TRANSITIONS[source]:
        raise InvalidTransition(f"{source} -> {target}")
