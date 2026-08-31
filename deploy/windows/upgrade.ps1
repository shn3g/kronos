# SPDX-License-Identifier: AGPL-3.0-or-later
# Upgrades an installed Kronos tree. Incompatible desktop/engine pairs are refused.
param(
    [Parameter(Mandatory = $true)]
    [string]$Target,
    [Parameter(Mandatory = $true)]
    [string]$ToVersion,
    [string]$EngineVersion = "0.1.0",
    [string]$MinClientVersion = "0.1.0",
    [string]$ClientVersion = "0.1.0"
)

$ErrorActionPreference = "Stop"
python -c "from pathlib import Path; from kronos_engine.ops.lifecycle import upgrade; upgrade(Path(r'$Target'), to_version='$ToVersion', engine_version='$EngineVersion', min_client_version='$MinClientVersion', client_version='$ClientVersion')"
Write-Output "Upgraded Kronos to $ToVersion"
