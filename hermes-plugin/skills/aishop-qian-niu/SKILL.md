---
name: aishop-qian-niu
description: Dispatch guarded QianNiu customer-service replies to a paired AIShop Android worker.
---

# AIShop QianNiu

Create the task first, then call `aishop_dispatch_workflow` with App Skill `qian-niu`, workflow `customer_reply`, and only `package_name`, `customer_name`, `reply_text`. Use the configured test account and white-listed customer. Never invent coordinates, bypass login or captcha, issue refunds, delete records, add contacts, or send in bulk. Use `DEVICE` only when the operator confirms a logged-in test phone; otherwise use `SIMULATED` and say so visibly.
