import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


class FakeContext:
    def __init__(self):
        self.tools = []
        self.skills = []

    def register_tool(self, **kwargs):
        self.tools.append(kwargs)

    def register_skill(self, name, path):
        self.skills.append((name, path))


def load_plugin():
    plugin_root = ROOT / "hermes-plugin"
    spec = importlib.util.spec_from_file_location(
        "aishop_plugin",
        plugin_root / "__init__.py",
        submodule_search_locations=[str(plugin_root)],
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_register_exposes_exact_declared_tools_and_skills():
    context = FakeContext()
    load_plugin().register(context)
    assert [tool["name"] for tool in context.tools] == [
        "aishop_create_task",
        "aishop_get_task",
        "aishop_transition_task",
        "aishop_stop_all",
        "aishop_dispatch_workflow",
    ]
    assert {tool["toolset"] for tool in context.tools} == {"aishop"}
    assert [name for name, _ in context.skills] == [
        "aishop-operator",
        "aishop-qian-niu",
        "aishop-dou-dian",
        "aishop-we-chat",
        "aishop-we-com",
        "aishop-qq",
    ]
    assert all(path.is_file() for _, path in context.skills)
