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
$SmokeTraceRoot = Join-Path $SmokeRoot "dry-run-traces"
$TraceDir = Join-Path $SmokeTraceRoot "trace-replay"
$BenchmarkTraceDir = Join-Path $SmokeTraceRoot "benchmark-replay"
New-Item -ItemType Directory -Force -Path $TraceDir | Out-Null
New-Item -ItemType Directory -Force -Path $BenchmarkTraceDir | Out-Null
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

# Benchmark replay is seeded locally so packaged verification covers monitoring
# reports without requiring live desktop input or long repeated runs.
@'
{
  "schema_version": "benchmark_report_v1",
  "generated_at": "2026-05-17T00:00:00+00:00",
  "task_path": "examples/browser-task.yaml",
  "trace_health_path": "trace-health.json",
  "trace_health_summary": {
    "health_status": "ok",
    "artifact_trace_count": 1
  },
  "report_artifacts": {
    "report": "benchmark-report.json",
    "metrics": "runs.jsonl",
    "summary": "benchmark-summary.md",
    "trace_health": "trace-health.json"
  },
  "iterations": 1,
  "summary": {
    "success_rate": 1.0,
    "grounding_accuracy": 1.0,
    "ambiguity_rate": 0.0,
    "recovery_rate": 0.0,
    "operator_intervention_rate": 0.0
  },
  "acceptance": {
    "status": "passed"
  },
  "baseline_comparison": {
    "status": "neutral"
  },
  "observability_contract": {
    "configured": true,
    "benchmark_task_id": "packaging-smoke",
    "pipeline_modes": ["packaged-cli", "replay"],
    "deep_search_sources": ["benchmark-report", "trace-health"],
    "required_trace_phases": ["observe_screen"],
    "required_report_fields": ["status"],
    "required_metrics": ["success_rate"]
  },
  "monitoring_coverage": {
    "configured": true,
    "passed": true,
    "observed_trace_phases": ["observe_screen"],
    "missing_trace_phases": [],
    "observed_report_fields": ["status"],
    "missing_report_fields": []
  },
  "runs": [
    {
      "iteration": 1,
      "status": "passed",
      "trace_dir": "dry-run-traces/trace-replay",
      "task_time_seconds": 0.1,
      "step_count": 0,
      "action_count": 0
    }
  ]
}
'@ | Set-Content -Encoding UTF8 (Join-Path $BenchmarkTraceDir "benchmark-report.json")

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
& $ExePath replay $BenchmarkTraceDir --write-summary
if (-not (Test-Path (Join-Path $BenchmarkTraceDir "replay-summary.md"))) {
    throw "Packaged benchmark replay did not write replay-summary.md"
}
$BenchmarkReplaySummary = Get-Content (Join-Path $BenchmarkTraceDir "replay-summary.md") -Raw
if ($BenchmarkReplaySummary -notmatch "Report Artifacts") {
    throw "Packaged benchmark replay summary did not include artifact manifest"
}
if ($BenchmarkReplaySummary -notmatch "Trace health artifacts") {
    throw "Packaged benchmark replay summary did not include trace-health summary"
}
if ($BenchmarkReplaySummary -notmatch "benchmark-report.json") {
    throw "Packaged benchmark replay summary did not include report artifact"
}
if ($BenchmarkReplaySummary -notmatch "runs.jsonl") {
    throw "Packaged benchmark replay summary did not include metrics artifact"
}

# Persist trace health so package smoke runs leave a reviewable monitoring artifact.
$TraceHealthReport = Join-Path $SmokeRoot "trace-health.json"
$TraceHealthSummary = Join-Path $SmokeRoot "trace-health.md"
$TraceHealthConsole = & $ExePath trace-health --trace-root $SmokeTraceRoot --output $TraceHealthReport --markdown-output $TraceHealthSummary --fail-on-attention
$TraceHealthConsole | Write-Host
if (-not (Test-Path $TraceHealthReport)) {
    throw "Packaged trace-health did not write $TraceHealthReport"
}
if (-not (Test-Path $TraceHealthSummary)) {
    throw "Packaged trace-health did not write $TraceHealthSummary"
}
$TraceHealth = Get-Content $TraceHealthReport -Raw | ConvertFrom-Json
if ($TraceHealth.schema_version -ne "trace_health_v1") {
    throw "Packaged trace-health report had schema $($TraceHealth.schema_version)"
}
if ($TraceHealth.trace_count -lt 3) {
    throw "Packaged trace-health report did not include smoke traces from $SmokeTraceRoot"
}
if ($TraceHealth.artifact_trace_count -lt 1) {
    throw "Packaged trace-health report did not include artifact traces"
}
if ($TraceHealth.health_status -ne "ok") {
    throw "Packaged trace-health reported $($TraceHealth.health_status)"
}
$TraceHealthConsoleText = $TraceHealthConsole -join "`n"
if ($TraceHealthConsoleText -notmatch "artifact_traces:") {
    throw "Packaged trace-health console output did not include artifact traces"
}
if ($TraceHealthConsoleText -notmatch "latest_traces:") {
    throw "Packaged trace-health console output did not include latest traces"
}
if ($TraceHealthConsoleText -notmatch "benchmark-replay") {
    throw "Packaged trace-health console output did not include benchmark replay"
}
if ($TraceHealthConsoleText -notmatch "benchmark-report.json") {
    throw "Packaged trace-health console output did not include benchmark report path"
}
if ($TraceHealthConsoleText -notmatch 'trace_health status=ok; artifacts=1') {
    throw "Packaged trace-health console output did not include benchmark trace-health summary"
}
$BenchmarkArtifactTrace = $TraceHealth.artifact_traces |
    Where-Object { $_.kind -eq "benchmark" } |
    Select-Object -First 1
if (-not $BenchmarkArtifactTrace) {
    throw "Packaged trace-health report did not include benchmark artifact trace metadata"
}
if ($BenchmarkArtifactTrace.trace_health_summary.health_status -ne "ok") {
    throw "Packaged trace-health report did not include benchmark trace-health status"
}
if ($BenchmarkArtifactTrace.trace_health_summary.artifact_trace_count -lt 1) {
    throw "Packaged trace-health report did not include benchmark trace-health artifact count"
}
$BenchmarkLatestTrace = $TraceHealth.latest |
    Where-Object { $_.kind -eq "benchmark" } |
    Select-Object -First 1
if (-not $BenchmarkLatestTrace) {
    throw "Packaged trace-health report did not include benchmark latest trace metadata"
}
if ($BenchmarkLatestTrace.report_path -notmatch "benchmark-report.json") {
    throw "Packaged trace-health report latest trace did not include benchmark report path"
}
$TraceHealthMarkdown = Get-Content $TraceHealthSummary -Raw
if ($TraceHealthMarkdown -notmatch "trace_health_v1") {
    throw "Packaged trace-health summary did not include schema version"
}
if ($TraceHealthMarkdown -notmatch "Artifact Traces") {
    throw "Packaged trace-health summary did not include artifact trace section"
}
if ($TraceHealthMarkdown -notmatch "Latest Traces") {
    throw "Packaged trace-health summary did not include latest trace links"
}
if ($TraceHealthMarkdown -notmatch "benchmark-replay") {
    throw "Packaged trace-health summary did not include benchmark replay"
}
if ($TraceHealthMarkdown -notmatch "artifacts") {
    throw "Packaged trace-health summary did not include benchmark artifacts"
}
if ($TraceHealthMarkdown -notmatch "runs.jsonl") {
    throw "Packaged trace-health summary did not include benchmark metrics artifact"
}
if ($TraceHealthMarkdown -notmatch 'trace_health `status=ok; artifacts=1`') {
    throw "Packaged trace-health summary did not include benchmark trace-health summary"
}

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

Write-Host "Packaged help, dry-run report, routine listing, trace replay, benchmark replay, trace health report, and app checks passed"
