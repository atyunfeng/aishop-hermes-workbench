import base64
import logging
from datetime import datetime
from typing import Any, NoReturn

from aishop.device_repository import (
    DeviceAuthenticationFailed,
    DeviceNotFound,
    PairingUnavailable,
    PendingCommandConflict,
)
from aishop.device_service import InvalidDeviceCommand
from aishop.domain import utc_now
from aishop.execution_repository import (
    ApprovalConflict,
    ApprovalNotFound,
    EvidenceNotFound,
    JobNotFound,
    LeaseConflict,
)
from aishop.execution_service import InvalidEvidence
from aishop.operator_auth import OperatorAuthenticationFailed
from aishop.repository import IdempotencyConflict, TaskNotFound, VersionConflict
from aishop.runtime import (
    get_business_data_service,
    get_demo_flow_service,
    get_device_service,
    get_dispatch_service,
    get_execution_service,
    get_inbound_event_service,
    get_maintenance_service,
    get_operator_auth,
    get_service,
)
from aishop.state_machine import InvalidTransition
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateTaskRequest(BaseModel):
    idempotency_key: str = Field(min_length=1)
    source: str = Field(min_length=1)
    title: str = Field(min_length=1)


class TransitionTaskRequest(BaseModel):
    expected_version: int = Field(ge=1)
    target_state: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class StopAllRequest(BaseModel):
    reason: str = Field(min_length=1)


class PairDeviceRequest(BaseModel):
    pairing_code: str = Field(pattern=r"^[0-9]{6}$")
    device_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    app_version: str = Field(min_length=1)
    capabilities: list[str]


class DevicePermissionsRequest(BaseModel):
    notifications: bool
    accessibility: bool
    screen_capture: bool


class InstalledAppRequest(BaseModel):
    package_name: str = Field(min_length=1)
    version_name: str = Field(min_length=1)


class HeartbeatRequest(BaseModel):
    sequence: int = Field(ge=1)
    worker_state: str = Field(min_length=1)
    current_task_id: str | None
    battery_percent: int = Field(ge=0, le=100)
    permissions: DevicePermissionsRequest
    installed_apps: list[InstalledAppRequest]
    acknowledged_command_id: str | None = None
    completed_step: dict[str, Any] | None = None


class DeviceCommandRequest(BaseModel):
    type: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class CreateExecutionJobRequest(BaseModel):
    task_id: str = Field(min_length=1)
    app_skill_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    inputs: dict[str, Any]
    mode: str = "DEVICE"


class EvidenceUploadRequest(BaseModel):
    task_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    source: str = "DEVICE"
    media_type: str = Field(min_length=1)
    content_base64: str = Field(min_length=1, max_length=1_000_000)
    label: str = Field(min_length=1, max_length=120)


class RunDemoFlowRequest(BaseModel):
    mode: str = "SIMULATED"
    fault: str = "none"
    run_id: str | None = None


class ApprovalDecisionRequest(BaseModel):
    approved: bool


class InboundAttachmentRequest(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    media_type: str = Field(min_length=1, max_length=100)


class InboundEventRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=40)
    account_id: str = Field(min_length=1, max_length=200)
    conversation_id: str = Field(min_length=1, max_length=200)
    sender: str = Field(min_length=1, max_length=200)
    event_type: str = Field(pattern=r"^(MESSAGE|IMAGE|ORDER|INSTRUCTION)$")
    text: str = Field(max_length=4000)
    attachments: list[InboundAttachmentRequest] = Field(max_length=10)
    occurred_at: datetime


class OrderImportRequest(BaseModel):
    source: str = Field(min_length=1, max_length=100)
    orders: list[dict[str, Any]] = Field(min_length=1, max_length=5000)


class KnowledgePutRequest(BaseModel):
    knowledge_id: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=200_000)
    media_type: str = "text/markdown"


class ImageAnalysisRequest(BaseModel):
    artifact_id: str = Field(min_length=1, max_length=200)
    provider: str | None = Field(default=None, max_length=100)


def require_operator(
    x_aishop_operator_token: str | None = Header(default=None),
) -> None:
    try:
        get_operator_auth().verify(x_aishop_operator_token)
    except OperatorAuthenticationFailed as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "OPERATOR_AUTHENTICATION_FAILED", "message": str(error)}},
        ) from error


def _raise_api_error(error: Exception) -> NoReturn:
    headers = None
    if isinstance(error, DeviceAuthenticationFailed):
        code, http_status = "DEVICE_AUTHENTICATION_FAILED", status.HTTP_401_UNAUTHORIZED
        headers = {"WWW-Authenticate": "Bearer"}
    elif isinstance(error, PairingUnavailable):
        code, http_status = "PAIRING_UNAVAILABLE", status.HTTP_410_GONE
    elif isinstance(error, DeviceNotFound):
        code, http_status = "DEVICE_NOT_FOUND", status.HTTP_404_NOT_FOUND
    elif isinstance(error, PendingCommandConflict):
        code, http_status = "PENDING_COMMAND_CONFLICT", status.HTTP_409_CONFLICT
    elif isinstance(error, InvalidDeviceCommand):
        code, http_status = "INVALID_DEVICE_COMMAND", status.HTTP_422_UNPROCESSABLE_CONTENT
    elif isinstance(error, JobNotFound):
        code, http_status = "JOB_NOT_FOUND", status.HTTP_404_NOT_FOUND
    elif isinstance(error, EvidenceNotFound):
        code, http_status = "EVIDENCE_NOT_FOUND", status.HTTP_404_NOT_FOUND
    elif isinstance(error, ApprovalNotFound):
        code, http_status = "APPROVAL_NOT_FOUND", status.HTTP_404_NOT_FOUND
    elif isinstance(error, (LeaseConflict, ApprovalConflict)):
        code, http_status = "EXECUTION_CONFLICT", status.HTTP_409_CONFLICT
    elif isinstance(error, InvalidEvidence):
        code, http_status = "INVALID_EVIDENCE", status.HTTP_422_UNPROCESSABLE_CONTENT
    elif isinstance(error, TaskNotFound):
        code, http_status = "TASK_NOT_FOUND", status.HTTP_404_NOT_FOUND
    elif isinstance(error, VersionConflict):
        code, http_status = "VERSION_CONFLICT", status.HTTP_409_CONFLICT
    elif isinstance(error, InvalidTransition):
        code, http_status = "INVALID_TRANSITION", status.HTTP_422_UNPROCESSABLE_CONTENT
    elif isinstance(error, IdempotencyConflict):
        code, http_status = "IDEMPOTENCY_CONFLICT", status.HTTP_409_CONFLICT
    elif isinstance(error, ValueError):
        code, http_status = "INVALID_ARGUMENT", status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        logger.exception("Unhandled AIShop plugin API error", exc_info=error)
        code, http_status = "INTERNAL_ERROR", status.HTTP_500_INTERNAL_SERVER_ERROR
    raise HTTPException(
        status_code=http_status,
        detail={"error": {"code": code, "message": str(error)}},
        headers=headers,
    ) from error


@router.get("/health")
def health():
    return {"status": "ok", "service": "aishop"}


@router.get("/workbench", dependencies=[Depends(require_operator)])
def get_workbench():
    try:
        service = get_service()
        return {
            "generated_at": utc_now().isoformat(),
            "task_counts": service.count_by_state(),
            "devices": get_device_service().list_devices(),
            "approvals": get_execution_service().list_pending_approvals(),
            "recent_tasks": service.list_recent(limit=20),
        }
    except Exception as error:
        _raise_api_error(error)


@router.get("/diagnostics", dependencies=[Depends(require_operator)])
def diagnostics():
    try:
        return get_maintenance_service().diagnostics()
    except Exception as error:
        _raise_api_error(error)


@router.post("/maintenance/run", dependencies=[Depends(require_operator)])
def run_maintenance():
    try:
        return get_maintenance_service().run()
    except Exception as error:
        _raise_api_error(error)


@router.post(
    "/tasks", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_operator)]
)
def create_task(request: CreateTaskRequest):
    try:
        return get_service().create_task(request.idempotency_key, request.source, request.title)
    except Exception as error:
        _raise_api_error(error)


@router.get("/tasks/{task_id}", dependencies=[Depends(require_operator)])
def get_task(task_id: str):
    try:
        return get_service().get_task(task_id)
    except Exception as error:
        _raise_api_error(error)


@router.post("/tasks/{task_id}/transitions", dependencies=[Depends(require_operator)])
def transition_task(task_id: str, request: TransitionTaskRequest):
    try:
        return get_service().transition(
            task_id,
            request.expected_version,
            request.target_state,
            request.reason,
            request.idempotency_key,
        )
    except Exception as error:
        _raise_api_error(error)


@router.post("/tasks/{task_id}/retry", dependencies=[Depends(require_operator)])
def retry_task(task_id: str):
    try:
        task = get_service().retry(task_id)
        get_execution_service().repository.retry_task_jobs(task_id, utc_now())
        return task
    except Exception as error:
        _raise_api_error(error)


@router.post("/stop-all", dependencies=[Depends(require_operator)])
def stop_all(request: StopAllRequest):
    try:
        tasks = get_service().stop_all(request.reason)
        get_execution_service().cancel_all(utc_now())
        get_device_service().emergency_stop_all(request.reason)
        return tasks
    except Exception as error:
        _raise_api_error(error)


@router.post("/demo/reset", dependencies=[Depends(require_operator)])
def reset_demo():
    try:
        return get_demo_flow_service().reset()
    except Exception as error:
        _raise_api_error(error)


@router.post(
    "/devices/pairing-sessions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operator)],
)
def create_pairing_session():
    try:
        return get_device_service().create_pairing_session()
    except Exception as error:
        _raise_api_error(error)


@router.post("/devices/pair", status_code=status.HTTP_201_CREATED)
def pair_device(request: PairDeviceRequest):
    try:
        return get_device_service().pair_device(
            request.pairing_code,
            request.device_id,
            request.display_name,
            request.app_version,
            request.capabilities,
        )
    except Exception as error:
        _raise_api_error(error)


def _bearer_token(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise DeviceAuthenticationFailed("device bearer token is required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise DeviceAuthenticationFailed("device bearer token is required")
    return token


@router.post("/devices/{device_id}/heartbeat")
def device_heartbeat(
    device_id: str,
    request: HeartbeatRequest,
    authorization: str | None = Header(default=None),
):
    try:
        return get_device_service().heartbeat(
            device_id,
            _bearer_token(authorization),
            request.model_dump(),
        )
    except Exception as error:
        _raise_api_error(error)


@router.post("/devices/{device_id}/events", status_code=status.HTTP_201_CREATED)
def ingest_device_event(
    device_id: str,
    request: InboundEventRequest,
    authorization: str | None = Header(default=None),
):
    try:
        get_device_service().authenticate_token(device_id, _bearer_token(authorization))
        return get_inbound_event_service().ingest(
            device_id, request.model_dump(mode="json"), utc_now()
        )
    except Exception as error:
        _raise_api_error(error)


@router.post(
    "/devices/{device_id}/commands",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operator)],
)
def queue_device_command(device_id: str, request: DeviceCommandRequest):
    try:
        return get_device_service().queue_command(device_id, request.type, request.reason)
    except Exception as error:
        _raise_api_error(error)


@router.post(
    "/devices/{device_id}/token/rotate",
    dependencies=[Depends(require_operator)],
)
def rotate_device_token(device_id: str):
    try:
        return get_device_service().rotate_token(device_id)
    except Exception as error:
        _raise_api_error(error)


@router.post(
    "/devices/{device_id}/token/revoke",
    dependencies=[Depends(require_operator)],
)
def revoke_device_token(device_id: str):
    try:
        return get_device_service().revoke_token(device_id)
    except Exception as error:
        _raise_api_error(error)


@router.post(
    "/execution/jobs",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operator)],
)
def create_execution_job(request: CreateExecutionJobRequest):
    try:
        return get_dispatch_service().dispatch(**request.model_dump())
    except Exception as error:
        _raise_api_error(error)


@router.get("/execution/jobs/{job_id}", dependencies=[Depends(require_operator)])
def get_execution_job(job_id: str):
    try:
        return get_execution_service().get_job(job_id)
    except Exception as error:
        _raise_api_error(error)


@router.get("/tasks/{task_id}/timeline", dependencies=[Depends(require_operator)])
def get_task_timeline(task_id: str):
    try:
        return get_execution_service().timeline(task_id)
    except Exception as error:
        _raise_api_error(error)


@router.post("/devices/{device_id}/evidence", status_code=status.HTTP_201_CREATED)
def upload_device_evidence(
    device_id: str,
    request: EvidenceUploadRequest,
    authorization: str | None = Header(default=None),
):
    try:
        get_device_service().authenticate_token(device_id, _bearer_token(authorization))
        return get_execution_service().upload_evidence(
            request.model_dump(), device_id=device_id, now=utc_now()
        )
    except Exception as error:
        _raise_api_error(error)


@router.get("/evidence/{evidence_id}", dependencies=[Depends(require_operator)])
def get_evidence(evidence_id: str):
    try:
        record, content = get_execution_service().repository.get_evidence(evidence_id)
        return Response(
            content=content,
            media_type=record.media_type,
            headers={
                "Cache-Control": "private, max-age=60",
                "X-Content-SHA256": record.sha256,
                "Content-Disposition": f'inline; filename="{record.evidence_id}"',
            },
        )
    except Exception as error:
        _raise_api_error(error)


@router.get("/evidence/{evidence_id}/data", dependencies=[Depends(require_operator)])
def get_evidence_data(evidence_id: str):
    try:
        record, content = get_execution_service().repository.get_evidence(evidence_id)
        return {
            "evidence_id": evidence_id,
            "media_type": record.media_type,
            "sha256": record.sha256,
            "content_base64": base64.b64encode(content).decode(),
        }
    except Exception as error:
        _raise_api_error(error)


@router.post(
    "/business/orders/import",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operator)],
)
def import_orders(request: OrderImportRequest):
    try:
        return get_business_data_service().import_orders(request.orders, request.source)
    except Exception as error:
        _raise_api_error(error)


@router.get("/business/orders/{order_id}", dependencies=[Depends(require_operator)])
def get_order(order_id: str):
    try:
        return get_business_data_service().get_order(order_id)
    except Exception as error:
        _raise_api_error(error)


@router.post(
    "/business/knowledge",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operator)],
)
def put_knowledge(request: KnowledgePutRequest):
    try:
        return get_business_data_service().put_knowledge(**request.model_dump())
    except Exception as error:
        _raise_api_error(error)


@router.get("/business/knowledge/search", dependencies=[Depends(require_operator)])
def search_knowledge(q: str, limit: int = 10):
    try:
        return get_business_data_service().search_knowledge(q, max(1, min(limit, 50)))
    except Exception as error:
        _raise_api_error(error)


@router.post(
    "/business/image-analysis",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operator)],
)
def create_image_analysis(request: ImageAnalysisRequest):
    try:
        return get_business_data_service().create_image_analysis(
            request.artifact_id, request.provider
        )
    except Exception as error:
        _raise_api_error(error)


@router.get("/demo/flows", dependencies=[Depends(require_operator)])
def list_demo_flows():
    try:
        return get_demo_flow_service().list_flows()
    except Exception as error:
        _raise_api_error(error)


@router.post(
    "/demo/flows/{flow_id}/run",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operator)],
)
def run_demo_flow(flow_id: str, request: RunDemoFlowRequest):
    try:
        return get_demo_flow_service().run(flow_id, request.mode, request.fault, request.run_id)
    except Exception as error:
        _raise_api_error(error)


@router.post(
    "/workflow-runs/{run_id}/reconcile", dependencies=[Depends(require_operator)]
)
def reconcile_workflow(run_id: str):
    try:
        return get_demo_flow_service().reconcile_workflow(run_id)
    except Exception as error:
        _raise_api_error(error)


@router.post(
    "/approvals/{approval_id}/decision", dependencies=[Depends(require_operator)]
)
def decide_approval(approval_id: str, request: ApprovalDecisionRequest):
    try:
        return get_dispatch_service().decide_and_resume(
            approval_id, request.approved, utc_now()
        )
    except Exception as error:
        _raise_api_error(error)
