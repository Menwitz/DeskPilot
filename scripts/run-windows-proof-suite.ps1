param(
    [string]$TraceRoot = "traces/windows-proof-suite",
    [double]$CountdownSeconds = 5,
    [int]$RandomSeed = 20260515,
    [double]$MovementSmoothness = 0.85,
    [string]$DeskPilotCommand = "",
    [switch]$UseUv,
    [switch]$ExternalVideo
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

if ($env:OS -ne "Windows_NT") {
    throw "Windows proof collection must run on an owned, unlocked Windows desktop or VM."
}

function Resolve-DeskPilotCommand {
    if ($UseUv) {
        return @("uv", "run", "desktop-agent")
    }
    if ($DeskPilotCommand) {
        return @($DeskPilotCommand)
    }

    # Prefer packaged executables when the script is run from an installer bundle.
    foreach ($Candidate in @("bin/deskpilot.exe", "dist/deskpilot.exe")) {
        if (Test-Path $Candidate) {
            return @((Resolve-Path $Candidate).Path)
        }
    }

    return @("desktop-agent")
}

function Invoke-DeskPilot {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $CommandPrefix = Resolve-DeskPilotCommand
    $Executable = $CommandPrefix[0]
    $PrefixArgs = @()
    if ($CommandPrefix.Count -gt 1) {
        $PrefixArgs = $CommandPrefix[1..($CommandPrefix.Count - 1)]
    }

    $DisplayCommand = @($Executable) + $PrefixArgs + $Arguments
    Write-Host ("> " + ($DisplayCommand -join " "))
    & $Executable @PrefixArgs @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "DeskPilot command failed with exit code ${LASTEXITCODE}: $($Arguments -join ' ')"
    }
}

$VideoPolicy = "full"
if ($ExternalVideo) {
    $VideoPolicy = "disabled"
}

New-Item -ItemType Directory -Force -Path $TraceRoot | Out-Null

Invoke-DeskPilot -Arguments @(
    "proof",
    "preflight",
    "--trace-root",
    $TraceRoot,
    "--video-policy",
    $VideoPolicy,
    "--write-report"
)

foreach ($ProofName in @("browser-fixture", "native-fixture", "mixed-fixture", "recovery-fixture")) {
    $ProofArgs = @(
        "proof",
        $ProofName,
        "--trace-root",
        $TraceRoot,
        "--countdown-seconds",
        [string]$CountdownSeconds,
        "--random-seed",
        [string]$RandomSeed,
        "--movement-smoothness",
        [string]$MovementSmoothness,
        "--video-policy",
        $VideoPolicy
    )
    if (-not $ExternalVideo) {
        $ProofArgs += "--record-video"
    }
    Invoke-DeskPilot -Arguments $ProofArgs
}

$ValidationArgs = @(
    "proof",
    "validate-suite",
    $TraceRoot,
    "--require-preflight",
    "--write-report",
    "--write-status-json",
    "--write-runbook",
    "--write-archive",
    "--write-review-template"
)
if ($ExternalVideo) {
    $ValidationArgs += "--allow-missing-video"
}
Invoke-DeskPilot -Arguments $ValidationArgs

$ReviewPath = Join-Path $TraceRoot "proof-suite-review.md"
$ReviewStatusPath = Join-Path $TraceRoot "proof-suite-review-status.json"
$AllowMissingVideo = ""
if ($ExternalVideo) {
    $AllowMissingVideo = " --allow-missing-video"
}
$CommandPrefixText = (Resolve-DeskPilotCommand -join " ")

Write-Host ""
Write-Host "Proof collection complete. Review the video, trace artifacts, and $ReviewPath."
Write-Host "After human review is complete, run:"
Write-Host "$CommandPrefixText proof validate-review $ReviewPath --write-status-json"
Write-Host "$CommandPrefixText proof promote-suite $TraceRoot$AllowMissingVideo --write-report --write-status-json --write-runbook --write-archive"
Write-Host "$CommandPrefixText proof verify-promotion $(Join-Path $TraceRoot 'proof-suite-promotion.json')"
Write-Host "$CommandPrefixText proof verify-archive $(Join-Path $TraceRoot 'proof-suite-artifacts.zip')"
Write-Host "Final review status path: $ReviewStatusPath"
