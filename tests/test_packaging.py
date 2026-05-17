import tomllib
from pathlib import Path

from desktop_agent.config import YamlConfigLoader


def test_packaging_files_exist() -> None:
    assert Path("packaging/desktop_agent_entry.py").exists()
    assert Path("packaging/deskpilot_app_entry.py").exists()
    assert Path("packaging/deskpilot.spec").exists()
    assert Path("packaging/deskpilot-app.spec").exists()
    assert Path("packaging/default-config.yaml").exists()
    assert Path("scripts/build-windows-exe.ps1").exists()
    assert Path("scripts/build-windows-installer.ps1").exists()
    assert Path("scripts/verify-windows-package.ps1").exists()
    assert Path("scripts/run-windows-proof-suite.ps1").exists()


def test_pyproject_exposes_optional_app_dependency_group() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    app_deps = pyproject["project"]["optional-dependencies"]["app"]

    assert any(dependency.startswith("PySide6>=") for dependency in app_deps)


def test_default_packaging_config_loads() -> None:
    config = YamlConfigLoader().load(Path("packaging/default-config.yaml"))

    assert config.trace_root == Path("traces")
    assert config.emergency_stop_hotkey == "ctrl+alt+esc"


def test_pyinstaller_spec_bundles_examples_and_docs() -> None:
    spec = Path("packaging/deskpilot.spec").read_text(encoding="utf-8")

    assert "examples" in spec
    assert "docs" in spec
    assert "default-config.yaml" in spec


def test_app_pyinstaller_spec_targets_pyside_entry_point() -> None:
    spec = Path("packaging/deskpilot-app.spec").read_text(encoding="utf-8")

    assert "deskpilot_app_entry.py" in spec
    assert "deskpilot-app" in spec
    assert "PySide6.QtWidgets" in spec


def test_windows_installer_script_packages_cli_app_and_local_assets() -> None:
    script = Path("scripts/build-windows-installer.ps1").read_text(
        encoding="utf-8",
    )

    assert "packaging/deskpilot.spec" in script
    assert "packaging/deskpilot-app.spec" in script
    assert "dist/deskpilot-windows-installer" in script
    assert "DeskPilot-Windows.zip" in script
    assert "deskpilot.exe" in script
    assert "deskpilot-app.exe" in script
    assert "default-config.yaml" in script
    assert "scripts/run-windows-proof-suite.ps1" in script
    assert "Copy-Item \"docs\"" in script
    assert "Copy-Item \"examples\"" in script
    assert "Copy-Item \"routine_packs\"" in script
    assert "Copy-Item \"playbooks\"" in script
    assert "install.ps1" in script
    assert "uninstall.ps1" in script
    assert "Compress-Archive" in script


def test_windows_package_verify_script_runs_packaged_smoke_matrix() -> None:
    script = Path("scripts/verify-windows-package.ps1").read_text(encoding="utf-8")

    assert "dist/deskpilot.exe" in script
    assert "dist/deskpilot-app.exe" in script
    assert "& $ExePath --help" in script
    assert "$SmokeTraceRoot = Join-Path $SmokeRoot \"dry-run-traces\"" in script
    assert "$TraceDir = Join-Path $SmokeTraceRoot \"trace-replay\"" in script
    assert (
        "$BenchmarkTraceDir = Join-Path $SmokeTraceRoot \"benchmark-replay\""
        in script
    )
    assert (
        "& $ExePath dry-run examples/browser-task.yaml --config $SmokeConfigPath"
        in script
    )
    assert "Packaged dry-run did not write final-report.json" in script
    assert "& $ExePath list-routines --routine-pack-root $RoutinePackRoot" in script
    assert "& $ExePath replay $TraceDir" in script
    assert "& $ExePath replay $BenchmarkTraceDir --write-summary" in script
    assert "Packaged benchmark replay did not write replay-summary.md" in script
    assert "$TraceHealthReport = Join-Path $SmokeRoot \"trace-health.json\"" in script
    assert "$TraceHealthSummary = Join-Path $SmokeRoot \"trace-health.md\"" in script
    assert (
        "& $ExePath trace-health --trace-root $SmokeTraceRoot "
        "--output $TraceHealthReport --markdown-output $TraceHealthSummary "
        "--fail-on-attention"
        in script
    )
    assert "Packaged trace-health did not write" in script
    assert "$TraceHealth.schema_version -ne \"trace_health_v1\"" in script
    assert "$TraceHealth.trace_count -lt 3" in script
    assert "$TraceHealth.health_status -ne \"ok\"" in script
    assert "Packaged trace-health summary did not include schema version" in script
    assert "Packaged trace-health summary did not include latest trace links" in script
    assert "Packaged trace-health summary did not include benchmark replay" in script
    assert "& $AppExePath --check" in script
    assert "PySide6: available" in script
    assert "& $AppExePath --describe-shell" in script
    assert "final-report.json" in script
    assert "benchmark-report.json" in script
    assert "trace health report" in script


def test_windows_proof_suite_runner_collects_reviewable_evidence() -> None:
    script = Path("scripts/run-windows-proof-suite.ps1").read_text(encoding="utf-8")

    assert '"proof",' in script
    assert '"preflight"' in script
    assert "browser-fixture" in script
    assert "native-fixture" in script
    assert "mixed-fixture" in script
    assert "recovery-fixture" in script
    assert "--record-video" in script
    assert "ExternalVideo" in script
    assert "--require-preflight" in script
    assert "--write-review-template" in script
    assert "proof validate-review" in script
    assert "proof finalize-suite" in script
    assert "proof-suite-review-status.json" in script
