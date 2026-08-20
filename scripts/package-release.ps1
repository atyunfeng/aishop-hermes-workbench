param(
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $RepositoryRoot "artifacts\AIShop-Hermes-Workbench-phase1.zip"
}

$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Python virtual environment is missing: $Python"
}

Push-Location $RepositoryRoot
try {
    & $Python -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { throw "Python verification failed" }
    & npm --prefix desktop-plugin test -- --run
    if ($LASTEXITCODE -ne 0) { throw "Desktop tests failed" }
    & npm --prefix desktop-plugin run build
    if ($LASTEXITCODE -ne 0) { throw "Desktop build failed" }
    & .\android-worker\gradlew.bat -p android-worker verifyProductionSigning testDemoDebugUnitTest lintDemoDebug assembleDemoDebug lintProductionRelease assembleProductionRelease
    if ($LASTEXITCODE -ne 0) { throw "Android build failed" }
    New-Item -ItemType Directory -Force -Path (Join-Path $RepositoryRoot "artifacts") | Out-Null
    Copy-Item `
        (Join-Path $RepositoryRoot "android-worker\app\build\outputs\apk\demo\debug\app-demo-debug.apk") `
        (Join-Path $RepositoryRoot "artifacts\aishop-worker-debug.apk") `
        -Force
    & $Python .\scripts\package-release.py --output $OutputPath
    if ($LASTEXITCODE -ne 0) { throw "Release bundle creation failed" }
}
finally {
    Pop-Location
}

Write-Host "Release bundle: $OutputPath"
