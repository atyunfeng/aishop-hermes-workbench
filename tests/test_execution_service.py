import base64
from datetime import UTC, datetime

from aishop.execution_domain import EvidenceSource
from aishop.execution_repository import ExecutionRepository
from aishop.execution_service import ExecutionService
from aishop.repository import TaskRepository
from aishop.service import TaskService

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def payload():
    return {
        "job_id": "job-1",
        "task_id": "task-1",
        "app_skill_id": "we-chat",
        "skill_version": "1.0.0",
        "required_packages": ["com.tencent.mm"],
        "required_capabilities": ["accessibility"],
        "steps": [
            {
                "step_id": "launch",
                "ordinal": 0,
                "action": "LAUNCH_APP",
                "arguments": {"package_name": "com.tencent.mm"},
            }
        ],
    }


def test_heartbeat_leases_compatible_job_and_acknowledges_result(tmp_path):
    service = ExecutionService(ExecutionRepository(tmp_path / "db"))
    service.create_job(payload())
    job, ack = service.heartbeat_job(
        "phone-1", "IDLE", {"com.tencent.mm"}, {"accessibility"}, None, NOW
    )
    assert job["lease_id"]
    assert ack is None
    completed = {
        "job_id": "job-1",
        "lease_id": job["lease_id"],
        "step_id": "launch",
        "status": "SUCCEEDED",
        "code": "OK",
        "message": "",
        "observed": {},
        "evidence_ids": [],
        "completed_at": NOW.isoformat(),
    }
    next_job, ack = service.heartbeat_job(
        "phone-1", "BUSY", {"com.tencent.mm"}, {"accessibility"}, completed, NOW
    )
    assert next_job is None
    assert ack == "launch"


def test_evidence_upload_is_bounded_and_strips_storage_path(tmp_path):
    service = ExecutionService(ExecutionRepository(tmp_path / "db"))
    envelope = service.upload_evidence(
        {
            "task_id": "task-1",
            "job_id": "job-1",
            "step_id": "step-1",
            "source": "SIMULATED",
            "media_type": "image/jpeg",
            "content_base64": base64.b64encode(b"jpeg").decode(),
            "label": "device screen",
        },
        source=EvidenceSource.SIMULATED,
    )
    assert envelope["source"] == "SIMULATED"
    assert "storage_path" not in envelope


def test_real_device_job_advances_task_through_verification(tmp_path):
    tasks = TaskService(TaskRepository(tmp_path / "db"))
    task = tasks.create_task("key", "we-chat", "reply")
    task = tasks.transition(task["task_id"], 1, "PLANNING", "planned", "plan")
    task = tasks.transition(task["task_id"], 2, "QUEUED", "queued", "queue")
    repository = ExecutionRepository(tmp_path / "db")
    service = ExecutionService(repository, tasks)
    job_payload = payload() | {"task_id": task["task_id"]}
    service.create_job(job_payload)
    job, _ = service.heartbeat_job(
        "phone-1", "IDLE", {"com.tencent.mm"}, {"accessibility"}, None, NOW
    )
    assert tasks.get_task(task["task_id"])["state"] == "EXECUTING"
    completed = {
        "job_id": "job-1",
        "lease_id": job["lease_id"],
        "step_id": "launch",
        "status": "SUCCEEDED",
        "code": "OK",
        "message": "",
        "observed": {},
        "evidence_ids": [],
        "completed_at": NOW.isoformat(),
    }
    service.heartbeat_job("phone-1", "BUSY", {"com.tencent.mm"}, {"accessibility"}, completed, NOW)
    assert tasks.get_task(task["task_id"])["state"] == "SUCCEEDED"
