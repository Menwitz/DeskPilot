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

$SmokeTraceRoot = Join-Path $SmokeRoot "dry-run-traces"
$SmokeConfigPath = Join-Path $SmokeRoot "default-config.yaml"
$SmokeTraceRootYaml = $SmokeTraceRoot -replace "\\", "/"
$SmokeConfig = Get-Content "packaging/default-config.yaml" -Raw
$SmokeConfig = $SmokeConfig -replace "(?m)^trace_root:.*$", "trace_root: $SmokeTraceRootYaml"
$SmokeConfig = $SmokeConfig -replace "(?m)^save_screenshots:.*$", "save_screenshots: false"
$SmokeConfig = $SmokeConfig -replace "(?m)^save_ocr_text:.*$", "save_ocr_text: false"
$SmokeConfig | Set-Content -Encoding UTF8 $SmokeConfigPath

& $ExePath --help
& $ExePath dry-run examples/browser-task.yaml --config $SmokeConfigPath
& $ExePath list-routines --routine-pack-root $RoutinePackRoot
& $ExePath replay $TraceDir
& $ExePath trace-health --trace-root $SmokeRoot

$DryRunReport = Get-ChildItem -Path $SmokeTraceRoot -Directory |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1 |
    ForEach-Object { Join-Path $_.FullName "final-report.json" }
if (-not $DryRunReport -or -not (Test-Path $DryRunReport)) {
    throw "Packaged dry-run did not write final-report.json under $SmokeTraceRoot"
}

if (Test-Path $AppExePath) {
    $AppCheckOutput = & $AppExePath --check
    $AppCheckOutput | Write-Host
    if (($AppCheckOutput -join "`n") -notmatch "PySide6: available") {
        throw "Packaged operator app did not report bundled PySide6 availability"
    }
    & $AppExePath --describe-shell
} else {
    Write-Host "Operator app executable not found; skipping app smoke: $AppExePath"
}

Write-Host "Packaged help, dry-run report, routine listing, trace replay, trace health, and app checks passed"
