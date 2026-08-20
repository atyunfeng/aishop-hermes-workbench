from pathlib import Path

import pytest
from aishop.app_skills import AppSkillRegistry

ROOT = Path(__file__).parents[1] / "hermes-plugin" / "app_skills"


def test_loads_five_versioned_app_skills_and_closed_actions():
    registry = AppSkillRegistry.load(ROOT)
    assert set(registry.skills) == {"qian-niu", "dou-dian", "we-chat", "we-com", "qq"}
    assert all(skill.version == "1.0.0" for skill in registry.skills.values())


def test_compiles_semantic_workflow_with_exact_inputs():
    registry = AppSkillRegistry.load(ROOT)
    job = registry.compile(
        "we-chat",
        "private_customer_reply",
        {
            "package_name": "com.tencent.mm",
            "customer_name": "AIShop 测试客户",
            "reply_text": "订单已发出，请留意物流更新。",
        },
        "task-1",
    )
    assert job["required_packages"] == ["com.tencent.mm"]
    assert job["steps"][0]["arguments"] == {"package_name": "com.tencent.mm"}
    assert all("x" not in step["arguments"] for step in job["steps"])
    assert job["steps"][-1]["evidence_required"] is True


def test_rejects_unknown_inputs_alias_and_partial_placeholder():
    registry = AppSkillRegistry.load(ROOT)
    base = {
        "package_name": "com.tencent.mm",
        "customer_name": "AIShop 测试客户",
        "reply_text": "回复",
    }
    with pytest.raises(ValueError, match="unknown"):
        registry.compile("we-chat", "private_customer_reply", {**base, "extra": "x"}, "task")
    with pytest.raises(ValueError, match="alias"):
        registry.compile(
            "we-chat", "private_customer_reply", {**base, "package_name": "bad.app"}, "task"
        )


def test_validates_recorded_fixtures_and_app_version_ranges():
    registry = AppSkillRegistry.load(ROOT)
    assert registry.supports_app_version("dou-dian", "com.bytedance.ep.android", "30.0.0")
    assert registry.supports_app_version("dou-dian", "com.ss.android.ugc.aweme", "31.2")
    assert not registry.supports_app_version("dou-dian", "bad.package", "1.0")
