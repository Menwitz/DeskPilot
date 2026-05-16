# Packaging

DeskPilot packages the Windows executable with PyInstaller.

## Files

- `packaging/desktop_agent_entry.py` is the executable entry point.
- `packaging/deskpilot.spec` is the PyInstaller build config.
- `packaging/deskpilot_app_entry.py` is the optional native app entry point.
- `packaging/deskpilot-app.spec` is the optional PySide6 app build config.
- `packaging/default-config.yaml` is bundled with the executable.
- `scripts/build-windows-exe.ps1` builds `dist/deskpilot.exe` on Windows.
- `scripts/verify-windows-package.ps1` runs packaged `--help` and `dry-run`
  checks.

Install the native operator app dependencies with:

```bash
pip install ".[app]"
```

## Windows Build

Run from the repository root in PowerShell:

```powershell
scripts/build-windows-exe.ps1
scripts/verify-windows-package.ps1
```

Real `run` verification still requires an unlocked Windows desktop with the
browser or native fixture visible.
