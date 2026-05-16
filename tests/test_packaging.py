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
    assert "& $ExePath dry-run examples/browser-task.yaml" in script
    assert "& $ExePath list-routines --routine-pack-root $RoutinePackRoot" in script
    assert "& $ExePath replay $TraceDir" in script
    assert "& $AppExePath --check" in script
    assert "final-report.json" in script
