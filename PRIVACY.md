# Privacy and data handling

AIShop Hermes Workbench is local-first and does not include product telemetry,
advertising SDKs or a hosted AIShop control plane. Operators remain responsible
for the legality of processing customer and employee data in their region and
on each connected platform.

## Data processed locally

Depending on the enabled workflow, the workbench can process:

- task titles, conversation identifiers and structured inbound event metadata;
- imported order snapshots and local knowledge entries;
- Android device identity, installed package capability and health status;
- notification text from the explicit commerce/social application allowlist;
- Accessibility semantic nodes used to locate and verify UI actions;
- screenshots explicitly captured after Android MediaProjection consent;
- approvals, task transitions, execution results and evidence audit records.

AIShop does not need a user's platform password. Platform applications keep
their own sessions. Do not put passwords, verification codes, raw tokens or
unredacted production exports into demo fixtures, logs, issues or pull requests.

## Storage and retention

Runtime data is stored in the local Hermes plugin data directory and the Android
application's private storage. Device tokens are encrypted with Android
Keystore; the desktop database stores only their SHA-256 digests. Evidence is
limited to 700 KiB per item, retained for seven days by default and bounded to
512 MiB unless the operator changes local configuration.

`scripts/export-local-data.py` exports redacted metadata without tokens, raw
message payloads, knowledge bodies or evidence file contents. To erase a demo,
use the workbench demo reset. To erase all operational data, first stop and
disable the plugin, then remove its local data directory and clear pairing in
the Android Worker. Back up anything required for audit before deletion.

## Network and third parties

The Android Worker connects only to the operator-configured Hermes plugin API.
Real workflows also interact with the installed third-party platform apps;
those platforms apply their own privacy policies and account rules. Model or
vision providers are not enabled by default. If an operator configures one,
that operator must disclose the provider and assess what data leaves the local
environment.

Security issues involving personal data should be reported privately as
described in [SECURITY.md](SECURITY.md).
