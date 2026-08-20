---
name: aishop-we-com
description: Dispatch a guarded WeCom multi-phone work summary to a white-listed test conversation.
---

# AIShop WeCom

Use App Skill `we-com` and workflow `instruction_report` only after the underlying child tasks have verifiable receipts. Inputs are `package_name`, `conversation_name`, and `report_text`. The report must distinguish completed, exceptional, and simulated counts. Never convert a broad WeCom instruction into bulk customer messaging; stop and request human takeover for login, captcha, or an unknown page.
