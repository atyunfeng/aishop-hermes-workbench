#!/usr/bin/env bash
set -euo pipefail

.venv/bin/python -m pytest tests -q
.venv/bin/ruff check hermes-plugin tests scripts/seed-demo.py
npm run desktop:test
npm run desktop:build

unexpected_imports="$({ rg -U -o "from\\s+['\"][^'\"]+['\"]|import\\s+['\"][^'\"]+['\"]" \
  hermes-plugin/desktop/plugin.js || true; } \
  | rg -v "(@hermes/plugin-sdk|react/jsx-runtime|react)['\"]$" || true)"
if [[ -n "$unexpected_imports" ]]; then
  printf '%s\n' "$unexpected_imports"
  exit 1
fi
