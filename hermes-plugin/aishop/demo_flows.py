import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import uuid4

from .app_skills import AppSkillRegistry
from .business_data import BusinessDataService
from .dispatch_service import DispatchService
from .domain import TaskState, utc_now
from .execution_domain import EvidenceSource, StepResult, StepStatus
from .execution_repository import ExecutionRepository
from .execution_service import ExecutionService
from .service import TaskService
from .workflow_runs import WorkflowRunService


@dataclass(frozen=True, slots=True)
class DemoFlow:
    flow_id: str
    name: str
    source: str
    title: str
    skill_id: str
    workflow_id: str
    inputs: dict[str, str]


FLOWS = {
    "qian_niu_customer_service": DemoFlow(
        "qian_niu_customer_service",
        "千牛 24 小时客服接管",
        "qian-niu",
        "回复测试客户的物流咨询",
        "qian-niu",
        "customer_reply",
        {
            "package_name": "com.taobao.qianniu",
            "customer_name": "AIShop 测试客户",
            "reply_text": "您的测试订单已发出，物流单号为 SF-DEMO-001，请留意更新。",
        },
    ),
    "dou_dian_image_after_sales": DemoFlow(
        "dou_dian_image_after_sales",
        "抖店/飞鸽图片售后",
        "dou-dian",
        "处理测试订单的图片售后咨询",
        "dou-dian",
        "image_after_sales_reply",
        {
            "package_name": "com.bytedance.ep.android",
            "order_id": "DEMO-DD-2001",
            "reply_text": "已收到测试商品图片，我们会先核对订单并由人工确认退款或退货动作。",
        },
    ),
    "we_chat_private_service": DemoFlow(
        "we_chat_private_service",
        "微信客户私域服务",
        "we-chat",
        "回复微信白名单测试客户",
        "we-chat",
        "private_customer_reply",
        {
            "package_name": "com.tencent.mm",
            "customer_name": "AIShop 微信测试客户",
            "reply_text": "已关联测试订单 DEMO-WX-3001，当前状态为待回复。",
        },
    ),
    "we_com_multi_phone": DemoFlow(
        "we_com_multi_phone",
        "企业微信指挥多手机协作",
        "we-com",
        "汇报测试订单协作处理结果",
        "we-com",
        "instruction_report",
        {
            "package_name": "com.tencent.wework",
            "conversation_name": "AIShop 企业微信测试群",
            "report_text": "模拟检查完成：4 个测试订单，3 个已处理，1 个资金动作等待人工审批。",
        },
    ),
}


class DemoFlowService:
    def __init__(
        self,
        tasks: TaskService,
        registry: AppSkillRegistry,
        execution: ExecutionService,
        repository: ExecutionRepository,
    ):
        self.tasks = tasks
        self.registry = registry
        self.execution = execution
        self.repository = repository
        self.dispatch = DispatchService(tasks, registry, execution, repository)
        self.workflow_runs = WorkflowRunService(repository.database_path)

    def list_flows(self) -> list[dict[str, str]]:
        return [
            {"flow_id": flow.flow_id, "name": flow.name, "source": flow.source}
            for flow in FLOWS.values()
        ]

    def run(
        self,
        flow_id: str,
        mode: str = "SIMULATED",
        fault: str = "none",
        run_id: str | None = None,
    ) -> dict[str, Any]:
        if mode not in {"SIMULATED", "DEVICE"}:
            raise ValueError("mode must be SIMULATED or DEVICE")
        if fault not in {"none", "offline", "captcha", "unknown-page"}:
            raise ValueError("unsupported demo fault")
        try:
            flow = FLOWS[flow_id]
        except KeyError as error:
            raise ValueError(f"unknown demo flow {flow_id}") from error
        safe_run_id = run_id or str(uuid4())
        task = self.tasks.create_task(
            f"demo:{flow_id}:{safe_run_id}", flow.source, f"[{mode}] {flow.title}"
        )
        task = self._transition(
            task, TaskState.PLANNING, "Hermes 已生成版本化 App Skill 计划", safe_run_id
        )
        workflow_run_id = None
        if flow_id == "we_com_multi_phone":
            workflow_run_id = f"demo-workflow:{safe_run_id}"
            self.workflow_runs.create(
                task["task_id"],
                [
                    {
                        "node_id": f"{workflow_run_id}:qian-niu",
                        "name": "千牛超时订单通知",
                        "target": "qian-niu",
                        "dependencies": [],
                        "payload": {
                            "skill_id": "qian-niu",
                            "workflow_id": "customer_reply",
                            "inputs": {
                                "package_name": "com.taobao.qianniu",
                                "customer_name": "AIShop 测试客户",
                                "reply_text": "测试超时订单已检查，请留意发货更新。",
                            },
                        },
                    },
                    {
                        "node_id": f"{workflow_run_id}:dou-dian",
                        "name": "抖店超时订单通知",
                        "target": "dou-dian",
                        "dependencies": [],
                        "payload": {
                            "skill_id": "dou-dian",
                            "workflow_id": "image_after_sales_reply",
                            "inputs": {
                                "package_name": "com.bytedance.ep.android",
                                "order_id": "DEMO-DD-2001",
                                "reply_text": "测试订单已进入超时发货跟进。",
                            },
                        },
                    },
                    {
                        "node_id": f"{workflow_run_id}:report",
                        "name": "企业微信结果汇总",
                        "target": "we-com",
                        "dependencies": [
                            f"{workflow_run_id}:qian-niu",
                            f"{workflow_run_id}:dou-dian",
                        ],
                        "payload": {
                            "skill_id": "we-com",
                            "workflow_id": "instruction_report",
                            "inputs": flow.inputs,
                        },
                    },
                ],
                workflow_run_id,
            )
            if mode == "SIMULATED":
                for node in self.workflow_runs.ready_nodes(workflow_run_id):
                    self.workflow_runs.complete_node(
                        node["node_id"], "SUCCEEDED", {"mode": "SIMULATED"}
                    )
            else:
                jobs = [
                    self._dispatch_workflow_node(workflow_run_id, node)
                    for node in self.workflow_runs.ready_nodes(workflow_run_id)
                ]
                task = self._transition(
                    task,
                    TaskState.QUEUED,
                    "多手机子任务已进入并行队列",
                    safe_run_id,
                )
                return self._result(
                    flow,
                    mode,
                    fault,
                    task,
                    jobs[0],
                    workflow_run_id,
                )
        dispatched = self.dispatch.dispatch(
            task["task_id"], flow.skill_id, flow.workflow_id, flow.inputs, mode
        )
        task = dispatched["task"]
        job = dispatched["job"]
        if mode == "DEVICE":
            return self._result(flow, mode, fault, task, job, workflow_run_id)

        claimed = self.repository.claim_job(
            "simulator",
            set(job["required_packages"]),
            set(job["required_capabilities"]),
            utc_now(),
        )
        task = self._transition(task, TaskState.ASSIGNED, "已分配确定性模拟设备", safe_run_id)
        task = self._transition(
            task, TaskState.EXECUTING, "开始执行真实 App Skill 编译结果", safe_run_id
        )
        if fault == "offline":
            self.repository.expire_leases(claimed.lease_expires_at + timedelta(microseconds=1))
            task = self._transition(
                task, TaskState.RETRY_WAIT, "模拟设备离线，租约已回收", safe_run_id
            )
            return self._result(
                flow,
                mode,
                fault,
                task,
                self.execution.get_job(job["job_id"]),
                workflow_run_id,
            )

        for step in claimed.steps:
            status = StepStatus.SUCCEEDED
            code = "SIMULATED_OK"
            message = "deterministic simulator completed semantic action"
            if fault in {"captcha", "unknown-page"} and step.ordinal == 1:
                status = StepStatus.HUMAN_TAKEOVER
                code = "CAPTCHA" if fault == "captcha" else "UNKNOWN_PAGE"
                message = "simulated safety stop"
            evidence_ids: tuple[str, ...] = ()
            if step.evidence_required or step.action == "CAPTURE_SCREEN":
                receipt = (
                    f"SIMULATED\nflow={flow.flow_id}\nstep={step.step_id}\n"
                    f"action={step.action}\nstatus={status}\n"
                ).encode()
                evidence = self.repository.store_evidence(
                    task["task_id"],
                    claimed.job_id,
                    step.step_id,
                    EvidenceSource.SIMULATED,
                    "text/plain",
                    receipt,
                    f"SIMULATED {flow.name} {step.action}",
                )
                evidence_ids = (evidence.evidence_id,)
            job_record = self.repository.record_step_result(
                "simulator",
                StepResult(
                    claimed.job_id,
                    claimed.lease_id,
                    step.step_id,
                    status,
                    code,
                    message,
                    {"mode": "SIMULATED", "action": str(step.action)},
                    evidence_ids,
                    utc_now(),
                ),
            )
            if status is StepStatus.HUMAN_TAKEOVER:
                task = self._transition(
                    task, TaskState.HUMAN_TAKEOVER, f"安全停止：{code}", safe_run_id
                )
                return self._result(
                    flow,
                    mode,
                    fault,
                    task,
                    self.execution.get_job(job_record.job_id),
                    workflow_run_id,
                )
        task = self._transition(
            task, TaskState.VERIFYING, "正在核对模拟回执与证据摘要", safe_run_id
        )
        task = self._transition(
            task, TaskState.SUCCEEDED, "回执、证据和后置条件均已验证", safe_run_id
        )
        if workflow_run_id:
            report = self.workflow_runs.ready_nodes(workflow_run_id)[0]
            self.workflow_runs.complete_node(
                report["node_id"], "SUCCEEDED", {"mode": "SIMULATED", "task_id": task["task_id"]}
            )
        return self._result(
            flow,
            mode,
            fault,
            task,
            self.execution.get_job(job["job_id"]),
            workflow_run_id,
        )

    def reset(self) -> dict[str, Any]:
        BusinessDataService(self.repository.database_path)
        evidence_paths: list[str] = []
        with closing(sqlite3.connect(self.repository.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            task_rows = connection.execute(
                "SELECT task_id FROM tasks WHERE idempotency_key LIKE 'demo:%'"
            ).fetchall()
            task_ids = [row["task_id"] for row in task_rows]
            if task_ids:
                placeholders = ",".join("?" for _ in task_ids)
                job_rows = connection.execute(
                    f"SELECT job_id FROM execution_jobs WHERE task_id IN ({placeholders})",
                    task_ids,
                ).fetchall()
                job_ids = [row["job_id"] for row in job_rows]
                evidence_paths = [
                    row["storage_path"]
                    for row in connection.execute(
                        f"SELECT storage_path FROM evidence WHERE task_id IN ({placeholders})",
                        task_ids,
                    ).fetchall()
                ]
                if job_ids:
                    job_marks = ",".join("?" for _ in job_ids)
                    connection.execute(
                        f"DELETE FROM step_results WHERE job_id IN ({job_marks})", job_ids
                    )
                    connection.execute(
                        f"DELETE FROM device_leases WHERE job_id IN ({job_marks})", job_ids
                    )
                    connection.execute(
                        f"DELETE FROM execution_jobs WHERE job_id IN ({job_marks})", job_ids
                    )
                connection.execute(
                    f"DELETE FROM evidence WHERE task_id IN ({placeholders})", task_ids
                )
                connection.execute(
                    f"DELETE FROM audit_events WHERE task_id IN ({placeholders})", task_ids
                )
                connection.execute(
                    f"DELETE FROM pending_dispatches WHERE task_id IN ({placeholders})", task_ids
                )
                connection.execute(
                    f"DELETE FROM approvals WHERE task_id IN ({placeholders})", task_ids
                )
                connection.execute(
                    f"DELETE FROM workflow_runs WHERE parent_task_id IN ({placeholders})", task_ids
                )
                connection.execute(
                    f"DELETE FROM task_events WHERE task_id IN ({placeholders})", task_ids
                )
                connection.execute(
                    f"DELETE FROM tasks WHERE task_id IN ({placeholders})", task_ids
                )
            connection.execute("DELETE FROM order_snapshots WHERE order_id LIKE 'DEMO-%'")
            connection.execute(
                "DELETE FROM knowledge_fts WHERE knowledge_id LIKE 'demo:%'"
            )
            connection.execute(
                "DELETE FROM knowledge_versions WHERE knowledge_id LIKE 'demo:%'"
            )
            connection.commit()
        for storage_path in evidence_paths:
            path = self.repository.evidence_dir / storage_path
            if not path.is_absolute():
                path.unlink(missing_ok=True)
            else:
                path.unlink(missing_ok=True)
        task = self.tasks.seed_demo()
        return {**task, "removed_tasks": len(task_ids)}

    def _transition(
        self, task: dict[str, Any], target: TaskState, reason: str, run_id: str
    ) -> dict[str, Any]:
        return self.tasks.transition(
            task["task_id"],
            task["version"],
            target,
            reason,
            f"demo:{run_id}:{target}:{task['version']}",
        )

    def _result(
        self,
        flow: DemoFlow,
        mode: str,
        fault: str,
        task: dict[str, Any],
        job: dict[str, Any],
        workflow_run_id: str | None = None,
    ) -> dict[str, Any]:
        result = {
            "flow_id": flow.flow_id,
            "flow_name": flow.name,
            "mode": mode,
            "fault": fault,
            "task": task,
            "job": job,
            "task_events": self.tasks.list_events(task["task_id"]),
            "timeline": self.repository.list_timeline(task["task_id"]),
        }
        if workflow_run_id:
            result["workflow_run"] = self.workflow_runs.get(workflow_run_id)
        return result

    def reconcile_workflow(self, run_id: str) -> dict[str, Any]:
        run = self.workflow_runs.get(run_id)
        for node in run["nodes"]:
            if node["status"] != "RUNNING" or not node["job_id"]:
                continue
            job = self.execution.get_job(node["job_id"])
            if job["status"] == "SUCCEEDED":
                self.workflow_runs.complete_node(
                    node["node_id"], "SUCCEEDED", {"job_id": job["job_id"]}
                )
            elif job["status"] == "HUMAN_TAKEOVER":
                self.workflow_runs.complete_node(
                    node["node_id"], "HUMAN_TAKEOVER", {"job_id": job["job_id"]}
                )
            elif job["status"] in {"FAILED", "CANCELLED"}:
                self.workflow_runs.complete_node(
                    node["node_id"], "FAILED", {"job_id": job["job_id"]}
                )
        run = self.workflow_runs.aggregate(run_id)
        for node in self.workflow_runs.ready_nodes(run_id):
            self._dispatch_workflow_node(run_id, node)
        run = self.workflow_runs.aggregate(run_id)
        if run["status"] != "RUNNING":
            task = self.tasks.get_task(run["parent_task_id"])
            if task["state"] == TaskState.QUEUED:
                task = self._transition(
                    task, TaskState.ASSIGNED, "多手机节点已汇总", run_id
                )
                task = self._transition(
                    task, TaskState.EXECUTING, "正在生成协作结果", run_id
                )
                if run["status"] == "SUCCEEDED":
                    task = self._transition(
                        task, TaskState.VERIFYING, "正在验证全部子任务", run_id
                    )
                    self._transition(task, TaskState.SUCCEEDED, "全部子任务已验证", run_id)
                else:
                    self._transition(
                        task,
                        TaskState.HUMAN_TAKEOVER,
                        f"多手机流程结束于 {run['status']}",
                        run_id,
                    )
        return self.workflow_runs.get(run_id)

    def _dispatch_workflow_node(
        self, run_id: str, node: dict[str, Any]
    ) -> dict[str, Any]:
        child = self.tasks.create_task(
            f"demo:workflow:{run_id}:{node['node_id']}",
            node["target"],
            node["name"],
        )
        child = self.tasks.transition(
            child["task_id"],
            child["version"],
            TaskState.PLANNING,
            "父工作流已下发节点",
            f"workflow:{run_id}:{node['node_id']}:planning",
        )
        payload = node["payload"]
        dispatched = self.dispatch.dispatch(
            child["task_id"],
            payload["skill_id"],
            payload["workflow_id"],
            payload["inputs"],
            "DEVICE",
        )
        job = dispatched["job"]
        self.workflow_runs.start_node(node["node_id"], child["task_id"], job["job_id"])
        return job
