param(
    [string]$GatewayUrl,
    [string]$HermesHome,
    [string]$OperatorToken = $env:AISHOP_OPERATOR_TOKEN
)

$ErrorActionPreference = "Continue"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($HermesHome)) {
    if (-not [string]::IsNullOrWhiteSpace($env:HERMES_HOME)) {
        $HermesHome = $env:HERMES_HOME
    }
    elseif (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $HermesHome = Join-Path $env:LOCALAPPDATA "hermes"
    }
}

$Checks = [ordered]@{}
$Checks.windows_11 = [Environment]::OSVersion.Platform -eq "Win32NT" -and `
    [Environment]::OSVersion.Version.Build -ge 22000
$Checks.python_311 = $false
$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
if (Test-Path $Python) {
    $Version = & $Python -c "import sys; print(int(sys.version_info >= (3, 11)))" 2>$null
    $Checks.python_311 = $Version -eq "1"
}
$Checks.hermes_cli = $null -ne (Get-Command hermes -ErrorAction SilentlyContinue)
$Checks.hermes_plugin_installed = -not [string]::IsNullOrWhiteSpace($HermesHome) -and `
    (Test-Path (Join-Path $HermesHome "plugins\aishop\plugin.yaml"))
$Checks.apk_present = Test-Path (Join-Path $RepositoryRoot "artifacts\aishop-worker-debug.apk")
$Checks.adb_available = $null -ne (Get-Command adb -ErrorAction SilentlyContinue)
$Checks.android_device_attached = $false
if ($Checks.adb_available) {
    $Devices = @(& adb devices 2>$null | Select-String "`tdevice$")
    $Checks.android_device_attached = $Devices.Count -gt 0
}
$Checks.gateway_reachable = $false
$Checks.gateway_operator_authenticated = $false
$Checks.gateway_https = $false
if (-not [string]::IsNullOrWhiteSpace($GatewayUrl)) {
    try {
        $GatewayUri = [Uri]$GatewayUrl
        $Checks.gateway_https = $GatewayUri.Scheme -eq "https"
        $Response = Invoke-WebRequest -Uri ($GatewayUrl.TrimEnd('/') + "/health") -TimeoutSec 5
        $Checks.gateway_reachable = $Response.StatusCode -eq 200
        if (-not [string]::IsNullOrWhiteSpace($OperatorToken)) {
            $Headers = @{ "X-AIShop-Operator-Token" = $OperatorToken }
            $OperatorResponse = Invoke-WebRequest `
                -Uri ($GatewayUrl.TrimEnd('/') + "/workbench") `
                -Headers $Headers `
                -TimeoutSec 5
            $Checks.gateway_operator_authenticated = $OperatorResponse.StatusCode -eq 200
        }
    }
    catch {
        $Checks.gateway_reachable = $false
    }
}

$Required = @("windows_11", "python_311", "hermes_cli", "hermes_plugin_installed", "apk_present")
if (-not [string]::IsNullOrWhiteSpace($GatewayUrl)) {
    $Required += @("gateway_reachable", "gateway_operator_authenticated")
}
$Failed = @($Required | Where-Object { -not $Checks[$_] })
$Result = [ordered]@{
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    checks = $Checks
    required_failures = $Failed
    manual_checks = @(
        "Windows Defender Firewall only allows the Hermes port on Private networks",
        "Test accounts are logged in for QianNiu, DouDian, WeChat, WeCom, and QQ",
        "Recipients and conversations are white-listed test identities",
        "Accessibility and MediaProjection show ready in the device wall",
        "Production Android workers use an HTTPS gateway; HTTP is demo flavor only",
        "No real refund, return, account, delete, add-contact, or bulk-send action is enabled"
    )
}
$Result | ConvertTo-Json -Depth 6
if ($Failed.Count -gt 0) { exit 2 }
