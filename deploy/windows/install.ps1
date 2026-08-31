# SPDX-License-Identifier: AGPL-3.0-or-later
# Installs the Kronos background engine as a per-user Windows service wrapper.
# Bundled desktop installers ship the matching Python engine; this script records versions.
param(
    [Parameter(Mandatory = $true)]
    [string]$Target,
    [string]$Version = "0.1.0",
    [string]$EngineVersion = "0.1.0"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path (Join-Path $Target "current") | Out-Null
$payload = @{ version = $Version; engine_version = $EngineVersion } | ConvertTo-Json
Set-Content -Path (Join-Path $Target "current\version.json") -Value $payload -Encoding utf8
Write-Output "Installed Kronos $Version (engine $EngineVersion) into $Target"
