import os
from functools import lru_cache
from pathlib import Path

from .app_skills import AppSkillRegistry
from .business_data import BusinessDataService
from .demo_flows import DemoFlowService
from .device_repository import DeviceRepository
from .device_service import DeviceService
from .dispatch_service import DispatchService
from .execution_repository import ExecutionRepository
from .execution_service import ExecutionService
from .inbound_events import InboundEventService
from .maintenance import MaintenanceService
from .operator_auth import OperatorAuth
from .repository import TaskRepository
from .service import TaskService
from .workflow_runs import WorkflowRunService


def resolve_data_dir() -> Path:
    if configured := os.getenv("AISHOP_DATA_DIR"):
        return Path(configured).expanduser()
    if os.name == "nt" and (local_app_data := os.getenv("LOCALAPPDATA")):
        return Path(local_app_data) / "hermes" / "plugins-data" / "aishop"
    if hermes_home := os.getenv("HERMES_HOME"):
        return Path(hermes_home).expanduser() / "plugins-data" / "aishop"
    return Path.home() / ".hermes" / "plugins-data" / "aishop"


@lru_cache(maxsize=1)
def get_service() -> TaskService:
    return TaskService(TaskRepository(resolve_data_dir() / "aishop.db"))


@lru_cache(maxsize=1)
def get_operator_auth() -> OperatorAuth:
    return OperatorAuth.load(resolve_data_dir())


@lru_cache(maxsize=1)
def get_inbound_event_service() -> InboundEventService:
    return InboundEventService(resolve_data_dir() / "aishop.db", get_service())


@lru_cache(maxsize=1)
def get_business_data_service() -> BusinessDataService:
    return BusinessDataService(resolve_data_dir() / "aishop.db")


@lru_cache(maxsize=1)
def get_workflow_run_service() -> WorkflowRunService:
    return WorkflowRunService(resolve_data_dir() / "aishop.db")


@lru_cache(maxsize=1)
def get_maintenance_service() -> MaintenanceService:
    execution = get_execution_service()
    return MaintenanceService(execution.repository.database_path, execution.repository)


@lru_cache(maxsize=1)
def get_device_service() -> DeviceService:
    return DeviceService(
        DeviceRepository(resolve_data_dir() / "aishop.db"),
        execution_service=get_execution_service(),
    )


@lru_cache(maxsize=1)
def get_execution_service() -> ExecutionService:
    data_dir = resolve_data_dir()
    return ExecutionService(
        ExecutionRepository(data_dir / "aishop.db", data_dir / "evidence"),
        get_service(),
    )


@lru_cache(maxsize=1)
def get_dispatch_service() -> DispatchService:
    execution = get_execution_service()
    return DispatchService(
        get_service(), get_app_skill_registry(), execution, execution.repository
    )


@lru_cache(maxsize=1)
def get_app_skill_registry() -> AppSkillRegistry:
    return AppSkillRegistry.load(Path(__file__).parents[1] / "app_skills")


@lru_cache(maxsize=1)
def get_demo_flow_service() -> DemoFlowService:
    execution = get_execution_service()
    return DemoFlowService(get_service(), get_app_skill_registry(), execution, execution.repository)


def clear_runtime_caches() -> None:
    for factory in (
        get_service,
        get_operator_auth,
        get_inbound_event_service,
        get_business_data_service,
        get_workflow_run_service,
        get_maintenance_service,
        get_device_service,
        get_execution_service,
        get_dispatch_service,
        get_app_skill_registry,
        get_demo_flow_service,
    ):
        factory.cache_clear()
