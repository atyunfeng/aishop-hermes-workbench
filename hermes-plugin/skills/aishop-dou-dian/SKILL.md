---
name: aishop-dou-dian
description: Dispatch guarded DouDian Feige image-after-sales replies to a paired AIShop Android worker.
---

# AIShop DouDian and Feige

Create the task first, then call `aishop_dispatch_workflow` with App Skill `dou-dian`, workflow `image_after_sales_reply`, and only `package_name`, `order_id`, `reply_text`. This workflow explains the after-sales plan but does not approve money movement, refund, return, deletion, or account changes. Those operations require a separate scoped approval and are not exposed by this skill. Stop for login failure, captcha, or unknown pages. Label simulated runs.
