<#
.SYNOPSIS
    reset-dev (Windows host wrapper) — restore the shared dev backend to a clean
    seed baseline before an E2E sweep. Group 19.1.

.DESCRIPTION
    Thin wrapper around reset_dev.py that runs it under the canonical test
    interpreter (C:/Python314/python.exe — the one `pytest` uses on Derek's
    machine, per CLAUDE.md), so `requests` resolves the same way the sweep does.
    All arguments pass straight through.

    Runs on the HOST (not inside the container): it docker-restarts
    inventory_hub and rewrites the bind-mounted locations.json.

.EXAMPLE
    ./reset-dev.ps1                 # non-destructive restore + docker restart
    ./reset-dev.ps1 --dry-run --prune   # preview, incl. sweep-created records
    ./reset-dev.ps1 --prune         # restore AND delete sweep-created records
    ./reset-dev.ps1 --capture       # re-snapshot current dev into seeds/
#>
$ErrorActionPreference = 'Stop'
$py = 'C:/Python314/python.exe'
if (-not (Test-Path $py)) { $py = 'python' }   # fall back to PATH python
$script = Join-Path $PSScriptRoot 'reset_dev.py'
& $py $script @args
exit $LASTEXITCODE
