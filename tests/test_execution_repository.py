import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from aishop.execution_domain import (
    ActionType,
    EvidenceSource,
    ExecutionStep,
    JobStatus,
    StepResult,
    StepStatus,
)
from aishop.execution_repository import ApprovalConflict, ExecutionRepository, LeaseConflict

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


@pytest.fixture
def repository(tmp_path):
    return ExecutionRepository(tmp_path / "aishop.db", tmp_path / "evidence")


def create_job(repository):
    return repository.create_job(
        "task-1",
        "we-chat",
        "1.0.0",
        (
            ExecutionStep("launch", 0, ActionType.LAUNCH_APP, {"package_name": "com.tencent.mm"}),
            ExecutionStep(
                "verify", 1, ActionType.VERIFY_NODE, {"text_any": ["发送"]}, evidence_required=True
            ),
        ),
        ("com.tencent.mm",),
        ("accessibility",),
        now=NOW,
    )


def test_lease_expires_and_resumes_on_compatible_device(repository):
    job = create_job(repository)
    first = repository.claim_job("phone-1", {"com.tencent.mm"}, {"accessibility"}, NOW)
    assert first.job_id == job.job_id
    assert repository.claim_job("phone-2", {"com.tencent.mm"}, {"accessibility"}, NOW) is None
    assert repository.expire_leases(NOW + timedelta(seconds=31)) == 1
    second = repository.claim_job(
        "phone-2", {"com.tencent.mm"}, {"accessibility"}, NOW + timedelta(seconds=31)
    )
    assert second.job_id == job.job_id
    assert second.lease_id != first.lease_id


def test_duplicate_result_is_idempotent_and_stale_lease_is_rejected(repository):
    job = create_job(repository)
    leased = repository.claim_job("phone-1", {"com.tencent.mm"}, {"accessibility"}, NOW)
    result = StepResult(
        job.job_id, leased.lease_id, "launch", StepStatus.SUCCEEDED, "OK", "", {}, (), NOW
    )
    repository.record_step_result("phone-1", result, NOW)
    repository.record_step_result("phone-1", result, NOW)
    assert (
        len(
            [
                event
                for event in repository.list_timeline("task-1")
                if event["event_type"] == "STEP_RESULT"
            ]
        )
        == 1
    )
    with pytest.raises(LeaseConflict):
        repository.record_step_result(
            "phone-2",
            StepResult(job.job_id, "stale", "verify", StepStatus.SUCCEEDED, "OK", "", {}, (), NOW),
            NOW,
        )


def test_last_successful_step_completes_job(repository):
    job = create_job(repository)
    leased = repository.claim_job("phone-1", {"com.tencent.mm"}, {"accessibility"}, NOW)
    for step_id in ("launch", "verify"):
        evidence_ids = ()
        if step_id == "verify":
            evidence = repository.store_evidence(
                "task-1",
                job.job_id,
                step_id,
                EvidenceSource.DEVICE,
                "text/plain",
                b"verified",
                "verified result",
                NOW,
                device_id="phone-1",
            )
            evidence_ids = (evidence.evidence_id,)
        job = repository.record_step_result(
            "phone-1",
            StepResult(
                job.job_id,
                leased.lease_id,
                step_id,
                StepStatus.SUCCEEDED,
                "OK",
                "",
                {},
                evidence_ids,
                NOW,
            ),
            NOW,
        )
    assert job.status is JobStatus.SUCCEEDED
    assert job.lease_id is None


def test_evidence_is_content_addressed_and_labelled(repository):
    record = repository.store_evidence(
        "task-1",
        "job-1",
        "step-1",
        EvidenceSource.SIMULATED,
        "text/plain",
        b"receipt",
        "SIMULATED receipt",
        NOW,
    )
    loaded, content = repository.get_evidence(record.evidence_id)
    assert content == b"receipt"
    assert loaded.sha256 == hashlib.sha256(content).hexdigest()
    assert loaded.source is EvidenceSource.SIMULATED


def test_approval_token_is_single_use_and_scope_bound(repository):
    raw = "approved-once"
    context = {"recipient": "test-customer", "amount": 20}
    approval = repository.create_approval(
        "task-1", "refund", context, NOW + timedelta(minutes=5), NOW
    )
    repository.decide_approval(
        approval.approval_id, True, hashlib.sha256(raw.encode()).hexdigest(), NOW
    )
    repository.consume_approval(hashlib.sha256(raw.encode()).hexdigest(), "refund", context, NOW)
    with pytest.raises(ApprovalConflict):
        repository.consume_approval(
            hashlib.sha256(raw.encode()).hexdigest(), "refund", context, NOW
        )


def test_global_stop_cancels_jobs_and_releases_active_leases(repository):
    job = create_job(repository)
    repository.claim_job("phone-1", {"com.tencent.mm"}, {"accessibility"}, NOW)
    assert repository.cancel_all(NOW) == 1
    cancelled = repository.get_job(job.job_id)
    assert cancelled.status is JobStatus.CANCELLED
    assert cancelled.lease_id is None


def test_claim_resolves_installed_alias_into_launch_step(repository):
    job = repository.create_job(
        "task-alias",
        "dou-dian",
        "1.0.0",
        (
            ExecutionStep(
                "launch-alias",
                0,
                ActionType.LAUNCH_APP,
                {"package_name": "com.bytedance.ep.android"},
            ),
        ),
        ("com.bytedance.ep.android", "com.ss.android.ugc.aweme"),
        ("accessibility",),
        now=NOW,
    )
    claimed = repository.claim_job(
        "phone-alias", {"com.ss.android.ugc.aweme"}, {"accessibility"}, NOW
    )
    assert claimed.job_id == job.job_id
    assert claimed.required_packages == ("com.ss.android.ugc.aweme",)
    assert claimed.steps[0].arguments["package_name"] == "com.ss.android.ugc.aweme"


def test_claim_rejects_unsupported_installed_app_version(repository):
    repository.create_job(
        "task-version",
        "we-chat",
        "1.0.0",
        (ExecutionStep("launch-version", 0, ActionType.LAUNCH_APP, {"package_name": "app"}),),
        ("app",),
        ("accessibility",),
        supported_app_versions={"app": {"min": "2.0", "max": "3.0"}},
        now=NOW,
    )
    assert repository.claim_job(
        "phone-old", {"app": "1.9"}, {"accessibility"}, NOW
    ) is None
    assert repository.claim_job(
        "phone-new", {"app": "2.5"}, {"accessibility"}, NOW
    ) is not None


def test_claim_normalizes_numeric_version_width(repository):
    repository.create_job(
        "task-version-width",
        "we-chat",
        "1.0.0",
        (ExecutionStep("launch-width", 0, ActionType.LAUNCH_APP, {"package_name": "app"}),),
        ("app",),
        ("accessibility",),
        supported_app_versions={"app": {"min": "2.0.0", "max": "2.1"}},
        now=NOW,
    )
    assert repository.claim_job(
        "phone-equal", {"app": "2"}, {"accessibility"}, NOW
    ) is not None


def test_server_receive_time_and_evidence_ownership_are_authoritative(repository):
    job = create_job(repository)
    leased = repository.claim_job("phone-1", {"com.tencent.mm"}, {"accessibility"}, NOW)
    with pytest.raises(LeaseConflict):
        repository.record_step_result(
            "phone-1",
            StepResult(
                job.job_id,
                leased.lease_id,
                "launch",
                StepStatus.SUCCEEDED,
                "OK",
                "",
                {},
                (),
                NOW,
            ),
            NOW + timedelta(seconds=31),
        )

    repository = ExecutionRepository(repository.database_path.parent / "other.db")
    job = create_job(repository)
    leased = repository.claim_job("phone-1", {"com.tencent.mm"}, {"accessibility"}, NOW)
    with pytest.raises(LeaseConflict):
        repository.validate_evidence_upload(
            "phone-2", "task-1", job.job_id, "verify", NOW
        )
    repository.validate_evidence_upload(
        "phone-1", "task-1", job.job_id, "verify", NOW
    )


def test_evidence_retention_removes_old_unreferenced_file(repository):
    record = repository.store_evidence(
        "task-old",
        "job-old",
        "step-old",
        EvidenceSource.SIMULATED,
        "text/plain",
        b"old",
        "old evidence",
        NOW - timedelta(days=8),
    )
    storage_path = repository.get_evidence(record.evidence_id)[0].storage_path
    result = repository.prune_evidence(NOW)
    assert result["removed"] == 1
    assert not Path(storage_path).exists()
