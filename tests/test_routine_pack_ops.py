import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from pytest import CaptureFixture

from desktop_agent.cli import main
from desktop_agent.routine_pack_ops import (
    RoutinePackOperationError,
    detect_routine_pack_conflicts,
    export_routine_pack,
    import_routine_pack,
)
from desktop_agent.routines import (
    load_routine_catalog,
    routine_execution_gate,
    routine_quarantine_status,
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


def test_routine_pack_import_rejects_unsafe_archive_member(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe-pack.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("../routine-pack.yaml", "pack_schema_version: '1'\n")

    with pytest.raises(RoutinePackOperationError, match="unsafe routine pack archive"):
        import_routine_pack(archive_path, tmp_path / "installed")


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


def test_routine_pack_conflicts_detect_ids_inputs_selectors_and_versions(
    tmp_path: Path,
) -> None:
    installed_root = tmp_path / "installed"
    existing = _write_pack(
        tmp_path / "existing-pack",
        pack_id="existing-pack",
        routine_id="shared.routine",
        input_name="query",
        target="Search",
    )
    incoming_duplicate_id = _write_pack(
        tmp_path / "incoming-duplicate-id",
        pack_id="incoming-pack",
        routine_id="shared.routine",
        input_name="query",
        target="Search",
    )
    incoming_overlap = _write_pack(
        tmp_path / "incoming-overlap",
        pack_id="incoming-overlap",
        routine_id="incoming.routine",
        input_name="query",
        target="Search",
    )
    import_routine_pack(existing, installed_root)

    duplicate_id_conflicts = detect_routine_pack_conflicts(
        incoming_duplicate_id,
        installed_root,
    )
    overlap_conflicts = detect_routine_pack_conflicts(incoming_overlap, installed_root)
    duplicate_kinds = {conflict.kind for conflict in duplicate_id_conflicts}
    overlap_kinds = {conflict.kind for conflict in overlap_conflicts}

    assert "routine_id" in duplicate_kinds
    assert overlap_kinds >= {"input_signature", "selector_signature"}
    with pytest.raises(RoutinePackOperationError, match="duplicate routine id"):
        import_routine_pack(incoming_duplicate_id, installed_root)


def test_routine_pack_conflicts_detect_installed_pack_version(
    tmp_path: Path,
) -> None:
    installed_root = tmp_path / "installed"
    first = _write_pack(tmp_path / "first-pack", pack_id="sample-pack")
    second = _write_pack(tmp_path / "second-pack", pack_id="sample-pack")
    import_routine_pack(first, installed_root)

    conflicts = detect_routine_pack_conflicts(second, installed_root)

    assert conflicts[0].kind == "pack_version"
    assert conflicts[0].severity == "error"


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


def test_trusted_routine_pack_cli_imports_and_validates_installed_pack(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    source = _write_pack(
        tmp_path / "trusted-pack",
        pack_id="trusted-pack",
        trust_level="trusted_local",
    )
    install_root = tmp_path / "installed"
    report_path = tmp_path / "trusted-pack-validation.json"

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
    import_output = capsys.readouterr().out
    assert "imported routine pack: trusted-pack" in import_output
    assert "trust_warnings: none" in import_output

    assert (
        main(
            [
                "list-routine-packs",
                "--routine-pack-root",
                str(install_root),
            ],
        )
        == 0
    )
    assert "trusted-pack\t0.1.0\ttrusted_local" in capsys.readouterr().out

    assert (
        main(
            [
                "test-routine-pack",
                "trusted-pack",
                "--routine-pack-root",
                str(install_root),
                "--output",
                str(report_path),
            ],
        )
        == 0
    )
    validation_output = capsys.readouterr().out
    validation_report = json.loads(report_path.read_text(encoding="utf-8"))

    assert "status: passed" in validation_output
    assert validation_report == {
        "errors": [],
        "pack_id": "trusted-pack",
        "routine_count": 1,
        "status": "passed",
        "validated_routine_count": 1,
    }


def test_installed_pack_routine_can_remain_quarantined_by_execution_gate(
    tmp_path: Path,
) -> None:
    source = _write_pack(
        tmp_path / "unsafe-pack",
        pack_id="unsafe-pack",
        routine_id="unsafe-pack.routine",
        quarantine_status="quarantined",
        quarantine_reason="unsafe imported selector requires review",
    )
    install_root = tmp_path / "installed"

    import_routine_pack(source, install_root)
    catalog = load_routine_catalog(install_root)
    routine = catalog.by_id("unsafe-pack.routine")
    gate = routine_execution_gate(catalog, "unsafe-pack.routine")

    assert routine is not None
    assert routine_quarantine_status(routine) == "quarantined"
    assert gate.allowed is False
    assert gate.reason == "routine_quarantined"


def _write_pack(
    root: Path,
    *,
    pack_id: str,
    routine_id: str | None = None,
    input_name: str = "topic",
    target: str = "Target",
    trust_level: str = "trusted_local",
    quarantine_status: str = "active",
    quarantine_reason: str | None = None,
) -> Path:
    root.mkdir(parents=True)
    (root / "README.md").write_text("# Sample Pack\n", encoding="utf-8")
    task_path = root / "tasks" / "sample.yaml"
    task_path.parent.mkdir()
    task_path.write_text(
        "\n".join(
            [
                "name: Sample task",
                "allowed_windows:",
                "  - Sample Window",
                "timeout_seconds: 30",
                "steps:",
                "  - id: click-target",
                "    action: click_text",
                f"    target: {target}",
                "",
            ],
        ),
        encoding="utf-8",
    )
    (root / "sample.routine.yaml").write_text(
        "\n".join(
            [
                f"id: {routine_id or f'{pack_id}.routine'}",
                "name: Sample routine",
                "description: Sample routine definition for pack copy tests.",
                "goal: Exercise routine pack import and export.",
                "required_app: Sample Window",
                "tags:",
                "  - sample",
                "inputs:",
                f"  - {input_name}",
                "outputs:",
                "  - result",
                "safety_class: low",
                "schedule_policy: manual",
                "approval_policy: none",
                "expected_duration_seconds: 30",
                f"quarantine_status: {quarantine_status}",
                *(
                    [f"quarantine_reason: {quarantine_reason}"]
                    if quarantine_reason
                    else []
                ),
                "reference:",
                "  type: task",
                "  path: tasks/sample.yaml",
                "",
            ],
        ),
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
