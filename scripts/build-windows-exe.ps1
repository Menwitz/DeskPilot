param(
    [string]$SpecPath = "packaging/deskpilot.spec"
)

$ErrorActionPreference = "Stop"

python -m pip install --upgrade pyinstaller
python -m PyInstaller $SpecPath --noconfirm --clean

Write-Host "Built dist/deskpilot.exe"
