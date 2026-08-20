from aishop.app_skills import AppSkillRegistry
from aishop.demo_flows import FLOWS, DemoFlowService
from aishop.execution_repository import ExecutionRepository
from aishop.execution_service import ExecutionService
from aishop.repository import TaskRepository
from aishop.service import TaskService


def service(tmp_path):
    repository = ExecutionRepository(tmp_path / "aishop.db", tmp_path / "evidence")
    return DemoFlowService(
        TaskService(TaskRepository(tmp_path / "aishop.db")),
        AppSkillRegistry.load("hermes-plugin/app_skills"),
        ExecutionService(repository),
        repository,
    )


def test_all_four_flows_run_ten_times_with_explicit_simulated_evidence(tmp_path):
    demo = service(tmp_path)
    for run_number in range(10):
        for flow_id in FLOWS:
            result = demo.run(flow_id, "SIMULATED", run_id=f"{flow_id}-{run_number}")
            assert result["mode"] == "SIMULATED"
            assert result["task"]["state"] == "SUCCEEDED"
            states = [event["to_state"] for event in result["task_events"]]
            assert states[-2:] == ["VERIFYING", "SUCCEEDED"]
            assert all(
                event["payload"].get("sha256")
                for event in result["timeline"]
                if event["event_type"] == "EVIDENCE_STORED"
            )


def test_offline_requeues_and_captcha_or_unknown_page_take_over(tmp_path):
    demo = service(tmp_path)
    offline = demo.run("we_chat_private_service", "SIMULATED", "offline")
    assert offline["task"]["state"] == "RETRY_WAIT"
    assert offline["job"]["status"] == "RETRY_WAIT"
    for fault in ("captcha", "unknown-page"):
        result = demo.run("qian_niu_customer_service", "SIMULATED", fault)
        assert result["task"]["state"] == "HUMAN_TAKEOVER"
        assert result["job"]["status"] == "HUMAN_TAKEOVER"


def test_device_mode_stays_queued_for_a_real_compatible_worker(tmp_path):
    result = service(tmp_path).run("we_com_multi_phone", "DEVICE")
    assert result["mode"] == "DEVICE"
    assert result["task"]["state"] == "QUEUED"
    assert result["job"]["status"] == "QUEUED"
    assert result["job"]["task_id"] != result["task"]["task_id"]
    assert len(
        [node for node in result["workflow_run"]["nodes"] if node["status"] == "RUNNING"]
    ) == 2
