---
name: aishop-we-chat
description: Dispatch one guarded WeChat private-domain reply to a white-listed test contact.
---

# AIShop WeChat

Create the task first, then call `aishop_dispatch_workflow` with App Skill `we-chat`, workflow `private_customer_reply`, and only `package_name`, `customer_name`, `reply_text`. Send one low-frequency message to a configured test contact. Do not add friends, broadcast, scrape contacts, bypass account controls, or continue after captcha/login/unknown-page signals. Label simulated runs as simulated evidence.
