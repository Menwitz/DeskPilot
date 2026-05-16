from pathlib import Path
from zipfile import ZipFile

import pytest
from pytest import CaptureFixture

from desktop_agent.cli import main
from desktop_agent.routine_pack_ops import (
    RoutinePackOperationError,
    export_routine_pack,
    import_routine_pack,
)


def test_routine_pack_import_export_directory_and_zip(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source-pack", pack_id="sample-pack")
    install_root = tmp_path / "installed"
    archive_path = tmp_path / "sample-pack.zip"
    second_root = tmp_path / "second-root"

    import_result = import_routine_pack(source, install_root)
    export_result = export_routine_pack(install_root, "sample-pack", archive_path)
    zip_import_result = import_routine_pack(archive_path, second_root)

    assert import_result.installed_path == install_root / "sample-pack"
    assert export_result.archive is True
    assert archive_path.exists()
    assert zip_import_result.installed_path == second_root / "sample-pack"
    assert (second_root / "sample-pack" / "README.md").exists()
    with ZipFile(archive_path) as archive:
        assert "sample-pack/routine-pack.yaml" in archive.namelist()


def test_routine_pack_import_rejects_existing_without_replace(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source-pack", pack_id="sample-pack")
    install_root = tmp_path / "installed"

    import_routine_pack(source, install_root)

    with pytest.raises(RoutinePackOperationError, match="already installed"):
        import_routine_pack(source, install_root)


def test_routine_pack_import_surfaces_unverified_trust_warning(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    source = _write_pack(
        tmp_path / "source-pack",
        pack_id="sample-pack",
        trust_level="unverified_local",
    )
    install_root = tmp_path / "installed"

    result = import_routine_pack(source, install_root)
    assert len(result.trust_warnings) == 1

    assert (
        main(
            [
                "import-routine-pack",
                str(source),
                "--routine-pack-root",
                str(install_root),
                "--replace",
            ],
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "trust_warnings:" in output
    assert "pack is unverified" in output


def test_routine_pack_cli_lists_shows_imports_and_exports(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    source = _write_pack(tmp_path / "source-pack", pack_id="sample-pack")
    install_root = tmp_path / "installed"
    export_path = tmp_path / "exported-pack"

    assert (
        main(
            [
                "import-routine-pack",
                str(source),
                "--routine-pack-root",
                str(install_root),
            ],
        )
        == 0
    )
    assert "imported routine pack: sample-pack" in capsys.readouterr().out

    assert (
        main(["list-routine-packs", "--routine-pack-root", str(install_root)])
        == 0
    )
    assert (
        "sample-pack\t0.1.0\ttrusted_local\tSample Pack\twarnings=0"
        in capsys.readouterr().out
    )

    assert (
        main(
            [
                "show-routine-pack",
                "sample-pack",
                "--routine-pack-root",
                str(install_root),
            ],
        )
        == 0
    )
    show_output = capsys.readouterr().out
    assert "trust_level: trusted_local" in show_output
    assert "proof.expected_artifacts: final-report.json" in show_output

    assert (
        main(
            [
                "export-routine-pack",
                "sample-pack",
                "--routine-pack-root",
                str(install_root),
                "--output",
                str(export_path),
            ],
        )
        == 0
    )
    assert "exported routine pack: sample-pack" in capsys.readouterr().out
    assert (export_path / "routine-pack.yaml").exists()


def _write_pack(
    root: Path,
    *,
    pack_id: str,
    trust_level: str = "trusted_local",
) -> Path:
    root.mkdir(parents=True)
    (root / "README.md").write_text("# Sample Pack\n", encoding="utf-8")
    (root / "sample.routine.yaml").write_text(
        "# placeholder routine definition for pack copy tests\n",
        encoding="utf-8",
    )
    (root / "routine-pack.yaml").write_text(
        "\n".join(
            [
                'pack_schema_version: "1"',
                f"id: {pack_id}",
                "name: Sample Pack",
                "description: Sample local routine pack.",
                'version: "0.1.0"',
                "publisher: Local Operator",
                f"trust_level: {trust_level}",
                "routine_globs:",
                '  - "*.routine.yaml"',
                "docs:",
                "  - README.md",
                "fixtures: []",
                "tests: []",
                "safety:",
                "  max_safety_class: low",
                "  requires_review: true",
                "  external_mutation_allowed: false",
                "  approval_required: false",
                "proof:",
                "  windows_proof_required: false",
                "  expected_artifacts:",
                "    - final-report.json",
                "",
            ],
        ),
        encoding="utf-8",
    )
    return root
