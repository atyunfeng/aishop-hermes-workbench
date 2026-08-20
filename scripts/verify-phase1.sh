#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

bash -n scripts/verify-foundation.sh scripts/verify-android-worker.sh scripts/verify-phase1.sh
.venv/bin/python -m pytest tests -q
.venv/bin/ruff check hermes-plugin tests scripts/*.py
npm --prefix desktop-plugin test -- --run
npm --prefix desktop-plugin run build
bash scripts/verify-android-worker.sh

unexpected_imports="$({ rg -U -o "from\\s+['\"][^'\"]+['\"]|import\\s+['\"][^'\"]+['\"]" \
  hermes-plugin/desktop/plugin.js || true; } \
  | rg -v "(@hermes/plugin-sdk|react/jsx-runtime|react)['\"]$" || true)"
if [[ -n "$unexpected_imports" ]]; then
  printf '%s\n' "$unexpected_imports"
  exit 1
fi

soak_dir="$(mktemp -d)"
cleanup() { rm -rf "$soak_dir"; }
trap cleanup EXIT
for demo_run in $(seq 1 10); do
  .venv/bin/python scripts/run-demo.py --flow all --mode simulated \
    --data-dir "$soak_dir/run-$demo_run" >/dev/null
done

.venv/bin/python scripts/package-release.py

apk_path="$repo_root/artifacts/aishop-worker-debug.apk"
if [[ -n "${ANDROID_HOME:-}" ]]; then
  aapt_path="$(ls "$ANDROID_HOME"/build-tools/*/aapt 2>/dev/null | sort -V | tail -1 || true)"
  if [[ -n "$aapt_path" ]]; then
    "$aapt_path" dump badging "$apk_path" | rg "package: name='com.aishop.worker.demo'|sdkVersion:'26'|targetSdkVersion:'35'"
  fi
fi

if command -v hermes >/dev/null 2>&1; then
  hermes plugins doctor hermes-plugin --ci
else
  printf 'UNAVAILABLE: Hermes CLI validation requires the Windows 11 demo machine.\n'
fi
if command -v adb >/dev/null 2>&1 && adb devices | rg -q $'\tdevice$'; then
  printf 'AVAILABLE: Android device attached; execute docs/real-device-validation.md.\n'
else
  printf 'UNAVAILABLE: no authorized physical Android device is attached.\n'
fi
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) printf 'AVAILABLE: Windows environment detected.\n' ;;
  *) printf 'UNAVAILABLE: Windows 11 platform validation was not executed on this host.\n' ;;
esac
