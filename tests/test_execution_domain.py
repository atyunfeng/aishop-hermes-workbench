import pytest
from aishop.execution_domain import ActionType, ExecutionStep


def test_semantic_action_accepts_one_selector_family():
    step = ExecutionStep("send", 1, ActionType.TAP_NODE, {"text_any": ["发送"]})
    assert step.action is ActionType.TAP_NODE


@pytest.mark.parametrize(
    "arguments",
    [
        {"x": 10, "y": 20},
        {"text_any": ["发送"], "view_id_any": ["send"]},
        {},
        {"text_any": []},
    ],
)
def test_semantic_action_rejects_coordinates_or_ambiguous_selector(arguments):
    with pytest.raises(ValueError):
        ExecutionStep("send", 1, ActionType.TAP_NODE, arguments)


def test_set_text_is_bounded():
    with pytest.raises(ValueError):
        ExecutionStep(
            "reply",
            2,
            ActionType.SET_TEXT,
            {"description_any": ["输入消息"], "text": "x" * 2001},
        )
