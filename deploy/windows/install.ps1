# SPDX-License-Identifier: AGPL-3.0-or-later
# Installs the Kronos background engine as a per-user Windows service wrapper.
# Copies a provided engine/desktop payload into $Target, then records versions.
param(
    [Parameter(Mandatory = $true)]
    [string]$Target,
    [string]$Version = "0.1.0",
    [string]$EngineVersion = "0.1.0",
    [string]$Payload = ""
)

$ErrorActionPreference = "Stop"
$current = Join-Path $Target "current"
New-Item -ItemType Directory -Force -Path $current | Out-Null
if ($Payload -ne "" -and (Test-Path -LiteralPath $Payload)) {
    Copy-Item -Path (Join-Path $Payload "*") -Destination $current -Recurse -Force
}
$payload = @{ version = $Version; engine_version = $EngineVersion } | ConvertTo-Json
Set-Content -Path (Join-Path $current "version.json") -Value $payload -Encoding utf8
Write-Output "Installed Kronos $Version (engine $EngineVersion) into $Target"
