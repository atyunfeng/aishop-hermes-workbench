// src/plugin.tsx
import {
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  STATUSBAR_AREAS,
  useQuery,
  useQueryClient
} from "@hermes/plugin-sdk";
import { useState } from "react";

// src/api.ts
function createApi(rest, operatorToken = () => "") {
  const authorized = (path, options = {}) => rest(path, {
    ...options,
    headers: {
      ...options.headers,
      "X-AIShop-Operator-Token": operatorToken()
    }
  });
  return {
    getWorkbench: () => authorized("/workbench"),
    getDiagnostics: () => authorized("/diagnostics"),
    createPairingSession: () => authorized("/devices/pairing-sessions", {
      method: "POST"
    }),
    sendDeviceCommand: (deviceId, type, reason) => authorized(`/devices/${encodeURIComponent(deviceId)}/commands`, {
      method: "POST",
      body: { type, reason }
    }),
    stopAll: (reason) => authorized("/stop-all", {
      method: "POST",
      body: { reason }
    }),
    listDemoFlows: () => authorized("/demo/flows"),
    runDemoFlow: (flowId, mode, fault = "none") => authorized(`/demo/flows/${encodeURIComponent(flowId)}/run`, {
      method: "POST",
      body: { mode, fault }
    }),
    getTimeline: (taskId) => authorized(`/tasks/${encodeURIComponent(taskId)}/timeline`),
    getTask: (taskId) => authorized(`/tasks/${encodeURIComponent(taskId)}`),
    getExecutionJob: (jobId) => authorized(`/execution/jobs/${encodeURIComponent(jobId)}`),
    getEvidenceData: (evidenceId) => authorized(`/evidence/${encodeURIComponent(evidenceId)}/data`),
    retryTask: (taskId) => authorized(`/tasks/${encodeURIComponent(taskId)}/retry`, { method: "POST" }),
    reconcileWorkflow: (runId) => authorized(`/workflow-runs/${encodeURIComponent(runId)}/reconcile`, {
      method: "POST"
    }),
    decideApproval: (approvalId, approved) => authorized(
      `/approvals/${encodeURIComponent(approvalId)}/decision`,
      { method: "POST", body: { approved } }
    )
  };
}

// src/device-view-model.ts
var STATUS_LABELS = {
  OFFLINE: "\u79BB\u7EBF",
  IDLE: "\u7A7A\u95F2",
  BUSY: "\u6267\u884C\u4E2D",
  PAUSED: "\u5DF2\u6682\u505C",
  TAKEOVER: "\u4EBA\u5DE5\u63A5\u7BA1",
  ERROR: "\u5F02\u5E38"
};
var ACTIONS = {
  OFFLINE: [],
  IDLE: ["PAUSE", "TAKEOVER", "STOP"],
  BUSY: ["PAUSE", "TAKEOVER", "STOP"],
  PAUSED: ["RESUME", "TAKEOVER", "STOP"],
  TAKEOVER: ["RESUME", "STOP"],
  ERROR: ["TAKEOVER", "STOP"]
};
function buildDeviceViewModels(devices) {
  return [...devices].sort((left, right) => {
    const onlineDifference = Number(right.online) - Number(left.online);
    return onlineDifference || left.display_name.localeCompare(right.display_name, "zh-CN");
  }).map((device) => ({
    device,
    statusLabel: STATUS_LABELS[device.worker_state],
    permissionWarnings: [
      !device.permissions.notifications && "\u901A\u77E5\u672A\u5C31\u7EEA",
      !device.permissions.accessibility && "Accessibility \u672A\u5C31\u7EEA",
      !device.permissions.screen_capture && "\u753B\u9762\u91C7\u96C6\u672A\u5C31\u7EEA"
    ].filter((warning) => Boolean(warning)),
    actions: device.online && !device.pending_command ? ACTIONS[device.worker_state] : []
  }));
}

// src/execution-view-model.ts
function buildExecutionViewModel(run, liveTimeline = run.timeline) {
  const taskItems = run.task_events.map(taskEventItem);
  const executionItems = liveTimeline.map((event) => ({
    id: event.event_id,
    at: event.created_at,
    label: event.event_type,
    detail: executionDetail(event),
    kind: event.event_type.includes("EXPIRED") ? "warning" : "execution"
  }));
  const evidence = liveTimeline.filter((event) => event.event_type === "EVIDENCE_STORED").map((event) => {
    const evidenceId = String(event.payload.evidence_id ?? "");
    return {
      evidenceId,
      label: String(event.payload.label ?? "\u6267\u884C\u8BC1\u636E"),
      source: String(event.payload.source ?? run.mode),
      mediaType: String(event.payload.media_type ?? ""),
      sha256: String(event.payload.sha256 ?? ""),
      url: `/api/plugins/aishop/evidence/${encodeURIComponent(evidenceId)}`
    };
  });
  return {
    modeLabel: run.mode === "SIMULATED" ? "\u786E\u5B9A\u6027\u6A21\u62DF" : "\u771F\u5B9E\u8BBE\u5907",
    isSimulated: run.mode === "SIMULATED",
    timeline: [...taskItems, ...executionItems].sort(
      (left, right) => left.at.localeCompare(right.at) || left.id.localeCompare(right.id)
    ),
    evidence
  };
}
function taskEventItem(event) {
  return {
    id: event.event_id,
    at: event.created_at,
    label: event.to_state,
    detail: event.reason,
    kind: event.to_state === "HUMAN_TAKEOVER" || event.to_state === "RETRY_WAIT" ? "warning" : "task"
  };
}
function executionDetail(event) {
  if (event.event_type === "STEP_RESULT") {
    return `${String(event.payload.step_id ?? "")} \xB7 ${String(event.payload.status ?? "")}`;
  }
  if (event.event_type === "EVIDENCE_STORED") {
    return `${String(event.payload.source ?? "")} \xB7 ${String(event.payload.label ?? "")}`;
  }
  return event.actor;
}

// src/view-model.ts
var TERMINAL_STATES = /* @__PURE__ */ new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);
function buildWorkbenchViewModel(summary) {
  const tasks = [...summary.recent_tasks].sort((left, right) => {
    const activeDifference = Number(TERMINAL_STATES.has(left.state)) - Number(TERMINAL_STATES.has(right.state));
    if (activeDifference !== 0) {
      return activeDifference;
    }
    return right.created_at.localeCompare(left.created_at);
  });
  return {
    activeCount: tasks.filter((task) => !TERMINAL_STATES.has(task.state)).length,
    tasks
  };
}
function filterTasks(tasks, search, filter) {
  const needle = search.toLowerCase();
  return tasks.filter((task) => {
    const matchesSearch = `${task.title} ${task.source}`.toLowerCase().includes(needle);
    const matchesFilter = filter === "ALL" || filter === "ACTIVE" && !TERMINAL_STATES.has(task.state) || filter === "FAILED" && ["FAILED", "RETRY_WAIT", "HUMAN_TAKEOVER"].includes(task.state) || filter === "SUCCEEDED" && task.state === "SUCCEEDED";
    return matchesSearch && matchesFilter;
  });
}
function resolveActiveRun(run, task, job) {
  return { ...run, task: task ?? run.task, job: job ?? run.job };
}
function approvalConfirmation(approval) {
  return [
    `\u52A8\u4F5C\uFF1A${approval.action}`,
    `\u76EE\u6807\uFF1A${String(approval.scope.target ?? "\u672A\u6307\u5B9A")}`,
    `\u6D41\u7A0B\uFF1A${String(approval.scope.workflow_id ?? "\u672A\u6307\u5B9A")}`,
    `\u6709\u6548\u671F\uFF1A${new Date(approval.expires_at).toLocaleString()}`,
    `\u7ED1\u5B9A\u6458\u8981\uFF1A${String(approval.scope.binding ?? "").slice(0, 16)}`
  ].join(" \xB7 ");
}

// src/plugin.tsx
import { jsx, jsxs } from "react/jsx-runtime";
var WORKBENCH_QUERY_KEY = ["aishop", "workbench"];
var SOURCE_URL = "https://github.com/atyunfeng/aishop-hermes-workbench";
function StateBadge({ task }) {
  const variant = task.state === "FAILED" ? "destructive" : task.state === "SUCCEEDED" ? "muted" : task.state === "WAITING_APPROVAL" ? "warn" : "default";
  return /* @__PURE__ */ jsx(Badge, { variant, children: task.state });
}
function WorkbenchPage({ api, onClearToken }) {
  const [stopDialogOpen, setStopDialogOpen] = useState(false);
  const [demoMode, setDemoMode] = useState("SIMULATED");
  const [activeRun, setActiveRun] = useState(null);
  const [runningFlowId, setRunningFlowId] = useState(null);
  const [taskSearch, setTaskSearch] = useState("");
  const [taskFilter, setTaskFilter] = useState("ALL");
  const [approvalDecision, setApprovalDecision] = useState(null);
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: WORKBENCH_QUERY_KEY,
    queryFn: api.getWorkbench,
    refetchInterval: 3e3
  });
  const demoFlows = useQuery({
    queryKey: ["aishop", "demo-flows"],
    queryFn: api.listDemoFlows
  });
  const diagnostics = useQuery({
    queryKey: ["aishop", "diagnostics"],
    queryFn: api.getDiagnostics,
    refetchInterval: 1e4
  });
  const liveTimeline = useQuery({
    queryKey: ["aishop", "timeline", activeRun?.task.task_id ?? "none"],
    queryFn: () => activeRun ? api.getTimeline(activeRun.task.task_id) : Promise.resolve([]),
    refetchInterval: activeRun ? 2e3 : void 0
  });
  const liveTask = useQuery({
    queryKey: ["aishop", "task", activeRun?.task.task_id ?? "none"],
    queryFn: () => activeRun ? api.getTask(activeRun.task.task_id) : Promise.resolve(null),
    refetchInterval: activeRun ? 2e3 : void 0
  });
  const liveJob = useQuery({
    queryKey: ["aishop", "job", activeRun?.job.job_id ?? "none"],
    queryFn: () => activeRun ? api.getExecutionJob(activeRun.job.job_id) : Promise.resolve(null),
    refetchInterval: activeRun ? 2e3 : void 0
  });
  const liveWorkflow = useQuery({
    queryKey: ["aishop", "workflow-run", activeRun?.workflow_run?.run_id ?? "none"],
    queryFn: () => activeRun?.workflow_run && activeRun.mode === "DEVICE" ? api.reconcileWorkflow(activeRun.workflow_run.run_id) : Promise.resolve(activeRun?.workflow_run),
    refetchInterval: activeRun?.workflow_run && activeRun.mode === "DEVICE" ? 2e3 : void 0
  });
  if (query.isLoading) {
    return /* @__PURE__ */ jsx(EmptyState, { title: "\u6B63\u5728\u8FDE\u63A5 AI \u5458\u5DE5\u4F5C\u53F0", description: "\u8BFB\u53D6\u672C\u5730\u4EFB\u52A1\u72B6\u6001\u2026" });
  }
  if (!query.data || query.error) {
    return /* @__PURE__ */ jsx(EmptyState, { title: "\u5DE5\u4F5C\u53F0\u6682\u4E0D\u53EF\u7528", description: "\u8BF7\u68C0\u67E5 AIShop \u63D2\u4EF6\u540E\u7AEF\u3002" });
  }
  const viewModel = buildWorkbenchViewModel(query.data);
  return /* @__PURE__ */ jsxs("main", { className: "flex h-full flex-col gap-4 overflow-auto p-5 text-sm", children: [
    /* @__PURE__ */ jsxs("header", { className: "flex items-center justify-between gap-4", children: [
      /* @__PURE__ */ jsxs("div", { children: [
        /* @__PURE__ */ jsx("h1", { className: "text-lg font-semibold", children: "AI \u5458\u5DE5\u4F5C\u53F0" }),
        /* @__PURE__ */ jsx("p", { className: "mt-1 text-xs text-(--ui-text-tertiary)", children: "Hermes \u672C\u5730\u4EFB\u52A1\u6307\u6325\u8231 \xB7 3 \u79D2\u81EA\u52A8\u5237\u65B0" })
      ] }),
      /* @__PURE__ */ jsxs("div", { className: "flex gap-2", children: [
        onClearToken ? /* @__PURE__ */ jsx(Button, { variant: "outline", onClick: onClearToken, children: "\u91CD\u65B0\u8BA4\u8BC1" }) : null,
        /* @__PURE__ */ jsx(Button, { variant: "destructive", onClick: () => setStopDialogOpen(true), children: "\u5168\u90E8\u505C\u6B62" })
      ] })
    ] }),
    /* @__PURE__ */ jsxs("section", { className: "grid grid-cols-4 gap-3", children: [
      /* @__PURE__ */ jsx(Metric, { label: "\u6D3B\u8DC3\u4EFB\u52A1", value: viewModel.activeCount }),
      /* @__PURE__ */ jsx(Metric, { label: "\u7B49\u5F85\u5BA1\u6279", value: query.data.approvals.length }),
      /* @__PURE__ */ jsx(Metric, { label: "\u5728\u7EBF\u624B\u673A\u5458\u5DE5", value: query.data.devices.filter((device) => device.online).length }),
      /* @__PURE__ */ jsx(
        Metric,
        {
          label: "\u8BC1\u636E\u5360\u7528 MiB",
          value: Math.round((diagnostics.data?.evidence_bytes ?? 0) / 1024 / 1024)
        }
      )
    ] }),
    /* @__PURE__ */ jsx(
      DemoLauncher,
      {
        flows: demoFlows.data ?? [],
        mode: demoMode,
        runningFlowId,
        onModeChange: setDemoMode,
        onRun: async (flowId) => {
          setRunningFlowId(flowId);
          try {
            const result = await api.runDemoFlow(flowId, demoMode);
            setActiveRun(result);
            await queryClient.invalidateQueries({ queryKey: WORKBENCH_QUERY_KEY });
          } finally {
            setRunningFlowId(null);
          }
        }
      }
    ),
    activeRun ? /* @__PURE__ */ jsx(
      ExecutionPanel,
      {
        api,
        run: resolveActiveRun(
          {
            ...activeRun,
            workflow_run: liveWorkflow.data ?? activeRun.workflow_run
          },
          liveTask.data,
          liveJob.data
        ),
        liveTimeline: liveTimeline.data
      }
    ) : null,
    query.data.approvals.length > 0 ? /* @__PURE__ */ jsxs("section", { className: "rounded-md border border-(--ui-warning) p-4", children: [
      /* @__PURE__ */ jsx("h2", { className: "mb-3 font-medium", children: "\u7B49\u5F85\u4EBA\u5DE5\u5BA1\u6279" }),
      /* @__PURE__ */ jsx("div", { className: "flex flex-col gap-2", children: query.data.approvals.map((approval) => /* @__PURE__ */ jsxs(
        "article",
        {
          className: "flex items-center justify-between gap-3 rounded border border-(--ui-stroke-secondary) p-3",
          children: [
            /* @__PURE__ */ jsxs("div", { children: [
              /* @__PURE__ */ jsxs("div", { className: "font-medium", children: [
                "\u9AD8\u98CE\u9669\u52A8\u4F5C\uFF1A",
                approval.action
              ] }),
              /* @__PURE__ */ jsxs("div", { className: "mt-1 text-xs text-(--ui-text-tertiary)", children: [
                "\u4EFB\u52A1 ",
                approval.task_id,
                " \xB7 \u76EE\u6807 ",
                String(approval.scope.target ?? "\u672A\u6307\u5B9A"),
                " \xB7 ",
                "\u6D41\u7A0B ",
                String(approval.scope.workflow_id ?? "\u672A\u6307\u5B9A"),
                " \xB7 ",
                "\u622A\u6B62 ",
                new Date(approval.expires_at).toLocaleTimeString()
              ] })
            ] }),
            /* @__PURE__ */ jsxs("div", { className: "flex gap-2", children: [
              /* @__PURE__ */ jsx(
                Button,
                {
                  variant: "outline",
                  onClick: () => setApprovalDecision({ approval, approved: false }),
                  children: "\u62D2\u7EDD"
                }
              ),
              /* @__PURE__ */ jsx(
                Button,
                {
                  variant: "destructive",
                  onClick: () => setApprovalDecision({ approval, approved: true }),
                  children: "\u9650\u5B9A\u6279\u51C6\u4E00\u6B21"
                }
              )
            ] })
          ]
        },
        approval.approval_id
      )) })
    ] }) : null,
    /* @__PURE__ */ jsxs("section", { className: "grid min-h-0 flex-1 grid-cols-[minmax(0,2fr)_minmax(16rem,1fr)] gap-4", children: [
      /* @__PURE__ */ jsxs("div", { className: "rounded-md border border-(--ui-stroke-secondary) p-4", children: [
        /* @__PURE__ */ jsxs("div", { className: "mb-3 flex items-center justify-between gap-2", children: [
          /* @__PURE__ */ jsx("h2", { className: "font-medium", children: "\u6700\u8FD1\u4EFB\u52A1" }),
          /* @__PURE__ */ jsxs("div", { className: "flex gap-2", children: [
            /* @__PURE__ */ jsx(
              "input",
              {
                "aria-label": "\u641C\u7D22\u4EFB\u52A1",
                className: "rounded border border-(--ui-stroke-secondary) bg-transparent px-2 py-1 text-xs",
                placeholder: "\u6807\u9898\u6216\u6765\u6E90",
                value: taskSearch,
                onChange: (event) => setTaskSearch(event.target.value)
              }
            ),
            /* @__PURE__ */ jsxs(
              "select",
              {
                "aria-label": "\u7B5B\u9009\u4EFB\u52A1\u72B6\u6001",
                className: "rounded border border-(--ui-stroke-secondary) bg-transparent px-2 py-1 text-xs",
                value: taskFilter,
                onChange: (event) => setTaskFilter(event.target.value),
                children: [
                  /* @__PURE__ */ jsx("option", { value: "ALL", children: "\u5168\u90E8" }),
                  /* @__PURE__ */ jsx("option", { value: "ACTIVE", children: "\u8FDB\u884C\u4E2D" }),
                  /* @__PURE__ */ jsx("option", { value: "FAILED", children: "\u5931\u8D25/\u63A5\u7BA1" }),
                  /* @__PURE__ */ jsx("option", { value: "SUCCEEDED", children: "\u5DF2\u5B8C\u6210" })
                ]
              }
            )
          ] })
        ] }),
        viewModel.tasks.length === 0 ? /* @__PURE__ */ jsx(EmptyState, { title: "\u6682\u65E0\u4EFB\u52A1", description: "\u901A\u8FC7 Hermes \u6307\u4EE4\u521B\u5EFA\u7B2C\u4E00\u4E2A\u4EFB\u52A1\u3002" }) : /* @__PURE__ */ jsx("div", { className: "flex flex-col gap-2", children: filterTasks(viewModel.tasks, taskSearch, taskFilter).map((task) => /* @__PURE__ */ jsxs(
          "article",
          {
            className: "flex items-center justify-between gap-3 rounded border border-(--ui-stroke-secondary) px-3 py-2",
            children: [
              /* @__PURE__ */ jsxs("div", { className: "min-w-0", children: [
                /* @__PURE__ */ jsx("div", { className: "truncate font-medium", children: task.title }),
                /* @__PURE__ */ jsxs("div", { className: "mt-1 text-xs text-(--ui-text-tertiary)", children: [
                  task.source,
                  " \xB7 v",
                  task.version
                ] })
              ] }),
              /* @__PURE__ */ jsxs("div", { className: "flex items-center gap-2", children: [
                task.state === "RETRY_WAIT" || task.state === "HUMAN_TAKEOVER" ? /* @__PURE__ */ jsx(
                  Button,
                  {
                    variant: "outline",
                    onClick: async () => {
                      await api.retryTask(task.task_id);
                      await queryClient.invalidateQueries({ queryKey: WORKBENCH_QUERY_KEY });
                    },
                    children: "\u5B89\u5168\u91CD\u8BD5"
                  }
                ) : null,
                /* @__PURE__ */ jsx(StateBadge, { task })
              ] })
            ]
          },
          task.task_id
        )) })
      ] }),
      /* @__PURE__ */ jsx("div", { className: "rounded-md border border-(--ui-stroke-secondary) p-4", children: /* @__PURE__ */ jsx(DeviceWall, { api, devices: query.data.devices }) })
    ] }),
    /* @__PURE__ */ jsxs("footer", { className: "flex flex-wrap items-center justify-between gap-2 border-t border-(--ui-stroke-secondary) pt-3 text-xs text-(--ui-text-tertiary)", children: [
      /* @__PURE__ */ jsx("span", { children: "AIShop v0.1.0-alpha \xB7 AGPLv3 \xB7 \u6309\u539F\u6837\u63D0\u4F9B\uFF0C\u4E0D\u9644\u5E26\u62C5\u4FDD" }),
      /* @__PURE__ */ jsx(
        "a",
        {
          className: "font-medium text-(--ui-text-primary) underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2",
          href: SOURCE_URL,
          rel: "noreferrer",
          target: "_blank",
          children: "\u67E5\u770B\u5B8C\u6574\u6E90\u7801"
        }
      )
    ] }),
    /* @__PURE__ */ jsx(
      ConfirmDialog,
      {
        open: stopDialogOpen,
        onClose: () => setStopDialogOpen(false),
        onConfirm: async () => {
          await api.stopAll("operator emergency stop");
          await queryClient.invalidateQueries({ queryKey: WORKBENCH_QUERY_KEY });
        },
        title: "\u505C\u6B62\u5168\u90E8 AIShop \u4EFB\u52A1\uFF1F",
        description: "\u6240\u6709\u672A\u5B8C\u6210\u4EFB\u52A1\u90FD\u4F1A\u8FDB\u5165 CANCELLED\uFF1B\u5DF2\u7ECF\u5B8C\u6210\u7684\u4EFB\u52A1\u4E0D\u4F1A\u6539\u53D8\u3002",
        confirmLabel: "\u786E\u8BA4\u5168\u90E8\u505C\u6B62",
        destructive: true
      }
    ),
    /* @__PURE__ */ jsx(
      ConfirmDialog,
      {
        open: approvalDecision !== null,
        onClose: () => setApprovalDecision(null),
        onConfirm: async () => {
          if (!approvalDecision) return;
          await api.decideApproval(
            approvalDecision.approval.approval_id,
            approvalDecision.approved
          );
          setApprovalDecision(null);
          await queryClient.invalidateQueries({ queryKey: WORKBENCH_QUERY_KEY });
        },
        title: approvalDecision?.approved ? "\u6279\u51C6\u8FD9\u4E2A\u7CBE\u786E\u8303\u56F4\u7684\u52A8\u4F5C\uFF1F" : "\u62D2\u7EDD\u8FD9\u4E2A\u52A8\u4F5C\uFF1F",
        description: approvalDecision ? approvalConfirmation(approvalDecision.approval) : void 0,
        confirmLabel: approvalDecision?.approved ? "\u9650\u5B9A\u6279\u51C6\u5E76\u6062\u590D\u4F5C\u4E1A" : "\u786E\u8BA4\u62D2\u7EDD",
        destructive: approvalDecision?.approved === true
      }
    )
  ] });
}
function DemoLauncher({
  flows,
  mode,
  runningFlowId,
  onModeChange,
  onRun
}) {
  return /* @__PURE__ */ jsxs("section", { className: "rounded-md border border-(--ui-stroke-secondary) p-4", children: [
    /* @__PURE__ */ jsxs("div", { className: "mb-3 flex items-start justify-between gap-3", children: [
      /* @__PURE__ */ jsxs("div", { children: [
        /* @__PURE__ */ jsx("h2", { className: "font-medium", children: "\u4E3B\u6F14\u793A\u6D41\u7A0B" }),
        /* @__PURE__ */ jsx("p", { className: "mt-1 text-xs text-(--ui-text-tertiary)", children: "\u6A21\u62DF\u4E0E\u771F\u673A\u4F7F\u7528\u540C\u4E00 App Skill \u548C\u8BC1\u636E\u534F\u8BAE\uFF1B\u6A21\u62DF\u7ED3\u679C\u59CB\u7EC8\u660E\u786E\u6807\u6CE8\u3002" })
      ] }),
      /* @__PURE__ */ jsxs("div", { className: "flex gap-2", children: [
        /* @__PURE__ */ jsx(
          Button,
          {
            variant: mode === "SIMULATED" ? "default" : "outline",
            onClick: () => onModeChange("SIMULATED"),
            children: "\u786E\u5B9A\u6027\u6A21\u62DF"
          }
        ),
        /* @__PURE__ */ jsx(
          Button,
          {
            variant: mode === "DEVICE" ? "default" : "outline",
            onClick: () => onModeChange("DEVICE"),
            children: "\u771F\u5B9E\u624B\u673A"
          }
        )
      ] })
    ] }),
    /* @__PURE__ */ jsx("div", { className: "grid grid-cols-2 gap-2", children: flows.map((flow) => /* @__PURE__ */ jsxs(
      "article",
      {
        className: "flex items-center justify-between gap-3 rounded border border-(--ui-stroke-secondary) p-3",
        children: [
          /* @__PURE__ */ jsxs("div", { children: [
            /* @__PURE__ */ jsx("div", { className: "font-medium", children: flow.name }),
            /* @__PURE__ */ jsx("div", { className: "mt-1 text-xs text-(--ui-text-tertiary)", children: flow.source })
          ] }),
          /* @__PURE__ */ jsx(
            Button,
            {
              variant: "outline",
              disabled: runningFlowId !== null,
              onClick: () => void onRun(flow.flow_id),
              children: runningFlowId === flow.flow_id ? "\u8FD0\u884C\u4E2D\u2026" : "\u8FD0\u884C"
            }
          )
        ]
      },
      flow.flow_id
    )) })
  ] });
}
function ExecutionPanel({
  api,
  run,
  liveTimeline
}) {
  const viewModel = buildExecutionViewModel(run, liveTimeline ?? run.timeline);
  return /* @__PURE__ */ jsxs("section", { className: "grid grid-cols-[minmax(0,3fr)_minmax(14rem,2fr)] gap-4 rounded-md border border-(--ui-stroke-secondary) p-4", children: [
    /* @__PURE__ */ jsxs("div", { children: [
      /* @__PURE__ */ jsxs("div", { className: "mb-3 flex items-center gap-2", children: [
        /* @__PURE__ */ jsx("h2", { className: "font-medium", children: run.flow_name }),
        /* @__PURE__ */ jsx(Badge, { variant: viewModel.isSimulated ? "warn" : "default", children: viewModel.modeLabel }),
        /* @__PURE__ */ jsx(Badge, { variant: "muted", children: run.task.state })
      ] }),
      viewModel.isSimulated ? /* @__PURE__ */ jsx("div", { className: "mb-3 rounded border border-(--ui-warning) p-2 text-xs", children: "\u8FD9\u662F\u786E\u5B9A\u6027\u6A21\u62DF\u56DE\u653E\uFF0C\u6CA1\u6709\u58F0\u79F0\u64CD\u4F5C\u771F\u5B9E\u5E73\u53F0\u8D26\u53F7\u3002" }) : null,
      run.workflow_run ? /* @__PURE__ */ jsxs("div", { className: "mb-3 rounded border border-(--ui-stroke-secondary) p-2 text-xs", children: [
        /* @__PURE__ */ jsxs("div", { className: "font-medium", children: [
          "\u591A\u624B\u673A\u534F\u4F5C \xB7 ",
          run.workflow_run.status
        ] }),
        /* @__PURE__ */ jsx("div", { className: "mt-1 text-(--ui-text-tertiary)", children: run.workflow_run.nodes.map((node) => `${node.name} ${node.status}`).join(" \xB7 ") })
      ] }) : null,
      /* @__PURE__ */ jsx("div", { className: "flex max-h-64 flex-col gap-2 overflow-auto", children: viewModel.timeline.map((item) => /* @__PURE__ */ jsxs("article", { className: "rounded border border-(--ui-stroke-secondary) p-2", children: [
        /* @__PURE__ */ jsxs("div", { className: "flex items-center justify-between gap-2", children: [
          /* @__PURE__ */ jsx("span", { className: "font-medium", children: item.label }),
          /* @__PURE__ */ jsx("span", { className: "text-xs text-(--ui-text-tertiary)", children: new Date(item.at).toLocaleTimeString() })
        ] }),
        /* @__PURE__ */ jsx("div", { className: "mt-1 text-xs text-(--ui-text-tertiary)", children: item.detail })
      ] }, item.id)) })
    ] }),
    /* @__PURE__ */ jsxs("div", { children: [
      /* @__PURE__ */ jsx("h3", { className: "mb-3 font-medium", children: "\u8BC1\u636E\u4E0E\u624B\u673A\u753B\u9762" }),
      viewModel.evidence.length === 0 ? /* @__PURE__ */ jsx(EmptyState, { title: "\u7B49\u5F85\u8BC1\u636E", description: "\u771F\u5B9E\u624B\u673A\u6267\u884C\u540E\u4F1A\u5728\u8FD9\u91CC\u663E\u793A\u622A\u56FE\u548C\u56DE\u6267\u3002" }) : /* @__PURE__ */ jsx("div", { className: "flex max-h-72 flex-col gap-2 overflow-auto", children: viewModel.evidence.map((item) => /* @__PURE__ */ jsxs("article", { className: "rounded border border-(--ui-stroke-secondary) p-2", children: [
        item.mediaType.startsWith("image/") ? /* @__PURE__ */ jsx(EvidencePreview, { api, evidenceId: item.evidenceId, label: item.label }) : null,
        /* @__PURE__ */ jsx("div", { className: "text-xs font-medium", children: item.label }),
        /* @__PURE__ */ jsxs("div", { className: "mt-1 text-xs text-(--ui-text-tertiary)", children: [
          item.source,
          " \xB7 ",
          item.sha256.slice(0, 12)
        ] })
      ] }, item.evidenceId)) })
    ] })
  ] });
}
function EvidencePreview({ api, evidenceId, label }) {
  const query = useQuery({
    queryKey: ["aishop", "evidence-data", evidenceId],
    queryFn: () => api.getEvidenceData(evidenceId)
  });
  if (!query.data) return /* @__PURE__ */ jsx("div", { className: "mb-2 text-xs text-(--ui-text-tertiary)", children: "\u8BFB\u53D6\u8BC1\u636E\u2026" });
  return /* @__PURE__ */ jsx(
    "img",
    {
      className: "mb-2 max-h-48 w-full rounded object-contain",
      src: `data:${query.data.media_type};base64,${query.data.content_base64}`,
      alt: label
    }
  );
}
function DeviceWall({ api, devices }) {
  const queryClient = useQueryClient();
  const [pairingSession, setPairingSession] = useState(null);
  const [confirmation, setConfirmation] = useState(null);
  const viewModels = buildDeviceViewModels(devices);
  async function sendCommand(device, type) {
    const reasons = {
      PAUSE: "operator requested pause",
      RESUME: "operator released pause or takeover",
      TAKEOVER: "operator requested manual takeover",
      STOP: "operator requested device stop"
    };
    await api.sendDeviceCommand(device.device_id, type, reasons[type]);
    await queryClient.invalidateQueries({ queryKey: WORKBENCH_QUERY_KEY });
  }
  return /* @__PURE__ */ jsxs("div", { className: "flex flex-col gap-3", children: [
    /* @__PURE__ */ jsxs("div", { className: "flex items-center justify-between gap-2", children: [
      /* @__PURE__ */ jsx("h2", { className: "font-medium", children: "\u624B\u673A\u5458\u5DE5" }),
      /* @__PURE__ */ jsx(
        Button,
        {
          variant: "outline",
          onClick: async () => setPairingSession(await api.createPairingSession()),
          children: "\u751F\u6210\u914D\u5BF9\u7801"
        }
      )
    ] }),
    pairingSession ? /* @__PURE__ */ jsxs("div", { className: "rounded border border-(--ui-accent) p-3 text-center", children: [
      /* @__PURE__ */ jsx("div", { className: "text-xs text-(--ui-text-tertiary)", children: "5 \u5206\u949F\u5185\u5728\u624B\u673A\u8F93\u5165" }),
      /* @__PURE__ */ jsx("div", { className: "mt-1 font-mono text-2xl tracking-[0.25em]", children: pairingSession.pairing_code }),
      /* @__PURE__ */ jsxs("div", { className: "mt-1 text-xs text-(--ui-text-tertiary)", children: [
        "\u8FC7\u671F\u65F6\u95F4 ",
        new Date(pairingSession.expires_at).toLocaleTimeString()
      ] })
    ] }) : null,
    viewModels.length === 0 ? /* @__PURE__ */ jsx(EmptyState, { title: "\u5C1A\u672A\u8FDE\u63A5\u8BBE\u5907", description: "\u751F\u6210\u914D\u5BF9\u7801\u540E\uFF0C\u5728 Android Worker \u4E2D\u5B8C\u6210\u8FDE\u63A5\u3002" }) : /* @__PURE__ */ jsx("div", { className: "flex flex-col gap-2", children: viewModels.map(({ device, statusLabel, permissionWarnings, actions }) => /* @__PURE__ */ jsxs("article", { className: "rounded border border-(--ui-stroke-secondary) p-3", children: [
      /* @__PURE__ */ jsxs("div", { className: "flex items-start justify-between gap-2", children: [
        /* @__PURE__ */ jsxs("div", { className: "min-w-0", children: [
          /* @__PURE__ */ jsx("div", { className: "truncate font-medium", children: device.display_name }),
          /* @__PURE__ */ jsxs("div", { className: "mt-1 text-xs text-(--ui-text-tertiary)", children: [
            device.battery_percent === null ? "\u7535\u91CF\u672A\u77E5" : `\u7535\u91CF ${device.battery_percent}%`,
            " \xB7 ",
            "v",
            device.app_version
          ] })
        ] }),
        /* @__PURE__ */ jsx(Badge, { variant: device.online ? "default" : "muted", children: device.online ? statusLabel : "\u79BB\u7EBF" })
      ] }),
      permissionWarnings.length > 0 ? /* @__PURE__ */ jsx("div", { className: "mt-2 text-xs text-(--ui-text-tertiary)", children: permissionWarnings.join(" \xB7 ") }) : null,
      device.pending_command ? /* @__PURE__ */ jsxs("div", { className: "mt-2 text-xs text-(--ui-accent)", children: [
        "\u7B49\u5F85\u624B\u673A\u786E\u8BA4\uFF1A",
        device.pending_command.type
      ] }) : null,
      actions.length > 0 ? /* @__PURE__ */ jsx("div", { className: "mt-3 flex flex-wrap gap-2", children: actions.map((type) => /* @__PURE__ */ jsx(
        Button,
        {
          variant: type === "STOP" ? "destructive" : "outline",
          onClick: () => {
            if (type === "STOP" || type === "TAKEOVER") {
              setConfirmation({ device, type });
            } else {
              void sendCommand(device, type);
            }
          },
          children: deviceActionLabel(type)
        },
        type
      )) }) : null
    ] }, device.device_id)) }),
    /* @__PURE__ */ jsx(
      ConfirmDialog,
      {
        open: confirmation !== null,
        onClose: () => setConfirmation(null),
        onConfirm: async () => {
          if (confirmation) await sendCommand(confirmation.device, confirmation.type);
        },
        title: confirmation?.type === "STOP" ? "\u505C\u6B62\u8FD9\u53F0\u624B\u673A\u5458\u5DE5\uFF1F" : "\u8FDB\u5165\u4EBA\u5DE5\u63A5\u7BA1\uFF1F",
        description: "\u547D\u4EE4\u4F1A\u6301\u7EED\u6295\u9012\uFF0C\u76F4\u5230 Android Worker \u660E\u786E\u786E\u8BA4\u3002",
        confirmLabel: confirmation?.type === "STOP" ? "\u786E\u8BA4\u505C\u6B62" : "\u786E\u8BA4\u63A5\u7BA1",
        destructive: confirmation?.type === "STOP"
      }
    )
  ] });
}
function deviceActionLabel(type) {
  return { PAUSE: "\u6682\u505C", RESUME: "\u7EE7\u7EED", TAKEOVER: "\u63A5\u7BA1", STOP: "\u505C\u6B62" }[type];
}
function Metric({ label, value }) {
  return /* @__PURE__ */ jsxs("div", { className: "rounded-md border border-(--ui-stroke-secondary) p-3", children: [
    /* @__PURE__ */ jsx("div", { className: "text-xs text-(--ui-text-tertiary)", children: label }),
    /* @__PURE__ */ jsx("div", { className: "mt-1 text-2xl font-semibold", children: value })
  ] });
}
function WorkbenchStatus({ api }) {
  const { data } = useQuery({
    queryKey: WORKBENCH_QUERY_KEY,
    queryFn: api.getWorkbench,
    refetchInterval: 3e3
  });
  const activeCount = data ? buildWorkbenchViewModel(data).activeCount : 0;
  return /* @__PURE__ */ jsxs("span", { className: "text-xs", children: [
    "AIShop ",
    activeCount
  ] });
}
function WorkbenchRoot({ rest }) {
  const [token, setToken] = useState(() => localStorage.getItem("aishop.operatorToken") ?? "");
  const [draft, setDraft] = useState(token);
  if (!token) {
    return /* @__PURE__ */ jsx("main", { className: "flex h-full items-center justify-center p-6", children: /* @__PURE__ */ jsxs("section", { className: "w-full max-w-lg rounded-md border border-(--ui-stroke-secondary) p-5", children: [
      /* @__PURE__ */ jsx("h1", { className: "text-lg font-semibold", children: "\u8FDE\u63A5 AIShop \u672C\u5730\u64CD\u4F5C\u5458" }),
      /* @__PURE__ */ jsx("p", { className: "mt-2 text-xs text-(--ui-text-tertiary)", children: "\u8F93\u5165 AISHOP_OPERATOR_TOKEN\uFF0C\u6216\u6570\u636E\u76EE\u5F55 operator.token \u6587\u4EF6\u4E2D\u7684\u4EE4\u724C\u3002" }),
      /* @__PURE__ */ jsx(
        "input",
        {
          "aria-label": "\u64CD\u4F5C\u5458\u4EE4\u724C",
          className: "mt-4 w-full rounded border border-(--ui-stroke-secondary) bg-transparent px-3 py-2",
          type: "password",
          value: draft,
          onChange: (event) => setDraft(event.target.value)
        }
      ),
      /* @__PURE__ */ jsx(
        Button,
        {
          className: "mt-3",
          disabled: !draft.trim(),
          onClick: () => {
            const value = draft.trim();
            localStorage.setItem("aishop.operatorToken", value);
            setToken(value);
          },
          children: "\u8FDE\u63A5"
        }
      )
    ] }) });
  }
  return /* @__PURE__ */ jsx(
    WorkbenchPage,
    {
      api: createApi(rest, () => token),
      onClearToken: () => {
        localStorage.removeItem("aishop.operatorToken");
        setToken("");
        setDraft("");
      }
    }
  );
}
function RegisteredWorkbenchStatus({ rest }) {
  const token = localStorage.getItem("aishop.operatorToken") ?? "";
  if (!token) return /* @__PURE__ */ jsx("span", { className: "text-xs", children: "AIShop \u672A\u8BA4\u8BC1" });
  return /* @__PURE__ */ jsx(WorkbenchStatus, { api: createApi(rest, () => token) });
}
var plugin = {
  id: "aishop",
  name: "AIShop",
  description: "\u672C\u5730\u7535\u5546 AI \u5458\u5DE5\u4EFB\u52A1\u6307\u6325\u8231",
  defaultEnabled: false,
  register(ctx) {
    ctx.registerMany([
      {
        id: "workbench-page",
        area: ROUTES_AREA,
        data: { path: "/aishop" },
        render: () => /* @__PURE__ */ jsx(WorkbenchRoot, { rest: ctx.rest })
      },
      {
        id: "workbench-nav",
        area: SIDEBAR_NAV_AREA,
        data: { path: "/aishop", label: "AI \u5458\u5DE5\u4F5C\u53F0", codicon: "dashboard" }
      },
      {
        id: "workbench-status",
        area: STATUSBAR_AREAS.right,
        order: 120,
        render: () => /* @__PURE__ */ jsx(RegisteredWorkbenchStatus, { rest: ctx.rest })
      }
    ]);
  }
};
var plugin_default = plugin;
export {
  plugin_default as default
};
