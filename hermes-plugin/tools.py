import json
from collections.abc import Callable
from typing import Any

from .aishop.repository import IdempotencyConflict, TaskNotFound, VersionConflict
from .aishop.runtime import get_dispatch_service, get_service
from .aishop.state_machine import InvalidTransition


def _run(operation: Callable[[], Any]) -> str:
    try:
        return json.dumps(operation(), ensure_ascii=False)
    except TaskNotFound as error:
        return _error("TASK_NOT_FOUND", str(error))
    except VersionConflict as error:
        return _error("VERSION_CONFLICT", str(error))
    except InvalidTransition as error:
        return _error("INVALID_TRANSITION", str(error))
    except IdempotencyConflict as error:
        return _error("IDEMPOTENCY_CONFLICT", str(error))
    except (KeyError, TypeError, ValueError) as error:
        return _error("INVALID_ARGUMENT", str(error))


def _error(code: str, message: str) -> str:
    return json.dumps({"error": {"code": code, "message": message}}, ensure_ascii=False)


def create_task(args: dict, **kwargs) -> str:
    return _run(
        lambda: get_service().create_task(args["idempotency_key"], args["source"], args["title"])
    )


def get_task(args: dict, **kwargs) -> str:
    return _run(lambda: get_service().get_task(args["task_id"]))


def transition_task(args: dict, **kwargs) -> str:
    return _run(
        lambda: get_service().transition(
            args["task_id"],
            args["expected_version"],
            args["target_state"],
            args["reason"],
            args["idempotency_key"],
        )
    )


def stop_all(args: dict, **kwargs) -> str:
    return _run(lambda: get_service().stop_all(args["reason"]))


def dispatch_workflow(args: dict, **kwargs) -> str:
    return _run(
        lambda: get_dispatch_service().dispatch(
            args["task_id"],
            args["app_skill_id"],
            args["workflow_id"],
            args["inputs"],
            args.get("mode", "DEVICE"),
        )
    )
