from pathlib import Path

from desktop_agent.config import YamlConfigLoader


def test_packaging_files_exist() -> None:
    assert Path("packaging/desktop_agent_entry.py").exists()
    assert Path("packaging/deskpilot.spec").exists()
    assert Path("packaging/default-config.yaml").exists()
    assert Path("scripts/build-windows-exe.ps1").exists()
    assert Path("scripts/verify-windows-package.ps1").exists()


def test_default_packaging_config_loads() -> None:
    config = YamlConfigLoader().load(Path("packaging/default-config.yaml"))

    assert config.trace_root == Path("traces")
    assert config.emergency_stop_hotkey == "ctrl+alt+esc"


def test_pyinstaller_spec_bundles_examples_and_docs() -> None:
    spec = Path("packaging/deskpilot.spec").read_text(encoding="utf-8")

    assert "examples" in spec
    assert "docs" in spec
    assert "default-config.yaml" in spec
