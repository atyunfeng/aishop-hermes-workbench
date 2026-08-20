import pytest
from aishop.domain import TaskState
from aishop.state_machine import InvalidTransition, require_transition


def test_execution_must_enter_verification_before_success():
    require_transition(TaskState.EXECUTING, TaskState.VERIFYING)
    require_transition(TaskState.VERIFYING, TaskState.SUCCEEDED)


def test_execution_cannot_skip_verification():
    with pytest.raises(InvalidTransition, match="EXECUTING -> SUCCEEDED"):
        require_transition(TaskState.EXECUTING, TaskState.SUCCEEDED)


def test_terminal_states_have_no_outgoing_transitions():
    for state in (TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED):
        with pytest.raises(InvalidTransition):
            require_transition(state, TaskState.QUEUED)
