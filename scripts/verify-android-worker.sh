#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
worker_root="$repo_root/android-worker"
apk_source="$worker_root/app/build/outputs/apk/demo/debug/app-demo-debug.apk"
artifact_dir="$repo_root/artifacts"
apk_target="$artifact_dir/aishop-worker-debug.apk"

cd "$worker_root"
./gradlew verifyProductionSigning testDemoDebugUnitTest lintDemoDebug assembleDemoDebug lintProductionRelease assembleProductionRelease

demo_manifest="$worker_root/app/build/intermediates/merged_manifests/demoDebug/processDemoDebugManifest/AndroidManifest.xml"
production_manifest="$worker_root/app/build/intermediates/merged_manifests/productionRelease/processProductionReleaseManifest/AndroidManifest.xml"
rg -q 'usesCleartextTraffic="true"' "$demo_manifest"
rg -q 'usesCleartextTraffic="false"' "$production_manifest"
rg -q 'com.bytedance.ep.android' "$demo_manifest"
rg -q 'cleartextTrafficPermitted="true"' "$worker_root/app/src/demo/res/xml/network_security_config.xml"
rg -q 'cleartextTrafficPermitted="false"' "$worker_root/app/src/main/res/xml/network_security_config.xml"

test -f "$apk_source"
mkdir -p "$artifact_dir"
cp "$apk_source" "$apk_target"
shasum -a 256 "$apk_target" > "$apk_target.sha256"
printf 'Android Worker APK: %s\n' "$apk_target"
