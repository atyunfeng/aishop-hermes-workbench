from pathlib import Path

from . import schemas, tools


def register(ctx):
    for name, schema, handler in (
        ("aishop_create_task", schemas.CREATE_TASK, tools.create_task),
        ("aishop_get_task", schemas.GET_TASK, tools.get_task),
        ("aishop_transition_task", schemas.TRANSITION_TASK, tools.transition_task),
        ("aishop_stop_all", schemas.STOP_ALL, tools.stop_all),
        ("aishop_dispatch_workflow", schemas.DISPATCH_WORKFLOW, tools.dispatch_workflow),
    ):
        ctx.register_tool(name=name, toolset="aishop", schema=schema, handler=handler)
    for skill_name in (
        "aishop-operator",
        "aishop-qian-niu",
        "aishop-dou-dian",
        "aishop-we-chat",
        "aishop-we-com",
        "aishop-qq",
    ):
        ctx.register_skill(skill_name, Path(__file__).parent / "skills" / skill_name / "SKILL.md")
