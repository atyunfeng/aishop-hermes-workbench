param(
    [string]$HermesHome
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($HermesHome)) {
    if (-not [string]::IsNullOrWhiteSpace($env:HERMES_HOME)) {
        $HermesHome = $env:HERMES_HOME
    }
    elseif (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $HermesHome = Join-Path $env:LOCALAPPDATA "hermes"
    }
    else {
        throw "Cannot resolve Hermes home. Pass -HermesHome or set HERMES_HOME."
    }
}

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$PluginSource = Join-Path $RepositoryRoot "hermes-plugin"
$PluginsRoot = Join-Path $HermesHome "plugins"
$Destination = Join-Path $PluginsRoot "aishop"
$Temporary = Join-Path $PluginsRoot (".aishop.install." + [guid]::NewGuid().ToString("N"))
$Backup = $null

if (-not (Test-Path (Join-Path $PluginSource "plugin.yaml"))) {
    throw "AIShop plugin source is incomplete: $PluginSource"
}

New-Item -ItemType Directory -Force -Path $PluginsRoot | Out-Null
Copy-Item -Path $PluginSource -Destination $Temporary -Recurse

try {
    if (Test-Path $Destination) {
        $Backup = Join-Path $PluginsRoot ("aishop.backup." + (Get-Date -Format "yyyyMMddHHmmss"))
        Move-Item -Path $Destination -Destination $Backup
    }
    Move-Item -Path $Temporary -Destination $Destination
}
catch {
    if ((Test-Path $Temporary) -and -not (Test-Path $Destination)) {
        Remove-Item -Path $Temporary -Recurse -Force
    }
    if (($null -ne $Backup) -and (Test-Path $Backup) -and -not (Test-Path $Destination)) {
        Move-Item -Path $Backup -Destination $Destination
    }
    throw
}

& hermes plugins doctor $Destination --ci

Write-Host "AIShop plugin installed at: $Destination"
if ($null -ne $Backup) {
    Write-Host "Previous plugin installation retained at: $Backup"
}
Write-Host "Plugin data was not changed: $(Join-Path $HermesHome 'plugins-data\aishop')"
Write-Host "Enable manually with: hermes plugins enable aishop"
