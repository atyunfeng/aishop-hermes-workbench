import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from aishop.execution_domain import RiskLevel
from aishop.execution_repository import ExecutionRepository
from aishop.policy import PolicyDenied, PolicyEngine

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def test_low_risk_whitelisted_reply_is_automatic(tmp_path):
    policy = PolicyEngine(ExecutionRepository(tmp_path / "db"), {"test-customer"})
    assert policy.authorize("reply", {"recipient": "test-customer"}, None, NOW) is RiskLevel.LOW
    with pytest.raises(PolicyDenied):
        policy.authorize("reply", {"recipient": "real-customer"}, None, NOW)


def test_captcha_is_human_only_even_with_token(tmp_path):
    policy = PolicyEngine(ExecutionRepository(tmp_path / "db"), {"test-customer"})
    with pytest.raises(PolicyDenied, match="human takeover"):
        policy.authorize(
            "reply", {"recipient": "test-customer", "signals": ["captcha"]}, "token", NOW
        )


def test_scoped_approval_allows_exactly_one_high_risk_action(tmp_path):
    repository = ExecutionRepository(tmp_path / "db")
    policy = PolicyEngine(repository, {"test-customer"})
    context = {"recipient": "test-customer", "amount": 20}
    approval = repository.create_approval(
        "task", "refund", context, NOW + timedelta(minutes=5), NOW
    )
    repository.decide_approval(
        approval.approval_id, True, hashlib.sha256(b"raw-token").hexdigest(), NOW
    )
    assert policy.authorize("refund", context, "raw-token", NOW) is RiskLevel.APPROVAL_REQUIRED
    with pytest.raises(PolicyDenied):
        policy.authorize("refund", context, "raw-token", NOW)
