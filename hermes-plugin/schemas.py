TASK_STATES = [
    "RECEIVED",
    "PLANNING",
    "WAITING_APPROVAL",
    "QUEUED",
    "ASSIGNED",
    "EXECUTING",
    "VERIFYING",
    "SUCCEEDED",
    "RETRY_WAIT",
    "HUMAN_TAKEOVER",
    "FAILED",
    "CANCELLED",
]


CREATE_TASK = {
    "type": "object",
    "additionalProperties": False,
    "required": ["idempotency_key", "source", "title"],
    "properties": {
        "idempotency_key": {"type": "string", "minLength": 1},
        "source": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 1},
    },
}

GET_TASK = {
    "type": "object",
    "additionalProperties": False,
    "required": ["task_id"],
    "properties": {"task_id": {"type": "string", "minLength": 1}},
}

TRANSITION_TASK = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "task_id",
        "expected_version",
        "target_state",
        "reason",
        "idempotency_key",
    ],
    "properties": {
        "task_id": {"type": "string", "minLength": 1},
        "expected_version": {"type": "integer", "minimum": 1},
        "target_state": {"type": "string", "enum": TASK_STATES},
        "reason": {"type": "string", "minLength": 1},
        "idempotency_key": {"type": "string", "minLength": 1},
    },
}

STOP_ALL = {
    "type": "object",
    "additionalProperties": False,
    "required": ["reason"],
    "properties": {"reason": {"type": "string", "minLength": 1}},
}

DISPATCH_WORKFLOW = {
    "type": "object",
    "additionalProperties": False,
    "required": ["task_id", "app_skill_id", "workflow_id", "inputs", "mode"],
    "properties": {
        "task_id": {"type": "string", "minLength": 1},
        "app_skill_id": {
            "type": "string",
            "enum": ["qian-niu", "dou-dian", "we-chat", "we-com", "qq"],
        },
        "workflow_id": {"type": "string", "minLength": 1},
        "inputs": {
            "type": "object",
            "additionalProperties": {"type": "string", "minLength": 1, "maxLength": 2000},
        },
        "mode": {"type": "string", "enum": ["DEVICE", "SIMULATED"]},
    },
}
