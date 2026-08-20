from datetime import UTC, datetime

import pytest
from aishop.inbound_events import InboundEventService
from aishop.repository import IdempotencyConflict, TaskRepository
from aishop.service import TaskService

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def payload(source="we-com", text="检查超时订单"):
    return {
        "event_id": "event-1",
        "source": source,
        "account_id": "shop-1",
        "conversation_id": "conversation-1",
        "sender": "AIShop 企业微信测试群",
        "event_type": "INSTRUCTION",
        "text": text,
        "attachments": [],
        "occurred_at": NOW.isoformat(),
    }


def service(tmp_path):
    database = tmp_path / "aishop.db"
    tasks = TaskService(TaskRepository(database))
    return InboundEventService(database, tasks), tasks


def test_known_event_is_idempotently_routed_to_one_task(tmp_path):
    events, tasks = service(tmp_path)
    first = events.ingest("phone-1", payload(), NOW)
    second = events.ingest("phone-1", payload(), NOW)
    assert first["task"]["task_id"] == second["task"]["task_id"]
    assert second["duplicate"] is True
    assert tasks.count_by_state() == {"RECEIVED": 1}


def test_reused_identity_with_different_payload_is_rejected(tmp_path):
    events, _ = service(tmp_path)
    events.ingest("phone-1", payload(), NOW)
    with pytest.raises(IdempotencyConflict):
        events.ingest("phone-1", payload(text="different"), NOW)


def test_unknown_source_is_quarantined_without_a_task(tmp_path):
    events, tasks = service(tmp_path)
    result = events.ingest("phone-1", payload(source="unknown"), NOW)
    assert result["event"]["status"] == "QUARANTINED"
    assert result["task"] is None
    assert tasks.count_by_state() == {}
