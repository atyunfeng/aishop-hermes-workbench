---
name: aishop-operator
description: Operate the local AIShop ecommerce task workbench through structured tools.
---

# AIShop Operator

Create an AIShop task with `aishop_create_task` before taking any AIShop action. Use a stable idempotency key derived from the source message or command.

Use the returned `task_id` and `version` for every `aishop_transition_task` call. Advance through only valid states and never move from `EXECUTING` directly to `SUCCEEDED`; enter `VERIFYING` and verify the result first.

Do not invent screen coordinates, shell commands, executable code, or unregistered actions. Money, account, deletion, contact-addition, and bulk-send operations require capabilities outside this foundation plugin.

Call `aishop_stop_all` only when the operator explicitly instructs you to stop all work. Never infer a global stop from a single task failure.
