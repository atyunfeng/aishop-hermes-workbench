from datetime import UTC, datetime

from aishop.business_data import BusinessDataService

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def test_order_import_is_idempotent_and_preserves_snapshot_metadata(tmp_path):
    service = BusinessDataService(tmp_path / "aishop.db")
    order = {"order_id": "ORDER-1", "status": "已发货"}
    assert service.import_orders([order], "manual", NOW) == {"imported": 1, "unchanged": 0}
    assert service.import_orders([order], "manual", NOW) == {"imported": 0, "unchanged": 1}
    loaded = service.get_order("ORDER-1")
    assert loaded["status"] == "已发货"
    assert loaded["snapshot_source"] == "manual"


def test_versioned_knowledge_is_searchable_with_citation_identity(tmp_path):
    service = BusinessDataService(tmp_path / "aishop.db")
    stored = service.put_knowledge(
        "returns", "v1", "退货规则", "商品破损可在七天内申请退货", now=NOW
    )
    results = service.search_knowledge("破损")
    assert results[0]["knowledge_id"] == "returns"
    assert results[0]["version"] == "v1"
    assert len(stored["content_sha256"]) == 64


def test_image_analysis_is_honest_when_provider_is_not_configured(tmp_path):
    service = BusinessDataService(tmp_path / "aishop.db")
    unavailable = service.create_image_analysis("artifact-1", now=NOW)
    assert unavailable["status"] == "UNAVAILABLE"
    assert unavailable["reason"] == "VISION_PROVIDER_NOT_CONFIGURED"
    queued = service.create_image_analysis("artifact-2", "vision-test", NOW)
    completed = service.complete_image_analysis(
        queued["request_id"], {"damage": True}, NOW
    )
    assert completed["status"] == "SUCCEEDED"
    assert completed["result"] == {"damage": True}
