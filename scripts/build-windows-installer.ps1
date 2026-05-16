param(
    [string]$CliSpecPath = "packaging/deskpilot.spec",
    [string]$AppSpecPath = "packaging/deskpilot-app.spec",
    [string]$InstallerRoot = "dist/deskpilot-windows-installer",
    [string]$ArchivePath = "dist/DeskPilot-Windows.zip",
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

if (-not $SkipDependencyInstall) {
    python -m pip install --upgrade pyinstaller
    python -m pip install ".[app]"
}

python -m PyInstaller $CliSpecPath --noconfirm --clean
python -m PyInstaller $AppSpecPath --noconfirm --clean

$CliExe = Join-Path $RepoRoot "dist/deskpilot.exe"
$AppExe = Join-Path $RepoRoot "dist/deskpilot-app.exe"
foreach ($Executable in @($CliExe, $AppExe)) {
    if (-not (Test-Path $Executable)) {
        throw "Expected packaged executable not found: $Executable"
    }
}

if (Test-Path $InstallerRoot) {
    Remove-Item $InstallerRoot -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $InstallerRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallerRoot "bin") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallerRoot "config") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallerRoot "scripts") | Out-Null

Copy-Item $CliExe (Join-Path $InstallerRoot "bin/deskpilot.exe")
Copy-Item $AppExe (Join-Path $InstallerRoot "bin/deskpilot-app.exe")
Copy-Item "packaging/default-config.yaml" (Join-Path $InstallerRoot "config/default-config.yaml")
Copy-Item "scripts/run-windows-proof-suite.ps1" (Join-Path $InstallerRoot "scripts/run-windows-proof-suite.ps1")
Copy-Item "docs" (Join-Path $InstallerRoot "docs") -Recurse
Copy-Item "examples" (Join-Path $InstallerRoot "examples") -Recurse
if (Test-Path "routine_packs") {
    Copy-Item "routine_packs" (Join-Path $InstallerRoot "routine_packs") -Recurse
}
if (Test-Path "playbooks") {
    Copy-Item "playbooks" (Join-Path $InstallerRoot "playbooks") -Recurse
}

# The bundled installer stays local and avoids machine-wide PATH edits by default.
@'
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\DeskPilot",
    [switch]$AddUserPath
)

$ErrorActionPreference = "Stop"

$SourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item (Join-Path $SourceRoot "*") $InstallDir -Recurse -Force

if ($AddUserPath) {
    $BinDir = Join-Path $InstallDir "bin"
    $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (($UserPath -split ";") -notcontains $BinDir) {
        [Environment]::SetEnvironmentVariable("Path", "$UserPath;$BinDir", "User")
    }
}

Write-Host "DeskPilot installed to $InstallDir"
Write-Host "CLI: $InstallDir\bin\deskpilot.exe"
Write-Host "Operator app: $InstallDir\bin\deskpilot-app.exe"
'@ | Set-Content -Encoding UTF8 (Join-Path $InstallerRoot "install.ps1")

@'
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\DeskPilot"
)

$ErrorActionPreference = "Stop"

if (Test-Path $InstallDir) {
    Remove-Item $InstallDir -Recurse -Force
}

Write-Host "DeskPilot removed from $InstallDir"
'@ | Set-Content -Encoding UTF8 (Join-Path $InstallerRoot "uninstall.ps1")

@'
DeskPilot Windows Installer Bundle

Run install.ps1 from PowerShell to copy the CLI, native operator app, default
config, examples, routine packs, playbooks, and documentation to a local
per-user install directory.

Commands after install:
- bin\deskpilot.exe --help
- bin\deskpilot.exe dry-run examples\browser-task.yaml --config config\default-config.yaml
- bin\deskpilot-app.exe --check
- scripts\run-windows-proof-suite.ps1 -DeskPilotCommand bin\deskpilot.exe
'@ | Set-Content -Encoding UTF8 (Join-Path $InstallerRoot "README.txt")

$Manifest = [ordered]@{
    name = "DeskPilot"
    package_kind = "local_windows_installer_bundle"
    cli_executable = "bin\deskpilot.exe"
    operator_app_executable = "bin\deskpilot-app.exe"
    default_config = "config\default-config.yaml"
    docs = "docs"
    examples = "examples"
    routine_packs = "routine_packs"
    playbooks = "playbooks"
    proof_suite_runner = "scripts\run-windows-proof-suite.ps1"
    created_at = (Get-Date).ToUniversalTime().ToString("o")
}
$Manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $InstallerRoot "manifest.json")

if (Test-Path $ArchivePath) {
    Remove-Item $ArchivePath -Force
}
Compress-Archive -Path (Join-Path $InstallerRoot "*") -DestinationPath $ArchivePath -Force

Write-Host "Built Windows installer bundle at $InstallerRoot"
Write-Host "Built archive at $ArchivePath"
