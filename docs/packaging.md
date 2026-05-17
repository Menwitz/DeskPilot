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
  routine listing, trace replay, benchmark replay, trace-health report, and
  native app smoke checks.
- `scripts/run-windows-proof-suite.ps1` runs the browser, native, mixed, and
  recovery proof pack on an owned unlocked Windows desktop, then writes suite
  reports, status JSON, archive, and review template artifacts.

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
scripts/run-windows-proof-suite.ps1 -UseUv -TraceRoot traces/windows-proof-suite
```

The installer bundle contains:

- `bin/deskpilot.exe`
- `bin/deskpilot-app.exe`
- `config/default-config.yaml`
- `docs/`
- `examples/`
- `scripts/run-windows-proof-suite.ps1`
- `routine_packs/`, when present
- `playbooks/`, when present
- `install.ps1`, `uninstall.ps1`, `README.txt`, and `manifest.json`

Run `dist\deskpilot-windows-installer\install.ps1` to copy the bundle to the
current user's local app-data directory. Pass `-AddUserPath` only when the user
wants `bin\` added to their user PATH.

`scripts\verify-windows-package.ps1` creates local smoke traces under
`dist\package-smoke\dry-run-traces`, runs `deskpilot.exe dry-run` with that
package-smoke trace root and verifies that `final-report.json` was written,
runs `deskpilot.exe replay` against run and benchmark replay fixtures in the
same trace root, writes a benchmark `replay-summary.md`, runs `deskpilot.exe
trace-health --output --markdown-output --fail-on-attention` against the smoke
trace root, verifies the persisted `trace-health.json` and `trace-health.md`
reports are healthy, schema-versioned, and include the benchmark replay in
latest-trace links, lists routines from `routine_packs\`, and runs
`deskpilot-app.exe --check` plus `deskpilot-app.exe --describe-shell` when the
app executable exists. The app check must report bundled PySide6 availability
for packaged Windows builds.

`scripts\run-windows-proof-suite.ps1` is the real desktop evidence collector.
Run it only from an owned, unlocked Windows desktop or VM. From source, pass
`-UseUv`; from the installer bundle, pass
`-DeskPilotCommand bin\deskpilot.exe`. Use `-ExternalVideo` when recording with
an external screen recorder instead of built-in `ffmpeg` capture. The script
writes `proof-preflight.json`, runs all four proof commands, validates the
suite, writes review artifacts, and prints the final `proof promote-suite`
command that emits `proof-suite-promotion.json` after human review passes.
That promotion JSON includes SHA-256 digests and byte sizes for the promoted
evidence artifacts so a copied archive can be checked later.
Run `proof verify-promotion <trace-root>\proof-suite-promotion.json` before
trusting copied proof evidence.
Run `proof verify-archive <trace-root>\proof-suite-artifacts.zip` to check the
self-contained archive members against the promotion digest record.
Both verifier commands support `--write-status-json` for monitoring artifacts.
For the normal post-review path, run `proof finalize-suite <trace-root>` after
`proof validate-review`; it writes the report, status JSON, runbook, promotion,
archive, both verifier status JSON files, and the monitoring rollup
`proof-finalization-status.json` in the correct order.

Real `run` verification still requires an unlocked Windows desktop with the
browser or native fixture visible.
