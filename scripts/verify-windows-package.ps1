param(
    [string]$ExePath = "dist/deskpilot.exe"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ExePath)) {
    throw "Packaged executable not found: $ExePath"
}

& $ExePath --help
& $ExePath dry-run examples/browser-task.yaml --config packaging/default-config.yaml

Write-Host "Packaged executable help and dry-run checks passed"
