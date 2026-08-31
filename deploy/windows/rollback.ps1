# SPDX-License-Identifier: AGPL-3.0-or-later
# Restores the previous Kronos version recorded beside the current tree.
param(
    [Parameter(Mandatory = $true)]
    [string]$Target
)

$ErrorActionPreference = "Stop"
python -c "from pathlib import Path; from kronos_engine.ops.lifecycle import rollback; print(rollback(Path(r'$Target')).version)"
