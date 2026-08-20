# Contributing

AIShop welcomes focused fixes, tests, documentation and new versioned App Skill
fixtures. The project is an Alpha safety-oriented automation workbench, so a
successful simulation must never be described as real-device acceptance.

## Before opening a pull request

1. Discuss large behavior or protocol changes in an issue first.
2. Do not submit customer data, platform credentials, proprietary UI dumps or
   source material you are not allowed to redistribute.
3. Add or update tests for changed behavior.
4. Run `bash scripts/verify-foundation.sh`; Android changes also require
   `bash scripts/verify-android-worker.sh`.
5. Keep `SIMULATED` and `DEVICE` evidence clearly separated.

## Developer Certificate of Origin

Contributions use the [Developer Certificate of Origin 1.1](https://developercertificate.org/).
Sign every commit with:

```text
Signed-off-by: Your Name <your-email@example.com>
```

Use `git commit -s` to add the line. By signing off, you certify that you have
the right to submit the contribution under this project's AGPLv3 license.

## Pull request expectations

- Explain the problem and the smallest solution.
- List exact tests run and distinguish local, simulated and device validation.
- Note security, privacy and compatibility effects.
- Keep generated `hermes-plugin/desktop/plugin.js` synchronized with its source.
- Avoid unrelated formatting or refactoring.

External contributions remain owned by their authors and are licensed to the
project under `AGPL-3.0-only`. No CLA or commercial relicensing grant is implied.
