from datetime import UTC, datetime

import pytest
from aishop.app_skills import AppSkillRegistry
from aishop.dispatch_service import DispatchService
from aishop.execution_repository import ApprovalConflict, ExecutionRepository
from aishop.execution_service import ExecutionService
from aishop.repository import TaskRepository
from aishop.service import TaskService

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def services(tmp_path):
    tasks = TaskService(TaskRepository(tmp_path / "aishop.db"))
    repository = ExecutionRepository(tmp_path / "aishop.db", tmp_path / "evidence")
    execution = ExecutionService(repository, tasks)
    dispatch = DispatchService(
        tasks,
        AppSkillRegistry.load("hermes-plugin/app_skills"),
        execution,
        repository,
        {"AIShop 测试客户", "DEMO-DD-2001"},
    )
    return tasks, repository, dispatch


def planning_task(tasks, key="dispatch:1"):
    task = tasks.create_task(key, "test", "dispatch")
    return tasks.transition(task["task_id"], 1, "PLANNING", "plan", f"{key}:plan")


def test_low_risk_workflow_is_compiled_and_queued_server_side(tmp_path):
    tasks, _, dispatch = services(tmp_path)
    task = planning_task(tasks)
    result = dispatch.dispatch(
        task["task_id"],
        "qian-niu",
        "customer_reply",
        {
            "package_name": "com.taobao.qianniu",
            "customer_name": "AIShop 测试客户",
            "reply_text": "已收到",
        },
        now=NOW,
    )
    assert result["status"] == "QUEUED"
    assert result["task"]["state"] == "QUEUED"
    assert result["job"]["app_skill_id"] == "qian-niu"


def test_approval_resumes_exact_bound_return_workflow_once(tmp_path):
    tasks, repository, dispatch = services(tmp_path)
    task = planning_task(tasks, "dispatch:approval")
    waiting = dispatch.dispatch(
        task["task_id"],
        "dou-dian",
        "create_return_request",
        {
            "package_name": "com.bytedance.ep.android",
            "order_id": "DEMO-DD-2001",
            "reason": "测试商品破损",
        },
        now=NOW,
    )
    approval_id = waiting["approval"]["approval_id"]
    assert waiting["task"]["state"] == "WAITING_APPROVAL"
    resumed = dispatch.decide_and_resume(approval_id, True, NOW)
    assert resumed["status"] == "QUEUED"
    assert resumed["job"]["task_id"] == task["task_id"]
    assert repository.get_approval(approval_id).used_at == NOW
    with pytest.raises((ApprovalConflict, ValueError)):
        dispatch.decide_and_resume(approval_id, True, NOW)


def test_rejected_approval_cancels_without_creating_job(tmp_path):
    tasks, _, dispatch = services(tmp_path)
    task = planning_task(tasks, "dispatch:reject")
    waiting = dispatch.dispatch(
        task["task_id"],
        "dou-dian",
        "create_return_request",
        {
            "package_name": "com.bytedance.ep.android",
            "order_id": "DEMO-DD-2001",
            "reason": "测试",
        },
        now=NOW,
    )
    result = dispatch.decide_and_resume(waiting["approval"]["approval_id"], False, NOW)
    assert result["task"]["state"] == "CANCELLED"
