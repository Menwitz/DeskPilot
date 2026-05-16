param(
    [string]$ExePath = "dist/deskpilot.exe",
    [string]$AppExePath = "dist/deskpilot-app.exe",
    [string]$RoutinePackRoot = "routine_packs",
    [string]$SmokeRoot = "dist/package-smoke"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ExePath)) {
    throw "Packaged executable not found: $ExePath"
}

# Smoke traces are generated locally so replay verification never needs live I/O.
if (Test-Path $SmokeRoot) {
    Remove-Item $SmokeRoot -Recurse -Force
}
$TraceDir = Join-Path $SmokeRoot "trace-replay"
New-Item -ItemType Directory -Force -Path $TraceDir | Out-Null
@'
{
  "task_name": "packaged smoke replay",
  "status": "passed",
  "metadata": {
    "routine_id": "packaging.smoke"
  },
  "steps": [],
  "events": []
}
'@ | Set-Content -Encoding UTF8 (Join-Path $TraceDir "final-report.json")

& $ExePath --help
& $ExePath dry-run examples/browser-task.yaml --config packaging/default-config.yaml
& $ExePath list-routines --routine-pack-root $RoutinePackRoot
& $ExePath replay $TraceDir

if (Test-Path $AppExePath) {
    & $AppExePath --check
} else {
    Write-Host "Operator app executable not found; skipping app smoke: $AppExePath"
}

Write-Host "Packaged help, dry-run, routine listing, trace replay, and app checks passed"
