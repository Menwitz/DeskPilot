# Packaging

DeskPilot packages the Windows executable with PyInstaller.

## Files

- `packaging/desktop_agent_entry.py` is the executable entry point.
- `packaging/deskpilot.spec` is the PyInstaller build config.
- `packaging/deskpilot_app_entry.py` is the optional native app entry point.
- `packaging/deskpilot-app.spec` is the optional PySide6 app build config.
- `packaging/default-config.yaml` is bundled with the executable.
- `scripts/build-windows-exe.ps1` builds `dist/deskpilot.exe` on Windows.
- `scripts/build-windows-installer.ps1` builds both executables and writes a
  local installer bundle plus `dist/DeskPilot-Windows.zip`.
- `scripts/verify-windows-package.ps1` runs packaged `--help`, dry-run,
  routine listing, trace replay, and native app smoke checks.

Install the native operator app dependencies with:

```bash
pip install ".[app]"
```

The optional app entry point is `deskpilot-app`. Use `deskpilot-app --check` to
verify that the script is installed and to see whether PySide6 is available in
the current environment.
The shell contract is documented in `docs/operator-app.md`.

## Windows Build

Run from the repository root in PowerShell:

```powershell
scripts/build-windows-exe.ps1
scripts/build-windows-installer.ps1
scripts/verify-windows-package.ps1
```

The installer bundle contains:

- `bin/deskpilot.exe`
- `bin/deskpilot-app.exe`
- `config/default-config.yaml`
- `docs/`
- `examples/`
- `routine_packs/`, when present
- `playbooks/`, when present
- `install.ps1`, `uninstall.ps1`, `README.txt`, and `manifest.json`

Run `dist\deskpilot-windows-installer\install.ps1` to copy the bundle to the
current user's local app-data directory. Pass `-AddUserPath` only when the user
wants `bin\` added to their user PATH.

`scripts\verify-windows-package.ps1` creates a local smoke trace under
`dist\package-smoke`, runs `deskpilot.exe replay` against it, lists routines
from `routine_packs\`, and runs `deskpilot-app.exe --check` when the app
executable exists.

Real `run` verification still requires an unlocked Windows desktop with the
browser or native fixture visible.
