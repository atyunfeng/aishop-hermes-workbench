# Security policy

## Supported versions

AIShop Hermes Workbench is currently an Alpha project. Security fixes are
provided only for the latest `0.1.x` release and the current `main` branch.

## Reporting a vulnerability

Please use **Security → Report a vulnerability** in this GitHub repository so
the report is delivered privately. Include the affected commit or release,
reproduction steps, impact, and any proposed mitigation. Do not include live
customer messages, access tokens, screenshots, order data, or platform account
credentials.

If private vulnerability reporting is temporarily unavailable, open a minimal
public issue asking the maintainers to enable a private channel. Do not publish
the exploit or sensitive evidence in that issue.

Maintainers will acknowledge a complete report when it is reviewed, coordinate
a fix and disclosure with the reporter, and credit the reporter if requested.
No response-time SLA is offered for this volunteer Alpha project.

## Security boundaries

- AIShop is not a credential vault. Keep operator, device and platform tokens
  outside source control and use a password manager for operator secrets.
- Demo HTTP is restricted to a trusted private LAN. Production builds reject
  cleartext traffic and should use HTTPS with a reviewed certificate setup.
- Accessibility, notification access and MediaProjection are powerful Android
  permissions. Enable only the capabilities required for the current worker.
- High-risk operations remain subject to one-time, scope-bound approval.
- A passing simulated run is not evidence that a real platform action is safe.
