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
